"""Detect a tight, probe-then-drain micro-cluster, even inside a busy surge."""

from __future__ import annotations

from typing import Optional

import numpy as np

from ml.schema import N_SEGMENTS


def _median(values: np.ndarray, axis: int = 0):
    # np.median's generic reduction overhead dominates on these tiny arrays.
    ordered = np.sort(values, axis=axis)
    n = ordered.shape[axis]
    low = np.take(ordered, (n - 1) // 2, axis=axis)
    high = np.take(ordered, n // 2, axis=axis)
    return (low + high) / 2.0


def _knn_tightness(vectors: np.ndarray, spread: float) -> float:
    """High when neighbours sit closer together than this segment usually does."""
    if len(vectors) > 24:
        vectors = vectors[-24:]
    n = len(vectors)
    k = min(8, n - 1)
    if k < 1:
        return 0.0
    distances = np.linalg.norm(vectors[:, None, :] - vectors[None, :, :], axis=2)
    np.fill_diagonal(distances, np.inf)
    nearest = np.partition(distances, k - 1, axis=1)[:, :k]
    median = float(_median(nearest.mean(axis=1)))
    scale = max(float(spread), 0.2)
    return float(np.clip(1.0 - median / (1.7 * scale), 0.0, 1.0))


def _cusum_ramp(amounts: np.ndarray) -> float:
    """A gradual climb in amount, not only the hard small-then-large pattern."""
    if len(amounts) < 6:
        return 0.0
    values = np.log1p(amounts)
    baseline = float(_median(values[: max(1, len(values) // 4)]))
    total = 0.0
    peak = 0.0
    for value in values:
        total = max(0.0, total + (value - baseline - 0.15))
        peak = max(peak, total)
    return float(np.clip(peak / 6.0, 0.0, 1.0))


def _probe_drain(amounts: np.ndarray) -> float:
    if len(amounts) < 6:
        return 0.0
    cut = max(1, len(amounts) // 3)
    early = float(_median(amounts[:cut]))
    late = float(_median(amounts[-cut:]))
    classic = 0.0
    if early <= 8.0 and late >= 40.0:
        classic = float(np.clip((late - early) / (late + 1.0), 0.0, 1.0))
    return float(max(classic, _cusum_ramp(amounts)))


def _micro_cluster(group: list, spread: float = 0.85) -> dict:
    vectors = np.asarray([r["v"] for r in group], dtype=float)
    median = _median(vectors, axis=0)
    dist = np.linalg.norm(vectors - median, axis=1)
    radius = max(0.45, 2.2 * float(spread))
    close_idx = np.where(dist <= radius)[0]
    close = [group[i] for i in close_idx]
    if len(close) >= 12:
        close_vectors = vectors[close_idx]
        tight = _knn_tightness(close_vectors, spread)
        amounts = np.asarray([r["amount"] for r in close], dtype=float)
        risks = np.asarray([r.get("risk", 0.0) for r in close], dtype=float)
        count = len(close)
    else:
        tight = _knn_tightness(vectors, spread) if len(group) >= 8 else 0.0
        amounts = np.asarray([r["amount"] for r in group], dtype=float)
        risks = np.asarray([r.get("risk", 0.0) for r in group], dtype=float)
        count = len(group) if tight >= 0.62 else 0
    return {
        "count": int(count),
        "tightness": float(tight),
        "probe": _probe_drain(amounts) if count >= 6 else 0.0,
        "mean_risk": float(risks.mean()) if len(risks) else 0.0,
    }


def _worst(window: list, spreads: list) -> tuple:
    count = max(len(window), 1)
    segments = []
    worst = None
    groups: dict = {}
    for row in window:
        groups.setdefault(row["segment"], []).append(row)
    for seg_id in range(N_SEGMENTS):
        group = groups.get(seg_id, [])
        if len(group) < 6:
            continue
        spread = spreads[seg_id] if seg_id < len(spreads) else 0.85
        micro = _micro_cluster(group, spread)
        entry = {"id": seg_id, "share": len(group) / count, **micro}
        segments.append(entry)
        strength = micro["tightness"] * (0.6 + 0.4 * micro["probe"]) * min(1.0, micro["count"] / 15.0)
        if worst is None or strength > worst[0]:
            worst = (strength, entry)
    return segments, worst


def analyze(records: list, now: float, cnt60_mean: float, cnt60_std: float, spreads=None, graph: Optional[dict] = None, count_60: Optional[int] = None, surge: Optional[dict] = None, profile: Optional[dict] = None) -> dict:
    window = [r for r in records if now - 60.0 <= r["time"] <= now]
    slow = [r for r in records if now - 300.0 <= r["time"] <= now]
    count = int(count_60) if count_60 is not None else len(window)
    std = cnt60_std if cnt60_std > 1 else 1.0
    vol_z = (count - cnt60_mean) / std
    spreads = list(spreads) if spreads is not None else [0.85] * N_SEGMENTS
    graph = graph or {}

    segments, worst = _worst(window, spreads)
    # A slow ring is tight but too thin to fill a 60-second window. Skip this on ordinary traffic.
    if worst and worst[1]["tightness"] >= 0.5 and worst[1]["count"] < 12:
        slow_segments, slow_worst = _worst(slow[-80:], spreads)
        if slow_worst and slow_worst[0] > worst[0]:
            segments, worst = slow_segments, slow_worst

    attacked = None
    coord = tight = dominance = probe = 0.0
    if worst:
        coord, top = worst
        tight = top["tightness"]
        dominance = top["share"]
        probe = top["probe"]
        geometric = top["count"] >= 12 and top["tightness"] >= 0.55 and (
            top["probe"] >= 0.4 or top["mean_risk"] >= 0.2 or top["tightness"] >= 0.75
        )
        if geometric:
            attacked = top["id"]

    fan_out = float(graph.get("fan_out") or 0)
    card_test = float(graph.get("card_test") or 0)
    fan_in_term = tight * min(1.0, float(graph.get("fan_in") or 0) / 12.0)
    fan_out_term = min(1.0, fan_out / 12.0)
    surge = surge or {}
    timing_cv = surge.get("timing_cv")
    device_div = surge.get("device_diversity")
    cadence = 0.0
    if timing_cv is not None:
        regular = float(np.clip(1.0 - float(timing_cv) / 1.2, 0.0, 1.0))
        device_term = 1.0 if device_div is None else float(np.clip(1.0 - float(device_div), 0.0, 1.0))
        cadence = regular * device_term
    profile = profile or {}
    profile_term = 0.1 if (
        profile.get("new_user") and float(profile.get("merchant_familiarity") or 0) < 0.25 and tight >= 0.55
    ) else 0.0
    evidence = float(np.clip(
        0.34 * tight + 0.21 * max(fan_in_term, fan_out_term) + 0.17 * probe + 0.13 * card_test + 0.15 * cadence + profile_term,
        0.0,
        1.0,
    ))
    mean_risk = float(np.mean([r.get("risk", 0.0) for r in window])) if window else 0.0
    if attacked is None and worst and (
        (evidence >= 0.62 and worst[1]["count"] >= 8)
        or card_test >= 0.7
        or (fan_out >= 12 and mean_risk >= 0.15)
    ):
        attacked = worst[1]["id"]

    diversity = float(graph.get("diversity") if graph.get("diversity") is not None else 1.0)
    genuine = surge.get("genuine_score")
    low_genuine = genuine is not None and float(genuine) < 0.5
    suspicious = bool(
        vol_z >= 2.5
        and attacked is None
        and ((diversity < 0.35 and tight >= 0.45) or low_genuine)
    )
    return {
        "count_60": count,
        "vol_z": float(vol_z),
        "coordination": float(np.clip(max(coord, evidence), 0.0, 1.0)),
        "tightness": float(tight),
        "dominance": float(dominance),
        "probe": float(probe),
        "attacked_segment": attacked,
        "mean_risk": mean_risk,
        "segments": segments,
        "evidence": round(evidence, 4),
        "diversity": round(diversity, 4),
        "suspicious": suspicious,
        "fan_in": int(graph.get("fan_in") or 0),
        "fan_out": int(fan_out),
        "card_test": round(card_test, 4),
        "detectors": {
            "geometry": round(float(tight), 3),
            "fan_in": round(float(fan_in_term), 3),
            "fan_out": round(float(fan_out_term), 3),
            "sequence": round(float(probe), 3),
            "card_test": round(card_test, 3),
            "cadence": round(float(cadence), 3),
            "profile": round(float(profile_term), 3),
        },
        "surge": surge,
        "profile": profile,
    }
