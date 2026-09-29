"""The router names a dataset. It does not score."""

from fastapi.testclient import TestClient

from ml.router import route

HEADERS = {"X-API-Key": "surgeshield-demo"}


def test_card_paysim_and_unknown_rows():
    assert route({"Time": 1, "V1": 0.1, "V28": 0.2, "Amount": 10})[0] == "creditcard"
    assert route({"step": 1, "nameOrig": "C1", "nameDest": "M1", "type": "TRANSFER", "amount": 20})[0] == "paysim"
    name, matched = route({"amount": 500, "timestamp": 1700000000})
    assert name == "creditcard"
    assert matched == "default fallback"


def test_route_endpoint_does_not_score():
    from backend.app.main import app

    with TestClient(app) as client:
        listed = client.get("/models", headers=HEADERS)
        assert listed.status_code == 200
        assert "datasets" in listed.json()
        body = client.post(
            "/models/route",
            headers=HEADERS,
            json={"nameOrig": "C1", "nameDest": "M1", "type": "CASH_OUT", "amount": 10},
        )
        assert body.status_code == 200
        payload = body.json()
        assert payload["dataset"] == "paysim"
        assert "has_model" in payload
        assert "score" not in payload
        assert "decision" not in payload
