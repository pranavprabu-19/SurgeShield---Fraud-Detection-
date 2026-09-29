"""Bank SDK, boundary-probe scenario, and one-seed red-team replay."""

import tempfile

from fastapi.testclient import TestClient

from backend.app.engine import Engine
from ml.schema import ARTIFACT_PATH
from sdk.surgeshield_sdk import ScoreResult, transaction_from_row

HEADERS = {"X-API-Key": "surgeshield-demo"}


def test_sdk_maps_a_csv_row_and_reads_a_real_score():
    from backend.app.main import app

    row = {"Time": 1200, "Amount": 42.5, **{f"V{i}": 0.01 * i for i in range(1, 29)}, "Class": 0}
    txn = transaction_from_row(row)
    assert txn["time"] == 1200
    assert len(txn["v"]) == 28
    assert txn["eval_label"] == 0
    with TestClient(app) as client:
        body = client.post("/score?explain=false", json=txn, headers=HEADERS).json()
    result = ScoreResult.from_json(body)
    assert result.decision in {"APPROVE", "STEP_UP", "BLOCK"}
    assert result.regime
    assert "totals" not in result.__dict__


def test_boundary_probe_steps_up_and_does_not_block():
    from backend.app.scenarios import build_scenario

    events = build_scenario("boundary_probe", seed=0)
    engine = Engine(ARTIFACT_PATH, audit_path=tempfile.mktemp(prefix="surgeshield-probe-test-", suffix=".db"))
    probes = []
    for event in events:
        result = engine.score(event, explain=False)
        if result.get("boundary_probe"):
            probes.append(result)
    assert probes, "the selector found no payment in the band under the block cut"
    assert any(row["decision"] == "STEP_UP" and row["friction"] == "STEP_UP_AUTH" for row in probes)
    assert all(row["decision"] != "BLOCK" for row in probes)


def test_redteam_replay_does_not_reset_the_live_stream():
    from backend.app import main

    with TestClient(app := main.app) as client:
        client.post("/score?explain=false", json={"time": 10, "amount": 20, "v": [0.0] * 28}, headers=HEADERS)
        before = main.engine.totals["seen"]
        body = client.post("/redteam/replay", headers=HEADERS)
        assert body.status_code == 200
        payload = body.json()
        assert payload["scenarios"]
        assert {"scenario", "events", "latched", "fraud_recall", "false_decline_rate", "rupees_leaked_before_latch"} <= set(payload["scenarios"][0])
        assert "invent" in payload["note"]
        assert main.engine.totals["seen"] == before
