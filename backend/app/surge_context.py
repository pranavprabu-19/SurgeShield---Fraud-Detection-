"""Macro shape of a window: concentration, round amounts, cadence, place, device."""

from __future__ import annotations

import math
from collections import Counter


def _gini(counts: list) -> float:
    vals = sorted(c for c in counts if c > 0)
    n = len(vals)
    if n <= 1:
        return 1.0 if n == 1 else 0.0
    if sum(vals) == 0:
        return 0.0
    total = float(sum(vals))
    weighted = sum((i + 1) * value for i, value in enumerate(vals))
    return float((2 * weighted) / (n * total) - (n + 1) / n)


def _entropy(counts: list) -> float | None:
    vals = [c for c in counts if c > 0]
    if len(vals) < 2:
        return 0.0 if vals else None
    total = float(sum(vals))
    h = 0.0
    for count in vals:
        p = count / total
        h -= p * math.log(p + 1e-12)
    return float(h / math.log(len(vals)))


def compose(records: list, ramp: float | None = None) -> dict:
    """None means the field was absent, so it must not count as evidence."""
    if len(records) < 6:
        return {
            "merchant_gini": 0.0,
            "round_ratio": 0.0,
            "timing_cv": None,
            "geo_entropy": None,
            "device_diversity": None,
            "genuine_score": None,
            "verdict": None,
            "ramp": None if ramp is None else round(float(ramp), 3),
        }
    merchants = Counter(row.get("merchant") or "" for row in records if row.get("merchant"))
    gini = _gini(list(merchants.values())) if merchants else 0.0
    amounts = [float(row.get("amount") or 0) for row in records]
    round_hits = sum(1 for amount in amounts if 49000 <= amount <= 50000 or (amount >= 100 and amount % 100 == 0))
    round_ratio = round_hits / len(amounts)

    times = sorted(float(row["time"]) for row in records)
    gaps = [b - a for a, b in zip(times, times[1:]) if b >= a]
    timing_cv = None
    if len(gaps) >= 4:
        mean = sum(gaps) / len(gaps)
        var = sum((gap - mean) ** 2 for gap in gaps) / len(gaps)
        timing_cv = float((var ** 0.5) / mean) if mean > 1e-9 else 0.0

    regions = [row.get("region") for row in records if row.get("region")]
    devices = [row.get("device") for row in records if row.get("device")]
    geo = _entropy(list(Counter(regions).values())) if regions else None
    device_div = (len(set(devices)) / len(records)) if devices else None

    parts = {"gini": (gini, 0.30), "round": (1.0 - round_ratio, 0.25)}
    if timing_cv is not None:
        parts["timing"] = (min(1.0, timing_cv / 1.2), 0.20)
    if device_div is not None:
        parts["device"] = (min(1.0, device_div), 0.15)
    if geo is not None:
        parts["geo"] = (1.0 - geo, 0.10)
    if ramp is not None:
        # Near 1 means traffic is spread across the minute. Near 6 means it all landed in the last 10 seconds.
        parts["ramp"] = (max(0.0, min(1.0, (3.5 - float(ramp)) / 3.5)), 0.08)
    weight = sum(item[1] for item in parts.values()) or 1.0
    genuine = sum(value * w for value, w in parts.values()) / weight
    return {
        "merchant_gini": round(gini, 4),
        "round_ratio": round(round_ratio, 4),
        "timing_cv": None if timing_cv is None else round(timing_cv, 4),
        "geo_entropy": None if geo is None else round(geo, 4),
        "device_diversity": None if device_div is None else round(device_div, 4),
        "genuine_score": round(float(genuine), 4),
        "verdict": "GENUINE" if genuine >= 0.5 else "SUSPICIOUS",
        "ramp": None if ramp is None else round(float(ramp), 3),
    }
