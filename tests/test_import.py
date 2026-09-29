"""The importer recognises files, maps custom ones, drops PII and leaks, and splits by time."""

import json

import numpy as np
import pandas as pd

from ml.datasets import DatasetSpec, load_canonical
from ml.import_dataset import detect, run


def _sparkov(n=60, seed=0):
    rng = np.random.default_rng(seed)
    rows = []
    for i in range(n):
        fraud = int(i % 10 == 0)
        rows.append({
            "Unnamed: 0": i,
            "trans_date_trans_time": str(pd.Timestamp("2019-12-01") + pd.Timedelta(minutes=i)),
            "cc_num": f"4{1000 + i % 7}",
            "merchant": f"m{i % 5}",
            "category": ["grocery_pos", "shopping_net"][i % 2],
            "amt": float(20 + rng.integers(0, 50)),
            "first": "Asha",
            "last": "Rao",
            "street": "MG Road",
            "job": "Clerk",
            "trans_num": f"t{i}",
            "gender": "F",
            "dob": "1990-01-01",
            "city": "Chennai",
            "lat": 13.08,
            "long": 80.27,
            "merch_lat": 13.1,
            "merch_long": 80.3,
            "city_pop": 1000 + (i % 3),
            "is_fraud": fraud,
        })
    return pd.DataFrame(rows)


def test_detects_the_known_files():
    assert detect(_sparkov().columns) == "sparkov"
    assert detect(["step", "amount", "isFraud", "nameOrig", "nameDest", "type"]) == "paysim"
    assert detect(["TransactionDT", "TransactionAmt", "isFraud", "card1"]) == "ieee_cis"
    assert detect(["a", "b"]) is None


def test_sparkov_import_drops_pii_and_splits_by_time(tmp_path):
    source = tmp_path / "fraudTrain.csv"
    _sparkov().to_csv(source, index=False)
    report = run(str(source), name="spk", out_dir=tmp_path / "data")
    target = tmp_path / "data" / "spk"
    train = pd.read_csv(target / "train.csv")
    test = pd.read_csv(target / "test.csv")
    for column in ("first", "last", "street", "job", "trans_num", "Unnamed: 0"):
        assert column not in train.columns
    assert "cc_num" in train.columns
    assert len(train) == 42 and len(test) == 18
    assert pd.to_datetime(train["trans_date_trans_time"]).max() <= pd.to_datetime(test["trans_date_trans_time"]).min()
    assert report["coverage"]["map of payment locations"] == "real"
    assert report["coverage"]["device farm"] == "simulated"
    spec = DatasetSpec.from_json(json.loads((target / "spec.json").read_text()))
    frame = load_canonical(target / "train.csv", spec)
    assert {"lat", "lon", "region", "category"}.issubset(frame.columns)
    assert "gender" not in frame.attrs["v_source"]


def test_leak_column_is_dropped(tmp_path):
    frame = _sparkov()
    frame["isFlaggedFraud"] = 0
    frame["leaky"] = frame["is_fraud"] * 100 + 1
    source = tmp_path / "leak.csv"
    frame.to_csv(source, index=False)
    report = run(str(source), name="leak", out_dir=tmp_path / "data")
    assert "isFlaggedFraud" in report["dropped"]["leak"]
    assert "leaky" in report["dropped"]["leak"]
    assert "leaky" not in report["model_features"]


def test_custom_map_round_trip(tmp_path):
    rows = []
    for i in range(40):
        rows.append({
            "txn_ts": f"2024-10-0{1 + i // 20} 12:{i % 60:02d}:00",
            "amt": 100 + i,
            "fraud": int(i % 8 == 0),
            "payer_vpa": f"user{i % 6}@upi",
            "payee_vpa": f"shop{i % 3}@upi",
            "city": "Mumbai",
            "device_id": f"d{i}",
            "balance": 5000 - i,
        })
    source = tmp_path / "upi.csv"
    pd.DataFrame(rows).to_csv(source, index=False)
    report = run(
        str(source),
        name="upi_bank",
        mapping="time=txn_ts,amount=amt,label=fraud,user=payer_vpa,merchant=payee_vpa,city=city,device=device_id",
        out_dir=tmp_path / "data",
    )
    spec = DatasetSpec.from_json(json.loads((tmp_path / "data" / "upi_bank" / "spec.json").read_text()))
    assert spec.user_id == "payer_vpa" and spec.city == "city" and spec.device == "device_id"
    assert report["coverage"]["device farm"] == "real"
    assert report["coverage"]["map of payment locations"] == "real city, no coordinates"
    frame = load_canonical(tmp_path / "data" / "upi_bank" / "train.csv", spec)
    assert set(frame["region"]) == {"Mumbai"}
    assert "balance" in frame.attrs["v_source"]
