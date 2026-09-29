"""Map a source file onto the columns SurgeShield trains and scores."""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, fields
from pathlib import Path

import numpy as np
import pandas as pd

from ml.features import load_transactions
from ml.schema import ARTIFACT_DIR, ARTIFACT_PATH, DATA_DIR, ROOT, V_COLS

IMPORT_DIR = ROOT / "data"

# Raw context that features, history, and the map read. Never model inputs.
PASSTHROUGH = ("region", "lat", "lon", "merch_lat", "merch_lon", "category", "channel", "device")


@dataclass(frozen=True)
class DatasetSpec:
    name: str
    time: str
    amount: str
    label: str
    user_id: str | None = None
    merchant_id: str | None = None
    device: str | None = None
    geo: tuple = ()
    channel: str | None = None
    category: str | None = None
    sensitive: tuple = ()
    pca: bool = False
    time_scale: float = 1.0
    city: str | None = None
    merch_geo: tuple = ()
    drop: tuple = ()
    features: tuple = ()
    # A device model name ("Windows") is shared by honest users; only a per-device id can reveal a farm.
    device_is_id: bool = True

    def to_json(self) -> dict:
        body = asdict(self)
        for key in ("geo", "sensitive", "merch_geo", "drop", "features"):
            body[key] = list(body[key])
        return body

    @classmethod
    def from_json(cls, body: dict) -> "DatasetSpec":
        known = {item.name for item in fields(cls)}
        clean = {key: value for key, value in body.items() if key in known}
        for key in ("geo", "sensitive", "merch_geo", "drop", "features"):
            if key in clean:
                clean[key] = tuple(clean[key] or ())
        return cls(**clean)


SPECS = {
    "creditcard": DatasetSpec("creditcard", "Time", "Amount", "Class", pca=True),
    "ieee_cis": DatasetSpec(
        "ieee_cis",
        "TransactionDT",
        "TransactionAmt",
        "isFraud",
        user_id="card1",
        merchant_id="addr1",
        device="DeviceInfo",
        channel="ProductCD",
        drop=("TransactionID",),
        device_is_id=False,
    ),
    "paysim": DatasetSpec(
        "paysim",
        "step",
        "amount",
        "isFraud",
        user_id="nameOrig",
        merchant_id="nameDest",
        channel="type",
        time_scale=3600.0,
        drop=("isFlaggedFraud",),
    ),
    "sparkov": DatasetSpec(
        "sparkov",
        "trans_date_trans_time",
        "amt",
        "is_fraud",
        user_id="cc_num",
        merchant_id="merchant",
        category="category",
        geo=("lat", "long"),
        sensitive=("gender", "dob"),
        city="city",
        merch_geo=("merch_lat", "merch_long"),
        drop=("Unnamed: 0", "unix_time", "zip", "trans_num", "first", "last", "street", "job"),
    ),
}
BUILTIN = frozenset(SPECS)


def load_imported() -> dict:
    found = {}
    if not IMPORT_DIR.exists():
        return found
    for spec_file in sorted(IMPORT_DIR.glob("*/spec.json")):
        try:
            spec = DatasetSpec.from_json(json.loads(spec_file.read_text()))
        except (ValueError, TypeError, KeyError):
            continue
        found[spec.name] = spec
    return found


SPECS.update(load_imported())


def active_name() -> str:
    return os.environ.get("SURGESHIELD_DATASET", "creditcard")


def active_spec() -> DatasetSpec:
    name = active_name()
    if name not in SPECS:
        SPECS.update(load_imported())
    if name not in SPECS:
        raise KeyError(f"unknown dataset {name}")
    return SPECS[name]


def artifact_path(name: str | None = None) -> Path:
    name = name or active_name()
    if name == "creditcard":
        return ARTIFACT_PATH
    return ARTIFACT_DIR / name / "model.joblib"


def data_paths(name: str | None = None) -> tuple[Path, Path]:
    override = os.environ.get("SURGESHIELD_DATA_PATH")
    if override and name is None:
        path = Path(override)
        if path.is_dir():
            return path / "train.csv", path / "test.csv"
        return path, path
    name = name or active_name()
    imported = IMPORT_DIR / name
    if (imported / "train.csv").exists():
        return imported / "train.csv", imported / "test.csv"
    return DATA_DIR / "train.csv", DATA_DIR / "test.csv"


def _as_time(series: pd.Series, scale: float) -> pd.Series:
    """Absolute seconds, so a train file and its test file share one clock."""
    numeric = pd.to_numeric(series, errors="coerce")
    if numeric.notna().mean() > 0.9:
        return numeric.fillna(numeric.median()).astype(float) * scale
    parsed = pd.to_datetime(series, errors="coerce")
    parsed = parsed.fillna(parsed.min())
    return parsed.astype("int64") / 1e9


def _signed_log(values: pd.Series) -> pd.Series:
    """Stateless scaling, so train and test files map the same way without shared statistics."""
    numeric = pd.to_numeric(values, errors="coerce").fillna(0).astype(float)
    return np.sign(numeric) * np.log1p(np.abs(numeric))


def _derived(raw: pd.DataFrame, spec: DatasetSpec, times: pd.Series, amounts: pd.Series) -> dict:
    """Per-row geometry for files with few numeric columns. Stateless, so train and test agree."""
    out = {
        "d_amount": np.log1p(amounts.clip(lower=0)).to_numpy(),
        "d_hour_sin": np.sin(2 * np.pi * ((times % 86400.0) / 86400.0)).to_numpy(),
        "d_hour_cos": np.cos(2 * np.pi * ((times % 86400.0) / 86400.0)).to_numpy(),
    }
    if len(spec.geo) == 2 and all(column in raw.columns for column in spec.geo):
        lat = pd.to_numeric(raw[spec.geo[0]], errors="coerce").fillna(0.0)
        lon = pd.to_numeric(raw[spec.geo[1]], errors="coerce").fillna(0.0)
        out["d_lat"] = (lat / 90.0).to_numpy()
        out["d_lon"] = (lon / 180.0).to_numpy()
        if len(spec.merch_geo) == 2 and all(column in raw.columns for column in spec.merch_geo):
            mlat = pd.to_numeric(raw[spec.merch_geo[0]], errors="coerce").fillna(lat)
            mlon = pd.to_numeric(raw[spec.merch_geo[1]], errors="coerce").fillna(lon)
            dlat = np.radians(mlat - lat)
            dlon = np.radians(mlon - lon)
            a = np.sin(dlat / 2) ** 2 + np.cos(np.radians(lat)) * np.cos(np.radians(mlat)) * np.sin(dlon / 2) ** 2
            km = 2 * 6371.0 * np.arcsin(np.sqrt(np.clip(a, 0, 1)))
            out["d_merchant_km"] = np.log1p(km).to_numpy()
    return out


def feature_columns(raw: pd.DataFrame, spec: DatasetSpec) -> list:
    reserved = {
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
        *spec.drop,
    }
    if spec.features:
        return [column for column in spec.features if column in raw.columns or column.startswith("freq_")]
    columns = [
        column
        for column in raw.columns
        if column not in reserved and not str(column).startswith("Unnamed") and pd.api.types.is_numeric_dtype(raw[column])
    ]
    columns += [f"freq_{column}" for column in (spec.channel, spec.category) if column and column in raw.columns]
    return columns[: len(V_COLS)]


def load_canonical(path, spec: DatasetSpec | None = None) -> pd.DataFrame:
    spec = spec or active_spec()
    if spec.pca:
        frame = load_transactions(path)
        frame.attrs["dataset"] = spec.name
        frame.attrs["base_cols"] = list(V_COLS)
        frame.attrs["v_source"] = list(V_COLS)
        return frame

    raw = pd.read_csv(path)
    out = pd.DataFrame()
    out["Time"] = _as_time(raw[spec.time], spec.time_scale)
    out["Amount"] = pd.to_numeric(raw[spec.amount], errors="coerce").fillna(0).astype(float)
    out["Class"] = pd.to_numeric(raw[spec.label], errors="coerce").fillna(0).astype(int)
    if spec.user_id and spec.user_id in raw.columns:
        out["user_id"] = raw[spec.user_id].astype(str)
    if spec.merchant_id and spec.merchant_id in raw.columns:
        out["merchant_id"] = raw[spec.merchant_id].astype(str)

    derived = _derived(raw, spec, out["Time"], out["Amount"])
    sources = (list(derived) + feature_columns(raw, spec))[: len(V_COLS)]
    for index, name in enumerate(V_COLS):
        if index < len(sources):
            column = sources[index]
            if column in derived:
                out[name] = derived[column]
            elif column.startswith("freq_") and column not in raw.columns:
                original = column[len("freq_"):]
                freq = raw[original].astype(str).value_counts(normalize=True)
                out[name] = raw[original].astype(str).map(freq).astype(float)
            else:
                out[name] = _signed_log(raw[column])
        else:
            out[name] = 0.0

    def text(column):
        return raw[column].astype(str).where(raw[column].notna(), None)

    def number(column):
        return pd.to_numeric(raw[column], errors="coerce")

    if spec.city and spec.city in raw.columns:
        out["region"] = text(spec.city)
    if len(spec.geo) == 2 and all(column in raw.columns for column in spec.geo):
        out["lat"] = number(spec.geo[0])
        out["lon"] = number(spec.geo[1])
    if len(spec.merch_geo) == 2 and all(column in raw.columns for column in spec.merch_geo):
        out["merch_lat"] = number(spec.merch_geo[0])
        out["merch_lon"] = number(spec.merch_geo[1])
    if spec.category and spec.category in raw.columns:
        out["category"] = text(spec.category)
    if spec.channel and spec.channel in raw.columns:
        out["channel"] = text(spec.channel)
    if spec.device and spec.device in raw.columns:
        out["device"] = text(spec.device)
    for column in spec.sensitive:
        if column in raw.columns:
            out[column] = raw[column].astype(str)
    before = len(out)
    out = out.drop_duplicates().reset_index(drop=True)
    out.attrs["dropped_duplicates"] = before - len(out)
    out.attrs["dataset"] = spec.name
    out.attrs["base_cols"] = list(V_COLS)
    out.attrs["v_source"] = sources
    out.attrs["passthrough"] = [column for column in PASSTHROUGH if column in out.columns]
    out.attrs["device_is_id"] = spec.device_is_id
    return out


def field_sources(name: str | None = None) -> dict:
    """Where location, device, and category come from for the active dataset."""
    spec = SPECS.get(name or active_name())
    if spec is None or spec.pca:
        return {"location": "simulated", "device": "simulated", "category": "simulated"}
    return {
        "location": "real" if len(spec.geo) == 2 else ("real city" if spec.city else "simulated"),
        "device": "real" if spec.device and spec.device_is_id else "simulated",
        "category": "real" if spec.category else "simulated",
    }


def installed() -> list:
    SPECS.update(load_imported())
    rows = []
    for name, spec in SPECS.items():
        imported = (IMPORT_DIR / name / "train.csv").exists()
        if name != "creditcard" and not imported:
            continue
        train_path, test_path = data_paths(name)
        report_file = IMPORT_DIR / name / "report.json"
        metrics_file = artifact_path(name).parent / "metrics.json"
        rows.append(
            {
                "name": name,
                "builtin": name in BUILTIN,
                "has_data": train_path.exists() and test_path.exists(),
                "has_model": artifact_path(name).exists(),
                "report": json.loads(report_file.read_text()) if report_file.exists() else None,
                "metrics": json.loads(metrics_file.read_text()) if metrics_file.exists() else None,
                "spec": spec.to_json(),
            }
        )
    return rows
