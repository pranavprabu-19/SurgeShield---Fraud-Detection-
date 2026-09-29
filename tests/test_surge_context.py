from backend.app.surge_context import compose


def test_one_merchant_is_concentrated_and_missing_fields_stay_missing():
    rows = [{"time": i, "amount": 12.5, "merchant": "m1"} for i in range(8)]
    body = compose(rows)
    assert body["merchant_gini"] == 1.0
    assert body["geo_entropy"] is None
    assert body["device_diversity"] is None
    assert body["round_ratio"] == 0.0


def test_round_amounts_and_metronome():
    rows = [{"time": i * 0.2, "amount": 1000, "merchant": f"m{i}", "region": f"r{i}", "device": "bot"} for i in range(10)]
    body = compose(rows)
    assert body["round_ratio"] == 1.0
    assert body["timing_cv"] < 0.05
    assert body["device_diversity"] < 0.2
    assert body["verdict"] == "SUSPICIOUS"
