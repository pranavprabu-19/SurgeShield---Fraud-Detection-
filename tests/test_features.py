import numpy as np
import pandas as pd

from ml.features import compute_features, fit_segments


def test_windows_do_not_see_the_future():
    rows = []
    for i, amount in enumerate([10, 20, 30, 40, 50]):
        row = {"Time": float(i * 10), "Amount": float(amount), "Class": 0}
        for v in range(1, 29):
            row[f"V{v}"] = float(i)
        rows.append(row)
    frame = pd.DataFrame(rows)
    kmeans, mean, std = fit_segments(frame)
    feats = compute_features(frame, kmeans, mean, std)
    # At t=20 the only past rows are t=0 and t=10, so the 60s count is 2.
    row = feats.loc[feats["Time"] == 20].iloc[0]
    assert row["cnt_60"] == 2
    assert row["amt_mean_60"] == 15
    assert feats.iloc[0]["cnt_60"] == 0
    assert feats.iloc[0]["amt_mean_60"] == 0


def test_empty_window_is_safe():
    row = {"Time": 5.0, "Amount": 12.0, "Class": 1}
    for v in range(1, 29):
        row[f"V{v}"] = 0.1
    frame = pd.DataFrame([row])
    kmeans, mean, std = fit_segments(frame)
    feats = compute_features(frame, kmeans, mean, std)
    assert feats.iloc[0]["cnt_10"] == 0
    assert np.isfinite(feats.iloc[0]["amt_z"])
