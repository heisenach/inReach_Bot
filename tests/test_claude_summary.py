from __future__ import annotations

import os
from types import SimpleNamespace

import pytest

from inreach_bot.llm.claude_summary import ClaudeSummaryError, summarize_report_with_claude


class _FakeMessages:
    def create(self, **kwargs):
        _ = kwargs
        return SimpleNamespace(content=[SimpleNamespace(text="  Stay conservative <b>today</b>.  ")])


class _FakeClient:
    def __init__(self, api_key: str):
        self.api_key = api_key
        self.messages = _FakeMessages()


def test_missing_api_key_raises(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    with pytest.raises(ClaudeSummaryError, match="ANTHROPIC_API_KEY"):
        summarize_report_with_claude({"a": 1}, 80)


def test_budget_zero_returns_empty(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test")
    assert summarize_report_with_claude({"a": 1}, 0) == ""


def test_success_normalizes_and_truncates(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test")

    import inreach_bot.llm.claude_summary as mod

    monkeypatch.setattr(mod.anthropic, "Anthropic", _FakeClient)
    out = summarize_report_with_claude({"a": 1}, 20)
    assert out == "Stay conservative..."