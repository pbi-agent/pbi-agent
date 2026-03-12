from __future__ import annotations

from pbi_agent.tools.output import MAX_OUTPUT_CHARS, bound_output


def test_bound_output_preserves_start_and_end_when_truncated() -> None:
    original = f"start-{'x' * (MAX_OUTPUT_CHARS + 200)}-end"

    bounded, truncated = bound_output(original)

    assert truncated is True
    assert len(bounded) <= MAX_OUTPUT_CHARS
    assert bounded.startswith("start-")
    assert bounded.endswith("-end")
    assert "chars omitted" in bounded


def test_bound_output_falls_back_to_simple_ellipsis_for_small_limits() -> None:
    bounded, truncated = bound_output("abcdef", limit=4)

    assert truncated is True
    assert bounded == "abc…"
