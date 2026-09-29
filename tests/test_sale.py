"""Big Billion Days: the rush stays open, the attacks inside it do not."""

from collections import Counter, defaultdict

import pytest

from backend.app.engine import Engine
from backend.app.policy import surge_shield_decision
from backend.app.scenarios import build_scenario
from ml.schema import ARTIFACT_PATH

pytestmark = pytest.mark.skipif(not ARTIFACT_PATH.exists(), reason="train the model first")

ATTACK_PHASES = {"scalper_bots", "card_testing", "account_takeover", "mule_cashout", "distributed_drain"}


@pytest.fixture(scope="module")
def big_billion_day():
    engine = Engine(ARTIFACT_PATH)
    engine.reset()
    engine.scenario = "big_billion_day"
    rows = []
    for event in build_scenario("big_billion_day", seed=0):
        rows.append((event, engine.score(event, explain=False)))
    return engine, rows


def test_opening_reaches_surge_before_attack(big_billion_day):
    _engine, rows = big_billion_day
    regimes = [result["regime"] for _event, result in rows]
    assert all(regime == "NORMAL" for (event, _), regime in zip(rows, regimes) if event["phase"] == "warmup")
    assert "SURGE" in regimes
    assert regimes.index("SURGE") < regimes.index("ATTACK")
    assert rows[regimes.index("SURGE")][0]["phase"] in {"sale_open", "scalper_bots"}


def test_genuine_buyers_are_rarely_declined(big_billion_day):
    _engine, rows = big_billion_day
    legit = [result for event, result in rows if event["eval_label"] == 0]
    blocked = sum(1 for result in legit if result["decision"] == "BLOCK")
    assert blocked / len(legit) <= 0.01


def test_every_attack_phase_is_blocked_or_stepped_up(big_billion_day):
    _engine, rows = big_billion_day
    by_phase = defaultdict(Counter)
    for event, result in rows:
        if event["phase"] in ATTACK_PHASES:
            by_phase[event["phase"]][result["decision"]] += 1
    assert set(by_phase) == {"scalper_bots", "card_testing", "account_takeover", "mule_cashout"}
    for phase, counts in by_phase.items():
        assert counts["APPROVE"] == 0, phase


def test_device_farm_and_travel_chips_fire_on_attacks_only(big_billion_day):
    _engine, rows = big_billion_day
    fired = Counter()
    for event, result in rows:
        for note in result["reasons"]:
            if note["feature"] in {"device_farm", "impossible_travel", "wormhole"}:
                fired[(note["feature"], event["phase"] in ATTACK_PHASES)] += 1
    assert fired[("device_farm", True)] > 0
    assert fired[("impossible_travel", True)] > 0
    assert fired[("device_farm", False)] == 0
    assert fired[("impossible_travel", False)] == 0


def test_context_signals_never_force_a_block():
    cfg = {"t_step": 0.3, "t_block": 0.7}
    assert surge_shield_decision(0.01, "NORMAL", 0, None, cfg, context_step_up=True) == "STEP_UP"
    assert surge_shield_decision(0.01, "NORMAL", 0, None, cfg, context_step_up=False) == "APPROVE"


def test_sale_report_has_phases_and_merchants(big_billion_day):
    engine, _rows = big_billion_day
    report = engine.sale_report()
    phases = [row["phase"] for row in report["phases"]]
    assert phases[0] == "warmup" and phases[-1] == "cooldown"
    assert report["sale"]["name"] == "Big Billion Days"
    assert any(row["name"] == "fk-mobiles" for row in report["merchants"])
    assert report["totals"]["fraud_leaked"] == 0
