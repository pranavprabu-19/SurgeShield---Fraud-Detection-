"""In-process replay of the four jury scenarios. Requires a trained artifact."""

import pytest

from ml.schema import ARTIFACT_PATH

pytestmark = pytest.mark.skipif(not ARTIFACT_PATH.exists(), reason="train the model first")


def _replay(name: str):
    from backend.app.engine import Engine
    from backend.app.scenarios import build_scenario

    model = Engine(ARTIFACT_PATH)
    model.scenario = name
    seen = []
    last = None
    for event in build_scenario(name):
        last = model.score(event, explain=False)
        seen.append(last["regime"])
    return seen, last


def test_flash_sale_is_not_called_an_attack():
    regimes, last = _replay("flash_sale")
    assert "SURGE" in regimes
    assert "ATTACK" not in regimes
    assert last["totals"]["ss_legit_blocked_n"] <= last["totals"]["st_legit_blocked_n"]


def test_bot_attack_is_caught():
    regimes, last = _replay("bot_attack")
    assert "ATTACK" in regimes
    assert last["totals"]["ss_fraud_caught_amt"] > 0


def test_attack_hidden_in_a_sale_is_separated():
    regimes, last = _replay("mixed")
    assert "ATTACK" in regimes
    assert last["totals"]["ss_fraud_caught_amt"] >= last["totals"]["st_fraud_caught_amt"] * 0.5
