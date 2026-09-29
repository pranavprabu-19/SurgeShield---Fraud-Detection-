"""Entity signals on HMAC tokens. Raw user and merchant ids never enter this module."""

from __future__ import annotations

import math
from collections import defaultdict


def _entropy(labels: list) -> float:
    if len(labels) < 2:
        return 0.0
    counts: dict = defaultdict(int)
    for label in labels:
        counts[label] += 1
    total = float(len(labels))
    h = 0.0
    for count in counts.values():
        p = count / total
        h -= p * math.log(p + 1e-12)
    return float(h / math.log(len(counts))) if len(counts) > 1 else 0.0


def analyze_graph(records: list, now: float, user: str = "", merchant: str = "") -> dict:
    window300 = [row for row in records if now - 300.0 <= row["time"] <= now]
    window60 = [row for row in records if now - 60.0 <= row["time"] <= now]
    users_for_merchant: dict = defaultdict(set)
    merchants_for_user: dict = defaultdict(set)
    first_seen: dict = {}
    for row in window300:
        token_u = row.get("user") or ""
        token_m = row.get("merchant") or ""
        if token_u and token_m:
            users_for_merchant[token_m].add(token_u)
        if token_u and token_u not in first_seen:
            first_seen[token_u] = row["time"]
    for row in window60:
        token_u = row.get("user") or ""
        token_m = row.get("merchant") or ""
        if token_u and token_m:
            merchants_for_user[token_u].add(token_m)

    fan_in = max((len(v) for v in users_for_merchant.values()), default=0)
    fan_out = len(merchants_for_user.get(user, ())) if user else 0
    this_fan_in = len(users_for_merchant.get(merchant, ())) if merchant else 0

    tiny = [row for row in window60 if row.get("amount", 99) < 2.0]
    tiny_merchants = {row.get("merchant") for row in tiny if row.get("merchant")}
    card_test = 0.0
    if len(window60) >= 12 and len(tiny) / max(len(window60), 1) >= 0.7 and len(tiny_merchants) >= 8:
        card_test = min(1.0, len(tiny_merchants) / 16.0)

    top_merchant = merchant
    top_count = this_fan_in
    if users_for_merchant:
        top_merchant, users = max(users_for_merchant.items(), key=lambda item: len(item[1]))
        top_count = len(users)
    new_on_top = 0
    if top_merchant:
        for row in window300:
            if row.get("merchant") == top_merchant and now - first_seen.get(row.get("user"), now) <= 300:
                new_on_top += 1
    mule_share = new_on_top / max(len(window300), 1)

    return {
        "fan_in": int(fan_in),
        "fan_out": int(fan_out),
        "merchant_fan_in": int(this_fan_in or top_count),
        "user_velocity_60": int(fan_out),
        "mule_share": round(float(mule_share), 4),
        "card_test": round(float(card_test), 4),
        "user_entropy": round(_entropy([row.get("user") for row in window60 if row.get("user")]), 4),
        "merchant_entropy": round(_entropy([row.get("merchant") for row in window60 if row.get("merchant")]), 4),
        "segment_entropy": round(_entropy([row.get("segment") for row in window60]), 4),
        "diversity": round(_entropy([row.get("segment") for row in window60]), 4),
    }
