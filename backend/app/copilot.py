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


def _case_facts(view: dict, judgment: tuple) -> dict:
    summary = view.get("summary") or {}
    history = view.get("history") or []
    risks = [int(event.get("risk_100") or 0) for event in history]
    half = max(1, len(risks) // 2) if risks else 1
    recent = risks[:half] or [0]
    return {
        "kind": "customer" if view.get("kind") == "user" else "merchant",
        "payments": int(summary.get("payments") or 0),
        "flags": int(summary.get("flags") or 0),
        "amount": summary.get("amount") or 0,
        "peak_risk": max(risks) if risks else 0,
        "recent_risk": round(sum(recent) / len(recent)),
        "signals": [item.get("name") for item in (summary.get("signals") or [])[:4] if item.get("name")],
        "cities": sorted({event.get("region") for event in history if event.get("region")})[:4],
        "incidents": [item.get("id") for item in (view.get("incidents") or []) if item.get("id")],
        "verdict": judgment[0],
        "why": judgment[1],
    }


def template_case(facts: dict) -> str:
    signals = ", ".join(facts["signals"]) if facts["signals"] else "no repeated signal"
    cities = ", ".join(facts["cities"]) if facts["cities"] else "no city on file"
    linked = f" It appears in {', '.join(facts['incidents'])}." if facts["incidents"] else ""
    return (
        f"This {facts['kind']} has {facts['payments']} stored payments, {facts['flags']} of them challenged, "
        f"worth ₹{facts['amount']:.0f}. "
        f"Peak risk is {facts['peak_risk']} and the recent half averages {facts['recent_risk']}. "
        f"Signals: {signals}. Cities: {cities}.{linked} "
        f"History judgment: {facts['verdict']}, {facts['why']}. This summary does not change the decision."
    )


def summarize_case(view: dict, judgment: tuple) -> dict:
    """Three sentences from the stored history. The model still owns the decision."""
    facts = _case_facts(view, judgment)
    fallback = template_case(facts)
    api_key = os.environ.get("SURGESHIELD_LLM_KEY", "").strip()
    base = os.environ.get("SURGESHIELD_LLM_BASE", "https://api.openai.com/v1").rstrip("/")
    model = os.environ.get("SURGESHIELD_LLM_MODEL", "gpt-4o-mini")
    if not api_key:
        return {"text": fallback, "source": "template", "decision_owner": "model"}
    payload = {
        "model": model,
        "temperature": 0,
        "messages": [
            {
                "role": "system",
                "content": (
                    "You are SurgeShield's analyst copilot. Write exactly three sentences from the facts given. "
                    "Do not invent age, account age, names, cities, signals, or identifiers. "
                    "Do not change the verdict. Say that this summary does not change the decision."
                ),
            },
            {"role": "user", "content": json.dumps(facts, default=str)},
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
