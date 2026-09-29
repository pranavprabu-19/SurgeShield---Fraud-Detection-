"""Compare logistic regression, LightGBM, and XGBoost on the same split.

None of these fits replace the committed champion. XGBoost is not loaded by the API.
"""

from __future__ import annotations

import json

import lightgbm as lgb
import numpy as np
import pandas as pd
import xgboost as xgb
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

from ml.datasets import active_spec, data_paths, load_canonical
from ml.features import compute_features, fit_segments
from ml.metrics import ranking_metrics
from ml.schema import ARTIFACT_DIR, FEATURE_NAMES, SEED, V_COLS
from ml.train import _split_masks


def _gaps(frame: pd.DataFrame) -> list:
    legit = frame[frame["Class"] == 0]
    fraud = frame[frame["Class"] == 1]
    rows = []
    for column in [col for col in [*V_COLS, "Amount"] if col in frame.columns]:
        left = legit[column]
        right = fraud[column]
        left_mean = float(left.mean()) if len(left) else 0.0
        right_mean = float(right.mean()) if len(right) else 0.0
        rows.append(
            {
                "feature": column,
                "legit_mean": round(left_mean, 4),
                "fraud_mean": round(right_mean, 4),
                "legit_median": round(float(left.median()) if len(left) else 0.0, 4),
                "fraud_median": round(float(right.median()) if len(right) else 0.0, 4),
                "legit_missing": round(float(left.isna().mean()) if len(left) else 0.0, 4),
                "fraud_missing": round(float(right.isna().mean()) if len(right) else 0.0, 4),
                "legit_positive": round(float((left.dropna() > 0).mean()) if left.notna().any() else 0.0, 4),
                "fraud_positive": round(float((right.dropna() > 0).mean()) if right.notna().any() else 0.0, 4),
                "legit_negative": round(float((left.dropna() < 0).mean()) if left.notna().any() else 0.0, 4),
                "fraud_negative": round(float((right.dropna() < 0).mean()) if right.notna().any() else 0.0, 4),
                "gap": round(abs(right_mean - left_mean), 4),
            }
        )
    rows.sort(key=lambda row: row["gap"], reverse=True)
    return rows


def compare() -> dict:
    spec = active_spec()
    train_path, test_path = data_paths()
    train_df = load_canonical(train_path, spec)
    test_df = load_canonical(test_path, spec)
    base_cols = list(train_df.attrs.get("base_cols") or V_COLS)
    names = list(FEATURE_NAMES)
    kmeans, seg_mean, seg_std = fit_segments(train_df, base_cols)
    train_frame = compute_features(train_df, kmeans, seg_mean, seg_std, base_cols)
    combined = pd.concat(
        [train_df.assign(_origin="train"), test_df.assign(_origin="test")],
        ignore_index=True,
    )
    combined_frame = compute_features(combined, kmeans, seg_mean, seg_std, base_cols)
    combined_sorted = combined.sort_values(["Time"], kind="mergesort").reset_index(drop=True)
    combined_frame["_origin"] = combined_sorted["_origin"].to_numpy()
    test_frame = combined_frame[combined_frame["_origin"] == "test"].reset_index(drop=True)
    train_mask, _, _ = _split_masks(train_frame["Time"].to_numpy())
    x_train = train_frame.loc[train_mask, names]
    y_train = train_frame.loc[train_mask, "Class"].to_numpy()
    y_test = test_frame["Class"].to_numpy()
    x_test = test_frame[names]

    models = {
        "logistic": make_pipeline(
            StandardScaler(),
            LogisticRegression(class_weight="balanced", max_iter=500, solver="lbfgs", random_state=SEED),
        ),
        "lightgbm": lgb.LGBMClassifier(
            n_estimators=200,
            learning_rate=0.05,
            num_leaves=31,
            min_child_samples=40,
            subsample=0.9,
            colsample_bytree=0.8,
            random_state=SEED,
            n_jobs=4,
            verbose=-1,
        ),
        "xgboost": xgb.XGBClassifier(
            n_estimators=200,
            max_depth=6,
            learning_rate=0.05,
            subsample=0.9,
            colsample_bytree=0.8,
            random_state=SEED,
            n_jobs=4,
            eval_metric="logloss",
        ),
    }
    scored = {}
    for name, model in models.items():
        model.fit(x_train, y_train)
        scores = model.predict_proba(x_test)[:, 1]
        scored[name] = ranking_metrics(y_test, scores)
    report = {
        "note": "Fresh fits on the same time split. XGBoost is not loaded by the API and does not decide.",
        "models": scored,
        "features": _gaps(test_df),
    }
    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    (ARTIFACT_DIR / "compare.json").write_text(json.dumps(report, indent=2))
    return report


if __name__ == "__main__":
    body = compare()
    for name, metrics in body["models"].items():
        print(name, round(metrics["pr_auc"], 3), round(metrics["roc_auc"], 3), round(metrics["recall_at_0_1pct_fpr"], 3))
