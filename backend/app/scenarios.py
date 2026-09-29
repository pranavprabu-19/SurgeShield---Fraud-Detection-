"""Scripted streams. Attack rows are resampled from real fraud vectors in test.csv."""

from __future__ import annotations

import numpy as np
import pandas as pd

from backend.app.sales import SALE_EVENTS
from ml.datasets import PASSTHROUGH, active_spec, data_paths, load_canonical
from ml.schema import V_COLS


def _vector(row) -> list:
    if all(col in row.index for col in V_COLS):
        return [float(row[col]) for col in V_COLS]
    skip = {"Time", "Amount", "Class", "user_id", "merchant_id", "device"}
    cols = [col for col in row.index if col not in skip and isinstance(row[col], (int, float, np.floating))]
    return [float(row[col]) for col in cols]


def _row_event(row, when: float, user_id: str, merchant_id: str, amount=None) -> dict:
    spec = active_spec()
    if user_id is None and "user_id" in row.index and pd.notna(row["user_id"]):
        user_id = str(row["user_id"])
    if merchant_id is None and "merchant_id" in row.index and pd.notna(row["merchant_id"]):
        merchant_id = str(row["merchant_id"])
    user_id = user_id or "user"
    merchant_id = merchant_id or "merchant"
    groups = {col: str(row[col]) for col in spec.sensitive if col in row.index}
    event = {
        "time": float(when),
        "amount": float(row["Amount"] if amount is None else amount),
        "v": _vector(row),
        "user_id": user_id,
        "merchant_id": merchant_id,
        "eval_label": int(row["Class"]),
    }
    if groups:
        event["groups"] = groups
    for column in PASSTHROUGH:
        if column not in row.index or (column == "device" and not spec.device_is_id):
            continue
        value = row[column]
        if value is None or (isinstance(value, float) and np.isnan(value)) or value == "":
            continue
        key = "region" if column == "region" else column
        event[key] = float(value) if column in {"lat", "lon", "merch_lat", "merch_lon"} else str(value)
    return event


def _poisson(events: list, start: float, mean: float, rng: np.random.Generator) -> list:
    clock = float(start)
    for event in events:
        clock += float(rng.exponential(mean))
        event["time"] = clock
    return events


def _human(events: list, rng: np.random.Generator, prefix: str = "phone", category: str = "electronics") -> list:
    cities = np.array(["Bengaluru", "Chennai", "Hyderabad"])
    for index, event in enumerate(events):
        if not event.get("region"):
            event["region"] = str(rng.choice(cities, p=[0.6, 0.25, 0.15]))
        if not event.get("device"):
            event["device"] = f"{prefix}-{index}"
        if not event.get("category"):
            event["category"] = category
        event["telemetry"] = {
            "simulated": True,
            "session_duration_sec": float(rng.uniform(45, 360)),
            "action_count": int(rng.integers(4, 14)),
            "typing_cps": float(rng.uniform(3.5, 8)),
            "mouse_entropy": float(rng.uniform(0.4, 0.9)),
            "action_interval_cv": float(rng.uniform(0.35, 0.9)),
        }
    return events


def _bot(events: list, rng: np.random.Generator, devices: int = 3, category: str = "transfer", prefix: str = "bot") -> list:
    regions = np.array(["Delhi", "Kolkata", "Jaipur", "Guwahati", "Kochi", "Lucknow"])
    for index, event in enumerate(events):
        if not event.get("region") and event.get("lat") is None:
            event["region"] = str(rng.choice(regions))
        if not event.get("device"):
            event["device"] = f"{prefix}-{index % devices}"
        if not event.get("category"):
            event["category"] = category
        event["telemetry"] = {
            "simulated": True,
            "session_duration_sec": 0.4,
            "action_count": 1,
            "typing_cps": 40.0,
            "mouse_entropy": 0.02,
            "action_interval_cv": 0.01,
        }
    return events


def build_scenario(name: str, seed: int = 42) -> list[dict]:
    spec = active_spec()
    _, test_path = data_paths()
    test = load_canonical(test_path, spec)
    fraud = test[test["Class"] == 1]
    legit = test[test["Class"] == 0]
    rng = np.random.default_rng(seed)
    if name == "normal":
        sample = legit.sample(n=220, random_state=seed)
        events = []
        has_user = "user_id" in sample.columns
        has_merchant = "merchant_id" in sample.columns
        for i, (_, row) in enumerate(sample.iterrows()):
            events.append(_row_event(
                row,
                10_000,
                None if has_user else f"user-{i}",
                None if has_merchant else f"m-{int(i % 40)}",
            ))
        return _human(_poisson(events, 10_000, 0.9, rng), rng)
    if name == "flash_sale":
        sample = legit.sample(n=360, random_state=seed)
        events = []
        has_user = "user_id" in sample.columns
        for i, (_, row) in enumerate(sample.iterrows()):
            events.append(_row_event(row, 50_000, None if has_user else f"buyer-{i}", "m-electronics-flash"))
        return _human(_poisson(events, 50_000, 0.07, rng), rng)
    if name == "bot_attack":
        if not spec.pca and "user_id" in fraud.columns and len(fraud) >= 8:
            return _replay_fraud(fraud.sort_values("Time"), 80_000)
        return _bot(_attack(fraud, rng, 80_000, seed), rng)
    if name == "noisy_ring":
        return _bot(_attack(fraud, rng, 100_000, seed, noise=0.08), rng)
    if name == "low_and_slow":
        return _bot(_attack(fraud, rng, 110_000, seed, spacing=6.0), rng)
    if name == "card_testing":
        return _bot(_attack(fraud, rng, 120_000, seed, n=48, spacing=0.35, n_users=48, n_merchants=24, amount_mode="tiny", probe_n=0), rng)
    if name == "account_takeover":
        return _bot(_attack(fraud, rng, 130_000, seed, n=18, spacing=0.4, n_users=1, n_merchants=18, amount_mode="drain", probe_n=0), rng)
    if name == "split_ring":
        return _bot(_attack(fraud, rng, 140_000, seed, n=36, two_bases=True, n_merchants=6), rng)
    if name == "mule_fan_in":
        return _bot(_attack(fraud, rng, 150_000, seed, n=40, n_users=40, n_merchants=2, amount_mode="drain", probe_n=0), rng)
    if name == "distributed_drain":
        return _bot(
            _attack(fraud, rng, 160_000, seed, n=40, spacing=0.22, n_users=40, n_merchants=30, amount_mode="round", probe_n=0),
            rng,
        )
    if name in SALE_EVENTS:
        return _sale(name, legit, fraud, rng, seed)
    if name == "mixed":
        sale = legit.sample(n=280, random_state=seed)
        events = []
        has_user = "user_id" in sale.columns
        for i, (_, row) in enumerate(sale.iterrows()):
            events.append(_row_event(row, 90_000, None if has_user else f"buyer-{i}", "m-electronics-flash"))
        events = _human(_poisson(events, 90_000, 0.08, rng), rng)
        attack = _bot(_attack(fraud, rng, 90_000 + 20.0, seed), rng)
        events.extend(attack)
        events.sort(key=lambda item: item["time"])
        return events
    if name == "replay_real":
        return _replay_real(test, limit=1500, span=600.0)
    if name == "real_peak":
        return _real_peak(test, limit=3000)
    raise ValueError(f"unknown scenario {name}")


def _stamp(frame: pd.DataFrame, start: float, times) -> list:
    has_user = "user_id" in frame.columns
    has_merchant = "merchant_id" in frame.columns
    events = []
    for i, ((_, row), when) in enumerate(zip(frame.iterrows(), times)):
        event = _row_event(row, when, None if has_user else f"row-{i}", None if has_merchant else f"m-{i % 40}")
        event["phase"] = "live"
        events.append(event)
    return events


def _replay_real(test: pd.DataFrame, limit: int, span: float) -> list:
    """The active test file in time order, first rows first, with the clock compressed into span seconds."""
    rows = test.sort_values("Time", kind="mergesort").head(limit)
    if rows.empty:
        return []
    raw = rows["Time"].to_numpy(dtype=float)
    width = max(float(raw[-1] - raw[0]), 1e-6)
    factor = min(1.0, span / width)
    return _stamp(rows, 1_000.0, 1_000.0 + (raw - raw[0]) * factor)


def _real_peak(test: pd.DataFrame, limit: int) -> list:
    """The busiest hour in the test file, replayed at its real pace."""
    if test.empty:
        return []
    hours = (test["Time"] // 3600.0).astype(int)
    busiest = int(hours.value_counts().idxmax())
    rows = test[hours == busiest].sort_values("Time", kind="mergesort").head(limit)
    raw = rows["Time"].to_numpy(dtype=float)
    return _stamp(rows, 1_000.0, 1_000.0 + (raw - raw[0]))


def _legit_batch(legit: pd.DataFrame, n: int, seed: int, start: float, mean_gap: float, rng, merchant_fn, user_fn) -> list:
    sample = legit.sample(n=min(n, len(legit)), random_state=seed, replace=len(legit) < n)
    has_user = "user_id" in sample.columns
    events = []
    for i, (_, row) in enumerate(sample.iterrows()):
        merchant_id, category = merchant_fn(i)
        event = _row_event(row, start, None if has_user else user_fn(i), merchant_id)
        if category and not event.get("category"):
            event["category"] = category
        events.append(event)
    return _poisson(events, start, mean_gap, rng)


def _tag(events: list, phase: str) -> list:
    for event in events:
        event["phase"] = phase
    return events


def _sale(name: str, legit: pd.DataFrame, fraud: pd.DataFrame, rng, seed: int) -> list:
    """Warm-up, the midnight ramp into a few flagships, attacks hidden inside the peak, then cool-down."""
    sale = SALE_EVENTS[name]
    flagships = list(sale["merchants"].items())
    weights = np.asarray(sale["weights"], dtype=float)
    weights = weights / weights.sum()
    prices = sale["prices"]
    start = 200_000.0 if name == "big_billion_day" else 300_000.0

    warm = _legit_batch(
        legit, 80, seed, start, 0.9, rng,
        lambda i: (f"m-{i % 40}", "grocery"),
        lambda i: f"shopper-{i}",
    )
    warm = _tag(_human(warm, rng, prefix=f"{name}-warm"), "warmup")

    open_at = warm[-1]["time"] + 1.0
    picks = rng.choice(len(flagships), size=600, p=weights)
    peak = _legit_batch(
        legit, 600, seed + 1, open_at, 0.06, rng,
        lambda i: flagships[int(picks[i])],
        lambda i: f"buyer-{name}-{i}",
    )
    for event in peak:
        event["amount"] = float(rng.choice(prices))
    peak = _tag(_human(peak, rng, prefix=f"{name}-peak"), "sale_open")

    attacks = []
    offsets = {"scalper_bots": 6.0, "card_testing": 16.0, "account_takeover": 26.0, "mule_cashout": 40.0, "distributed_drain": 20.0}
    flagship_id, flagship_cat = flagships[0]
    for kind in sale["attacks"]:
        at = open_at + offsets[kind]
        if kind == "scalper_bots":
            ring = _attack(fraud, rng, at, seed + 11, n=36, spacing=0.2, n_users=36, n_merchants=1, amount_mode="drain", probe_n=0)
            sku = float(prices[-1])
            for event in ring:
                event["merchant_id"] = flagship_id
                event["amount"] = sku
            ring = _bot(ring, rng, devices=4, category=flagship_cat, prefix=f"{name}-scalper")
        elif kind == "card_testing":
            ring = _bot(
                _attack(fraud, rng, at, seed + 12, n=48, spacing=0.3, n_users=48, n_merchants=24, amount_mode="tiny", probe_n=0),
                rng,
                prefix=f"{name}-cardtest",
            )
        elif kind == "account_takeover":
            ring = _attack(fraud, rng, at, seed + 13, n=18, spacing=0.4, n_users=1, n_merchants=18, amount_mode="drain", probe_n=0)
            for event in ring:
                event["user_id"] = f"saved-card-{name}"
            ring = _bot(ring, rng, devices=1, category="electronics", prefix=f"{name}-ato")
        elif kind == "mule_cashout":
            ring = _bot(
                _attack(fraud, rng, at, seed + 14, n=40, n_users=40, n_merchants=2, amount_mode="drain", probe_n=0),
                rng,
                prefix=f"{name}-mule",
            )
        else:
            ring = _bot(
                _attack(fraud, rng, at, seed + 15, n=40, spacing=0.22, n_users=40, n_merchants=30, amount_mode="round", probe_n=0),
                rng,
                prefix=f"{name}-drain",
            )
        attacks.extend(_tag(ring, kind))

    tail_at = max(peak[-1]["time"], max(event["time"] for event in attacks)) + 2.0
    cool = _legit_batch(
        legit, 120, seed + 2, tail_at, 0.5, rng,
        lambda i: flagships[i % len(flagships)],
        lambda i: f"late-{name}-{i}",
    )
    for event in cool:
        event["amount"] = float(rng.choice(prices))
    cool = _tag(_human(cool, rng, prefix=f"{name}-cool"), "cooldown")

    events = warm + peak + attacks + cool
    events.sort(key=lambda item: item["time"])
    return events


def _replay_fraud(fraud: pd.DataFrame, start: float, n: int = 40) -> list[dict]:
    """Play real fraud rows, with their own ids, instead of cloning one vector."""
    rows = fraud.head(n)
    events = []
    for i, (_, row) in enumerate(rows.iterrows()):
        events.append(_row_event(row, start + i * 0.3, None, None))
    return events


def _attack(
    fraud: pd.DataFrame,
    rng: np.random.Generator,
    start: float,
    seed: int,
    noise: float = 0.012,
    n: int = 40,
    spacing: float = 0.22,
    n_users: int = 28,
    n_merchants: int = 5,
    probe_n: int = 12,
    amount_mode: str = "probe_drain",
    two_bases: bool = False,
) -> list[dict]:
    bases = fraud.sample(n=2 if two_bases and len(fraud) > 1 else 1, random_state=seed)
    if len(bases) == 1 and two_bases:
        bases = pd.concat([bases, bases], ignore_index=True)
    # Split rings should land in different cohorts: pick a second fraud row far away.
    vector_cols = [col for col in V_COLS if col in fraud.columns]
    if not vector_cols:
        vector_cols = [col for col in fraud.columns if col not in {"Time", "Amount", "Class", "user_id", "merchant_id", "device"} and pd.api.types.is_numeric_dtype(fraud[col])]
    if two_bases and len(fraud) > 2 and vector_cols:
        first = bases.iloc[0]
        dist = np.linalg.norm(fraud[vector_cols].to_numpy(dtype=float) - first[vector_cols].to_numpy(dtype=float), axis=1)
        bases = pd.concat([first.to_frame().T, fraud.iloc[[int(np.argmax(dist))]]], ignore_index=True)
    events = []
    for i in range(n):
        base = bases.iloc[0 if not two_bases or i < n // 2 else 1]
        noisy = base.copy()
        for col in vector_cols:
            noisy[col] = float(base[col]) + float(rng.normal(0, noise))
        if amount_mode == "round":
            amount = float(rng.choice([1000, 5000, 10000, 49999]))
        elif amount_mode == "tiny":
            amount = float(rng.uniform(0.2, 1.8))
        elif amount_mode == "drain":
            amount = float(rng.uniform(80, 360))
        else:
            amount = float(rng.uniform(0.3, 1.4)) if i < probe_n else float(rng.uniform(120, 420))
        user = "victim-1" if n_users == 1 else f"mule-{i % max(n_users, 1)}"
        events.append(
            _row_event(
                noisy,
                start + i * spacing,
                user,
                f"cashout-{i % max(n_merchants, 1)}",
                amount=amount,
            )
        )
    return events
