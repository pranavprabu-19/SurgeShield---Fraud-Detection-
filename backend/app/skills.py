"""Anomaly skills the payment stream can actually see.

The champion model is not retrained on these. A skill either reuses a live
detector or raises a step-up. It never blocks by itself. Skills that need
network, employee, or database telemetry stay unavailable: those fields are
not invented.
"""

from __future__ import annotations

import re

# Defensive scan of free-text fields. The matched text is never stored or returned.
_SYNTAX = re.compile(r"(?i)(union\s+select|<\s*script|--|/\*|\bdrop\s+table\b)")
_TEXT_FIELDS = ("user_id", "merchant_id", "region", "device", "category")

CATALOG = (
    {
        "id": "volume_shape",
        "family": "Stream shape",
        "name": "Volume shape, not raw volume",
        "status": "live",
        "sees": "Regime from the 10s, 60s, and 5-minute rings: volume z-score, score PSI, and micro-cluster density.",
        "action": "SURGE keeps the sale open. ATTACK tightens thresholds only on the attacked segment.",
    },
    {
        "id": "micro_cluster",
        "family": "Stream shape",
        "name": "Look-alike micro-clusters",
        "status": "live",
        "sees": "kNN tightness inside a behavioral segment, including a probe-then-drain amount ramp.",
        "action": "Feeds the regime. The champion score still decides the block.",
    },
    {
        "id": "payment_spike",
        "family": "Network and infrastructure",
        "name": "Payment-volume spike",
        "status": "live",
        "sees": "How many payments arrived in the last minute versus this file's normal minute.",
        "action": "A diverse spike becomes SURGE. This is not a packet-flood detector: the stream has no server requests, only payments.",
    },
    {
        "id": "outbound_beacon",
        "family": "Network and infrastructure",
        "name": "Unusual outbound traffic",
        "status": "unavailable",
        "sees": "Needs host and network logs. A payment row has no destination IP.",
        "action": "Not scored. Nothing is simulated in its place.",
    },
    {
        "id": "hardware_command",
        "family": "Network and infrastructure",
        "name": "Hardware command anomaly",
        "status": "unavailable",
        "sees": "Needs device-command logs from cash machines or branch hardware.",
        "action": "Not scored.",
    },
    {
        "id": "login_context",
        "family": "Behavior and identity",
        "name": "Unusual place, device, or hour",
        "status": "live",
        "sees": "A known customer's first region, first device, unusual hour, or travel faster than 900 km/h.",
        "action": "Step-up. This is the payment's location, not a separate login event.",
    },
    {
        "id": "insider_access",
        "family": "Behavior and identity",
        "name": "Insider access",
        "status": "unavailable",
        "sees": "Needs employee access logs. Customers and merchants are the only identities here.",
        "action": "Not scored.",
    },
    {
        "id": "auth_flood",
        "family": "Behavior and identity",
        "name": "Failed-login flood",
        "status": "unavailable",
        "sees": "Needs authentication attempts. The stream only contains payments that were submitted.",
        "action": "Not scored.",
    },
    {
        "id": "amount_spike",
        "family": "Transactions",
        "name": "Ticket far above this customer",
        "status": "live",
        "sees": "Amount at least 10 times the customer's own average, after 3 or more payments.",
        "action": "Step-up only. A large ticket does not block.",
    },
    {
        "id": "velocity_burst",
        "family": "Transactions",
        "name": "Rapid payments from one customer",
        "status": "live",
        "sees": "Eight or more payments from one token in 60 seconds, plus the existing tiny-amount burst detector.",
        "action": "Step-up. Card testing still latches ATTACK through the champion and the card-test detector.",
    },
    {
        "id": "wormhole",
        "family": "Transactions",
        "name": "One device in two far places",
        "status": "live",
        "sees": "The same device token pays from two points 300 km apart within 60 seconds, under different accounts.",
        "action": "Step-up only. On the credit-card file the location is simulated. It is real only when the row carries a device and coordinates.",
    },
    {
        "id": "model_probe",
        "family": "Transactions",
        "name": "Amounts stepping toward the block line",
        "status": "live",
        "sees": "Five or more payments in 10 minutes, each larger than the last, all scored in the band just under the block cut.",
        "action": "Step-up only. It never blocks, and it does not move the champion score.",
    },
    {
        "id": "ood",
        "family": "Transactions",
        "name": "Outside the training distance",
        "status": "partial",
        "sees": "Distance to the payment's segment centre, against the 99.9th percentile from training.",
        "action": "Step-up only, and only when baselines.json is present. It never blocks.",
    },
    {
        "id": "topology",
        "family": "Transactions",
        "name": "Repeat payers into one or two merchants",
        "status": "partial",
        "sees": "The connected group of customers, merchants, and devices in the last 5 minutes.",
        "action": "A note when that group has 12 or more nodes, at most two merchants, and the same people pay again. Not a step-up, so a one-time flash sale is left alone.",
    },
    {
        "id": "fund_routing",
        "family": "Transactions",
        "name": "Rapid multi-merchant routing",
        "status": "partial",
        "sees": "One account across many merchants, or many cards into a few merchants.",
        "action": "Feeds the regime. Conversion into other asset types is not visible on this stream.",
    },
    {
        "id": "data_export",
        "family": "Data and application",
        "name": "Bulk data export",
        "status": "unavailable",
        "sees": "Needs database audit logs. Payment features are not a copy of the customer file.",
        "action": "Not scored.",
    },
    {
        "id": "input_syntax",
        "family": "Data and application",
        "name": "Unexpected syntax in a text field",
        "status": "live",
        "sees": "Customer, merchant, region, device, and category text.",
        "action": "Step-up. The text is not executed, stored, or repeated in the reason.",
    },
    {
        "id": "audit_chain",
        "family": "Data and application",
        "name": "Audit trail integrity",
        "status": "live",
        "sees": "The hash-chained decision log. A broken record fails verification.",
        "action": "Detection only. It does not change a payment decision.",
    },
)


def suspicious_text(txn: dict) -> bool:
    for key in _TEXT_FIELDS:
        value = txn.get(key)
        if isinstance(value, str) and _SYNTAX.search(value):
            return True
    return False


def mark(profile: dict, txn: dict) -> None:
    """Set step-up flags from signals already computed. Does not change the score."""
    known = not profile.get("new_user")
    profile["amount_spike"] = bool(known and float(profile.get("amount_ratio") or 1) >= 10)
    profile["suspicious_syntax"] = suspicious_text(txn)


def mark_velocity(profile: dict, velocity: int) -> None:
    profile["velocity_burst"] = int(velocity) >= 8


def step_up(profile: dict) -> bool:
    return bool(profile.get("amount_spike") or profile.get("velocity_burst") or profile.get("suspicious_syntax"))


def notes(profile: dict) -> list:
    out = []
    if profile.get("amount_spike"):
        out.append({
            "feature": "amount_spike",
            "shap": profile.get("amount_ratio") or 0,
            "direction": "up",
            "text": f"amount is {profile.get('amount_ratio')}x this customer's own average",
        })
    if profile.get("velocity_burst"):
        out.append({
            "feature": "velocity_burst",
            "shap": 0.4,
            "direction": "up",
            "text": "this customer sent 8 or more payments in 60 seconds",
        })
    if profile.get("suspicious_syntax"):
        out.append({
            "feature": "input_syntax",
            "shap": 0.4,
            "direction": "up",
            "text": "a text field contained unexpected syntax and was not executed",
        })
    if profile.get("model_probe"):
        out.append({
            "feature": "model_probe",
            "shap": 0.4,
            "direction": "up",
            "text": "amounts rose on purpose through the band just under the block cut",
        })
    return out


def fired_skills(row: dict) -> list:
    """Live skills visible on one already-scored payment. Unavailable skills are omitted."""
    profile = row.get("profile") or {}
    detectors = row.get("detectors") or {}
    fired = []
    if row.get("regime") == "ATTACK":
        fired.append("volume_shape")
    if float(detectors.get("geometry") or 0) >= 0.55 or float(detectors.get("sequence") or 0) >= 0.45:
        fired.append("micro_cluster")
    if float(row.get("vol_z") or 0) >= 2.5 and row.get("regime") != "SURGE":
        fired.append("payment_spike")
    if profile.get("impossible_travel") or profile.get("region_new") or profile.get("device_new") or profile.get("hour_unusual") or profile.get("device_farm"):
        fired.append("login_context")
    if profile.get("amount_spike"):
        fired.append("amount_spike")
    if profile.get("velocity_burst"):
        fired.append("velocity_burst")
    if profile.get("model_probe"):
        fired.append("model_probe")
    if profile.get("wormhole"):
        fired.append("wormhole")
    if profile.get("ood"):
        fired.append("ood")
    if profile.get("topology"):
        fired.append("topology")
    if profile.get("auth_flood"):
        fired.append("auth_flood")
    if float(detectors.get("fan_out") or 0) >= 0.5 or float(detectors.get("fan_in") or 0) >= 0.45:
        fired.append("fund_routing")
    if profile.get("suspicious_syntax"):
        fired.append("input_syntax")
    return fired


def apply_skills(champion: str, skills: list) -> str:
    """The champion blocks. A live skill can only turn a quiet approve into a step-up."""
    if champion == "BLOCK":
        return "BLOCK"
    if champion == "APPROVE" and skills:
        return "STEP_UP"
    return champion


def judge_history(events: list, summary: dict) -> tuple:
    """Approve or block one customer or merchant from their stored history, not one row."""
    payments = int(summary.get("payments") or 0)
    flags = int(summary.get("flags") or 0)
    if payments <= 0:
        return "APPROVE", "no payments on file"
    rate = flags / payments
    risks = [int(event.get("risk_100") or 0) for event in events] or [0]
    half = max(1, len(risks) // 2)
    recent = sum(risks[:half]) / half
    older_rows = risks[half:] or risks
    older = sum(older_rows) / len(older_rows)
    trend = recent - older
    attack = {"device_farm", "impossible_travel", "wormhole", "card_test", "fan_out", "fan_in", "geometry", "sequence", "amount_spike", "velocity_burst", "input_syntax", "model_probe", "ood", "topology", "auth_flood"}
    attack_hits = sum(1 for event in events for feature in (event.get("features") or []) if feature in attack)
    if rate >= 0.85 and payments >= 3:
        return "BLOCK", f"{flags} of {payments} payments were challenged and the pattern did not ease"
    if attack_hits >= 3 and rate >= 0.75:
        return "BLOCK", "attack signals repeat across this history"
    if trend >= 30 and recent >= 70:
        return "BLOCK", "risk rose across the history"
    if rate >= 0.8 and recent >= 50:
        return "BLOCK", f"risk stayed near {round(recent)} on {flags} of {payments} payments"
    if rate <= 0.5 and recent < 60:
        return "APPROVE", "most of the history is quiet and risk is not climbing"
    if recent < 25 and trend <= 0:
        return "APPROVE", "recent payments are quieter than the earlier ones"
    return "APPROVE", "the history does not show a sustained attack"


def coverage() -> dict:
    from backend.app.logsignals import loaded_kinds
    from ml.schema import ARTIFACT_DIR

    kinds = loaded_kinds()
    has_base = (ARTIFACT_DIR / "baselines.json").exists()
    skills = []
    for skill in CATALOG:
        row = dict(skill)
        if has_base and skill["id"] in {"ood", "topology"}:
            row["status"] = "live"
        if "login" in kinds and skill["id"] == "auth_flood":
            row["status"] = "live"
            row["sees"] = "A login log is loaded. Ten or more failures in ten minutes step that account up."
            row["action"] = "Step-up only. It does not block."
        if "network" in kinds and skill["id"] == "outbound_beacon":
            row["status"] = "live"
            row["sees"] = "Sources whose outbound bytes are above the 99.9th percentile of the imported network log."
            row["action"] = "A monitor on Governance. A payment has no source address, so none is changed."
        if "atm" in kinds and skill["id"] == "hardware_command":
            row["status"] = "live"
            row["sees"] = "Terminals with a dispense and no card event within 30 seconds."
            row["action"] = "An incident list. No payment is changed."
        if skill["id"] == "auth_flood" and row["status"] != "live":
            row["file"] = "Import a login log with user_id, time, success"
        if skill["id"] == "outbound_beacon" and row["status"] != "live":
            row["file"] = "Import a network log with src, dst, bytes, time"
        if skill["id"] == "hardware_command" and row["status"] != "live":
            row["file"] = "Import an ATM log with terminal_id, event, time"
        skills.append(row)
    return {
        "champion": "unchanged",
        "rule": "These skills explain or step a payment up. They do not retrain the champion and they do not block alone.",
        "skills": skills,
    }
