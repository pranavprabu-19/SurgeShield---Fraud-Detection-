"""Known sale events. They label expected merchants. They never loosen attack rules."""

from __future__ import annotations

SALE_EVENTS = {
    "big_billion_day": {
        "name": "Big Billion Days",
        "merchants": {
            "fk-mobiles": "mobiles",
            "fk-electronics": "electronics",
            "fk-fashion": "fashion",
            "fk-appliances": "appliances",
        },
        "weights": [0.4, 0.3, 0.2, 0.1],
        "prices": [99, 149, 199, 299, 499, 799, 1299],
        "attacks": ["scalper_bots", "card_testing", "account_takeover", "mule_cashout"],
        "phases": [
            {"id": "warmup", "label": "Warm-up"},
            {"id": "sale_open", "label": "Midnight open"},
            {"id": "scalper_bots", "label": "Scalper bots"},
            {"id": "card_testing", "label": "Card testing"},
            {"id": "account_takeover", "label": "Account takeover"},
            {"id": "mule_cashout", "label": "Mule cash-out"},
            {"id": "cooldown", "label": "Cool-down"},
        ],
    },
    "great_indian_festival": {
        "name": "Great Indian Festival",
        "merchants": {
            "amz-mobiles": "mobiles",
            "amz-home": "home",
            "amz-fashion": "fashion",
            "amz-electronics": "electronics",
        },
        "weights": [0.35, 0.25, 0.25, 0.15],
        "prices": [149, 249, 399, 599, 899, 1199, 1499],
        "attacks": ["scalper_bots", "account_takeover", "distributed_drain"],
        "phases": [
            {"id": "warmup", "label": "Warm-up"},
            {"id": "sale_open", "label": "Lightning deals open"},
            {"id": "scalper_bots", "label": "Scalper bots"},
            {"id": "account_takeover", "label": "Account takeover"},
            {"id": "distributed_drain", "label": "Distributed drain"},
            {"id": "cooldown", "label": "Cool-down"},
        ],
    },
}


def public_events(tokenize_fn=None) -> list:
    out = []
    for key, event in SALE_EVENTS.items():
        merchants = []
        for merchant, category in event["merchants"].items():
            merchants.append({
                "id": merchant,
                "category": category,
                "token": tokenize_fn(merchant) if tokenize_fn else None,
            })
        out.append({
            "id": key,
            "name": event["name"],
            "merchants": merchants,
            "attacks": list(event["attacks"]),
            "phases": list(event["phases"]),
        })
    return out
