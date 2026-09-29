"""Print the scorecard and prove the four scenarios separate surge from attack."""

from __future__ import annotations

import json

from backend.app.engine import Engine
from backend.app.scenarios import build_scenario
from ml.schema import ARTIFACT_PATH
import joblib


def main():
    artifact = joblib.load(ARTIFACT_PATH)
    print(json.dumps(artifact["metrics"], indent=2))
    for name in ("normal", "flash_sale", "bot_attack", "mixed"):
        model = Engine(ARTIFACT_PATH)
        model.scenario = name
        regimes = []
        last = None
        for event in build_scenario(name):
            last = model.score(event, explain=False)
            regimes.append(last["regime"])
        print(
            name,
            "regimes",
            sorted(set(regimes)),
            "fraud_stopped",
            round(last["totals"]["ss_fraud_caught_amt"], 1),
            "legit_declines",
            last["totals"]["ss_legit_blocked_n"],
            "static_declines",
            last["totals"]["st_legit_blocked_n"],
        )


if __name__ == "__main__":
    main()
