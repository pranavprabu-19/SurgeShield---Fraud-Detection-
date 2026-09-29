"""HTTP contract for the scoring API."""

from fastapi.testclient import TestClient

from backend.app.main import app

HEADERS = {"X-API-Key": "surgeshield-demo"}
TXN = {
    "time": 12_000,
    "amount": 42.5,
    "v": [0.1] * 28,
    "user_id": "rahul",
    "merchant_id": "m-electronics",
}


def test_health_is_open():
    with TestClient(app) as client:
        response = client.get("/health")
        assert response.status_code == 200
        assert response.json()["ok"] is True
        assert response.json()["model"] is True


def test_score_requires_key():
    with TestClient(app) as client:
        response = client.post("/score", json=TXN)
        assert response.status_code == 401


def test_score_approves_a_quiet_payment():
    with TestClient(app) as client:
        response = client.post("/score", json=TXN, headers=HEADERS)
        assert response.status_code == 200
        body = response.json()
        assert body["decision"] in {"APPROVE", "STEP_UP", "BLOCK"}
        assert body["user_token"] != "rahul"
        assert "merchant" not in (body["merchant_token"] or "")
        assert body["latency_ms"] < 50


def test_audit_and_kill_switch():
    with TestClient(app) as client:
        assert client.get("/audit/verify", headers=HEADERS).json()["ok"] is True
        switched = client.post("/killswitch?enabled=true", headers=HEADERS).json()
        assert switched["safe_mode"] is True
        client.post("/killswitch?enabled=false", headers=HEADERS)
        copilot = client.post(
            "/copilot",
            headers=HEADERS,
            json={"decision": "BLOCK", "regime": "ATTACK", "reasons": [{"text": "tight burst"}]},
        ).json()
        assert copilot["decision_owner"] == "model"
        assert copilot["source"] == "template"


def test_analyze_alias_surge_status_and_csv():
    with TestClient(app) as client:
        body = client.post("/api/analyze", json=TXN, headers=HEADERS).json()
        assert "risk_100" in body
        assert "layers" in body
        assert body["layers"]["model"]["label"] == "champion probability"
        status = client.get("/api/surge-status", headers=HEADERS).json()
        assert "surge" in status
        assert "flash_sale_merchants" in status
        header = "Time,Amount," + ",".join(f"V{i}" for i in range(1, 29))
        row = "100,12.5," + ",".join(["0.1"] * 28)
        uploaded = client.post(
            "/score/csv",
            headers=HEADERS,
            files={"file": ("rows.csv", f"{header}\n{row}\n", "text/csv")},
        )
        assert uploaded.status_code == 200
        assert uploaded.json()["count"] == 1
        fat = f"{header}\n" + f"{row}\n" * 120_000
        assert len(fat.encode()) > 8_000_000
        large = client.post(
            "/score/csv",
            headers=HEADERS,
            files={"file": ("fat.csv", fat, "text/csv")},
        )
        assert large.status_code == 200
        assert large.json()["count"] == 2000
        assert large.json()["truncated"] is True
        header_only = "Time,Amount," + ",".join(f"V{i}" for i in range(1, 29))
        quiet = "200,40," + ",".join(["0"] * 28)
        noisy = "201,40," + ",".join(["0"] * 28)
        uploaded_case = client.post(
            "/score/csv",
            headers=HEADERS,
            files={"file": ("plain.csv", f"{header_only}\n{quiet}\n{noisy}\n", "text/csv")},
        )
        assert uploaded_case.status_code == 200
        rows = uploaded_case.json()["decisions"]
        assert rows[0]["user_token"]
        assert rows[0]["user_token"] != rows[1]["user_token"]
        cases = client.get("/cases", headers=HEADERS).json()["cases"]
        opened = [case for case in cases if case["why"] == "challenged CSV row"]
        assert opened
        view = client.get(f"/entity/user/{opened[0]['token']}", headers=HEADERS).json()
        assert view["summary"]["payments"] >= 1


def test_sales_cases_entity_and_actions():
    from backend.app import main

    with TestClient(app) as client:
        events = client.get("/sales", headers=HEADERS).json()["events"]
        assert {event["id"] for event in events} >= {"big_billion_day", "great_indian_festival"}
        report = client.get("/sale/report", headers=HEADERS).json()
        assert {"phases", "merchants", "totals"} <= set(report)

        token = "t" * 24
        for i in range(3):
            main.engine.history.record(
                {
                    "id": 90_000 + i,
                    "decision": "STEP_UP",
                    "score": 0.4,
                    "risk_100": 40,
                    "amount": 250.0,
                    "regime": "NORMAL",
                    "user_token": token,
                    "merchant_token": "m" * 24,
                    "reasons": [{"feature": "impossible_travel", "text": "moved too fast"}],
                    "lat": 19.07,
                    "lon": 72.88,
                    "geo_source": "simulated",
                }
            )
        body = client.get("/cases", headers=HEADERS).json()
        case_id = f"user-{token}"
        assert case_id in {case["id"] for case in body["cases"]}
        assert any(row["token"] == token for row in body["watchlist"])

        view = client.get(f"/entity/user/{token}", headers=HEADERS).json()
        assert view["summary"]["flags"] == 3
        assert view["sources"]["location"] in {"real", "simulated", "unavailable"}
        assert view["geo"] and view["timeline"]
        assert client.get("/entity/user/nobody", headers=HEADERS).status_code == 404
        assert client.get(f"/entity/card/{token}", headers=HEADERS).status_code == 404

        noted = client.post(f"/cases/{case_id}/action", json={"action": "NOTE", "note": "called the customer"}, headers=HEADERS)
        assert noted.status_code == 200
        verify = client.post(f"/cases/{case_id}/action", json={"action": "VERIFY", "note": ""}, headers=HEADERS).json()
        assert verify["case"]["status"] == "VERIFY_REQUESTED"
        assert client.post("/cases/user-missing/action", json={"action": "NOTE", "note": "x"}, headers=HEADERS).status_code == 404
        assert client.post(f"/cases/{case_id}/action", json={"action": "DELETE", "note": ""}, headers=HEADERS).status_code == 422

        found = client.post("/entity/lookup", json={"kind": "user", "raw_id": "someone-new"}, headers=HEADERS).json()
        assert found["found"] is False


def test_reports_cover_uploads_and_installed_datasets():
    header = "Time,Amount," + ",".join(f"V{i}" for i in range(1, 29))
    row = "100,12.5," + ",".join(["0.1"] * 28)
    with TestClient(app) as client:
        uploaded = client.post(
            "/score/csv",
            headers=HEADERS,
            files={"file": ("plain-report.csv", f"{header}\n{row}\n{row}\n", "text/csv")},
        )
        assert uploaded.status_code == 200
        body = client.get("/reports", headers=HEADERS).json()
        names = [item["name"] for item in body["uploads"]]
        assert "plain-report.csv" in names
        saved = next(item for item in body["uploads"] if item["name"] == "plain-report.csv")
        assert "decisions" not in saved
        assert set(saved["summary"]) <= {"APPROVE", "STEP_UP", "BLOCK"}
        installed = {item["name"]: item for item in body["installed"]}
        assert installed["creditcard"]["score"]["count"] > 0
        assert set(installed["creditcard"]["score"]["summary"]) <= {"APPROVE", "STEP_UP", "BLOCK"}
        assert installed["creditcard"]["pr_auc"] is not None


def test_datasets_listing_and_unknown_activation():
    with TestClient(app) as client:
        body = client.get("/datasets", headers=HEADERS).json()
        assert body["active"] == "creditcard"
        assert "creditcard" in {row["name"] for row in body["datasets"]}
        missing = client.post("/datasets/activate", json={"name": "nope", "note": ""}, headers=HEADERS)
        assert missing.status_code == 404
