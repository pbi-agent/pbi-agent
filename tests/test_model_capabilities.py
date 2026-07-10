import pytest

from pbi_agent.models.capabilities import (
    ModelReasoningCapabilities,
    reasoning_capabilities_for_model,
)


def test_openai_reasoning_capabilities_are_model_specific() -> None:
    assert reasoning_capabilities_for_model(
        "openai", "gpt-5.6-sol"
    ) == ModelReasoningCapabilities(
        efforts=("none", "low", "medium", "high", "xhigh", "max"),
        modes=("standard", "pro"),
    )
    assert reasoning_capabilities_for_model(
        "openai", "gpt-5.4-pro-2026-03-05"
    ) == ModelReasoningCapabilities(efforts=("medium", "high", "xhigh"))
    assert reasoning_capabilities_for_model(
        "openai", "gpt-5.1-2025-11-13"
    ) == ModelReasoningCapabilities(efforts=("none", "low", "medium", "high"))


@pytest.mark.parametrize(
    ("model_id", "efforts"),
    [
        ("gpt-5", ("minimal", "low", "medium", "high")),
        ("gpt-5-2025-08-07", ("minimal", "low", "medium", "high")),
        ("gpt-5-mini", ("minimal", "low", "medium", "high")),
        ("gpt-5-nano-2025-08-07", ("minimal", "low", "medium", "high")),
        ("gpt-5-pro", ("high",)),
        ("gpt-5-codex", ("low", "medium", "high")),
        ("gpt-5-codex-mini", ("medium", "high")),
        ("gpt-5.1-codex", ("low", "medium", "high")),
        ("gpt-5.1-codex-mini", ("medium", "high")),
        ("gpt-5.1-codex-max", ("low", "medium", "high", "xhigh")),
        ("gpt-5.2-codex", ("low", "medium", "high", "xhigh")),
        ("o1", ("low", "medium", "high")),
        ("o3-2025-04-16", ("low", "medium", "high")),
        ("o3-mini", ("low", "medium", "high")),
        ("o3-pro", ("high",)),
        ("o4-mini-2025-04-16", ("low", "medium", "high")),
    ],
)
def test_openai_legacy_reasoning_families_have_model_specific_efforts(
    model_id: str,
    efforts: tuple[str, ...],
) -> None:
    assert reasoning_capabilities_for_model(
        "openai", model_id
    ) == ModelReasoningCapabilities(efforts=efforts)


def test_reasoning_capabilities_are_scoped_by_provider() -> None:
    assert (
        reasoning_capabilities_for_model("chatgpt", "gpt-5.6-sol")
        == ModelReasoningCapabilities()
    )
    assert (
        reasoning_capabilities_for_model("openai", "custom-reasoning-model")
        == ModelReasoningCapabilities()
    )
