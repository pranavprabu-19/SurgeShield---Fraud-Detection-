"""Case summaries, friction labels, drift health, and probing. None of these block alone."""

from fastapi.testclient import TestClient

from backend.app.copilot import summarize_case
from backend.app.engine import Engine
from backend.app.main import app
from backend.app.policy import friction_tier, surge_shield_decision
from ml.schema import ARTIFACT_PATH

HEADERS = {"X-API-Key": "surgeshield-demo"}


def test_case_summary_uses_only_the_stored_history(monkeypatch):
    monkeypatch.delenv("SURGESHIELD_LLM_KEY", raising=False)
    view = {
        "kind": "user",
        "token": "secret-token-should-not-appear",
        "summary": {"payments": 8, "flags": 8, "amount": 1400, "signals": [{"name": "geometry", "n": 8}]},
        "history": [{"risk_100": 22, "region": "Bengaluru", "features": ["geometry"]} for _ in range(8)],
        "incidents": [{"id": "INC-0001"}],
    }
    result = summarize_case(view, ("BLOCK", "8 of 8 payments were challenged and the pattern did not ease"))
    text = result["text"]
    assert result["source"] == "template"
    assert result["decision_owner"] == "model"
    assert "8 of 8" in text
    assert "Bengaluru" in text
    assert "geometry" in text
    assert "INC-0001" in text
    assert "secret-token" not in text
    assert "account age" not in text.lower()
    assert "years old" not in text.lower()


def test_friction_labels_do_not_change_the_decision():
    cfg = {"t_step": 0.2, "t_block": 0.5, "surge_relief": 0.04, "attack_tighten": 0.12}
    assert surge_shield_decision(0.1, "NORMAL", 0, None, cfg) == "APPROVE"
    assert friction_tier("APPROVE", 0.1, cfg, {}, 40, "NORMAL") == "NONE"
    assert friction_tier("BLOCK", 0.9, cfg, {"model_probe": True}, 40, "NORMAL") == "BLOCKED"
    assert friction_tier("STEP_UP", 0.3, cfg, {"model_probe": True}, 40, "NORMAL") == "STEP_UP_AUTH"
    assert friction_tier("STEP_UP", 0.3, cfg, {"new_user": True}, 40, "NORMAL") == "PUSH"
    assert friction_tier("STEP_UP", 0.3, cfg, {"new_user": True}, 12_000, "NORMAL") == "OTP"
    assert friction_tier("STEP_UP", 0.3, cfg, {}, 40, "NORMAL") == "DEVICE_CHECK"


def test_probing_steps_up_and_never_blocks():
    engine = Engine(ARTIFACT_PATH)
    engine.reset()
    block = float(engine.art["thresholds"]["t_block"])
    planned = [block * (0.78 + i * 0.01) for i in range(5)]
    assert all(block * 0.75 <= score < block for score in planned)
    cursor = iter(planned)
    engine._fuse = lambda features, explain=False: (next(cursor), 0.0, 0.0)
    rows = [
        engine.score(
            {"time": 80_000 + i * 30, "amount": 80 + i * 15, "v": [0.0] * 28, "user_id": "walker"},
            explain=False,
        )
        for i in range(5)
    ]
    assert all(row["decision"] != "BLOCK" for row in rows)
    assert rows[-1]["decision"] == "STEP_UP"
    assert rows[-1]["friction"] == "STEP_UP_AUTH"
    assert any(note["feature"] == "model_probe" for note in rows[-1]["reasons"])


def test_drift_reports_mean_shift_and_a_sustained_alert():
    engine = Engine(ARTIFACT_PATH)
    engine.reset()
    engine.recent_scores.extend([0.4] * 50)
    quiet = engine.drift()
    assert "mean_shift" in quiet
    assert quiet["baseline_mean"] >= 0
    assert quiet["sustained"] is False
    assert quiet["suggestion"] == ""
    engine.psi_history.extend([{"t": i, "psi": 0.4, "alert": True} for i in range(3)])
    alert = engine.drift()
    assert alert["sustained"] is True
    assert "kill switch" in alert["suggestion"]
    assert "does not flip" in alert["suggestion"]
    engine.regime.state = "ATTACK"
    during_attack = engine.drift()
    assert "ATTACK" in during_attack["suggestion"]
    assert "manual" in during_attack["suggestion"]


def test_case_summary_route_returns_the_history_verdict():
    from backend.app import main

    with TestClient(app) as client:
        main.engine.reset()
        for i in range(8):
            main.engine.history.record(
                {
                    "id": i,
                    "decision": "BLOCK",
                    "score": 0.9,
                    "risk_100": 22,
                    "amount": 100.0,
                    "regime": "ATTACK",
                    "user_token": f"buyer-{i}",
                    "merchant_token": "summary-shop",
                    "reasons": [{"feature": "geometry", "text": "alike"}],
                    "region": "Mumbai",
                }
            )
        body = client.post("/cases/merchant-summary-shop/summary", headers=HEADERS).json()
    assert body["source"] == "template"
    assert body["verdict"] == "BLOCK"
    assert "8 of 8" in body["text"]
    assert "Mumbai" in body["text"]
