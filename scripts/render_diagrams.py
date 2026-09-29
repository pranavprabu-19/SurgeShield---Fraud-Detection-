"""Render the jury diagrams as PNGs. No browser required."""

from pathlib import Path

import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch

OUT = Path(__file__).resolve().parents[1] / "docs" / "img"
OUT.mkdir(parents=True, exist_ok=True)


def _box(ax, xy, text, color):
    patch = FancyBboxPatch(
        xy, 2.4, 0.8, boxstyle="round,pad=0.08,rounding_size=0.12",
        facecolor=color, edgecolor="#dbe7f5", linewidth=1,
    )
    ax.add_patch(patch)
    ax.text(xy[0] + 1.2, xy[1] + 0.4, text, ha="center", va="center", color="#07111f", fontsize=9, wrap=True)


def poster(name, title, rows):
    fig, ax = plt.subplots(figsize=(12, 7))
    fig.patch.set_facecolor("#07111f")
    ax.set_facecolor("#07111f")
    ax.set_xlim(0, 12)
    ax.set_ylim(0, 8)
    ax.axis("off")
    ax.text(0.4, 7.4, title, color="#3ee0c5", fontsize=18, fontweight="bold")
    y = 6.4
    for heading, body in rows:
        ax.text(0.5, y, heading, color="#ffb020", fontsize=12, fontweight="bold")
        ax.text(0.5, y - 0.45, body, color="#e8eef7", fontsize=11)
        y -= 1.15
    fig.tight_layout()
    fig.savefig(OUT / name, dpi=140)
    plt.close(fig)


def main():
    poster("01_ai_governance.png", "AI governance", [
        ("Versioned champion", "One artifact, one model card, one lineage hash of both CSVs."),
        ("Shadow, don't flip", "Logistic regression is scored on every payment and never decides."),
        ("Kill switch", "Rules keep checkout alive if the model is pulled."),
        ("Human queue", "Step-up and block can be released or upheld. The override is audited."),
        ("Drift tripwire", "PSI on recent scores. Alert at 0.2."),
    ])
    poster("02_responsible_ai.png", "Responsible AI developer", [
        ("Time before shuffle", "Fit, calibrate, and choose thresholds on earlier hours only."),
        ("The metric is not accuracy", "99.83% goes to the model that approves everyone."),
        ("No invented fraud", "Class weights, not SMOTE."),
        ("Say the gap", "Age, gender, and city are not in the file, so we do not claim fairness there."),
        ("Reproducible", "Seed 42, frozen test pass, unit tests on leakage and regime."),
    ])
    poster("03_data_privacy.png", "Data privacy and protection", [
        ("Already anonymized", "V1-V28 are PCA. We do not try to reverse them."),
        ("Minimize the log", "Audit stores decision, score, segment, amount. Not the vector."),
        ("Tokenize identifiers", "HMAC-SHA256. The raw id is not written."),
        ("Encrypt and expire", "AES-256-GCM at rest. Retention redacts and rebuilds the chain."),
        ("DPDP and RBI", "Purpose limitation, step-up authentication, incident kill switch."),
    ])
    poster("04_data_principles.png", "Data principles", [
        ("Reject bad rows", "Pydantic blocks negative amounts and short vectors."),
        ("No future", "A window at time t uses only payments before t."),
        ("No double approve", "The same fingerprint inside 30 seconds becomes a step-up."),
        ("Train statistics only", "Segment means come from the training slice."),
        ("Lineage on the artifact", "Seed, hashes, timestamp, model name."),
    ])
    poster("05_transparency_encryption.png", "Transparency and encryption", [
        ("Reasons", "TreeSHAP names the three features that moved the score."),
        ("Chain", "Each record hashes the previous record. Verify walks the chain."),
        ("Tamper is visible", "Flip one byte and verify points at that record."),
        ("AES-256-GCM", "The payload is ciphertext. The hash covers the ciphertext."),
        ("Access", "API key on the routes. TLS in front of any real deployment."),
    ])
    poster("06_prompt_principles.png", "Prompt and response principles", [
        ("The model decides", "The copilot is not in the scoring path."),
        ("Narrow input", "It receives the decision, the regime, and the reason codes."),
        ("Fixed instructions", "Do not invent features. Do not change the decision."),
        ("Temperature 0", "And a template when no key is configured."),
        ("Fallback is the default", "A jury laptop does not need an LLM account."),
    ])
    poster("07_documentation.png", "Documentation", [
        ("README", "Create a venv, train, start the API, start the dashboard."),
        ("Model card and datasheet", "What it is, what it is not, how it was split."),
        ("Threat model", "The ring we handle, and the takeover we do not claim."),
        ("OpenAPI", "/docs is generated from the FastAPI routes."),
        ("Pitch", "docs/PITCH.md is the five-minute script."),
    ])
    print("wrote", OUT)


if __name__ == "__main__":
    main()
