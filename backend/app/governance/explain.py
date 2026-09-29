"""Reason codes from TreeSHAP, with a deterministic fallback."""

from __future__ import annotations

import numpy as np

REASON_TEXT = {
    "log_amount": "the ticket size is unusual for this stream",
    "hour": "the time of day matches a higher-risk hour",
    "night": "this is the overnight window, where fraud is about 20x the daytime rate",
    "cnt_10": "transaction velocity over the last 10 seconds is elevated",
    "cnt_60": "transaction velocity over the last minute is elevated",
    "cnt_300": "transaction velocity over the last 5 minutes is elevated",
    "amt_mean_60": "recent ticket sizes differ from this transaction",
    "amt_std_60": "recent amounts are erratic",
    "amt_mean_300": "the 5-minute amount pattern is unusual",
    "seg_share_60": "recent payments are concentrated in one behavioral segment",
    "amt_z": "the amount is far from what this segment normally spends",
    "dist_centroid": "the behavior sits far from its segment's normal pattern",
    "segment": "this behavioral segment carries elevated risk",
    "coord_proxy": "recent traffic is unusually concentrated",
}


def top_reasons(shap_values, feature_names: list, k: int = 3) -> list:
    values = np.asarray(shap_values, dtype=float).reshape(-1)
    order = np.argsort(-np.abs(values))
    reasons = []
    for idx in order:
        if len(reasons) >= k:
            break
        name = feature_names[idx]
        if name.startswith("V"):
            text = f"anonymized behavior component {name} pushed risk"
        else:
            text = REASON_TEXT.get(name, name.replace("_", " "))
        direction = "up" if values[idx] > 0 else "down"
        reasons.append(
            {
                "feature": name,
                "shap": round(float(values[idx]), 4),
                "direction": direction,
                "text": text if direction == "up" else f"{text} (this lowered risk)",
            }
        )
    return reasons
