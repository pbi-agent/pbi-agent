"""Provider/model capability rules independent of discovery response shapes."""

from __future__ import annotations

from dataclasses import dataclass
from fnmatch import fnmatchcase


@dataclass(frozen=True, slots=True)
class ModelReasoningCapabilities:
    efforts: tuple[str, ...] = ()
    modes: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class _ModelCapabilityRule:
    provider_kind: str
    model_pattern: str
    reasoning: ModelReasoningCapabilities


_STANDARD_GPT_5_EFFORTS = ("none", "low", "medium", "high", "xhigh")
_PRO_GPT_5_EFFORTS = ("medium", "high", "xhigh")
_ORIGINAL_GPT_5_EFFORTS = ("minimal", "low", "medium", "high")
_O_SERIES_EFFORTS = ("low", "medium", "high")

# Keep more-specific model patterns before broader family patterns. This catalog
# is intentionally provider-aware so model capability rules for other backends
# can be added without coupling them to discovery response shapes.
_MODEL_CAPABILITY_RULES = (
    _ModelCapabilityRule(
        provider_kind="openai",
        model_pattern="gpt-5.6*",
        reasoning=ModelReasoningCapabilities(
            # The GPT-5.6 model reference advertises max in addition to the
            # standard GPT-5 reasoning effort values.
            efforts=("none", "low", "medium", "high", "xhigh", "max"),
            modes=("standard", "pro"),
        ),
    ),
    _ModelCapabilityRule(
        provider_kind="openai",
        model_pattern="gpt-5.5-pro*",
        reasoning=ModelReasoningCapabilities(efforts=_PRO_GPT_5_EFFORTS),
    ),
    _ModelCapabilityRule(
        provider_kind="openai",
        model_pattern="gpt-5.5*",
        reasoning=ModelReasoningCapabilities(efforts=_STANDARD_GPT_5_EFFORTS),
    ),
    _ModelCapabilityRule(
        provider_kind="openai",
        model_pattern="gpt-5.4-pro*",
        reasoning=ModelReasoningCapabilities(efforts=_PRO_GPT_5_EFFORTS),
    ),
    _ModelCapabilityRule(
        provider_kind="openai",
        model_pattern="gpt-5.4*",
        reasoning=ModelReasoningCapabilities(efforts=_STANDARD_GPT_5_EFFORTS),
    ),
    _ModelCapabilityRule(
        provider_kind="openai",
        model_pattern="gpt-5.2-codex*",
        reasoning=ModelReasoningCapabilities(
            efforts=("low", "medium", "high", "xhigh")
        ),
    ),
    _ModelCapabilityRule(
        provider_kind="openai",
        model_pattern="gpt-5.2-pro*",
        reasoning=ModelReasoningCapabilities(efforts=_PRO_GPT_5_EFFORTS),
    ),
    _ModelCapabilityRule(
        provider_kind="openai",
        model_pattern="gpt-5.2*",
        reasoning=ModelReasoningCapabilities(efforts=_STANDARD_GPT_5_EFFORTS),
    ),
    _ModelCapabilityRule(
        provider_kind="openai",
        model_pattern="gpt-5.1-codex-max*",
        reasoning=ModelReasoningCapabilities(
            efforts=("low", "medium", "high", "xhigh")
        ),
    ),
    _ModelCapabilityRule(
        provider_kind="openai",
        model_pattern="gpt-5.1-codex-mini*",
        reasoning=ModelReasoningCapabilities(efforts=("medium", "high")),
    ),
    _ModelCapabilityRule(
        provider_kind="openai",
        model_pattern="gpt-5.1-codex*",
        reasoning=ModelReasoningCapabilities(efforts=("low", "medium", "high")),
    ),
    _ModelCapabilityRule(
        provider_kind="openai",
        model_pattern="gpt-5.1*",
        reasoning=ModelReasoningCapabilities(efforts=("none", "low", "medium", "high")),
    ),
    _ModelCapabilityRule(
        provider_kind="openai",
        model_pattern="gpt-5-codex-mini*",
        reasoning=ModelReasoningCapabilities(efforts=("medium", "high")),
    ),
    _ModelCapabilityRule(
        provider_kind="openai",
        model_pattern="gpt-5-codex*",
        reasoning=ModelReasoningCapabilities(efforts=("low", "medium", "high")),
    ),
    _ModelCapabilityRule(
        provider_kind="openai",
        model_pattern="gpt-5-pro*",
        reasoning=ModelReasoningCapabilities(efforts=("high",)),
    ),
    _ModelCapabilityRule(
        provider_kind="openai",
        model_pattern="gpt-5-mini*",
        reasoning=ModelReasoningCapabilities(efforts=_ORIGINAL_GPT_5_EFFORTS),
    ),
    _ModelCapabilityRule(
        provider_kind="openai",
        model_pattern="gpt-5-nano*",
        reasoning=ModelReasoningCapabilities(efforts=_ORIGINAL_GPT_5_EFFORTS),
    ),
    _ModelCapabilityRule(
        provider_kind="openai",
        model_pattern="gpt-5-20*",
        reasoning=ModelReasoningCapabilities(efforts=_ORIGINAL_GPT_5_EFFORTS),
    ),
    _ModelCapabilityRule(
        provider_kind="openai",
        model_pattern="gpt-5",
        reasoning=ModelReasoningCapabilities(efforts=_ORIGINAL_GPT_5_EFFORTS),
    ),
    _ModelCapabilityRule(
        provider_kind="openai",
        model_pattern="o4-mini-20*",
        reasoning=ModelReasoningCapabilities(efforts=_O_SERIES_EFFORTS),
    ),
    _ModelCapabilityRule(
        provider_kind="openai",
        model_pattern="o4-mini",
        reasoning=ModelReasoningCapabilities(efforts=_O_SERIES_EFFORTS),
    ),
    _ModelCapabilityRule(
        provider_kind="openai",
        model_pattern="o3-pro*",
        reasoning=ModelReasoningCapabilities(efforts=("high",)),
    ),
    _ModelCapabilityRule(
        provider_kind="openai",
        model_pattern="o3-mini*",
        reasoning=ModelReasoningCapabilities(efforts=_O_SERIES_EFFORTS),
    ),
    _ModelCapabilityRule(
        provider_kind="openai",
        model_pattern="o3-20*",
        reasoning=ModelReasoningCapabilities(efforts=_O_SERIES_EFFORTS),
    ),
    _ModelCapabilityRule(
        provider_kind="openai",
        model_pattern="o3",
        reasoning=ModelReasoningCapabilities(efforts=_O_SERIES_EFFORTS),
    ),
    _ModelCapabilityRule(
        provider_kind="openai",
        model_pattern="o1-pro*",
        reasoning=ModelReasoningCapabilities(efforts=("high",)),
    ),
    _ModelCapabilityRule(
        provider_kind="openai",
        model_pattern="o1-20*",
        reasoning=ModelReasoningCapabilities(efforts=_O_SERIES_EFFORTS),
    ),
    _ModelCapabilityRule(
        provider_kind="openai",
        model_pattern="o1",
        reasoning=ModelReasoningCapabilities(efforts=_O_SERIES_EFFORTS),
    ),
)


def reasoning_capabilities_for_model(
    provider_kind: str,
    model_id: str,
) -> ModelReasoningCapabilities:
    normalized_provider = provider_kind.strip().casefold()
    normalized_model = model_id.strip().casefold()
    for rule in _MODEL_CAPABILITY_RULES:
        if rule.provider_kind == normalized_provider and fnmatchcase(
            normalized_model, rule.model_pattern
        ):
            return rule.reasoning
    return ModelReasoningCapabilities()
