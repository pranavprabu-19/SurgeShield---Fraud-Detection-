from backend.app.regime import RegimeDetector


def _snap(**kwargs):
    base = {
        "vol_z": 0,
        "psi": 0,
        "tightness": 0.1,
        "dominance": 0.1,
        "count_60": 10,
        "probe": 0,
        "mean_risk": 0.01,
        "attacked_segment": None,
    }
    base.update(kwargs)
    return base


def test_flash_sale_becomes_surge_not_attack():
    detector = RegimeDetector(dwell=3)
    snap = _snap(vol_z=6, psi=0.02, tightness=0.2, count_60=400)
    states = [detector.update(snap) for _ in range(5)]
    assert "SURGE" in states
    assert "ATTACK" not in states


def test_tight_probe_becomes_attack():
    detector = RegimeDetector(dwell=3)
    snap = _snap(vol_z=2, tightness=0.9, dominance=0.8, count_60=40, probe=0.8, attacked_segment=3, mean_risk=0.6)
    states = [detector.update(snap) for _ in range(4)]
    assert states[-1] == "ATTACK"
    assert detector.attacked_segment == 3


def test_recovery_after_attack():
    detector = RegimeDetector(dwell=2)
    attack = _snap(tightness=0.9, dominance=0.8, count_60=30, probe=0.7, attacked_segment=1)
    calm = _snap()
    for _ in range(2):
        detector.update(attack)
    assert detector.state == "ATTACK"
    for _ in range(2):
        detector.update(calm)
    assert detector.state == "RECOVERY"
