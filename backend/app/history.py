"""Bounded per-entity transaction history and investigation cases. Keys are HMAC tokens."""

from __future__ import annotations

import threading
import time
from collections import Counter, OrderedDict, deque

CASE_FLAGS = 2
CASE_STATUSES = {"OPEN", "APPROVED", "DECLINED", "ESCALATED", "VERIFY_REQUESTED"}


def _event(result: dict) -> dict:
    return {
        "id": result["id"],
        "t": time.time(),
        "decision": result["decision"],
        "score": result["score"],
        "risk_100": result.get("risk_100"),
        "amount": result["amount"],
        "regime": result["regime"],
        "phase": result.get("phase") or "",
        "region": result.get("region") or "",
        "category": result.get("category") or "",
        "lat": result.get("lat"),
        "lon": result.get("lon"),
        "geo_source": result.get("geo_source") or "unavailable",
        "device_token": result.get("device_token") or "",
        "user_token": result.get("user_token") or "",
        "merchant_token": result.get("merchant_token") or "",
        "review_id": result.get("review_id"),
        "eval_label": result.get("eval_label"),
        "reasons": [note.get("text") for note in (result.get("reasons") or [])[:4] if note.get("text")],
        "features": [note.get("feature") for note in (result.get("reasons") or []) if note.get("feature")],
    }


class History:
    def __init__(self, user_limit: int = 5_000, user_depth: int = 40, merchant_limit: int = 1_000, merchant_depth: int = 200):
        self.limits = {"user": (user_limit, user_depth), "merchant": (merchant_limit, merchant_depth)}
        self.stores = {"user": OrderedDict(), "merchant": OrderedDict()}
        self.cases: OrderedDict = OrderedDict()
        self._lock = threading.Lock()

    def reset(self) -> None:
        with self._lock:
            for store in self.stores.values():
                store.clear()
            self.cases.clear()

    def _row(self, kind: str, token: str) -> dict:
        store = self.stores[kind]
        limit, depth = self.limits[kind]
        if token in store:
            store.move_to_end(token)
            return store[token]
        if len(store) >= limit:
            evicted, _ = store.popitem(last=False)
            case = self.cases.get(f"{kind}-{evicted}")
            if case and case["status"] == "OPEN" and not case["notes"]:
                self.cases.pop(f"{kind}-{evicted}", None)
        row = {"events": deque(maxlen=depth), "n": 0, "flags": 0, "amount": 0.0, "blocked": 0.0, "first_t": time.time(), "features": Counter()}
        store[token] = row
        return row

    def record(self, result: dict) -> None:
        event = _event(result)
        flagged = event["decision"] != "APPROVE"
        with self._lock:
            for kind, token in (("user", event["user_token"]), ("merchant", event["merchant_token"])):
                if not token:
                    continue
                row = self._row(kind, token)
                row["events"].appendleft(event)
                row["n"] += 1
                row["amount"] += float(event["amount"])
                if flagged:
                    row["flags"] += 1
                    row["features"].update(event["features"])
                if event["decision"] == "BLOCK":
                    row["blocked"] += float(event["amount"])
                if kind == "user" and row["flags"] >= CASE_FLAGS:
                    self._open_case(kind, token, "repeated flags")
                elif kind == "merchant" and row["flags"] >= 5 and row["flags"] >= 0.2 * row["n"]:
                    self._open_case(kind, token, "merchant targeted")

    def _open_case(self, kind: str, token: str, why: str) -> dict:
        case_id = f"{kind}-{token}"
        case = self.cases.get(case_id)
        if case is None:
            case = {
                "id": case_id,
                "kind": kind,
                "token": token,
                "status": "OPEN",
                "opened_at": time.time(),
                "why": why,
                "notes": [],
                "actions": [],
            }
            self.cases[case_id] = case
            while len(self.cases) > 2_000:
                self.cases.popitem(last=False)
        return case

    def link_incidents(self, incidents: list) -> None:
        with self._lock:
            for inc in incidents:
                for token in inc.get("mules") or []:
                    if token in self.stores["user"]:
                        self._open_case("user", token, f"member of {inc['id']}")

    def list_cases(self, incidents: list, limit: int = 100) -> list:
        self.link_incidents(incidents)
        with self._lock:
            out = []
            for case in self.cases.values():
                row = self.stores[case["kind"]].get(case["token"])
                if row is None:
                    continue
                last = row["events"][0] if row["events"] else {}
                out.append(
                    {
                        **{key: case[key] for key in ("id", "kind", "token", "status", "opened_at", "why")},
                        "payments": row["n"],
                        "flags": row["flags"],
                        "amount": round(row["amount"], 2),
                        "blocked": round(row["blocked"], 2),
                        "max_risk": max((event.get("risk_100") or 0) for event in row["events"]) if row["events"] else 0,
                        "last_decision": last.get("decision"),
                        "last_region": last.get("region"),
                        "last_phase": last.get("phase"),
                        "top_signals": [name for name, _ in row["features"].most_common(3)],
                        "notes": len(case["notes"]),
                    }
                )
        out.sort(key=lambda item: (item["status"] != "OPEN", -item["max_risk"], -item["flags"]))
        return out[:limit]

    def known(self, kind: str, token: str) -> bool:
        with self._lock:
            return token in self.stores.get(kind, {})

    def watchlist(self, limit: int = 12) -> list:
        with self._lock:
            rows = []
            for kind, store in self.stores.items():
                for token, row in store.items():
                    if row["flags"]:
                        rows.append({"kind": kind, "token": token, "flags": row["flags"], "payments": row["n"], "amount": round(row["amount"], 2)})
        rows.sort(key=lambda item: (-item["flags"], -item["amount"]))
        return rows[:limit]

    def top_merchants(self, limit: int = 10) -> list:
        with self._lock:
            rows = [
                {
                    "token": token,
                    "payments": row["n"],
                    "flags": row["flags"],
                    "amount": round(row["amount"], 2),
                    "blocked": round(row["blocked"], 2),
                    "flag_rate": round(row["flags"] / row["n"], 4) if row["n"] else 0.0,
                    "category": next((event["category"] for event in row["events"] if event["category"]), ""),
                }
                for token, row in self.stores["merchant"].items()
            ]
        rows.sort(key=lambda item: -item["payments"])
        return rows[:limit]

    def entity(self, kind: str, token: str) -> dict | None:
        with self._lock:
            row = self.stores.get(kind, {}).get(token)
            if row is None:
                return None
            events = list(row["events"])
            case = self.cases.get(f"{kind}-{token}")
            case = {**case, "notes": list(case["notes"]), "actions": list(case["actions"])} if case else None
            summary = {
                "payments": row["n"],
                "flags": row["flags"],
                "amount": round(row["amount"], 2),
                "blocked": round(row["blocked"], 2),
                "first_seen": row["first_t"],
                "signals": [{"name": name, "n": n} for name, n in row["features"].most_common(8)],
            }
        other = "merchant_token" if kind == "user" else "user_token"
        counterparts = Counter(event[other] for event in events if event[other])
        geo = [
            {
                "lat": event["lat"],
                "lon": event["lon"],
                "region": event["region"],
                "decision": event["decision"],
                "amount": event["amount"],
                "source": event["geo_source"],
                "id": event["id"],
            }
            for event in events
            if event["lat"] is not None and event["lon"] is not None
        ]
        return {
            "kind": kind,
            "token": token,
            "summary": summary,
            "history": events,
            "geo": geo,
            "counterparts": [{"token": name, "n": n} for name, n in counterparts.most_common(10)],
            "case": case,
        }

    def act(self, case_id: str, action: str, note: str = "", status: str | None = None) -> dict | None:
        with self._lock:
            case = self.cases.get(case_id)
            if case is None:
                kind, _, token = case_id.partition("-")
                if kind not in self.stores or token not in self.stores[kind]:
                    return None
                case = self._open_case(kind, token, "opened by analyst")
            entry = {"t": time.time(), "action": action, "note": note[:500]}
            if action == "NOTE":
                case["notes"].append(entry)
            else:
                case["actions"].append(entry)
                if status in CASE_STATUSES:
                    case["status"] = status
                if action in {"APPROVE", "DECLINE"} and note:
                    case["why"] = note[:500]
            return {**case, "notes": list(case["notes"]), "actions": list(case["actions"])}

    def latest_open_review(self, kind: str, token: str, open_ids: set) -> int | None:
        with self._lock:
            row = self.stores.get(kind, {}).get(token)
            if row is None:
                return None
            for event in row["events"]:
                if event.get("review_id") and event["review_id"] in open_ids:
                    return int(event["review_id"])
        return None
