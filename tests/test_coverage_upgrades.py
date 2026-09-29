"""Checks that only step a payment up, and logs that stay dark until a real file is loaded."""

import csv
import tempfile
from pathlib import Path

from backend.app.engine import Engine
from backend.app.logsignals import load, summary
from backend.app.scenarios import build_scenario
from backend.app.taxonomy import coverage
from ml.import_logs import import_file
from ml.schema import ARTIFACT_PATH


def _engine():
    return Engine(ARTIFACT_PATH, audit_path=tempfile.mktemp(prefix="surgeshield-cov-", suffix=".db"))


def _quiet(when, user="alice", merchant="shop"):
    return {
        "time": when,
        "amount": 40.0,
        "v": [0.0] * 28,
        "user_id": user,
        "merchant_id": merchant,
        "device": f"handset-{user}",
        "region": "Delhi",
        "eval_label": 0,
    }


def test_ood_steps_up_and_never_blocks():
    engine = _engine()
    engine.baselines = {"ood_distance": [0.0] * 32}
    result = engine.score(_quiet(1_000), explain=False)
    assert result["profile"]["ood"] is True
    assert result["decision"] == "STEP_UP"
    assert result["decision"] != "BLOCK"


def test_topology_note_skips_the_flash_sale_and_does_not_step_up():
    engine = _engine()
    seen = False
    for event in build_scenario("flash_sale", seed=1):
        result = engine.score(event, explain=False)
        assert result["profile"]["topology"] is False
        seen = True
    assert seen
    engine = _engine()
    last = None
    for index in range(22):
        last = engine.score(_quiet(2_000 + index, user=f"mule-{index % 11}", merchant="sink"), explain=False)
    assert last["profile"]["topology"] is True
    assert last["decision"] != "BLOCK"
    assert any(note["feature"] == "topology" for note in last["reasons"])


def test_drift_reports_correlation_and_volatility():
    engine = _engine()
    engine.baselines = {
        "correlation_columns": ["V1", "Amount"],
        "correlation": [[1.0, 0.0], [0.0, 1.0]],
        "volatility_std": [0.01] * 32,
        "ood_distance": [1e9] * 32,
    }
    engine._corr_idx = [0, -1]
    for index in range(45):
        row = _quiet(3_000 + index * 0.2, user=f"u-{index}", merchant=f"m-{index}")
        row["v"] = [float(index)] + [0.0] * 27
        row["amount"] = 20.0 * float(index)
        engine.score(row, explain=False)
    report = engine.drift()
    assert report["correlation_shift"] is not None
    assert report["correlation_shift"] > 0
    assert report["volatility_high"] is True


def test_login_log_steps_up_that_account_only():
    root = Path(tempfile.mkdtemp(prefix="surgeshield-logs-"))
    raw = root / "login.csv"
    with raw.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["user_id", "time", "success", "email"])
        writer.writeheader()
        for index in range(10):
            writer.writerow({"user_id": "alice", "time": 1000 + index, "success": "false", "email": "a@example.com"})
        writer.writerow({"user_id": "bob", "time": 1000, "success": "true", "email": "b@example.com"})
    report = import_file("login", raw, root / "login")
    assert report["rows"] == 11
    assert "email" in report["dropped_pii"]
    load(root)
    assert "login" in summary()["kinds"]
    engine = _engine()
    load(root)
    assert {item["name"]: item for item in coverage()["items"]}["Credential stuffing"]["status"] == "live"
    hit = engine.score(_quiet(5_000, user="alice"), explain=False)
    quiet = engine.score(_quiet(5_010, user="bob"), explain=False)
    assert hit["profile"]["auth_flood"] is True
    assert hit["decision"] == "STEP_UP"
    assert hit["decision"] != "BLOCK"
    assert quiet["profile"]["auth_flood"] is False
    empty = Path(tempfile.mkdtemp(prefix="surgeshield-empty-"))
    load(empty)
    body = coverage()
    names = {item["name"]: item for item in body["items"]}
    assert names["Credential stuffing"]["status"] == "needs data"
    assert names["ATM jackpotting"]["status"] == "needs data"
    assert "user_id, time, success" in names["Credential stuffing"]["file"]
    assert names["Novelty detection"]["status"] == "live"
