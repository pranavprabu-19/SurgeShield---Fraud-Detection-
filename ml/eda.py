"""Charts the jury will see: imbalance, night-time fraud, amount shape."""

from __future__ import annotations

import json

import matplotlib.pyplot as plt
import pandas as pd

from ml.features import load_transactions
from ml.schema import ARTIFACT_DIR, DATA_DIR, ROOT


def run() -> dict:
    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    img = ROOT / "docs" / "img"
    img.mkdir(parents=True, exist_ok=True)
    train = load_transactions(DATA_DIR / "train.csv")
    test = load_transactions(DATA_DIR / "test.csv")
    train["hour"] = (train["Time"] // 3600) % 24
    by_hour = train.groupby("hour")["Class"].agg(count="size", fraud_rate="mean")

    summary = {
        "train_rows": int(len(train)),
        "test_rows": int(len(test)),
        "train_fraud": int(train["Class"].sum()),
        "test_fraud": int(test["Class"].sum()),
        "train_fraud_rate": float(train["Class"].mean()),
        "duplicates_dropped_train": int(train.attrs.get("dropped_duplicates", 0)),
        "duplicates_dropped_test": int(test.attrs.get("dropped_duplicates", 0)),
        "amount_median_legit": float(train.loc[train.Class == 0, "Amount"].median()),
        "amount_median_fraud": float(train.loc[train.Class == 1, "Amount"].median()),
        "always_legit_accuracy": float((train.Class == 0).mean()),
        "fraud_rate_by_hour": {str(int(i)): round(float(v), 5) for i, v in by_hour["fraud_rate"].items()},
    }
    (ARTIFACT_DIR / "eda_summary.json").write_text(json.dumps(summary, indent=2))

    fig, ax = plt.subplots(figsize=(8, 3.6))
    colors = ["#e11d48" if v > 0.004 else "#0f766e" for v in by_hour["fraud_rate"]]
    ax.bar(by_hour.index, by_hour["fraud_rate"] * 100, color=colors)
    ax.set_xlabel("Hour of the 48-hour window")
    ax.set_ylabel("Fraud rate (%)")
    ax.set_title("Fraud concentrates overnight")
    fig.tight_layout()
    fig.savefig(img / "fraud_by_hour.png", dpi=140)
    plt.close(fig)

    fig, ax = plt.subplots(figsize=(6, 3.6))
    ax.hist(train.loc[train.Class == 0, "Amount"].clip(0, 400), bins=40, alpha=0.7, label="Legit", color="#0f766e")
    ax.hist(train.loc[train.Class == 1, "Amount"].clip(0, 400), bins=40, alpha=0.7, label="Fraud", color="#e11d48")
    ax.set_xlabel("Amount (clipped at 400)")
    ax.set_title("Fraud tickets are smaller, not larger")
    ax.legend()
    fig.tight_layout()
    fig.savefig(img / "amount_by_class.png", dpi=140)
    plt.close(fig)
    print(json.dumps(summary, indent=2))
    return summary


if __name__ == "__main__":
    run()
