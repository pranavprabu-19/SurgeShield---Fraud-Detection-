"""Training baselines for checks that must not invent a threshold.

Writes ml/artifacts/baselines.json. If train/train.csv is missing, writes nothing.
"""

from __future__ import annotations

import json

import joblib
import numpy as np

from ml.datasets import active_spec, data_paths, load_canonical
from ml.schema import ARTIFACT_DIR, ARTIFACT_PATH, V_COLS


def build() -> dict | None:
    train_path, _ = data_paths()
    if not train_path.exists() or not ARTIFACT_PATH.exists():
        return None
    spec = active_spec()
    frame = load_canonical(train_path, spec)
    art = joblib.load(ARTIFACT_PATH)
    base = list(frame.attrs.get("base_cols") or V_COLS)
    values = frame[base].to_numpy(dtype=float)
    labels = art["kmeans"].predict(values)
    centers = art["kmeans"].cluster_centers_
    distance = np.linalg.norm(values - centers[labels], axis=1)
    ood = []
    volatility = []
    minutes = (frame["Time"].to_numpy(dtype=float) // 60.0).astype(int)
    amounts = frame["Amount"].to_numpy(dtype=float)
    for seg in range(len(centers)):
        part = distance[labels == seg]
        ood.append(float(np.quantile(part, 0.999)) if len(part) else 1e9)
        spread = []
        for minute in np.unique(minutes[labels == seg]):
            chunk = amounts[(labels == seg) & (minutes == minute)]
            if len(chunk) >= 5:
                spread.append(float(np.std(chunk)))
        volatility.append(float(np.median(spread)) if spread else 0.0)
    columns = [col for col in [*V_COLS[:8], "Amount"] if col in frame.columns]
    matrix = frame[columns].corr().fillna(0.0).to_numpy(dtype=float)
    report = {
        "ood_distance": ood,
        "volatility_std": volatility,
        "correlation_columns": columns,
        "correlation": [[round(float(value), 5) for value in row] for row in matrix],
    }
    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    (ARTIFACT_DIR / "baselines.json").write_text(json.dumps(report))
    return report


if __name__ == "__main__":
    body = build()
    print("no training file" if body is None else f"ood cuts {len(body['ood_distance'])}")
