"""Optional checkout telemetry. Missing fields stay missing. They never block alone."""

from __future__ import annotations


def human_score(telemetry: dict | None) -> float | None:
    if not telemetry:
        return None
    keys = ("session_duration_sec", "action_count", "typing_cps", "mouse_entropy", "action_interval_cv")
    if not any(key in telemetry and telemetry[key] is not None for key in keys):
        return None

    def session_band(value):
        if value is None:
            return None
        if value < 2:
            return 0
        if value < 10:
            return 20
        if value < 60:
            return 60
        return 90

    def action_band(value):
        if value is None:
            return None
        if value <= 1:
            return 5
        if value <= 3:
            return 40
        if value <= 15:
            return 85
        return 70

    def typing_band(value):
        if value is None:
            return None
        if value > 20:
            return 10
        if value > 12:
            return 50
        if value > 3:
            return 90
        return 70

    def timing_band(value):
        if value is None:
            return None
        if value < 0.05:
            return 10
        if value < 0.2:
            return 40
        return 85

    parts = {
        "session": (session_band(telemetry.get("session_duration_sec")), 0.25),
        "actions": (action_band(telemetry.get("action_count")), 0.25),
        "typing": (typing_band(telemetry.get("typing_cps")), 0.15),
        "mouse": (None if telemetry.get("mouse_entropy") is None else max(0.0, min(100.0, float(telemetry["mouse_entropy"]) * 100)), 0.15),
        "timing": (timing_band(telemetry.get("action_interval_cv")), 0.20),
    }
    present = [(score, weight) for score, weight in parts.values() if score is not None]
    if not present:
        return None
    weight = sum(item[1] for item in present)
    return round(sum(score * w for score, w in present) / weight, 2)
