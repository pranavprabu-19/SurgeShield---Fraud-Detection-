"""Replay every attack shape and record what the live engine actually catches.

The baseline file is written once and kept, so later runs can show before/after.
"""

from __future__ import annotations

import json
from pathlib import Path

from backend.app.engine import Engine
from backend.app.scenarios import build_scenario
from ml.schema import ARTIFACT_DIR, ARTIFACT_PATH, STEP_UP_CATCH_RATE

SCENARIOS = [
    "normal",
    "flash_sale",
    "bot_attack",
    "mixed",
    "noisy_ring",
    "low_and_slow",
    "card_testing",
    "account_takeover",
    "split_ring",
    "mule_fan_in",
    "distributed_drain",
    "big_billion_day",
    "great_indian_festival",
]

BASELINE_PATH = ARTIFACT_DIR / "redteam_baseline.json"
OUT_PATH = ARTIFACT_DIR / "redteam.json"


def replay(engine: Engine, name: str, seed: int, shadow: bool = False) -> dict:
    engine.reset()
    engine.scenario = name
    events = build_scenario(name, seed=seed)
    detect_at = None
    detect_seconds = None
    leaked = 0.0
    fraud_n = fraud_caught = 0
    fraud_amt = caught_amt = static_caught = 0.0
    legit_n = legit_blocked = static_legit_blocked = 0
    shadow_caught = 0
    t_block = float(engine.art["thresholds"]["t_block"])
    start = events[0]["time"] if events else 0.0
    for index, event in enumerate(events):
        result = engine.score(event, explain=shadow)
        if detect_at is None and result["regime"] == "ATTACK":
            detect_at = index
            detect_seconds = round(event["time"] - start, 2)
        label = int(event.get("eval_label") or 0)
        amount = float(event["amount"])
        if label == 1:
            fraud_n += 1
            fraud_amt += amount
            caught = result["decision"] == "BLOCK" or result["decision"] == "STEP_UP"
            if result["decision"] == "BLOCK":
                caught_amt += amount
                fraud_caught += 1
            elif result["decision"] == "STEP_UP":
                caught_amt += STEP_UP_CATCH_RATE * amount
                fraud_caught += 1
            if result["static_decision"] == "BLOCK":
                static_caught += amount
            if detect_at is None and result["decision"] != "BLOCK":
                leaked += amount if result["decision"] == "APPROVE" else (1 - STEP_UP_CATCH_RATE) * amount
            if shadow and result.get("shadow_score", 0) >= t_block:
                shadow_caught += 1
        else:
            legit_n += 1
            if result["decision"] == "BLOCK":
                legit_blocked += 1
            if result["static_decision"] == "BLOCK":
                static_legit_blocked += 1
    if detect_at is None and any(engine.regime.state == "ATTACK" for _ in [0]):
        pass
    return {
        "scenario": name,
        "seed": seed,
        "events": len(events),
        "detected": detect_at is not None,
        "detect_event": detect_at,
        "detect_seconds": detect_seconds,
        "rupees_leaked_before_latch": round(leaked, 2),
        "fraud_n": fraud_n,
        "fraud_recall": round(fraud_caught / fraud_n, 4) if fraud_n else None,
        "fraud_rupees_caught": round(caught_amt, 2),
        "static_fraud_rupees": round(static_caught, 2),
        "legit_n": legit_n,
        "false_decline_rate": round(legit_blocked / legit_n, 4) if legit_n else None,
        "static_false_decline_rate": round(static_legit_blocked / legit_n, 4) if legit_n else None,
        "final_regime": engine.regime.state,
        "shadow_block_rate": round(shadow_caught / fraud_n, 4) if shadow and fraud_n else None,
    }


def _mean(rows: list, key: str):
    vals = [row[key] for row in rows if row.get(key) is not None]
    if not vals:
        return None
    if isinstance(vals[0], bool):
        return round(sum(1 for v in vals if v) / len(vals), 4)
    return round(sum(vals) / len(vals), 4)


def summarise(runs: list) -> list:
    out = []
    for name in SCENARIOS:
        group = [row for row in runs if row["scenario"] == name]
        out.append(
            {
                "scenario": name,
                "detected_rate": _mean([{**row, "detected": row["detected"]} for row in group], "detected") if False else round(sum(row["detected"] for row in group) / max(len(group), 1), 4),
                "detect_seconds": _mean(group, "detect_seconds"),
                "rupees_leaked_before_latch": _mean(group, "rupees_leaked_before_latch"),
                "fraud_recall": _mean(group, "fraud_recall"),
                "false_decline_rate": _mean(group, "false_decline_rate"),
                "static_false_decline_rate": _mean(group, "static_false_decline_rate"),
                "fraud_rupees_caught": _mean(group, "fraud_rupees_caught"),
                "static_fraud_rupees": _mean(group, "static_fraud_rupees"),
                "shadow_block_rate": _mean(group, "shadow_block_rate"),
            }
        )
    return out


def run(seeds: int = 5, shadow: bool = False, write_baseline: bool = False) -> dict:
    engine = Engine(ARTIFACT_PATH)
    runs = [replay(engine, name, seed, shadow=shadow) for name in SCENARIOS for seed in range(seeds)]
    summary = summarise(runs)
    payload = {"seeds": seeds, "summary": summary, "runs": runs}
    if write_baseline or not BASELINE_PATH.exists():
        BASELINE_PATH.write_text(json.dumps({"seeds": seeds, "summary": summary}, indent=2))
    baseline = json.loads(BASELINE_PATH.read_text()) if BASELINE_PATH.exists() else {"summary": []}
    before = {row["scenario"]: row for row in baseline.get("summary", [])}
    for row in summary:
        prior = before.get(row["scenario"])
        row["baseline_detected_rate"] = prior.get("detected_rate") if prior else None
        row["baseline_fraud_recall"] = prior.get("fraud_recall") if prior else None
        row["baseline_rupees_leaked"] = prior.get("rupees_leaked_before_latch") if prior else None
    payload["summary"] = summary
    OUT_PATH.write_text(json.dumps(payload, indent=2))
    return payload


def evasion_sweep(noises=(0.01, 0.04, 0.08, 0.15), spacings=(0.22, 1.0, 3.0, 6.0)) -> list:
    """How far an attacker can push noise and pacing before the latch fails."""
    from backend.app.scenarios import _attack
    from ml.features import load_transactions
    from ml.schema import DATA_DIR

    engine = Engine(ARTIFACT_PATH)
    fraud = load_transactions(DATA_DIR / "test.csv")
    fraud = fraud[fraud["Class"] == 1]
    rows = []
    for noise in noises:
        for spacing in spacings:
            engine.reset()
            events = _attack(fraud, __import__("numpy").random.default_rng(1), 200_000, 1, noise=noise, spacing=spacing)
            detected = False
            for event in events:
                result = engine.score(event, explain=False)
                if result["regime"] == "ATTACK":
                    detected = True
                    break
            rows.append({"noise": noise, "spacing": spacing, "detected": detected})
    path = ARTIFACT_DIR / "redteam_sweep.json"
    path.write_text(json.dumps(rows, indent=2))
    return rows


if __name__ == "__main__":
    import sys

    baseline = "--baseline" in sys.argv
    shadow = "--shadow" in sys.argv
    result = run(seeds=5, shadow=shadow, write_baseline=baseline)
    for row in result["summary"]:
        print(
            f"{row['scenario']:20} detect {row['detected_rate']} recall {row['fraud_recall']} "
            f"leak {row['rupees_leaked_before_latch']} fdr {row['false_decline_rate']}"
        )
