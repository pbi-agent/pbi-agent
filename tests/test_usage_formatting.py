from __future__ import annotations

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

    subtitle = format_session_subtitle(usage)

    assert "Session 10 tokens" in subtitle
    assert "main 7" in subtitle
    assert "sub-agent 3" in subtitle
