"""Load imported login, network, and ATM logs. Empty until a real file is present."""

from __future__ import annotations

import csv
import os
from pathlib import Path

import numpy as np

from ml.schema import ROOT

_STATE = {"kinds": set(), "login": set(), "network": [], "atm": []}


def directory() -> Path:
    raw = os.environ.get("SURGESHIELD_LOG_DIR")
    return Path(raw) if raw else ROOT / "data" / "logs"


def load(path: Path | None = None) -> dict:
    root = Path(path) if path is not None else directory()
    _STATE["kinds"] = set()
    _STATE["login"] = set()
    _STATE["network"] = []
    _STATE["atm"] = []
    for kind, reader in (("login", _login), ("network", _network), ("atm", _atm)):
        file = root / kind / "events.csv"
        if not file.exists():
            continue
        with file.open(newline="") as handle:
            rows = list(csv.DictReader(handle))
        _STATE["kinds"].add(kind)
        reader(rows)
    return summary()


def loaded_kinds() -> set:
    return set(_STATE["kinds"])


def login_hot(token: str | None) -> bool:
    return bool(token) and token in _STATE["login"]


def summary() -> dict:
    return {
        "kinds": sorted(_STATE["kinds"]),
        "login_accounts": len(_STATE["login"]),
        "network": list(_STATE["network"]),
        "atm": list(_STATE["atm"]),
    }


def _stamp(value) -> float:
    text = str(value or "").strip()
    try:
        return float(text)
    except ValueError:
        return 0.0


def _login(rows: list) -> None:
    by_user: dict[str, list] = {}
    for row in rows:
        user = row.get("user_id") or ""
        if not user:
            continue
        failed = str(row.get("success") or "").strip().lower() in {"0", "false", "no", "fail", "failed"}
        if failed:
            by_user.setdefault(user, []).append(_stamp(row.get("time")))
    hot = set()
    for user, stamps in by_user.items():
        stamps.sort()
        left = 0
        for right, stamp in enumerate(stamps):
            while stamp - stamps[left] > 600:
                left += 1
            if right - left + 1 >= 10:
                hot.add(user)
                break
    _STATE["login"] = hot


def _network(rows: list) -> None:
    totals: dict[str, float] = {}
    for row in rows:
        src = row.get("src") or ""
        if not src:
            continue
        try:
            totals[src] = totals.get(src, 0.0) + float(row.get("bytes") or 0)
        except ValueError:
            continue
    if not totals:
        return
    cut = float(np.quantile(list(totals.values()), 0.999))
    _STATE["network"] = [
        {"src": src, "bytes": int(total)}
        for src, total in sorted(totals.items(), key=lambda item: -item[1])
        if total > cut
    ][:20]


def _atm(rows: list) -> None:
    by_terminal: dict[str, list] = {}
    for row in rows:
        terminal = row.get("terminal_id") or ""
        if terminal:
            by_terminal.setdefault(terminal, []).append((_stamp(row.get("time")), str(row.get("event") or "").lower()))
    incidents = []
    for terminal, events in by_terminal.items():
        events.sort()
        for index, (stamp, name) in enumerate(events):
            if "dispense" not in name:
                continue
            earlier = [event for when, event in events[:index] if 0 <= stamp - when <= 30]
            if not any("card" in event for event in earlier):
                incidents.append({"terminal_id": terminal, "time": stamp, "event": name})
    _STATE["atm"] = incidents[:50]
