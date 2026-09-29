"""SurgeShield bank SDK. Standard library only.

    from sdk.surgeshield_sdk import SurgeShieldClient, transaction_from_row

    client = SurgeShieldClient("http://localhost:8010", "surgeshield-demo")
    result = client.score(transaction_from_row(row))
    if result.blocked:
        decline(result.reasons)
    elif result.step_up:
        challenge(result.friction)
    else:
        approve()
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from dataclasses import dataclass


@dataclass
class ScoreResult:
    decision: str
    risk_100: int
    regime: str
    friction: str
    latency_ms: float
    reasons: list

    @classmethod
    def from_json(cls, data: dict) -> "ScoreResult":
        return cls(
            decision=str(data.get("decision") or ""),
            risk_100=int(data.get("risk_100") or 0),
            regime=str(data.get("regime") or ""),
            friction=str(data.get("friction") or ""),
            latency_ms=float(data.get("latency_ms") or 0),
            reasons=list(data.get("reasons") or []),
        )

    @property
    def approved(self) -> bool:
        return self.decision == "APPROVE"

    @property
    def step_up(self) -> bool:
        return self.decision == "STEP_UP"

    @property
    def blocked(self) -> bool:
        return self.decision == "BLOCK"


class SurgeShieldClient:
    def __init__(self, base_url: str, api_key: str, timeout_s: float = 2.0):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.timeout_s = timeout_s

    def _post(self, path: str, payload: dict) -> dict:
        request = urllib.request.Request(
            f"{self.base_url}{path}",
            data=json.dumps(payload).encode(),
            headers={"X-API-Key": self.api_key, "Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout_s) as response:
                return json.loads(response.read().decode())
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode()
            raise RuntimeError(f"SurgeShield {exc.code}: {detail}") from exc

    def score(self, transaction: dict) -> ScoreResult:
        return ScoreResult.from_json(self._post("/score?explain=false", transaction))

    def score_batch(self, transactions: list) -> list:
        body = self._post("/score/batch", {"transactions": transactions, "explain": False})
        return [ScoreResult.from_json(row) for row in body["decisions"]]


def transaction_from_row(row: dict) -> dict:
    """Map a credit-card CSV row (Time, V1-V28, Amount) onto POST /score."""
    if "v" in row and isinstance(row["v"], list):
        values = [float(item) for item in row["v"]]
    else:
        values = [float(row.get(f"V{i}", row.get(f"v{i}", 0.0))) for i in range(1, 29)]
    event = {
        "time": float(row.get("Time", row.get("time", 0.0))),
        "amount": float(row.get("Amount", row.get("amount", 0.0))),
        "v": values,
    }
    for src, dest in (("user_id", "user_id"), ("merchant_id", "merchant_id"), ("Class", "eval_label")):
        if row.get(src) is not None and row.get(src) != "":
            event[dest] = int(row[src]) if src == "Class" else str(row[src])
    return event


def _demo() -> None:
    client = SurgeShieldClient("http://localhost:8010", "surgeshield-demo")
    sample = {"Time": 86400, "Amount": 49.0, **{f"V{i}": 0.0 for i in range(1, 29)}}
    result = client.score(transaction_from_row(sample))
    print(f"Decision : {result.decision}")
    print(f"Risk     : {result.risk_100}")
    print(f"Regime   : {result.regime}")
    print(f"Friction : {result.friction}")
    print(f"Latency  : {result.latency_ms} ms")


if __name__ == "__main__":
    _demo()
