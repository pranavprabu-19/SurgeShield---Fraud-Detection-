"""Shared feature schema. Training and the live scorer must use this exact order."""

from pathlib import Path

SEED = 42
N_SEGMENTS = 8
V_COLS = [f"V{i}" for i in range(1, 29)]
# Tightness uses a subset so the ring buffer stays small.
TIGHT_DIMS = 8

STREAM_FEATURES = [
    "log_amount",
    "hour",
    "night",
    "cnt_10",
    "cnt_60",
    "cnt_300",
    "amt_mean_60",
    "amt_std_60",
    "amt_mean_300",
    "seg_share_60",
    "amt_z",
    "dist_centroid",
    "segment",
    "coord_proxy",
    "user_velocity_60",
    "merchant_fan_in_300",
]

FEATURE_NAMES = V_COLS + STREAM_FEATURES

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "train"
ARTIFACT_DIR = ROOT / "ml" / "artifacts"
ARTIFACT_PATH = ARTIFACT_DIR / "surgeshield.joblib"

# Friction cost of a hard decline, as a fraction of the ticket plus a floor.
FALSE_DECLINE_RATE = 0.08
FALSE_DECLINE_FLOOR = 5.0
# An OTP challenge is assumed to stop this share of fraud attempts.
STEP_UP_CATCH_RATE = 0.70
# OTP friction on a legitimate buyer (rupees of annoyance, not a lost sale).
STEP_UP_FRICTION = 1.0
