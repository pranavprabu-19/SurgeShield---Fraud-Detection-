"""Endpoints that feed the operations console."""

from fastapi.testclient import TestClient

from backend.app.main import app
from backend.app.scenarios import build_scenario

HEADERS = {"X-API-Key": "surgeshield-demo"}


def test_config_timeseries_and_analytics():
    with TestClient(app) as client:
        client.post("/simulate/reset", headers=HEADERS)
        config = client.get("/config", headers=HEADERS)
        assert config.status_code == 200
        body = config.json()
        assert "t_block" in body["thresholds"]
        assert body["regime_rules"]["vol_z_surge"] == 2.5
        assert len(body["artifact_sha256"]) == 64

        txn = build_scenario("normal", seed=1)[0]
        scored = client.post("/score", json=txn, headers=HEADERS)
        assert scored.status_code == 200
        row = scored.json()
        assert "coordination" in row and "id" in row

        recent = client.get("/recent", headers=HEADERS).json()
        assert "user_token" in recent["transactions"][0]
        series = client.get("/timeseries?seconds=30", headers=HEADERS).json()
        assert series["buckets"]
        analytics = client.get("/analytics", headers=HEADERS).json()
        assert len(analytics["score_histogram"]) == 40
        assert len(analytics["segments"]) == 8
        drift = client.get("/drift", headers=HEADERS).json()
        assert "history" in drift


def test_attack_opens_an_incident():
    with TestClient(app) as client:
        client.post("/simulate/reset", headers=HEADERS)
        for event in build_scenario("bot_attack")[:40]:
            response = client.post("/score?explain=false", json=event, headers=HEADERS)
            assert response.status_code == 200
        listing = client.get("/incidents", headers=HEADERS).json()
        assert listing["items"], "bot attack should latch an incident"
        incident_id = listing["items"][0]["id"]
        acked = client.post(f"/incidents/{incident_id}/ack", headers=HEADERS)
        assert acked.status_code == 200
        assert acked.json()["status"] in {"ACK", "RESOLVED"}
        missing = client.post("/incidents/INC-9999/ack", headers=HEADERS)
        assert missing.status_code == 404
