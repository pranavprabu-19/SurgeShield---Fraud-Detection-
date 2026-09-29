"""Skills step a payment up. They do not retrain the champion or block alone."""

from fastapi.testclient import TestClient

from backend.app.engine import Engine
from backend.app.main import app
from backend.app.policy import surge_shield_decision
from backend.app.skills import coverage, suspicious_text
from ml.schema import ARTIFACT_PATH

HEADERS = {"X-API-Key": "surgeshield-demo"}
QUIET = {"time": 12_000, "amount": 40.0, "v": [0.1] * 28, "user_id": "skill-user", "merchant_id": "skill-shop"}


def test_unavailable_skills_are_named_and_not_invented():
    body = coverage()
    by_id = {row["id"]: row for row in body["skills"]}
    for skill_id in ("outbound_beacon", "hardware_command", "insider_access", "auth_flood", "data_export"):
        assert by_id[skill_id]["status"] == "unavailable"
    assert body["champion"] == "unchanged"


def test_skills_only_step_up_a_quiet_approve():
    from backend.app.skills import apply_skills, fired_skills

    assert apply_skills("BLOCK", ["amount_spike"]) == "BLOCK"
    assert apply_skills("APPROVE", []) == "APPROVE"
    quiet = {"decision": "APPROVE", "regime": "SURGE", "vol_z": 3.0, "profile": {}, "detectors": {}}
    assert fired_skills(quiet) == []
    spiked = {"decision": "APPROVE", "regime": "NORMAL", "vol_z": 0, "profile": {"amount_spike": True}, "detectors": {}}
    assert apply_skills("APPROVE", fired_skills(spiked)) == "STEP_UP"
    assert "outbound_beacon" not in fired_skills(spiked)
    assert suspicious_text({"category": "union select x"}) is True
    assert suspicious_text({"category": "electronics"}) is False


def test_syntax_and_amount_spike_step_up_without_blocking():
    cfg = {"t_step": 0.3, "t_block": 0.7}
    assert surge_shield_decision(0.01, "NORMAL", 0, None, cfg, context_step_up=True) == "STEP_UP"

    engine = Engine(ARTIFACT_PATH)
    engine.reset()
    dirty = {**QUIET, "category": "union select"}
    result = engine.score(dirty, explain=False)
    assert result["decision"] == "STEP_UP"
    texts = " ".join(note["text"] for note in result["reasons"])
    assert "unexpected syntax" in texts
    assert "union" not in texts

    for i in range(3):
        engine.score({**QUIET, "time": 20_000 + i, "amount": 50.0, "user_id": "spender"}, explain=False)
    spiked = engine.score({**QUIET, "time": 20_010, "amount": 800.0, "user_id": "spender"}, explain=False)
    assert spiked["decision"] == "STEP_UP"
    assert any(note["feature"] == "amount_spike" for note in spiked["reasons"])


def test_history_blocks_a_sustained_pattern_and_approves_a_quiet_one():
    from backend.app.skills import judge_history

    attacked = [{"risk_100": 22, "features": ["V12", "V14"]} for _ in range(8)]
    decision, why = judge_history(attacked, {"payments": 8, "flags": 8})
    assert decision == "BLOCK"
    assert "8 of 8" in why

    quiet = [{"risk_100": 8, "features": []} for _ in range(10)]
    decision, _why = judge_history(quiet, {"payments": 10, "flags": 1})
    assert decision == "APPROVE"


def test_investigate_run_reviews_open_cases():
    from fastapi.testclient import TestClient

    from backend.app.main import app

    headers = {"X-API-Key": "surgeshield-demo"}
    with TestClient(app) as client:
        body = client.post("/investigate/run", headers=headers).json()
        assert set(body["summary"]) == {"APPROVE", "BLOCK"}
        assert isinstance(body["rows"], list)
    with TestClient(app) as client:
        body = client.get("/skills", headers=HEADERS).json()
        assert {row["status"] for row in body["skills"]} >= {"live", "partial", "unavailable"}
