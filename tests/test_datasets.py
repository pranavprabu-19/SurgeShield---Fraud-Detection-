"""Dataset specs stay mapped, and sensitive columns never become model inputs."""

from pathlib import Path

import pandas as pd

from ml.datasets import SPECS, load_canonical
from ml.features import compute_features, fit_segments
from ml.schema import FEATURE_NAMES, STREAM_FEATURES


def test_builtin_specs_cover_the_four_files():
    assert {"creditcard", "ieee_cis", "paysim", "sparkov"} <= set(SPECS)
    assert SPECS["paysim"].time_scale == 3600
    assert SPECS["sparkov"].sensitive == ("gender", "dob")
    assert "gender" not in FEATURE_NAMES


def _write(path: Path, rows: list) -> None:
    pd.DataFrame(rows).to_csv(path, index=False)


def test_paysim_fixture_fills_graph_features(tmp_path):
    path = tmp_path / "paysim.csv"
    rows = []
    for i in range(12):
        rows.append({
            "step": 0,
            "amount": 20 + i,
            "nameOrig": "C1" if i < 6 else f"C{i}",
            "nameDest": "M1",
            "type": "TRANSFER",
            "isFraud": 1 if i > 8 else 0,
            "oldbalanceOrg": 100,
        })
    _write(path, rows)
    frame = load_canonical(path, SPECS["paysim"])
    assert "user_id" in frame.columns
    assert "gender" not in frame.columns
    kmeans, means, stds = fit_segments(frame, frame.attrs["base_cols"])
    features = compute_features(frame, kmeans, means, stds, frame.attrs["base_cols"])
    assert features["user_velocity_60"].max() >= 1
    assert features["merchant_fan_in_300"].max() >= 2
    assert set(STREAM_FEATURES).issubset(features.columns)
    assert "gender" not in features.columns


def test_sparkov_keeps_sensitive_off_the_model(tmp_path):
    path = tmp_path / "sparkov.csv"
    _write(path, [
        {
            "trans_date_trans_time": "2024-01-01 10:00:00",
            "cc_num": "4111",
            "merchant": "cafe",
            "category": "food",
            "amt": 12.5,
            "gender": "F",
            "dob": "1990-01-01",
            "lat": 12.9,
            "long": 77.5,
            "is_fraud": 0,
            "city_pop": 1000,
        },
        {
            "trans_date_trans_time": "2024-01-01 10:05:00",
            "cc_num": "4222",
            "merchant": "cafe",
            "category": "food",
            "amt": 400,
            "gender": "M",
            "dob": "1980-01-01",
            "lat": 13.0,
            "long": 77.6,
            "is_fraud": 1,
            "city_pop": 1000,
        },
    ])
    frame = load_canonical(path, SPECS["sparkov"])
    assert set(frame["gender"]) == {"F", "M"}
    assert "gender" not in frame.attrs["v_source"]
    assert "freq_category" in frame.attrs["v_source"]
    assert frame.attrs["base_cols"] == [f"V{i}" for i in range(1, 29)]
    assert {"lat", "lon", "category"}.issubset(frame.columns)
    assert "lat" not in frame.attrs["v_source"]


def test_offline_context_features_match_the_live_engine(tmp_path):
    from backend.app.engine import Engine
    from backend.app.scenarios import _row_event
    from ml.schema import ARTIFACT_PATH

    path = tmp_path / "ctx.csv"
    rows = []
    places = [(12.97, 77.59), (28.61, 77.21), (19.07, 72.88)]
    for i in range(14):
        lat, lon = places[i % 3]
        rows.append({
            "trans_date_trans_time": f"2024-01-01 10:{i:02d}:{(i * 7) % 60:02d}",
            "cc_num": f"card-{i % 4}",
            "merchant": f"shop-{i % 2}",
            "category": "electronics",
            "amt": 100 + 40 * i,
            "gender": "F",
            "dob": "1990-01-01",
            "lat": lat,
            "long": lon,
            "is_fraud": 0,
            "device_id": f"dev-{i % 3}",
        })
    _write(path, rows)
    spec = SPECS["sparkov"].__class__(**{**SPECS["sparkov"].__dict__, "name": "ctx", "device": "device_id"})
    frame = load_canonical(path, spec)
    kmeans, means, stds = fit_segments(frame, frame.attrs["base_cols"])
    offline = compute_features(frame, kmeans, means, stds, frame.attrs["base_cols"])
    assert {"accounts_per_device_300", "travel_kmh", "merchant_ticket_ratio"}.issubset(offline.columns)

    engine = Engine(ARTIFACT_PATH)
    engine.reset()
    ordered = frame.sort_values("Time", kind="mergesort").reset_index(drop=True)
    for index, row in ordered.iterrows():
        event = _row_event(row, float(row["Time"]), None, None)
        result = engine.score(event, explain=False)
        profile = result["profile"]
        assert profile["device_users"] == offline.loc[index, "accounts_per_device_300"]
        assert abs(min(profile["travel_kmh"], 20000.0) - offline.loc[index, "travel_kmh"]) <= 0.1
        assert abs(profile["ticket_ratio"] - offline.loc[index, "merchant_ticket_ratio"]) <= 1e-3


def test_ieee_spec_maps_identity_columns():
    spec = SPECS["ieee_cis"]
    assert spec.user_id == "card1"
    assert spec.device == "DeviceInfo"
    assert spec.pca is False
