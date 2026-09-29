"""Short silent backup of the scorecard, for when the live demo cannot start."""

from __future__ import annotations

import shutil
import subprocess
import textwrap
from pathlib import Path

import matplotlib.pyplot as plt
import joblib

from ml.schema import ARTIFACT_PATH, ROOT

OUT = ROOT / "docs" / "demo_backup.mp4"
FRAMES = ROOT / "docs" / "img" / "frames"


def _frame(path, title, body):
    fig, ax = plt.subplots(figsize=(12.8, 7.2))
    fig.patch.set_facecolor("#07111f")
    ax.set_facecolor("#07111f")
    ax.axis("off")
    ax.text(0.05, 0.82, title, color="#3ee0c5", fontsize=22, fontweight="bold", transform=ax.transAxes)
    ax.text(0.05, 0.62, body, color="#e8eef7", fontsize=16, transform=ax.transAxes, va="top")
    fig.savefig(path)
    plt.close(fig)


def main():
    metrics = joblib.load(ARTIFACT_PATH)["metrics"]
    test = metrics["test"]
    FRAMES.mkdir(parents=True, exist_ok=True)
    slides = [
        ("SurgeShield", "A flash sale and a bot ring look the same to a static threshold.\nThey do not look the same to the shape of the traffic."),
        ("The trap", f"Approving everyone is {test['always_legit_accuracy']*100:.2f}% accurate\nand stops zero fraud."),
        ("Held-out test", f"PR-AUC {test['pr_auc']:.3f}\nRecall at 0.1% FPR {test['recall_at_0_1pct_fpr']:.3f}\nROC-AUC {test['roc_auc']:.3f}"),
        ("Rupees", f"Test-set cost, static threshold {metrics['test_cost_static']['total_cost']:.0f}\nSurgeShield {metrics['test_cost_surgeshield']['total_cost']:.0f}\nSaved {metrics['money_saved_vs_static']:.0f}"),
        ("Trust", "Encrypted hash-chained audit log.\nKill switch to rules.\nThe copilot explains. It does not decide."),
        ("Detection", "Slow rings, card testing, fan-out and mule fan-in\nnow latch ATTACK. A flash sale still does not.\nThresholds move at most 0.03, and a person promotes any challenger."),
    ]
    for i, (title, body) in enumerate(slides):
        _frame(FRAMES / f"frame_{i:02d}.png", title, textwrap.fill(body, 60) if False else body)
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        print("ffmpeg missing; frames are in", FRAMES)
        return
    subprocess.check_call(
        [
            ffmpeg, "-y", "-framerate", "1/3",
            "-i", str(FRAMES / "frame_%02d.png"),
            "-c:v", "libx264", "-pix_fmt", "yuv420p",
            str(OUT),
        ]
    )
    print("wrote", OUT)


if __name__ == "__main__":
    main()
