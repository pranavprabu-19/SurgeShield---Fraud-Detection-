"""Import a fraud CSV once, so training, replay, history, and the map all run on its real fields.

    PYTHONPATH=. .venv/bin/python -m ml.import_dataset --path fraudTrain.csv --test fraudTest.csv
    PYTHONPATH=. .venv/bin/python -m ml.import_dataset --path upi.csv --name upi_bank \
        --map time=txn_ts,amount=amt,label=fraud,user=payer_vpa,merchant=payee_vpa,city=city,lat=lat,lon=lon
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.metrics import roc_auc_score

from ml.datasets import IMPORT_DIR, SPECS, DatasetSpec, _as_time

SIGNATURES = {
    "creditcard": {"Time", "Amount", "Class", "V1", "V28"},
    "sparkov": {"trans_date_trans_time", "amt", "is_fraud", "cc_num", "merchant"},
    "ieee_cis": {"TransactionDT", "TransactionAmt", "isFraud"},
    "paysim": {"step", "amount", "isFraud", "nameOrig", "nameDest"},
}
KNOWN_LEAKS = {"isFlaggedFraud"}
ID_PATTERN = re.compile(r"(^id$|_id$|^id_|transactionid|txn_?id|trans_?num|^index$|^row_?num)", re.I)
PII_PATTERN = re.compile(r"^(first|last|name|full_?name|street|address|addr_line|job|email|phone|mobile|ssn|aadhaar|pan|trans_num|zip|pincode)$", re.I)
MAP_KEYS = {
    "time": "time",
    "amount": "amount",
    "label": "label",
    "user": "user_id",
    "merchant": "merchant_id",
    "device": "device",
    "category": "category",
    "channel": "channel",
    "city": "city",
}
LEAK_AUC = 0.98


def detect(columns) -> str | None:
    present = set(columns)
    for name, signature in SIGNATURES.items():
        if signature.issubset(present):
            return name
    return None


def parse_map(text: str) -> dict:
    pairs = {}
    for chunk in (text or "").split(","):
        if "=" not in chunk:
            continue
        key, value = chunk.split("=", 1)
        pairs[key.strip()] = value.strip()
    return pairs


def spec_from_map(name: str, pairs: dict) -> DatasetSpec:
    missing = [key for key in ("time", "amount", "label") if key not in pairs]
    if missing:
        raise SystemExit(f"--map needs {', '.join(missing)}")
    body = {"name": name}
    for key, field in MAP_KEYS.items():
        if key in pairs:
            body[field] = pairs[key]
    if "lat" in pairs and "lon" in pairs:
        body["geo"] = (pairs["lat"], pairs["lon"])
    if "merch_lat" in pairs and "merch_lon" in pairs:
        body["merch_geo"] = (pairs["merch_lat"], pairs["merch_lon"])
    if "sensitive" in pairs:
        body["sensitive"] = tuple(part for part in pairs["sensitive"].split(";") if part)
    if "time_scale" in pairs:
        body["time_scale"] = float(pairs["time_scale"])
    return DatasetSpec(**body)


def mapped_columns(spec: DatasetSpec) -> list:
    return [
        column
        for column in (
            spec.time,
            spec.amount,
            spec.label,
            spec.user_id,
            spec.merchant_id,
            spec.device,
            spec.channel,
            spec.category,
            spec.city,
            *spec.geo,
            *spec.merch_geo,
            *spec.sensitive,
        )
        if column
    ]


def _label(frame: pd.DataFrame, spec: DatasetSpec) -> np.ndarray:
    return pd.to_numeric(frame[spec.label], errors="coerce").fillna(0).astype(int).to_numpy()


def clean(frame: pd.DataFrame, spec: DatasetSpec) -> tuple[pd.DataFrame, dict, list]:
    keep = set(mapped_columns(spec))
    dropped = {"pii": [], "leak": [], "identifier": [], "text": [], "spec": []}
    label = _label(frame, spec)
    features = []
    for column in frame.columns:
        if column in keep:
            continue
        if column in spec.drop or str(column).startswith("Unnamed"):
            dropped["spec"].append(column)
            continue
        if PII_PATTERN.match(str(column)):
            dropped["pii"].append(column)
            continue
        if column in KNOWN_LEAKS:
            dropped["leak"].append(column)
            continue
        if not pd.api.types.is_numeric_dtype(frame[column]):
            dropped["text"].append(column)
            continue
        values = pd.to_numeric(frame[column], errors="coerce").fillna(0)
        unique = values.nunique() > 0.95 * len(values) and len(values) > 20
        if ID_PATTERN.search(str(column)) or (pd.api.types.is_integer_dtype(frame[column]) and unique and values.is_monotonic_increasing):
            dropped["identifier"].append(column)
            continue
        if 0 < label.sum() < len(label) and values.nunique() > 1:
            auc = roc_auc_score(label, values)
            if max(auc, 1 - auc) > LEAK_AUC:
                dropped["leak"].append(column)
                continue
        features.append(column)
    columns = [column for column in frame.columns if column in keep or column in features]
    return frame[columns].copy(), dropped, features


def coverage(spec: DatasetSpec) -> dict:
    has_user = bool(spec.user_id)
    has_merchant = bool(spec.merchant_id)
    has_geo = len(spec.geo) == 2
    has_device = bool(spec.device) and spec.device_is_id

    def pick(real: bool, fallback: str = "simulated") -> str:
        return "real" if real else fallback

    return {
        "customer history and cases": pick(has_user),
        "merchant leaderboard and fan-in": pick(has_merchant),
        "map of payment locations": "real" if has_geo else ("real city, no coordinates" if spec.city else "simulated"),
        "impossible travel": pick(has_geo and has_user),
        "device farm": pick(has_device and has_user),
        "category risk": pick(bool(spec.category)),
        "merchant ticket ratio": pick(has_merchant),
        "fairness report": pick(bool(spec.sensitive), "unavailable"),
        "checkout telemetry (human score)": "simulated",
    }


def time_split(frame: pd.DataFrame, spec: DatasetSpec, share: float = 0.7) -> tuple[pd.DataFrame, pd.DataFrame]:
    order = _as_time(frame[spec.time], spec.time_scale).sort_values(kind="mergesort").index
    ordered = frame.loc[order].reset_index(drop=True)
    cut = int(len(ordered) * share)
    return ordered.iloc[:cut].reset_index(drop=True), ordered.iloc[cut:].reset_index(drop=True)


def run(path: str, test: str | None = None, name: str | None = None, mapping: str | None = None, out_dir: Path | None = None, limit: int | None = None) -> dict:
    out_dir = Path(out_dir or IMPORT_DIR)
    raw = pd.read_csv(path, nrows=limit)
    detected = detect(raw.columns)
    if mapping:
        spec = spec_from_map(name or Path(path).stem.lower(), parse_map(mapping))
    elif detected:
        base = SPECS[detected]
        spec = DatasetSpec.from_json({**base.to_json(), "name": name or detected})
    else:
        raise SystemExit("Could not recognise this file. Pass --map time=...,amount=...,label=...")
    if spec.pca:
        raise SystemExit("The creditcard file is already installed under train/. Nothing to import.")

    duplicates = int(raw.duplicated().sum())
    raw = raw.drop_duplicates().reset_index(drop=True)
    train_raw, dropped, features = clean(raw, spec)
    if test:
        test_raw = pd.read_csv(test, nrows=limit).drop_duplicates().reset_index(drop=True)
        test_raw = test_raw[[column for column in train_raw.columns if column in test_raw.columns]]
    else:
        train_raw, test_raw = time_split(train_raw, spec)
    device_is_id = spec.device_is_id
    if spec.device and spec.device in raw.columns and spec.user_id and spec.user_id in raw.columns:
        device_is_id = bool(raw[spec.device].nunique() >= 0.2 * max(raw[spec.user_id].nunique(), 1))
    features = features + [f"freq_{column}" for column in (spec.channel, spec.category) if column and column in raw.columns]
    spec = DatasetSpec.from_json({
        **spec.to_json(),
        "features": features[:28],
        "drop": sorted(set(spec.drop) | set(sum(dropped.values(), []))),
        "device_is_id": device_is_id,
    })

    target = out_dir / spec.name
    target.mkdir(parents=True, exist_ok=True)
    train_raw.to_csv(target / "train.csv", index=False)
    test_raw.to_csv(target / "test.csv", index=False)
    (target / "spec.json").write_text(json.dumps(spec.to_json(), indent=2))

    train_time = _as_time(pd.concat([train_raw[spec.time], test_raw[spec.time]], ignore_index=True), spec.time_scale)
    labels = np.concatenate([_label(train_raw, spec), _label(test_raw, spec)])
    report = {
        "name": spec.name,
        "detected": detected,
        "source": Path(path).name,
        "rows": {"train": len(train_raw), "test": len(test_raw)},
        "fraud_rate": round(float(labels.mean()) if len(labels) else 0.0, 5),
        "time_span_days": round(float(train_time.max() - train_time.min()) / 86400.0, 2) if len(train_time) else 0.0,
        "duplicates_dropped": duplicates,
        "mapped": {field: getattr(spec, field) for field in ("time", "amount", "label", "user_id", "merchant_id", "device", "category", "channel", "city") if getattr(spec, field)},
        "geo": list(spec.geo),
        "model_features": features[:28],
        "dropped": dropped,
        "split": "given test file" if test else "70/30 by time",
        "coverage": coverage(spec),
    }
    (target / "report.json").write_text(json.dumps(report, indent=2, default=str))
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--path", required=True)
    parser.add_argument("--test")
    parser.add_argument("--name")
    parser.add_argument("--map", dest="mapping")
    parser.add_argument("--limit", type=int, help="read at most this many rows from each file")
    args = parser.parse_args()
    report = run(args.path, args.test, args.name, args.mapping, limit=args.limit)
    print(json.dumps(report, indent=2, default=str))
    print(f"\nNext: SURGESHIELD_DATASET={report['name']} PYTHONPATH=. .venv/bin/python -m ml.train")


if __name__ == "__main__":
    main()
