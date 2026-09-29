"""Bounded user and merchant memory. Keys are HMAC tokens, never raw ids."""

from __future__ import annotations

from collections import OrderedDict, defaultdict

from backend.app.geo import haversine_km

TRAVEL_KMH = 900.0
TRAVEL_MIN_KM = 300.0

CATEGORY_RISK = {
    "electronics": 0.7,
    "jewellery": 0.85,
    "jewelry": 0.85,
    "transfer": 0.6,
    "grocery": 0.15,
    "groceries": 0.15,
}


def category_risk(category: str) -> float:
    return float(CATEGORY_RISK.get((category or "").strip().lower(), 0.4))


class ProfileStore:
    def __init__(self, user_limit: int = 50_000, merchant_limit: int = 5_000):
        self.user_limit = user_limit
        self.merchant_limit = merchant_limit
        self.users: OrderedDict = OrderedDict()
        self.merchants: OrderedDict = OrderedDict()

    def reset(self) -> None:
        self.users.clear()
        self.merchants.clear()

    def _touch(self, store: OrderedDict, key: str, limit: int) -> dict:
        if key in store:
            store.move_to_end(key)
            return store[key]
        if len(store) >= limit:
            store.popitem(last=False)
        row = {
            "n": 0,
            "avg": 0.0,
            "merchants": defaultdict(int),
            "categories": defaultdict(int),
            "hours": defaultdict(int),
            "regions": defaultdict(int),
            "devices": defaultdict(int),
            "users": set(),
            "unique_n": 0,
            "times": [],
            "baseline": 0.15,
            "last": None,
            "peak_velocity": 0,
            "last_geo": None,
        }
        store[key] = row
        return row

    def summary(self, kind: str, token: str) -> dict | None:
        store = self.users if kind == "user" else self.merchants
        row = store.get(token)
        if row is None:
            return None

        def top(counts, n=5):
            return [{"name": name, "n": int(count)} for name, count in sorted(counts.items(), key=lambda item: item[1], reverse=True)[:n] if name]

        out = {
            "payments": int(row["n"]),
            "avg_amount": round(float(row["avg"]), 2),
            "categories": top(row["categories"]),
            "regions": top(row["regions"]),
            "hours": top(row["hours"], 24),
            "devices": len([name for name in row["devices"] if name]),
        }
        if kind == "user":
            out["merchants"] = len(row["merchants"])
            out["peak_velocity_60s"] = int(row.get("peak_velocity") or 0)
        else:
            out["unique_buyers"] = int(row.get("unique_n") or len(row.get("users") or ()))
        return out

    def _rate(self, row: dict, now: float) -> tuple:
        recent = [stamp for stamp in row.get("times") or [] if now - 60.0 <= stamp <= now]
        rate = len(recent) / 60.0
        baseline = float(row.get("baseline") or 0.15)
        return rate, baseline, rate / max(baseline, 0.05)

    def signals(
        self,
        user: str,
        merchant: str,
        amount: float,
        hour: int,
        category: str = "",
        region: str = "",
        device: str = "",
        now: float = 0.0,
        velocity: int = 0,
        lat=None,
        lon=None,
    ) -> dict:
        user_row = self.users.get(user) if user else None
        travel_km = 0.0
        travel_kmh = 0.0
        travel_minutes = 0.0
        previous = user_row.get("last_geo") if user_row else None
        if previous and lat is not None and lon is not None:
            travel_km = haversine_km(previous[0], previous[1], float(lat), float(lon))
            seconds = max(float(now) - float(previous[2]), 1.0)
            travel_minutes = seconds / 60.0
            travel_kmh = travel_km / (seconds / 3600.0)
        impossible = bool(travel_km >= TRAVEL_MIN_KM and travel_kmh > TRAVEL_KMH)
        merchant_row = self.merchants.get(merchant) if merchant else None
        visits = int(user_row["merchants"].get(merchant, 0)) if user_row else 0
        familiarity = min(1.0, visits / 4.0)
        if user_row and user_row["n"] >= 3 and user_row["avg"] > 0:
            ratio = float(amount) / float(user_row["avg"])
        else:
            ratio = 1.0
        new_user = (user_row is None) or user_row["n"] < 3
        known = bool(user_row and user_row["n"] >= 3)
        category_new = bool(known and category and user_row["categories"].get(category, 0) == 0)
        region_new = bool(known and region and user_row["regions"].get(region, 0) == 0)
        device_new = bool(known and device and user_row["devices"].get(device, 0) == 0)
        hour_share = 0.0
        if user_row and user_row["n"] >= 10:
            hour_share = user_row["hours"].get(int(hour), 0) / user_row["n"]
        hour_unusual = bool(user_row and user_row["n"] >= 10 and hour_share < 0.05)
        peak = int(user_row.get("peak_velocity") or 0) if user_row else 0
        velocity_vs_max = (float(velocity) / peak) if peak else 1.0

        merchant_n = int(merchant_row["n"]) if merchant_row else 0
        unique_n = int(merchant_row.get("unique_n") or 0) if merchant_row else 0
        unique_share = (unique_n / merchant_n) if merchant_n else 1.0
        if merchant_row and merchant_row["n"] >= 3 and merchant_row["avg"] > 0:
            ticket_ratio = float(amount) / float(merchant_row["avg"])
            avg_ticket = float(merchant_row["avg"])
        else:
            ticket_ratio = 1.0
            avg_ticket = float(amount)
        if merchant_row:
            _rate, _base, surge_ratio = self._rate(merchant_row, now)
        else:
            surge_ratio = 1.0
        return {
            "merchant_familiarity": round(familiarity, 4),
            "amount_ratio": round(ratio, 4),
            "new_user": new_user,
            "merchant_trending": bool(merchant_row and merchant_row["n"] >= 40),
            "category": category or "",
            "region": region or "",
            "device": device or "",
            "hour": int(hour),
            "category_new": category_new,
            "hour_unusual": hour_unusual,
            "region_new": region_new,
            "device_new": device_new,
            "velocity_vs_max": round(velocity_vs_max, 3),
            "merchant_n": merchant_n,
            "unique_users": unique_n,
            "unique_share": round(unique_share, 4),
            "merchant_surge_ratio": round(float(surge_ratio), 3),
            "avg_ticket": round(avg_ticket, 2),
            "ticket_ratio": round(ticket_ratio, 3),
            "category_risk": category_risk(category),
            "flash_sale": False,
            "travel_km": round(travel_km, 1),
            "travel_kmh": round(travel_kmh, 1),
            "travel_minutes": round(travel_minutes, 2),
            "impossible_travel": impossible,
            "device_users": 0,
            "device_farm": False,
        }

    def update(
        self,
        user: str,
        merchant: str,
        amount: float,
        hour: int,
        category: str = "",
        region: str = "",
        device: str = "",
        now: float = 0.0,
        velocity: int = 0,
        lat=None,
        lon=None,
    ) -> None:
        if user:
            row = self._touch(self.users, user, self.user_limit)
            if lat is not None and lon is not None:
                row["last_geo"] = (float(lat), float(lon), float(now))
            row["n"] += 1
            row["avg"] += (float(amount) - row["avg"]) / row["n"]
            if merchant:
                row["merchants"][merchant] += 1
            if category:
                row["categories"][category] += 1
            row["hours"][int(hour)] += 1
            if region:
                row["regions"][region] += 1
            if device:
                row["devices"][device] += 1
            row["peak_velocity"] = max(int(row.get("peak_velocity") or 0), int(velocity))
        if merchant:
            row = self._touch(self.merchants, merchant, self.merchant_limit)
            rate, baseline, _ratio = self._rate(row, now)
            last = row.get("last")
            dt = 0.0 if last is None else max(float(now) - float(last), 0.0)
            alpha = min(0.02, dt / 180.0)
            row["baseline"] = baseline + (rate - baseline) * alpha
            times = [stamp for stamp in row["times"] if now - stamp <= 120.0]
            times.append(float(now))
            row["times"] = times[-800:]
            row["last"] = float(now)
            row["n"] += 1
            row["avg"] += (float(amount) - row["avg"]) / row["n"]
            if user and user not in row["users"]:
                row["unique_n"] = int(row.get("unique_n") or 0) + 1
                if len(row["users"]) < 2000:
                    row["users"].add(user)
