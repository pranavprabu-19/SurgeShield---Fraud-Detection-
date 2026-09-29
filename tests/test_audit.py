import os

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from backend.app.governance.audit import AuditLog
from backend.app.governance.privacy import tokenize


def test_chain_detects_tamper(tmp_path):
    key = os.urandom(32)
    log = AuditLog(str(tmp_path / "audit.db"), key)
    log.append({"decision": "APPROVE", "amount": 10})
    log.append({"decision": "BLOCK", "amount": 80})
    assert log.verify()["ok"] is True
    log.tamper_latest()
    report = log.verify()
    assert report["ok"] is False
    assert report["broken_at"] == 2


def test_retention_redacts_and_keeps_chain(tmp_path):
    key = os.urandom(32)
    log = AuditLog(str(tmp_path / "audit.db"), key)
    log.append({"decision": "APPROVE", "user_token": "abc"})
    assert log.enforce_retention(0)["redacted"] == 1
    assert log.verify()["ok"] is True
    row = log.conn.execute("select nonce, ciphertext from audit").fetchone()
    plain = AESGCM(key).decrypt(row[0], row[1], None)
    assert b"redacted" in plain


def test_override_is_itself_audited(tmp_path):
    key = os.urandom(32)
    log = AuditLog(str(tmp_path / "audit.db"), key)
    review_id = log.enqueue_review("BLOCK", 0.9, 100, [{"feature": "night"}])
    log.override(review_id, "RELEASE", "customer confirmed")
    assert log.list_reviews()[0]["status"] == "CLOSED"
    assert log.verify()["ok"] is True


def test_tokenizer_hides_raw_id():
    secret = b"s" * 32
    token = tokenize("customer-42", secret)
    assert "customer" not in token
    assert token == tokenize("customer-42", secret)
    assert token != tokenize("customer-43", secret)
