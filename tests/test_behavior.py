from backend.app.behavior import human_score
from backend.app.policy import surge_shield_decision

CFG = {"t_step": 0.5, "t_block": 0.8}


def test_missing_telemetry_is_not_a_score():
    assert human_score(None) is None
    assert human_score({}) is None
    assert surge_shield_decision(0.1, "NORMAL", 0, None, CFG, human_score=None) == "APPROVE"


def test_bot_telemetry_steps_up_and_does_not_block():
    score = human_score({
        "session_duration_sec": 0.3,
        "action_count": 1,
        "typing_cps": 40,
        "mouse_entropy": 0.01,
        "action_interval_cv": 0.01,
    })
    assert score < 35
    assert surge_shield_decision(0.1, "NORMAL", 0, None, CFG, human_score=score) == "STEP_UP"
    assert surge_shield_decision(0.9, "NORMAL", 0, None, CFG, human_score=score) == "BLOCK"
