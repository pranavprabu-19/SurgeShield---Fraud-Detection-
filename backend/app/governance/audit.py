"""Tamper-evident, encrypted audit log and the human review queue."""

from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import threading
import time

from cryptography.hazmat.primitives.ciphers.aead import AESGCM


class AuditLog:
    def __init__(self, path: str, key: bytes):
        self.key = key
        os.makedirs(os.path.dirname(path), exist_ok=True)
        self.conn = sqlite3.connect(path, check_same_thread=False)
        self.conn.execute(
            """create table if not exists audit (
                id integer primary key autoincrement,
                created_at real,
                nonce blob,
                ciphertext blob,
                prev_hash text,
                row_hash text
            )"""
        )
        self.conn.execute(
            """create table if not exists review (
                id integer primary key autoincrement,
                created_at real,
                decision text,
                score real,
                amount real,
                reasons text,
                status text,
                override_action text,
                override_note text
            )"""
        )
        self.conn.execute(
            """create table if not exists feedback (
                id integer primary key autoincrement,
                created_at real,
                review_id integer,
                action text,
                segment integer,
                score real,
                label integer,
                features text
            )"""
        )
        self.conn.commit()
        # One connection is shared across request threads. SQLite aborts the
        # process if two threads use it at once, which the governance page does.
        self._lock = threading.RLock()

    def append(self, payload: dict) -> dict:
        body = json.dumps(payload, sort_keys=True, default=str).encode()
        nonce = os.urandom(12)
        ciphertext = AESGCM(self.key).encrypt(nonce, body, None)
        with self._lock:
            prev = self.conn.execute("select row_hash from audit order by id desc limit 1").fetchone()
            prev_hash = prev[0] if prev else "GENESIS"
            row_hash = hashlib.sha256(prev_hash.encode() + nonce + ciphertext).hexdigest()
            cur = self.conn.execute(
                "insert into audit (created_at, nonce, ciphertext, prev_hash, row_hash) values (?,?,?,?,?)",
                (time.time(), nonce, ciphertext, prev_hash, row_hash),
            )
            self.conn.commit()
            return {"id": cur.lastrowid, "row_hash": row_hash}

    def verify(self) -> dict:
        with self._lock:
            rows = self.conn.execute(
                "select id, nonce, ciphertext, prev_hash, row_hash from audit order by id"
            ).fetchall()
        prev = "GENESIS"
        for row_id, nonce, ciphertext, prev_hash, row_hash in rows:
            if prev_hash != prev:
                return {"ok": False, "records": len(rows), "broken_at": row_id, "reason": "prev_hash mismatch"}
            expect = hashlib.sha256(prev_hash.encode() + nonce + ciphertext).hexdigest()
            if expect != row_hash:
                return {"ok": False, "records": len(rows), "broken_at": row_id, "reason": "row hash mismatch"}
            prev = row_hash
        return {"ok": True, "records": len(rows), "head": prev if rows else "GENESIS"}

    def tamper_latest(self) -> dict:
        """Demo only: flip one ciphertext byte so verify() can show the break."""
        with self._lock:
            row = self.conn.execute(
                "select id, ciphertext from audit order by id desc limit 1"
            ).fetchone()
            if not row:
                return {"ok": False, "reason": "empty log"}
            flipped = bytearray(row[1])
            flipped[0] ^= 0xFF
            self.conn.execute("update audit set ciphertext=? where id=?", (bytes(flipped), row[0]))
            self.conn.commit()
            return {"ok": True, "tampered_id": row[0]}

    def enforce_retention(self, ttl_seconds: float) -> dict:
        """Replace expired payloads with a redaction notice and rebuild the chain."""
        cutoff = time.time() - ttl_seconds
        with self._lock:
            old = self.conn.execute(
                "select id, nonce, ciphertext from audit where created_at < ? order by id",
                (cutoff,),
            ).fetchall()
            aes = AESGCM(self.key)
            redacted = 0
            for row_id, nonce, ciphertext in old:
                try:
                    plain = json.loads(aes.decrypt(nonce, ciphertext, None))
                except Exception:
                    plain = {}
                if plain.get("redacted"):
                    continue
                notice = {"redacted": True, "id": row_id, "reason": "retention TTL elapsed"}
                new_nonce = os.urandom(12)
                new_ct = aes.encrypt(new_nonce, json.dumps(notice, sort_keys=True).encode(), None)
                self.conn.execute(
                    "update audit set nonce=?, ciphertext=? where id=?",
                    (new_nonce, new_ct, row_id),
                )
                redacted += 1
            self._rebuild_chain()
            self.conn.commit()
            return {"redacted": redacted}

    def _rebuild_chain(self) -> None:
        rows = self.conn.execute("select id, nonce, ciphertext from audit order by id").fetchall()
        prev = "GENESIS"
        for row_id, nonce, ciphertext in rows:
            row_hash = hashlib.sha256(prev.encode() + nonce + ciphertext).hexdigest()
            self.conn.execute(
                "update audit set prev_hash=?, row_hash=? where id=?",
                (prev, row_hash, row_id),
            )
            prev = row_hash

    def enqueue_review(self, decision: str, score: float, amount: float, reasons: list) -> int:
        with self._lock:
            cur = self.conn.execute(
                "insert into review (created_at, decision, score, amount, reasons, status) values (?,?,?,?,?,?)",
                (time.time(), decision, score, amount, json.dumps(reasons), "OPEN"),
            )
            self.conn.commit()
            return int(cur.lastrowid)

    def list_reviews(self, limit: int = 50) -> list:
        with self._lock:
            rows = self.conn.execute(
                "select id, created_at, decision, score, amount, reasons, status, override_action, override_note "
                "from review order by id desc limit ?",
                (limit,),
            ).fetchall()
        out = []
        for row in rows:
            out.append(
                {
                    "id": row[0],
                    "created_at": row[1],
                    "decision": row[2],
                    "score": row[3],
                    "amount": row[4],
                    "reasons": json.loads(row[5] or "[]"),
                    "status": row[6],
                    "override_action": row[7],
                    "override_note": row[8],
                }
            )
        return out

    def override(self, review_id: int, action: str, note: str) -> dict:
        if action not in {"UPHOLD", "RELEASE"}:
            raise ValueError("action must be UPHOLD or RELEASE")
        with self._lock:
            self.conn.execute(
                "update review set status=?, override_action=?, override_note=? where id=?",
                ("CLOSED", action, note[:500], review_id),
            )
            self.conn.commit()
        record = {"review_id": review_id, "override": action, "note": note[:500]}
        self.append({"type": "analyst_override", **record})
        return record

    def save_feedback(self, review_id: int, action: str, segment: int, score: float, features) -> None:
        label = 1 if action == "UPHOLD" else 0
        with self._lock:
            self.conn.execute(
                "insert into feedback (created_at, review_id, action, segment, score, label, features) values (?,?,?,?,?,?,?)",
                (time.time(), review_id, action, int(segment), float(score), label, json.dumps(features) if features else None),
            )
            self.conn.commit()

    def list_feedback(self, limit: int = 200) -> list:
        with self._lock:
            rows = self.conn.execute(
                "select review_id, action, segment, score, label, features from feedback order by id desc limit ?",
                (limit,),
            ).fetchall()
        out = []
        for row in rows:
            out.append(
                {
                    "review_id": row[0],
                    "action": row[1],
                    "segment": row[2],
                    "score": row[3],
                    "label": row[4],
                    "features": json.loads(row[5]) if row[5] else None,
                }
            )
        return out

    def stats(self) -> dict:
        with self._lock:
            count = self.conn.execute("select count(*) from audit").fetchone()[0]
            open_reviews = self.conn.execute(
                "select count(*) from review where status='OPEN'"
            ).fetchone()[0]
        return {"audit_records": count, "open_reviews": open_reviews}
