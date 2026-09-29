"""Morph a real row. The champion file and the comparison file stay put."""

import hashlib
import tempfile

from fastapi.testclient import TestClient

from backend.app.engine import Engine
from ml.schema import ARTIFACT_DIR, ARTIFACT_PATH

HEADERS = {"X-API-Key": "surgeshield-demo"}


def _quiet(when=1_000):
    return {
        "time": when,
        "amount": 40.0,
        "v": [0.0] * 28,
        "user_id": "alice",
        "merchant_id": "shop",
        "device": "handset",
        "region": "Delhi",
        "eval_label": 0,
    }


def test_synthesize_tags_copies_and_leaves_compare_file():
    compare = ARTIFACT_DIR / "compare.json"
    before = hashlib.sha256(compare.read_bytes()).hexdigest() if compare.exists() else None
    champion = hashlib.sha256(ARTIFACT_PATH.read_bytes()).hexdigest()
    engine = Engine(ARTIFACT_PATH, audit_path=tempfile.mktemp(prefix="surgeshield-morph-", suffix=".db"))
    first = engine.score(_quiet(), explain=False)
    body = engine.synthesize(source_id=first["id"], amount_scale=1.5, v_shift={"V14": 1.0}, copies=2)
    assert body["baseline"] is None
    assert len(body["copies"]) == 2
    assert all(row["synthesized"] is True for row in body["copies"])
    assert all(row["decision"] != "BLOCK" for row in body["copies"])
    assert all(row["signals"]["V14"] == 1.0 for row in body["copies"])
    assert hashlib.sha256(ARTIFACT_PATH.read_bytes()).hexdigest() == champion
    if before:
        assert hashlib.sha256(compare.read_bytes()).hexdigest() == before


def test_synthesize_endpoint_unknown_id():
    from backend.app.main import app

    with TestClient(app) as client:
        missing = client.post("/synthesize", json={"id": 9_999_999, "copies": 1}, headers=HEADERS)
        assert missing.status_code == 404
