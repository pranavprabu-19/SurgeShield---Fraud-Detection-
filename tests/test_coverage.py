"""Wormhole step-up, saved histories, and the taxonomy list."""

import tempfile

from fastapi.testclient import TestClient

from backend.app.engine import Engine
from backend.app.history import History
from ml.schema import ARTIFACT_PATH

HEADERS = {"X-API-Key": "surgeshield-demo"}


def _quiet(when, user, region):
    return {
        "time": when,
        "amount": 40.0,
        "v": [0.0] * 28,
        "user_id": user,
        "merchant_id": "shop",
        "device": "shared-handset",
        "region": region,
        "eval_label": 0,
    }


def test_wormhole_steps_up_and_does_not_block():
    engine = Engine(ARTIFACT_PATH, audit_path=tempfile.mktemp(prefix="surgeshield-worm-", suffix=".db"))
    first = engine.score(_quiet(1_000, "alice", "Delhi"), explain=False)
    second = engine.score(_quiet(1_020, "bob", "Chennai"), explain=False)
    assert second["decision"] == "STEP_UP"
    assert second["friction"] == "STEP_UP_AUTH"
    assert second["profile"]["wormhole"] is True
    assert second["profile"]["wormhole_simulated"] is True
    assert "Step-up only" in second["reasons"][0]["text"] or any("Step-up only" in note["text"] for note in second["reasons"])
    assert first["decision"] != "BLOCK"
    assert second["decision"] != "BLOCK"


def test_history_round_trip():
    path = tempfile.mktemp(prefix="surgeshield-hist-", suffix=".db")
    history = History()
    history.record({
        "id": 1,
        "decision": "BLOCK",
        "score": 0.4,
        "risk_100": 40,
        "amount": 80,
        "regime": "ATTACK",
        "user_token": "user-a",
        "merchant_token": "shop-a",
        "reasons": [{"feature": "wormhole", "text": "far apart"}],
        "lat": 1.0,
        "lon": 2.0,
        "region": "Delhi",
        "geo_source": "simulated",
    })
    history.record({
        "id": 2,
        "decision": "STEP_UP",
        "score": 0.3,
        "risk_100": 30,
        "amount": 90,
        "regime": "ATTACK",
        "user_token": "user-a",
        "merchant_token": "shop-a",
        "reasons": [{"feature": "wormhole", "text": "again"}],
    })
    history.save(path)
    fresh = History()
    fresh.load(path)
    view = fresh.entity("user", "user-a")
    assert view["summary"]["payments"] == 2
    assert view["history"][0]["id"] == 2
    assert "user-user-a" in fresh.cases


def test_taxonomy_names_what_is_missing():
    from backend.app.main import app

    with TestClient(app) as client:
        body = client.get("/taxonomy", headers=HEADERS).json()
    names = {item["name"] for item in body["items"]}
    assert "Point anomalies" in names
    assert "SIM swap" in names
    assert "ATM jackpotting" in names
    sim = [item for item in body["items"] if item["name"] == "SIM swap"][0]
    assert sim["status"] == "needs data"
    assert body["counts"]["needs data"] > 0
