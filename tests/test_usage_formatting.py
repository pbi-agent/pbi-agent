from __future__ import annotations

import json

import pytest

from pbi_agent.models.messages import (
    ModelCatalog,
    TokenUsage,
    _pricing_for_model,
    context_window_for_model,
)
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


def test_unknown_model_returns_zero_cost() -> None:
    """Unknown models should have zero pricing so cost displays as $0."""
    usage = TokenUsage(model="totally-unknown-model-xyz")
    usage.add(
        TokenUsage(
            input_tokens=1_000_000,
            output_tokens=1_000_000,
            model="totally-unknown-model-xyz",
        )
    )
    assert usage.estimated_cost_usd == 0.0


def test_known_model_pricing() -> None:
    pricing = _pricing_for_model("gpt-5.3-codex")
    assert pricing == (1.75, 1.75, 1.75, 0.175, 14.00)


def test_prefix_matching() -> None:
    pricing = _pricing_for_model("gpt-5.3-codex-some-variant")
    assert pricing == (1.75, 1.75, 1.75, 0.175, 14.00)

    ctx = context_window_for_model("gpt-5.3-codex-some-variant")
    assert ctx == 1_047_576


def test_unknown_model_context_window_returns_default() -> None:
    assert context_window_for_model("totally-unknown-model-xyz") == 200_000


def test_user_override_catalog(tmp_path, monkeypatch) -> None:
    """User overrides in ~/.pbi-agent/model_catalog.json take precedence."""
    user_catalog = {
        "models": {
            "my-custom-model": {
                "context_window": 999_999,
                "pricing": {
                    "input": 10.0,
                    "cache_write_5m": 10.0,
                    "cache_write_1h": 10.0,
                    "cache_hit": 1.0,
                    "output": 50.0,
                },
            }
        }
    }
    pbi_dir = tmp_path / ".pbi-agent"
    pbi_dir.mkdir()
    (pbi_dir / "model_catalog.json").write_text(json.dumps(user_catalog))

    monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path)
    catalog = ModelCatalog()

    assert catalog.get_context_window("my-custom-model") == 999_999
    assert catalog.get_pricing("my-custom-model") == (10.0, 10.0, 10.0, 1.0, 50.0)
    # Bundled models should still be available
    assert catalog.get_pricing("gpt-5.3-codex") == (1.75, 1.75, 1.75, 0.175, 14.00)
