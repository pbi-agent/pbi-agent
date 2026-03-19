from __future__ import annotations

import pytest

from pbi_agent.models.messages import TokenUsage
from pbi_agent.ui.formatting import format_session_subtitle, format_usage_summary


def test_format_usage_summary_includes_sub_agent_breakdown() -> None:
    usage = TokenUsage(model="gpt-5")
    usage.add(TokenUsage(input_tokens=7, output_tokens=3, model="gpt-5"))
    usage.add_sub_agent(TokenUsage(input_tokens=2, output_tokens=1, model="gpt-5"))

    summary = format_usage_summary(usage, label="Turn")

    assert "main:" in summary
    assert "sub-agent:" in summary
    assert "13 tokens" in summary


def test_format_session_subtitle_includes_sub_agent_breakdown() -> None:
    usage = TokenUsage(input_tokens=7, output_tokens=0, model="gpt-5")
    usage.add_sub_agent(TokenUsage(input_tokens=2, output_tokens=1, model="gpt-5"))

    subtitle = format_session_subtitle(usage, reasoning_effort="xhigh")

    assert "gpt-5 (xhigh)" in subtitle
    assert "10 tok" in subtitle
    assert "main 7" in subtitle
    assert "sub 3" in subtitle


def test_estimated_cost_uses_sub_agent_model_pricing() -> None:
    usage = TokenUsage(model="gpt-5.4-2026-03-05")
    usage.add(
        TokenUsage(
            input_tokens=1_000_000,
            output_tokens=1_000_000,
            model="gpt-5.4-2026-03-05",
        )
    )
    usage.add_sub_agent(
        TokenUsage(
            input_tokens=1_000_000,
            output_tokens=1_000_000,
            model="gpt-5.3-codex",
        )
    )

    assert usage.estimated_cost_usd == pytest.approx(33.25)
