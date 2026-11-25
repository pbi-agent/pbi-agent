from __future__ import annotations

import pytest

from pbi_agent.agent.session import compaction
from pbi_agent.config import Settings, effective_compact_threshold
from pbi_agent.models.messages import TokenUsage


@pytest.mark.parametrize(
    ("compact_threshold", "model", "override_model", "expected"),
    [
        (None, "gpt-5.3-codex", None, 244_800),
        (None, "unknown-model-for-tests", None, 180_000),
        (None, "unknown-model-for-tests", "gpt-5.3-codex", 244_800),
        (123_456, "gpt-5.3-codex", None, 123_456),
        (0, "gpt-5.3-codex", None, 0),
    ],
)
def test_effective_compact_threshold(
    compact_threshold: int | None,
    model: str,
    override_model: str | None,
    expected: int,
) -> None:
    settings = Settings(
        api_key="test", model=model, compact_threshold=compact_threshold
    )

    assert effective_compact_threshold(settings, override_model) == expected


@pytest.mark.parametrize(
    ("context_tokens", "expected"),
    [(244_799, False), (244_800, True)],
)
def test_should_auto_compact_triggers_at_ninety_percent_of_window(
    context_tokens: int,
    expected: bool,
) -> None:
    settings = Settings(api_key="test", model="gpt-5.3-codex")
    usage = TokenUsage()
    usage.context_tokens = context_tokens

    assert (
        compaction._should_auto_compact(
            session_usage=usage,
            settings=settings,
            store=None,
            session_id=None,
        )
        is expected
    )


def test_should_auto_compact_disabled_by_zero_threshold() -> None:
    settings = Settings(api_key="test", model="gpt-5.3-codex", compact_threshold=0)
    usage = TokenUsage()
    usage.context_tokens = 10_000_000

    assert not compaction._should_auto_compact(
        session_usage=usage,
        settings=settings,
        store=None,
        session_id=None,
    )
