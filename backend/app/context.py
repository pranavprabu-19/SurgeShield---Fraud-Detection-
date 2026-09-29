"""In-memory ring of recent transactions. Updates are O(1) amortized."""

from __future__ import annotations

from collections import deque

from ml.schema import TIGHT_DIMS


class ContextStore:
    def __init__(self, horizon: float = 300.0, limit: int = 500):
        self.horizon = horizon
        self.limit = limit
        self.events: deque = deque()

    def reset(self) -> None:
        self.events.clear()

    def add(self, event: dict) -> None:
        self.events.append(event)
        self._evict(event["time"])
        while len(self.events) > self.limit:
            self.events.popleft()

    def _evict(self, now: float) -> None:
        cutoff = now - self.horizon
        while self.events and self.events[0]["time"] < cutoff:
            self.events.popleft()

    def tail(self, limit: int = 96) -> list:
        events = self.events
        n = len(events)
        start = max(0, n - limit)
        return [events[i] for i in range(start, n)]

    def window_counts(self, now: float, segment: int) -> tuple:
        """Counts and amount moments without copying three windows."""
        cut10 = now - 10.0
        cut60 = now - 60.0
        cut300 = now - 300.0
        c10 = c60 = c300 = same = 0
        sum60 = sumsq = sum300 = 0.0
        for event in reversed(self.events):
            t = event["time"]
            if t > now:
                continue
            if t < cut300:
                break
            amount = event["amount"]
            c300 += 1
            sum300 += amount
            if t >= cut60:
                c60 += 1
                sum60 += amount
                sumsq += amount * amount
                if event["segment"] == segment:
                    same += 1
                if t >= cut10:
                    c10 += 1
        return c10, c60, c300, sum60, sumsq, sum300, same

    def slice(self, now: float, seconds: float) -> list:
        cutoff = now - seconds
        # Deque is time-ordered. Walk from the right because windows are short.
        out = []
        for event in reversed(self.events):
            if event["time"] < cutoff:
                break
            if event["time"] > now:
                continue
            out.append(event)
        out.reverse()
        return out

    @staticmethod
    def snapshot(txn: dict, segment: int, user_token: str = "", merchant_token: str = "") -> dict:
        return {
            "time": float(txn["time"]),
            "amount": float(txn["amount"]),
            "segment": int(segment),
            "v": [float(x) for x in txn["v"][:TIGHT_DIMS]],
            "user": user_token,
            "merchant": merchant_token,
            "region": txn.get("region") or "",
            "device": txn.get("device") or "",
            "category": txn.get("category") or "",
            "self": False,
        }
