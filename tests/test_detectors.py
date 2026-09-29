"""Graph, sequence, and adaptive-threshold checks."""

from backend.app.graph import analyze_graph
from backend.app.policy import surge_shield_decision


def test_fan_out_and_card_testing_signals():
    records = []
    for i in range(20):
        records.append({"time": 1000 + i * 0.4, "amount": 0.8, "user": "victim", "merchant": f"m-{i}", "segment": 1})
    graph = analyze_graph(records, 1010, user="victim", merchant="m-0")
    assert graph["fan_out"] >= 15
    assert graph["card_test"] >= 0.7


def test_diverse_buyers_are_not_card_testing():
    records = []
    for i in range(30):
        records.append({"time": 5000 + i * 0.1, "amount": 80, "user": f"u-{i}", "merchant": "m-electronics-flash", "segment": i % 6})
    graph = analyze_graph(records, 5003, user="u-0", merchant="m-electronics-flash")
    assert graph["card_test"] == 0.0
    assert graph["diversity"] > 0.5


def test_suspicious_burst_is_stepped_up():
    cfg = {"t_step": 0.5, "t_block": 0.8, "surge_relief": 0.05, "attack_tighten": 0.1}
    decision = surge_shield_decision(0.3, "NORMAL", 1, 1, cfg, suspicious=True)
    assert decision == "STEP_UP"


def test_adaptive_offset_is_capped_by_policy():
    cfg = {"t_step": 0.2, "t_block": 0.4}
    loosened = surge_shield_decision(0.2, "NORMAL", 0, None, cfg, threshold_offset=0.03)
    assert loosened == "APPROVE"
    tightened = surge_shield_decision(0.38, "NORMAL", 0, None, cfg, threshold_offset=-0.03)
    assert tightened == "BLOCK"


def test_challenger_refuses_a_tiny_label_set():
    from ml.challenger import propose

    assert propose([{"label": 1, "features": [0.1] * 4}])["recommend"] is False
