"""Fit a challenger on analyst labels. It never replaces the champion by itself."""

from __future__ import annotations

import joblib
import numpy as np
from sklearn.linear_model import LogisticRegression

from ml.schema import ARTIFACT_DIR


def propose(rows: list) -> dict:
    """Fit on earlier review labels and score the later ones. A human still promotes."""
    usable = [row for row in rows if row.get("features") and row.get("label") is not None]
    labels = {int(row["label"]) for row in usable}
    if len(usable) < 8 or len(labels) < 2:
        return {"status": "need_more_labels", "n": len(usable), "recommend": False}
    x = np.asarray([row["features"] for row in usable], dtype=float)
    y = np.asarray([int(row["label"]) for row in usable], dtype=int)
    hold = max(2, len(y) // 3)
    x_fit, y_fit, x_hold, y_hold = x[:-hold], y[:-hold], x[-hold:], y[-hold:]
    if len(set(y_fit.tolist())) < 2:
        return {"status": "need_more_labels", "n": len(usable), "recommend": False}
    model = LogisticRegression(max_iter=200, class_weight="balanced")
    model.fit(x_fit, y_fit)
    holdout = float(model.score(x_hold, y_hold))
    champion_holdout = _champion_holdout(x_hold, y_hold)
    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    joblib.dump(
        {"model": model, "n": int(len(y_fit)), "holdout_accuracy": holdout},
        ARTIFACT_DIR / "challenger.joblib",
    )
    better = champion_holdout is None or holdout >= champion_holdout
    return {
        "status": "proposed",
        "n": int(len(y_fit)),
        "holdout_n": int(hold),
        "holdout_accuracy": round(holdout, 4),
        "champion_holdout_accuracy": None if champion_holdout is None else round(champion_holdout, 4),
        "recommend": bool(holdout >= 0.7 and better),
        "note": "Scored on later review labels only. Promotion does not swap the live champion.",
    }


def _champion_holdout(x_hold: np.ndarray, y_hold: np.ndarray):
    from ml.schema import ARTIFACT_PATH

    if not ARTIFACT_PATH.exists():
        return None
    art = joblib.load(ARTIFACT_PATH)
    model = art.get("champion")
    if model is None or x_hold.shape[1] != getattr(model, "n_features_in_", x_hold.shape[1]):
        return None
    try:
        pred = model.predict(x_hold)
    except Exception:
        return None
    return float(np.mean(pred == y_hold))
