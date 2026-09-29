"""Three-way decisions. Thresholds move with the regime, and only for the attacked segment."""

from __future__ import annotations


def surge_shield_decision(
    score: float,
    regime: str,
    segment: int,
    attacked_segment,
    cfg: dict,
    suspicious: bool = False,
    merchant_hot: bool = False,
    threshold_offset: float = 0.0,
    human_score=None,
    context_step_up: bool = False,
) -> str:
    t_step = float(cfg["t_step"]) + threshold_offset
    t_block = float(cfg["t_block"]) + threshold_offset
    relief = float(cfg.get("surge_relief", 0.04))
    tighten = float(cfg.get("attack_tighten", 0.12))

    if regime == "SURGE" and segment != attacked_segment and not suspicious:
        t_block = min(0.995, t_block + relief)
        t_step = min(t_block - 0.01, t_step + relief / 2)
    hot = attacked_segment is None or segment == attacked_segment or merchant_hot
    if regime == "ATTACK" and hot:
        t_block = max(0.05, t_block - tighten)
        t_step = max(0.02, t_step - tighten)

    if score >= t_block:
        return "BLOCK"
    if score >= t_step:
        return "STEP_UP"
    # A loud but non-diverse burst is not a sale. Challenge it instead of approving quietly.
    if suspicious and hot and score >= t_step * 0.5:
        return "STEP_UP"
    if human_score is not None and float(human_score) < 35 and score < t_block:
        return "STEP_UP"
    if context_step_up:
        return "STEP_UP"
    return "APPROVE"


def static_decision(score: float, t_static: float) -> str:
    return "BLOCK" if score >= t_static else "APPROVE"


def friction_tier(decision: str, score: float, cfg: dict, profile: dict, amount: float, regime: str, attack_hot: bool = False) -> str:
    """Name the least-disruptive check for a decision that was already made."""
    del score, cfg
    if decision == "APPROVE":
        return "NONE"
    if decision == "BLOCK":
        return "BLOCKED"
    profile = profile or {}
    if profile.get("device_farm") or profile.get("impossible_travel") or profile.get("model_probe") or (regime == "ATTACK" and attack_hot):
        return "STEP_UP_AUTH"
    if float(amount) >= 10_000:
        return "OTP"
    known_device = not profile.get("new_user") and not profile.get("device_new")
    if known_device and regime != "ATTACK":
        return "DEVICE_CHECK"
    return "PUSH"


def safe_mode_decision(amount: float, night: float, tightness: float, count_60: int) -> str:
    if amount >= 2000 or (night > 0 and amount >= 800 and tightness >= 0.7 and count_60 >= 20):
        return "BLOCK"
    if night > 0 and amount >= 400:
        return "STEP_UP"
    return "APPROVE"
