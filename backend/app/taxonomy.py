"""What this payment stream can and cannot see. Status is live, partial, or needs data.

Nothing in the needs-data list is simulated.
"""

from __future__ import annotations

from collections import Counter

ITEMS = (
    {"group": "Anomaly types", "name": "Point anomalies", "status": "live", "basis": "The champion score on one payment."},
    {"group": "Anomaly types", "name": "Contextual anomalies", "status": "live", "basis": "Amount, hour, device, and place against that customer's own history."},
    {"group": "Anomaly types", "name": "Collective anomalies", "status": "live", "basis": "Micro-cluster tightness and the regime detector."},
    {"group": "Anomaly types", "name": "Multivariate anomalies", "status": "live", "basis": "The champion uses the full feature vector, not one column."},
    {"group": "Anomaly types", "name": "Correlational anomalies", "status": "partial", "basis": "Segment distance and fan-in. There is no separate correlation model."},
    {"group": "Anomaly types", "name": "Inlier anomalies", "status": "partial", "basis": "Fraud that sits inside the normal cloud is the hard case. The model does not claim to catch it."},
    {"group": "Anomaly types", "name": "Level shifts", "status": "live", "basis": "Score PSI against the training distribution."},
    {"group": "Anomaly types", "name": "Trend anomalies", "status": "live", "basis": "History judging uses the rise in risk across a customer's payments."},
    {"group": "Anomaly types", "name": "Volatility anomalies", "status": "partial", "basis": "Volume z-score. There is no returns-volatility series."},
    {"group": "Anomaly types", "name": "Seasonal anomalies", "status": "partial", "basis": "Unusual hour for a known customer. The file is two days, so there is no season."},
    {"group": "Anomaly types", "name": "Subsequence anomalies", "status": "live", "basis": "Probe-then-drain sequence and the boundary probe."},
    {"group": "Anomaly types", "name": "Structural anomalies", "status": "partial", "basis": "Regime change from NORMAL to SURGE or ATTACK."},
    {"group": "Anomaly types", "name": "Topological anomalies", "status": "partial", "basis": "Fan-in and fan-out on HMAC tokens. There is no graph embedding."},
    {"group": "Anomaly types", "name": "Clique formations", "status": "live", "basis": "Look-alike micro-clusters inside one segment."},
    {"group": "Anomaly types", "name": "Bridge anomalies", "status": "live", "basis": "Wormhole: one device in two far places within a minute, plus fan-in and fan-out."},
    {"group": "Anomaly types", "name": "Micro-cluster anomalies", "status": "live", "basis": "kNN tightness against that segment's own spread."},
    {"group": "Anomaly types", "name": "Protocol anomalies", "status": "needs data", "basis": "Needs packet or API protocol logs. A payment row has none."},
    {"group": "Anomaly types", "name": "Payload anomalies", "status": "live", "basis": "Unexpected syntax in customer, merchant, region, device, or category text. The text is not executed."},
    {"group": "Anomaly types", "name": "Syntactic anomalies", "status": "live", "basis": "The same input-syntax scan. It steps up and does not block."},
    {"group": "Anomaly types", "name": "Semantic anomalies", "status": "needs data", "basis": "Needs the meaning of free text. These columns are PCA components or short ids."},
    {"group": "Anomaly types", "name": "Concept drift", "status": "partial", "basis": "PSI warns. It does not swap the champion or flip the kill switch."},
    {"group": "Anomaly types", "name": "Covariate shift", "status": "live", "basis": "The same PSI on the score distribution versus training."},
    {"group": "Anomaly types", "name": "Distributional anomalies", "status": "live", "basis": "Isolation forest is a feature, not the decider. The champion still blocks."},
    {"group": "Anomaly types", "name": "Novelty detection", "status": "partial", "basis": "A new device, region, or merchant for a known customer is a step-up."},
    {"group": "Anomaly types", "name": "Out-of-distribution anomalies", "status": "partial", "basis": "Distance to the nearest segment center. It is a feature, not a second decision."},
    {"group": "Entry", "name": "Spearphishing and business email compromise", "status": "needs data", "basis": "Needs mail logs."},
    {"group": "Entry", "name": "Watering-hole sites", "status": "needs data", "basis": "Needs browser or proxy logs."},
    {"group": "Entry", "name": "Public-application exploits", "status": "needs data", "basis": "Needs vulnerability and request logs."},
    {"group": "Entry", "name": "Bought valid accounts", "status": "partial", "basis": "A new device or place on a known customer steps up. There is no dark-web feed."},
    {"group": "Entry", "name": "Rogue hardware on the branch LAN", "status": "needs data", "basis": "Needs network-access logs."},
    {"group": "Identity", "name": "Credential stuffing", "status": "needs data", "basis": "Needs failed-login attempts. The stream is payments only."},
    {"group": "Identity", "name": "Adversary in the middle", "status": "needs data", "basis": "Needs session cookies. They are not on a payment row."},
    {"group": "Identity", "name": "SIM swap", "status": "needs data", "basis": "Needs telecom events."},
    {"group": "Identity", "name": "Synthetic identity", "status": "needs data", "basis": "Needs application and identity fields. This file has neither."},
    {"group": "Identity", "name": "Mobile overlay", "status": "needs data", "basis": "Needs device telemetry from the banking app."},
    {"group": "Persistence", "name": "Living off the land", "status": "needs data", "basis": "Needs endpoint process logs."},
    {"group": "Persistence", "name": "Scheduled task abuse", "status": "needs data", "basis": "Needs host scheduler logs."},
    {"group": "Persistence", "name": "Packed malware", "status": "needs data", "basis": "Needs file and endpoint telemetry."},
    {"group": "Persistence", "name": "Log deletion", "status": "partial", "basis": "The audit chain shows a tampered record. It cannot see a deleted host log."},
    {"group": "Infrastructure", "name": "SQL injection", "status": "live", "basis": "The syntax scan steps up a payment whose text looks like a query. It does not run the query."},
    {"group": "Infrastructure", "name": "Cross-site scripting", "status": "live", "basis": "The same scan. The matched text is not stored or echoed."},
    {"group": "Infrastructure", "name": "Broken object authorization", "status": "needs data", "basis": "Needs API object ids. Payments do not carry them."},
    {"group": "Infrastructure", "name": "Denial of service", "status": "partial", "basis": "A payment-volume spike is visible. Packet floods are not."},
    {"group": "Infrastructure", "name": "DNS spoofing", "status": "needs data", "basis": "Needs DNS logs."},
    {"group": "Fraud", "name": "ACH and wire rerouting", "status": "needs data", "basis": "Needs the beneficiary account. This file has an amount, not a destination."},
    {"group": "Fraud", "name": "Man in the browser", "status": "needs data", "basis": "Needs the browser session. A changed amount can still look odd to the champion."},
    {"group": "Fraud", "name": "Smurfing", "status": "live", "basis": "Tiny-amount bursts and the distributed-drain scenario. Round amounts feed the surge verdict."},
    {"group": "Fraud", "name": "Cryptojacking", "status": "needs data", "basis": "Needs host CPU metrics."},
    {"group": "Insider", "name": "Privilege escalation", "status": "needs data", "basis": "Needs employee access logs."},
    {"group": "Insider", "name": "Data exfiltration", "status": "needs data", "basis": "Needs database audit logs."},
    {"group": "Insider", "name": "Open cloud bucket", "status": "needs data", "basis": "Needs cloud configuration logs."},
    {"group": "Insider", "name": "Vendor pivot", "status": "needs data", "basis": "Needs identity from the vendor network."},
    {"group": "Physical", "name": "ATM jackpotting", "status": "needs data", "basis": "Needs dispenser command logs."},
    {"group": "Physical", "name": "Skimming and shimming", "status": "needs data", "basis": "Needs terminal hardware events."},
    {"group": "Physical", "name": "Card or cash trapping", "status": "needs data", "basis": "Needs ATM sensor logs."},
    {"group": "Impact", "name": "Ransomware", "status": "needs data", "basis": "Needs endpoint and backup logs."},
    {"group": "Impact", "name": "Wiper malware", "status": "needs data", "basis": "Needs host integrity logs."},
    {"group": "Impact", "name": "Service stop", "status": "partial", "basis": "The kill switch is a manual fallback. It is not an attacker killing a process."},
)


def coverage() -> dict:
    from backend.app.logsignals import loaded_kinds
    from ml.schema import ARTIFACT_DIR

    kinds = loaded_kinds()
    has_base = (ARTIFACT_DIR / "baselines.json").exists()
    upgrades = {
        "Novelty detection": (
            "live",
            "Already live: a known customer's new device, region, or merchant category steps the payment up.",
        ),
    }
    if has_base:
        upgrades.update({
            "Correlational anomalies": (
                "live",
                "Largest change in the V1–V8 and Amount correlation versus training, over the last 400 scores. A monitor, not a decision.",
            ),
            "Volatility anomalies": (
                "live",
                "A segment whose amount spread in the last minute is over three times the training median. It can mark the regime suspicious. It does not decide one payment.",
            ),
            "Topological anomalies": (
                "live",
                "A connected group of 12 or more, at most two merchants, and the same people paying again. A note, not a step-up.",
            ),
            "Out-of-distribution anomalies": (
                "live",
                "Distance above that segment's training 99.9th percentile steps the payment up. It does not block.",
            ),
        })
    if "login" in kinds:
        upgrades["Credential stuffing"] = (
            "live",
            "A login log is loaded. Accounts with 10 or more failed logins in 10 minutes step up on the next payment.",
        )
    if "atm" in kinds:
        upgrades["ATM jackpotting"] = (
            "live",
            "An ATM log is loaded. A dispense with no card event in the previous 30 seconds is an incident. No payment changes.",
        )
    files = {
        "Credential stuffing": "Import a login log with user_id, time, success",
        "ATM jackpotting": "Import an ATM log with terminal_id, event, time",
    }
    items = []
    for item in ITEMS:
        row = dict(item)
        if item["name"] in upgrades:
            row["status"], row["basis"] = upgrades[item["name"]]
        if item["name"] in files and row["status"] == "needs data":
            row["file"] = files[item["name"]]
        items.append(row)
    counts = Counter(item["status"] for item in items)
    return {
        "items": items,
        "counts": {"live": counts["live"], "partial": counts["partial"], "needs data": counts["needs data"]},
        "note": "Needs data is named and not simulated. A step-up never blocks. Only the champion blocks.",
    }
