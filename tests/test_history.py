"""Per-entity history stays bounded, opens cases, and never stores raw ids."""

from backend.app.history import History


def _result(i, user="u1", merchant="m1", decision="APPROVE"):
    return {
        "id": i,
        "decision": decision,
        "score": 0.5,
        "risk_100": 50,
        "amount": 100.0,
        "regime": "NORMAL",
        "user_token": user,
        "merchant_token": merchant,
        "reasons": [{"feature": "geometry", "text": "alike"}] if decision != "APPROVE" else [],
        "lat": 12.9,
        "lon": 77.6,
        "geo_source": "simulated",
    }


def test_ring_buffer_and_lru_bounds():
    history = History(user_limit=3, user_depth=5, merchant_limit=2, merchant_depth=4)
    for i in range(12):
        history.record(_result(i, user=f"u{i % 4}", merchant=f"m{i % 3}"))
    assert len(history.stores["user"]) == 3
    assert len(history.stores["merchant"]) == 2
    history.record(_result(99, user="solo"))
    for i in range(10):
        history.record(_result(100 + i, user="solo"))
    assert len(history.stores["user"]["solo"]["events"]) == 5
    assert history.stores["user"]["solo"]["n"] == 11


def test_csv_row_opens_on_the_first_challenge():
    history = History()
    history.record(_result(1, decision="STEP_UP"))
    assert history.list_cases([]) == []
    flagged = _result(2, user="csv", decision="STEP_UP", merchant="file")
    flagged["from_csv"] = True
    history.record(flagged)
    cases = history.list_cases([])
    assert cases[0]["id"] == "user-csv"
    assert cases[0]["why"] == "challenged CSV row"
    assert cases[0]["flags"] == 1


def test_case_opens_after_two_flags():
    history = History()
    history.record(_result(1, decision="BLOCK"))
    assert history.list_cases([]) == []
    history.record(_result(2, decision="STEP_UP"))
    cases = history.list_cases([])
    assert [case["id"] for case in cases] == ["user-u1"]
    view = history.entity("user", "u1")
    assert view["summary"]["flags"] == 2
    assert len(view["geo"]) == 2


def test_incident_membership_opens_a_case():
    history = History()
    history.record(_result(1, user="mule"))
    cases = history.list_cases([{"id": "INC-0001", "mules": ["mule"]}])
    assert cases and cases[0]["why"] == "member of INC-0001"


def test_lookup_tokenizes_without_storing_the_raw_id():
    from fastapi.testclient import TestClient

    from backend.app import main

    raw = "card-4111-raw-id"
    with TestClient(main.app) as client:
        response = client.post("/entity/lookup", json={"kind": "user", "raw_id": raw}, headers={"X-API-Key": "surgeshield-demo"})
        assert response.status_code == 200
        body = response.json()
        assert len(body["token"]) == 24 and raw not in body["token"]
        assert body["found"] is False
        stores = main.engine.history.stores
        assert raw not in stores["user"] and raw not in stores["merchant"]
        assert not any(raw in str(case) for case in main.engine.history.cases.values())
