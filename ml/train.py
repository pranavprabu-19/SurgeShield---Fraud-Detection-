"""Train the champion, the calibrated stacker, and the cost-based thresholds."""

from __future__ import annotations

import hashlib
import json
import time
from datetime import datetime, timezone

import joblib
import lightgbm as lgb
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from sklearn.ensemble import IsolationForest
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import average_precision_score, precision_recall_curve
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

from backend.app.policy import static_decision, surge_shield_decision
from ml.datasets import active_spec, artifact_path, data_paths, load_canonical
from ml.features import compute_features, fit_segments
from ml.metrics import binary_rates, ranking_metrics, stream_cost
from ml.schema import (
    ARTIFACT_DIR,
    ARTIFACT_PATH,
    DATA_DIR,
    FEATURE_NAMES,
    SEED,
    V_COLS,
)


def _file_hash(path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _split_masks(times: np.ndarray):
    t1, t2 = np.quantile(times, [0.80, 0.90])
    train = times <= t1
    cal = (times > t1) & (times <= t2)
    hold = times > t2
    return train, cal, hold


def _anomaly_scores(model, frame: pd.DataFrame, lo: float, hi: float, columns) -> np.ndarray:
    raw = -model.decision_function(frame[list(columns)].to_numpy())
    span = max(hi - lo, 1e-6)
    return np.clip((raw - lo) / span, 0.0, 1.0)


def _search_thresholds(y, amount, scores) -> dict:
    """Block the confident fraud. Step-up is a real band below that, not a sliver."""
    y = np.asarray(y).astype(int)
    scores = np.asarray(scores)
    legit = scores[y == 0]
    best = None
    for t_block in np.quantile(scores, np.linspace(0.90, 0.999, 20)):
        for gap in (0.04, 0.08, 0.12, 0.2):
            t_step = max(0.01, float(t_block) - gap)
            if legit.size and (legit >= t_block).mean() > 0.002:
                continue
            decisions = np.where(scores >= t_block, "BLOCK", np.where(scores >= t_step, "STEP_UP", "APPROVE"))
            cost = stream_cost(y, amount, decisions)
            if best is None or cost["total_cost"] < best["total_cost"]:
                best = {"t_step": float(t_step), "t_block": float(t_block), **cost}
    if best is None:
        best = {"t_step": 0.2, "t_block": 0.5, "total_cost": 0}
    return best


def _search_static(y, amount, scores) -> dict:
    best = None
    for threshold in np.linspace(0.05, 0.99, 30):
        decisions = np.where(scores >= threshold, "BLOCK", "APPROVE")
        cost = stream_cost(y, amount, decisions)
        if best is None or cost["total_cost"] < best["total_cost"]:
            best = {"t_static": float(threshold), **cost}
    return best


def train() -> dict:
    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    spec = active_spec()
    train_path, test_path = data_paths()
    train_df = load_canonical(train_path, spec)
    test_df = load_canonical(test_path, spec)
    base_cols = list(train_df.attrs.get("base_cols") or V_COLS)
    names = list(FEATURE_NAMES)
    kmeans, seg_mean, seg_std = fit_segments(train_df, base_cols)
    train_frame = compute_features(train_df, kmeans, seg_mean, seg_std, base_cols)
    for extra in ("device_share", "merchant_familiarity", "user_amount_ratio", "accounts_per_device_300", "travel_kmh", "merchant_ticket_ratio"):
        if extra in train_frame.columns and extra not in names:
            names.append(extra)
    combined = pd.concat(
        [train_df.assign(_origin="train"), test_df.assign(_origin="test")],
        ignore_index=True,
    )
    combined_frame = compute_features(combined, kmeans, seg_mean, seg_std, base_cols)
    # compute_features sorts by time, so recover origin by merging on a row key.
    combined_sorted = combined.sort_values(["Time"], kind="mergesort").reset_index(drop=True)
    combined_frame["_origin"] = combined_sorted["_origin"].to_numpy()
    test_frame = combined_frame[combined_frame["_origin"] == "test"].reset_index(drop=True)

    train_mask, cal_mask, hold_mask = _split_masks(train_frame["Time"].to_numpy())
    x_train = train_frame.loc[train_mask, names]
    y_train = train_frame.loc[train_mask, "Class"].to_numpy()
    x_cal = train_frame.loc[cal_mask, names]
    y_cal = train_frame.loc[cal_mask, "Class"].to_numpy()
    x_hold = train_frame.loc[hold_mask, names]
    y_hold = train_frame.loc[hold_mask, "Class"].to_numpy()

    # On this PCA file the fraud is close to linearly separable. A huge
    # scale_pos_weight makes LightGBM worse, so the linear model is champion
    # when it wins the time-holdout, and LightGBM stays the shadow.
    champion = make_pipeline(
        StandardScaler(),
        LogisticRegression(class_weight="balanced", max_iter=500, solver="lbfgs", random_state=SEED),
    )
    champion.fit(x_train, y_train)
    shadow = lgb.LGBMClassifier(
        n_estimators=400,
        learning_rate=0.05,
        num_leaves=31,
        min_child_samples=40,
        subsample=0.9,
        colsample_bytree=0.8,
        scale_pos_weight=1,
        random_state=SEED,
        n_jobs=-1,
        verbose=-1,
    )
    shadow.fit(x_train, y_train)
    future = train_frame.loc[cal_mask | hold_mask, names]
    y_future = train_frame.loc[cal_mask | hold_mask, "Class"].to_numpy()
    linear_ap = average_precision_score(y_future, champion.predict_proba(future)[:, 1])
    tree_ap = average_precision_score(y_future, shadow.predict_proba(future)[:, 1])
    if tree_ap > linear_ap + 0.01:
        champion, shadow = shadow, champion
        champion_kind = "tree"
    else:
        champion_kind = "linear"

    legit_idx = np.flatnonzero(y_train == 0)
    rng = np.random.default_rng(SEED)
    take = rng.choice(legit_idx, size=min(60_000, len(legit_idx)), replace=False)
    iforest = IsolationForest(
        n_estimators=200,
        contamination=0.002,
        random_state=SEED,
        n_jobs=-1,
    )
    iforest_cols = V_COLS + ["log_amount"]
    iforest_fit = x_train.iloc[take][iforest_cols].to_numpy()
    iforest.fit(iforest_fit)
    legit_raw = -iforest.decision_function(iforest_fit)
    ano_lo, ano_hi = np.percentile(legit_raw, [5, 99.5])

    def calibrated_parts(frame: pd.DataFrame):
        raw = champion.predict_proba(frame[names])[:, 1]
        anomaly = _anomaly_scores(iforest, frame, ano_lo, ano_hi, iforest_cols)
        coord = frame["coord_proxy"].to_numpy()
        return raw, anomaly, coord

    raw_cal, ano_cal, coord_cal = calibrated_parts(train_frame.loc[cal_mask])
    platt = LogisticRegression(random_state=SEED)
    platt.fit(raw_cal.reshape(-1, 1), y_cal)
    p_cal = platt.predict_proba(raw_cal.reshape(-1, 1))[:, 1]
    stacker = LogisticRegression(random_state=SEED, max_iter=200)
    stack_x = np.column_stack([p_cal, ano_cal, coord_cal])
    if y_cal.sum() >= 5 and (y_cal == 0).sum() >= 5:
        stacker.fit(stack_x, y_cal)
        stacked = stacker.predict_proba(stack_x)[:, 1]
    else:
        stacker = None
        stacked = p_cal

    raw_hold, ano_hold, coord_hold = calibrated_parts(train_frame.loc[hold_mask])
    p_hold = platt.predict_proba(raw_hold.reshape(-1, 1))[:, 1]
    if stacker is not None:
        fused_hold = stacker.predict_proba(np.column_stack([p_hold, ano_hold, coord_hold]))[:, 1]
    else:
        fused_hold = p_hold
    use_stacker = average_precision_score(y_hold, fused_hold) >= average_precision_score(y_hold, p_hold) - 0.005
    chosen_hold = fused_hold if use_stacker else p_hold

    amount_hold = train_frame.loc[hold_mask, "Amount"].to_numpy()
    tuned = _search_thresholds(y_hold, amount_hold, chosen_hold)
    static = _search_static(y_hold, amount_hold, chosen_hold)
    cfg = {
        "t_step": tuned["t_step"],
        "t_block": tuned["t_block"],
        "t_static": static["t_static"],
        "surge_relief": 0.05,
        "attack_tighten": 0.15,
        "use_stacker": bool(use_stacker and stacker is not None),
    }

    def fuse(frame: pd.DataFrame) -> np.ndarray:
        raw, anomaly, coord = calibrated_parts(frame)
        p = platt.predict_proba(raw.reshape(-1, 1))[:, 1]
        if cfg["use_stacker"]:
            return stacker.predict_proba(np.column_stack([p, anomaly, coord]))[:, 1]
        # Coordination still matters: a tight burst lifts an already risky score.
        return np.clip(p + 0.12 * np.maximum(0.0, coord - 0.75), 0.0, 1.0)

    test_scores = fuse(test_frame)
    y_test = test_frame["Class"].to_numpy()
    test_rank = ranking_metrics(y_test, test_scores)
    test_rates = binary_rates(y_test, test_scores, cfg["t_block"])
    ss_dec = np.array([
        surge_shield_decision(float(s), "NORMAL", int(seg), None, cfg)
        for s, seg in zip(test_scores, test_frame["segment_id"])
    ])
    st_dec = np.array([static_decision(float(s), cfg["t_static"]) for s in test_scores])
    test_cost = stream_cost(y_test, test_frame["Amount"].to_numpy(), ss_dec)
    static_cost = stream_cost(y_test, test_frame["Amount"].to_numpy(), st_dec)
    hold_rank = ranking_metrics(y_hold, chosen_hold)
    shadow_scores = shadow.predict_proba(test_frame[names])[:, 1]
    shadow_rank = ranking_metrics(y_test, shadow_scores)
    champion_raw = ranking_metrics(y_test, champion.predict_proba(test_frame[names])[:, 1])

    legit_cnt = train_frame.loc[train_frame["Class"] == 0, "cnt_60"].to_numpy()
    edges = np.linspace(0, 1, 11)
    ref_scores = fuse(train_frame.loc[train_mask].sample(n=min(20_000, int(train_mask.sum())), random_state=SEED))
    ref_hist, _ = np.histogram(ref_scores, bins=edges)
    ref_hist = ref_hist.astype(float)
    ref_hist = ref_hist / max(ref_hist.sum(), 1)

    metrics = {
        "test": test_rank,
        "test_at_block_threshold": test_rates,
        "test_cost_surgeshield": test_cost,
        "test_cost_static": static_cost,
        "money_saved_vs_static": float(static_cost["total_cost"] - test_cost["total_cost"]),
        "holdout": hold_rank,
        "logreg_baseline_test": champion_raw if champion_kind == "linear" else shadow_rank,
        "lightgbm_raw_test": shadow_rank if champion_kind == "linear" else champion_raw,
        "champion_kind": champion_kind,
        "thresholds": cfg,
        "train_rows": int(train_mask.sum()),
        "cal_rows": int(cal_mask.sum()),
        "hold_rows": int(hold_mask.sum()),
        "test_rows": int(len(test_frame)),
        "train_fraud": int(y_train.sum()),
        "test_fraud": int(y_test.sum()),
        "duplicates_dropped_train": int(train_df.attrs.get("dropped_duplicates", 0)),
        "pr_curve": _curve_points(y_test, test_scores),
        "calibration": _calibration_bins(y_test, test_scores),
        "feature_importance": _importance(champion, names),
    }

    artifact = {
        "champion": champion,
        "shadow": shadow,
        "champion_kind": champion_kind,
        "platt": platt,
        "stacker": stacker if cfg["use_stacker"] else None,
        "iforest": iforest,
        "anomaly_lo": float(ano_lo),
        "anomaly_hi": float(ano_hi),
        "kmeans": kmeans,
        "seg_mean": seg_mean,
        "seg_std": seg_std,
        "feature_names": names,
        "base_cols": base_cols,
        "dataset": spec.name,
        "iforest_features": iforest_cols,
        "feature_mean": x_train.mean().to_numpy(),
        "feature_std": x_train.std().replace(0, 1).to_numpy(),
        "thresholds": cfg,
        "psi_edges": edges,
        "psi_expected": ref_hist,
        "cnt60_mean": float(legit_cnt.mean()),
        "cnt60_std": float(legit_cnt.std() or 1),
        "segment_spread": _segment_spread(kmeans, train_df, base_cols),
        "metrics": metrics,
        "lineage": {
            "seed": SEED,
            "trained_at": datetime.now(timezone.utc).isoformat(),
            "train_sha256": _file_hash(train_path),
            "test_sha256": _file_hash(test_path),
            "dataset": spec.name,
            "model": champion_kind + "-platt" + ("-stacker" if cfg["use_stacker"] else ""),
        },
    }
    target = artifact_path(spec.name)
    target.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(artifact, target)
    (target.parent / "metrics.json").write_text(json.dumps(metrics, indent=2))

    precision, recall, _ = precision_recall_curve(y_test, test_scores)
    fig, ax = plt.subplots(figsize=(6, 4))
    ax.plot(recall, precision, color="#0f766e", lw=2)
    ax.set_xlabel("Recall")
    ax.set_ylabel("Precision")
    ax.set_title(f"SurgeShield PR curve  AP={test_rank['pr_auc']:.3f}")
    fig.tight_layout()
    fig.savefig(target.parent / "pr_curve.png", dpi=140)
    plt.close(fig)
    print(json.dumps(metrics, indent=2))
    return metrics


def _segment_spread(kmeans, frame: pd.DataFrame, columns) -> list:
    columns = list(columns)
    labels = kmeans.predict(frame[columns].to_numpy())
    values = frame[columns[:8]].to_numpy()
    spreads = []
    for seg_id in range(8):
        part = values[labels == seg_id]
        spreads.append(float(np.mean(np.std(part, axis=0))) if len(part) > 5 else 1.0)
    return spreads


def _curve_points(y_true, scores, n: int = 80) -> list:
    """Evenly spaced cuts, so the dashboard slider can read precision and recall."""
    labels = np.asarray(y_true)
    values = np.asarray(scores)
    fraud = max(int((labels == 1).sum()), 1)
    points = []
    for threshold in np.linspace(0.02, 0.98, n):
        predicted = values >= threshold
        tp = int(((labels == 1) & predicted).sum())
        fp = int(((labels == 0) & predicted).sum())
        precision = tp / (tp + fp) if (tp + fp) else 1.0
        recall = tp / fraud
        points.append(
            {
                "precision": round(precision, 4),
                "recall": round(recall, 4),
                "threshold": round(float(threshold), 4),
            }
        )
    return points


def _calibration_bins(y_true, scores, bins: int = 10) -> list:
    edges = np.linspace(0, 1, bins + 1)
    rows = []
    for i in range(bins):
        if i == bins - 1:
            mask = (scores >= edges[i]) & (scores <= edges[i + 1])
        else:
            mask = (scores >= edges[i]) & (scores < edges[i + 1])
        count = int(mask.sum())
        if count == 0:
            continue
        rows.append(
            {
                "lo": round(float(edges[i]), 2),
                "hi": round(float(edges[i + 1]), 2),
                "mean_score": round(float(scores[mask].mean()), 4),
                "fraud_rate": round(float(y_true[mask].mean()), 4),
                "n": count,
            }
        )
    return rows


def _importance(champion, names: list) -> list:
    model = champion
    if hasattr(champion, "named_steps"):
        model = champion.named_steps.get("logisticregression", champion)
    coef = getattr(model, "coef_", None)
    if coef is None:
        return []
    values = np.asarray(coef).reshape(-1)
    order = np.argsort(-np.abs(values))[:15]
    return [
        {"feature": names[int(i)], "coef": round(float(values[int(i)]), 4)}
        for i in order
        if int(i) < len(names)
    ]


if __name__ == "__main__":
    started = time.time()
    train()
    print(f"trained in {time.time() - started:.1f}s")
