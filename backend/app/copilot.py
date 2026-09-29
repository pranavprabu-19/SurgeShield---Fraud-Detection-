"""The copilot explains a decision. It never makes one."""

from __future__ import annotations

import json
import os
import urllib.request

SYSTEM_PROMPT = (
    "You are SurgeShield's analyst copilot. Rewrite the given reason codes into two plain sentences "
    "for a bank reviewer. You must not change the decision, invent features, or ask for raw transactions, "
    "names, or account numbers. If the input is incomplete, say so."
)


def template_explanation(decision: str, regime: str, reasons: list) -> str:
    if not reasons:
        return f"Decision {decision} during {regime}. No single feature dominated the score."
    bits = [r["text"] for r in reasons[:3]]
    joined = "; ".join(bits)
    return (
        f"SurgeShield chose {decision} while the stream was in {regime}. "
        f"The main factors were: {joined}."
    )


def explain(decision: str, regime: str, reasons: list) -> dict:
    fallback = template_explanation(decision, regime, reasons)
    api_key = os.environ.get("SURGESHIELD_LLM_KEY", "").strip()
    base = os.environ.get("SURGESHIELD_LLM_BASE", "https://api.openai.com/v1").rstrip("/")
    model = os.environ.get("SURGESHIELD_LLM_MODEL", "gpt-4o-mini")
    if not api_key:
        return {"text": fallback, "source": "template", "decision_owner": "model"}

    payload = {
        "model": model,
        "temperature": 0,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {
                "role": "user",
                "content": json.dumps(
                    {"decision": decision, "regime": regime, "reason_codes": reasons},
                    default=str,
                ),
            },
        ],
    }
    request = urllib.request.Request(
        f"{base}/chat/completions",
        data=json.dumps(payload).encode(),
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=8) as response:
            body = json.loads(response.read().decode())
        text = body["choices"][0]["message"]["content"].strip()
        return {"text": text, "source": "llm", "decision_owner": "model"}
    except Exception:
        return {"text": fallback, "source": "template", "decision_owner": "model"}
