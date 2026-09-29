"""Replay a scenario into a running SurgeShield API."""

from __future__ import annotations

import argparse
import json
import os
import time
import urllib.request

from backend.app.scenarios import build_scenario

API = os.environ.get("SURGESHIELD_API", "http://127.0.0.1:8000")
KEY = os.environ.get("SURGESHIELD_API_KEY", "surgeshield-demo")


def _post(path: str, payload=None):
    data = json.dumps(payload or {}).encode()
    request = urllib.request.Request(
        API + path,
        data=data,
        headers={"Content-Type": "application/json", "X-API-Key": KEY},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.loads(response.read().decode())


def _get(path: str):
    request = urllib.request.Request(
        API + path,
        headers={"X-API-Key": KEY},
        method="GET",
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.loads(response.read().decode())


def main():
    parser = argparse.ArgumentParser(description="Replay a SurgeShield scenario")
    parser.add_argument("--scenario", default="mixed", choices=["normal", "flash_sale", "bot_attack", "mixed"])
    parser.add_argument("--eps", type=float, default=40)
    parser.add_argument("--local", action="store_true", help="score in-process instead of over HTTP")
    args = parser.parse_args()
    events = build_scenario(args.scenario)
    if args.local:
        from backend.app.engine import Engine
        from ml.schema import ARTIFACT_PATH

        model = Engine(ARTIFACT_PATH)
        model.scenario = args.scenario
        last = None
        for event in events:
            last = model.score(event, explain=False)
        print(json.dumps({"regime": last["regime"], "totals": last["totals"]}, indent=2))
        return
    _post("/simulate/reset")
    print(_post("/simulate", {"scenario": args.scenario, "events_per_second": args.eps}))
    time.sleep(len(events) / args.eps + 1)
    print(json.dumps(_get("/regime"), indent=2))


if __name__ == "__main__":
    main()
