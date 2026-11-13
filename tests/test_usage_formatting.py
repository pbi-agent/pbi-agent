from __future__ import annotations

import json
from pathlib import Path

import pytest

from pbi_agent.display.formatting import (
    format_context_tooltip,
    format_session_subtitle,
    format_session_subtitle_parts,
    format_usage_summary,
)
from pbi_agent.models.messages import (
    ModelCatalog,
    TokenUsage,
    _pricing_for_model,
    context_window_for_model,
)


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


@pytest.mark.parametrize("model", ["gpt-6-astra", "GPT-6-ASTRA", "gpt-6-astra-variant"])
def test_gpt_6_astra_pricing(model: str) -> None:
    assert _pricing_for_model(model) == (10.00, 12.50, 12.50, 1.00, 50.00)
    usage = TokenUsage(
        model=model,
        input_tokens=4_000_000,
        cached_input_tokens=1_000_000,
        cache_write_tokens=1_000_000,
        cache_write_1h_tokens=1_000_000,
        output_tokens=1_000_000,
    )
    assert usage.estimated_cost_usd == pytest.approx(86.00)


def test_known_model_pricing() -> None:
    pricing = _pricing_for_model("gpt-5.6-sol")
    assert pricing == (4.00, 5.00, 5.00, 0.40, 20.00)

    pricing = _pricing_for_model("gpt-5.6-terra")
    assert pricing == (2.00, 2.50, 2.50, 0.20, 12.00)

    pricing = _pricing_for_model("gpt-5.6-luna")
    assert pricing == (0.20, 0.25, 0.25, 0.02, 1.20)

    pricing = _pricing_for_model("gpt-5.3-codex")
    assert pricing == (1.75, 1.75, 1.75, 0.175, 14.00)

    pricing = _pricing_for_model("gpt-5.5")
    assert pricing == (5.00, 5.00, 5.00, 0.50, 30.00)

    pricing = _pricing_for_model("gpt-5.5-pro")
    assert pricing == (30.00, 30.00, 30.00, 0.00, 180.00)

    pricing = _pricing_for_model("glm-5.2")
    assert pricing == (1.40, 1.40, 1.40, 0.26, 4.40)

    pricing = _pricing_for_model("minimax-m3")
    assert pricing == (0.30, 0.30, 0.30, 0.06, 1.20)


def test_prefix_matching() -> None:
    pricing = _pricing_for_model("gpt-5.6")
    assert pricing == (4.00, 5.00, 5.00, 0.40, 20.00)

    pricing = _pricing_for_model("gpt-5.6-terra-2026-04-23")
    assert pricing == (2.00, 2.50, 2.50, 0.20, 12.00)

    ctx = context_window_for_model("gpt-5.6-luna")
    assert ctx == 1_050_000

    pricing = _pricing_for_model("gpt-5.3-codex-some-variant")
    assert pricing == (1.75, 1.75, 1.75, 0.175, 14.00)

    ctx = context_window_for_model("gpt-5.3-codex-some-variant")
    assert ctx == 272_000

    pricing = _pricing_for_model("gpt-5.5-2026-04-23")
    assert pricing == (5.00, 5.00, 5.00, 0.50, 30.00)

    ctx = context_window_for_model("gpt-5.5-2026-04-23")
    assert ctx == 1_000_000

    pricing = _pricing_for_model("gpt-5.5-pro-2026-04-23")
    assert pricing == (30.00, 30.00, 30.00, 0.00, 180.00)

    ctx = context_window_for_model("gpt-5.5-pro-2026-04-23")
    assert ctx == 1_000_000


def test_model_matching_is_case_insensitive() -> None:
    pricing = _pricing_for_model("GLM-5.2")
    assert pricing == (1.40, 1.40, 1.40, 0.26, 4.40)

    pricing = _pricing_for_model("MINIMAX-M3")
    assert pricing == (0.30, 0.30, 0.30, 0.06, 1.20)

    pricing = _pricing_for_model("GPT-5.3-CODEX-SOME-VARIANT")
    assert pricing == (1.75, 1.75, 1.75, 0.175, 14.00)

    ctx = context_window_for_model("GPT-5.3-CODEX-SOME-VARIANT")
    assert ctx == 272_000


def test_unknown_model_context_window_returns_default() -> None:
    assert context_window_for_model("totally-unknown-model-xyz") == 200_000


def test_user_override_catalog(tmp_path, monkeypatch) -> None:
    """User overrides in ~/.pbi-agent/model_catalog.json take precedence."""
    user_catalog = {
        "models": {
            "MY-CUSTOM-MODEL": {
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
    assert catalog.get_context_window("My-Custom-Model") == 999_999
    assert catalog.get_pricing("my-custom-model") == (10.0, 10.0, 10.0, 1.0, 50.0)
    # Bundled models should still be available
    assert catalog.get_pricing("gpt-5.3-codex") == (1.75, 1.75, 1.75, 0.175, 14.00)


def test_flex_service_tier_halves_cost() -> None:
    """OpenAI flex tier should halve the estimated cost."""
    base_usage = TokenUsage(
        input_tokens=1_000_000,
        output_tokens=1_000_000,
        model="gpt-5.3-codex",
    )
    flex_usage = TokenUsage(
        input_tokens=1_000_000,
        output_tokens=1_000_000,
        model="gpt-5.3-codex",
        service_tier="flex",
    )
    assert flex_usage.estimated_cost_usd == pytest.approx(
        base_usage.estimated_cost_usd / 2
    )


def test_priority_service_tier_doubles_cost() -> None:
    """OpenAI priority tier should double the estimated cost."""
    base_usage = TokenUsage(
        input_tokens=1_000_000,
        output_tokens=1_000_000,
        model="gpt-5.3-codex",
    )
    priority_usage = TokenUsage(
        input_tokens=1_000_000,
        output_tokens=1_000_000,
        model="gpt-5.3-codex",
        service_tier="priority",
    )
    assert priority_usage.estimated_cost_usd == pytest.approx(
        base_usage.estimated_cost_usd * 2
    )


def test_gpt_5_6_cache_writes_use_the_documented_rate() -> None:
    usage = TokenUsage(
        input_tokens=100_000,
        cached_input_tokens=20_000,
        cache_write_tokens=30_000,
        output_tokens=10_000,
        model="gpt-5.6-sol",
    )

    assert usage.non_cached_input_tokens == 50_000
    assert usage.estimated_cost_usd == pytest.approx(0.558)


def test_default_service_tier_no_change() -> None:
    """'auto' and 'default' tiers should not change pricing."""
    base_usage = TokenUsage(
        input_tokens=1_000_000,
        output_tokens=1_000_000,
        model="gpt-5.3-codex",
    )
    for tier in ("auto", "default"):
        tier_usage = TokenUsage(
            input_tokens=1_000_000,
            output_tokens=1_000_000,
            model="gpt-5.3-codex",
            service_tier=tier,
        )
        assert tier_usage.estimated_cost_usd == pytest.approx(
            base_usage.estimated_cost_usd
        ), f"tier={tier} should not change cost"


def test_format_context_tooltip_with_known_model() -> None:
    usage = TokenUsage(context_tokens=100_000, model="gpt-5.3-codex")
    tip = format_context_tooltip(usage, model="gpt-5.3-codex")
    assert tip is not None
    assert "100,000" in tip
    assert "272,000" in tip
    assert "Utilization:" in tip


def test_format_context_tooltip_no_context_tokens() -> None:
    usage = TokenUsage(model="gpt-5.3-codex")
    assert format_context_tooltip(usage) is None


def test_format_context_tooltip_unknown_model() -> None:
    usage = TokenUsage(context_tokens=50_000, model="unknown-model")
    tip = format_context_tooltip(usage, model="unknown-model")
    assert tip is not None
    assert "50,000" in tip
    assert "200,000" in tip


def test_format_session_subtitle_parts_extracts_context_label() -> None:
    usage = TokenUsage(
        input_tokens=8,
        output_tokens=3,
        context_tokens=100_000,
        model="gpt-5.3-codex",
    )

    subtitle, context_label = format_session_subtitle_parts(
        usage,
        model="gpt-5.3-codex",
    )

    assert "gpt-5.3-codex" in subtitle
    assert "11 tok" in subtitle
    assert "ctx" not in subtitle
    assert context_label == "ctx 37%"


def test_format_session_subtitle_parts_uses_informal_workspace_path(
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        "pbi_agent.display.formatting.Path.cwd",
        lambda: Path("/mnt/c/Users/nbensaid/workspace/oai-ws"),
    )

    subtitle, _ = format_session_subtitle_parts(TokenUsage(model="gpt-5.3-codex"))

    assert "workspace/oai-ws" in subtitle


@pytest.mark.parametrize(
    ("model", "expected"),
    [
        ("gpt-6.1-sol", (2, 2.5, 2.5, 0.1, 10)),
        ("gpt-6.1-terra", (1, 1.25, 1.25, 0.05, 5)),
        ("gpt-6-luna", (0.1, 0.125, 0.125, 0.01, 0.5)),
        ("gpt-6-sol", (2, 2.5, 2.5, 0.2, 10)),
        ("gpt-5.6-sol", (4, 5, 5, 0.4, 20)),
        ("gpt-5.6-terra", (2, 2.5, 2.5, 0.2, 12)),
        ("gpt-5.6-luna", (0.2, 0.25, 0.25, 0.02, 1.2)),
        ("gpt-5.6", (4, 5, 5, 0.4, 20)),
        ("gpt-5.4-pro", (30, 30, 30, 0, 180)),
        ("gpt-5.2", (1.75, 1.75, 1.75, 0.175, 14)),
        ("gpt-5.2-pro", (21, 21, 21, 0, 168)),
        ("gpt-5.1", (1.25, 1.25, 1.25, 0.125, 10)),
        ("gpt-5", (1.25, 1.25, 1.25, 0.125, 10)),
        ("gpt-5-mini", (0.25, 0.25, 0.25, 0.025, 2)),
        ("gpt-5-nano", (0.05, 0.05, 0.05, 0.005, 0.4)),
        ("gpt-5-pro", (15, 15, 15, 0, 120)),
        ("gpt-4.1", (2, 2, 2, 0.5, 8)),
        ("gpt-4.1-mini", (0.4, 0.4, 0.4, 0.1, 1.6)),
        ("gpt-4o", (2.5, 2.5, 2.5, 1.25, 10)),
        ("gpt-4o-mini", (0.15, 0.15, 0.15, 0.075, 0.6)),
        ("o3-pro", (20, 20, 20, 0, 80)),
        ("o3", (2, 2, 2, 0.5, 8)),
        ("gpt-6-cyber", (20, 25, 25, 2, 100)),
        ("gpt-5.6-cyber", (12.5, 15.625, 15.625, 1.25, 75)),
        ("gpt-5.5-cyber-preview", (12.5, 12.5, 12.5, 1.25, 75)),
        ("gpt-6-rosalind", (15, 18.75, 18.75, 1.5, 75)),
        ("gpt-rosalind-research", (5, 5, 5, 0.5, 25)),
        ("gpt-rosalind-discovery", (5, 5, 5, 0.5, 25)),
        ("gpt-6-astra-law", (10, 10, 10, 1, 50)),
        ("chat-latest", (5, 5, 5, 0.5, 30)),
        ("gpt-5-search-api", (1.25, 1.25, 1.25, 0.125, 10)),
    ],
)
def test_supplied_standard_text_pricing(
    model: str, expected: tuple[float, float, float, float, float]
) -> None:
    for variant in (model, model.upper(), f"{model}-2026-11-13"):
        assert _pricing_for_model(variant) == expected
        usage = TokenUsage(
            model=variant,
            input_tokens=4_000_000,
            cached_input_tokens=1_000_000,
            cache_write_tokens=1_000_000,
            cache_write_1h_tokens=1_000_000,
            output_tokens=1_000_000,
        )
        assert usage.estimated_cost_usd == pytest.approx(sum(expected))


@pytest.mark.parametrize(
    ("model", "expected"),
    [
        ("claude-fable-5.2", (8, 10, 16, 0.2, 40)),
        ("claude-mythos-5.2", (8, 10, 16, 0.2, 40)),
        ("claude-fable-5.1", (10, 12.5, 20, 0.25, 50)),
        ("claude-mythos-5.1", (10, 12.5, 20, 0.25, 50)),
        ("claude-fable-5", (10, 12.5, 20, 1, 50)),
        ("claude-mythos-5", (10, 12.5, 20, 1, 50)),
        ("claude-opus-5.5", (4, 5, 8, 0.2, 20)),
        ("claude-opus-5", (5, 6.25, 10, 0.5, 25)),
        ("claude-opus-4.8", (5, 6.25, 10, 0.5, 25)),
        ("claude-opus-4.7", (5, 6.25, 10, 0.5, 25)),
        ("claude-opus-4.6", (5, 6.25, 10, 0.5, 25)),
        ("claude-opus-4.5", (5, 6.25, 10, 0.5, 25)),
        ("claude-opus-4.1", (15, 18.75, 30, 1.5, 75)),
        ("claude-opus-4", (15, 18.75, 30, 1.5, 75)),
        ("claude-sonnet-5.5", (2, 2.5, 4, 0.1, 10)),
        ("claude-sonnet-5", (2, 2.5, 4, 0.2, 10)),
        ("claude-sonnet-4.6", (3, 3.75, 6, 0.3, 15)),
        ("claude-sonnet-4.5", (3, 3.75, 6, 0.3, 15)),
        ("claude-sonnet-4", (3, 3.75, 6, 0.3, 15)),
        ("claude-haiku-5.5", (0.1, 0.125, 0.2, 0.01, 0.5)),
        ("claude-haiku-4.5", (1, 1.25, 2, 0.1, 5)),
    ],
)
def test_supplied_claude_standard_pricing(
    model: str, expected: tuple[float, float, float, float, float]
) -> None:
    # Haiku 5.5 uses its <=100k prompt rate; the catalog has no length tiers.
    for alias in dict.fromkeys((model, model.replace(".", "-"))):
        suffix = "20261113" if "." in model else "latest"
        for variant in (alias, alias.upper(), f"{alias}-{suffix}"):
            assert _pricing_for_model(variant) == expected
            usage = TokenUsage(
                model=variant,
                input_tokens=100_000,
                cached_input_tokens=25_000,
                cache_write_tokens=25_000,
                cache_write_1h_tokens=25_000,
                output_tokens=25_000,
            )
            assert usage.estimated_cost_usd == pytest.approx(sum(expected) * 0.025)


@pytest.mark.parametrize(
    ("model", "expected"),
    [
        ("claude-opus-5.5", (4, 5, 8, 0.2, 20)),
        ("claude-opus-4.6", (5, 6.25, 10, 0.5, 25)),
    ],
)
def test_dotted_claude_ids_resolve_to_canonical_entries(
    model: str, expected: tuple[float, float, float, float, float]
) -> None:
    assert _pricing_for_model(model) == expected
    assert context_window_for_model(model) == context_window_for_model(
        model.replace(".", "-")
    )


def test_bundled_catalog_has_unique_model_entries() -> None:
    def unique_keys(pairs: list[tuple[str, object]]) -> dict[str, object]:
        result: dict[str, object] = {}
        for key, value in pairs:
            assert key not in result, f"Duplicate JSON key: {key}"
            result[key] = value
        return result

    path = Path(__file__).parents[1] / "src/pbi_agent/models/model_catalog.json"
    data = json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=unique_keys)
    seen: dict[str, str] = {}
    for model in data["models"]:
        canonical = model.lower()
        if canonical.startswith("claude-"):
            canonical = canonical.replace(".", "-")
        assert canonical not in seen, (
            f"Duplicate models: {seen.get(canonical)}, {model}"
        )
        seen[canonical] = model
