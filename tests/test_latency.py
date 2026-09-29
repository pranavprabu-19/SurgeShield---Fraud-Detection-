"""Throughput check. Explainability is off, the same way checkout would skip it."""

import time

import pytest

from ml.schema import ARTIFACT_PATH

pytestmark = pytest.mark.skipif(not ARTIFACT_PATH.exists(), reason="train the model first")


def test_batch_throughput_clears_one_thousand_per_second():
    from backend.app.engine import Engine
    from backend.app.scenarios import build_scenario

    model = Engine(ARTIFACT_PATH)
    seed = build_scenario("normal")
    events = [seed[i % len(seed)] for i in range(1200)]
    # Give every copy a distinct timestamp so the ring buffer stays honest.
    for i, event in enumerate(events):
        event["time"] = 1000 + i * 0.01
        event["eval_label"] = None
    started = time.perf_counter()
    for event in events:
        model.score(event, explain=False)
    elapsed = time.perf_counter() - started
    tps = len(events) / elapsed
    assert tps >= 1000, f"only {tps:.0f} tx/s, p99={model.totals['latency_p99']}ms"
