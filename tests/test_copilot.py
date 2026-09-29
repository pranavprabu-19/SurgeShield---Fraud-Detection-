"""Guarded explanations. Decision ownership stays with the model."""

from backend.app.copilot import explain


def test_template_does_not_require_a_key(monkeypatch):
    monkeypatch.delenv("SURGESHIELD_LLM_KEY", raising=False)
    result = explain("BLOCK", "ATTACK", [{"text": "part of a tight burst"}])
    assert result["source"] == "template"
    assert result["decision_owner"] == "model"
    assert "BLOCK" in result["text"]
    assert "tight burst" in result["text"]
