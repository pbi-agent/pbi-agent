from __future__ import annotations

import pytest

from pbi_agent.tools.apply_diff import apply_diff, diff_line_numbers


def test_apply_diff_create_mode_builds_new_file_content() -> None:
    diff = "+alpha\n+beta\n+gamma"

    result = apply_diff("", diff, mode="create")

    assert result == "alpha\nbeta\ngamma"


def test_apply_diff_update_mode_preserves_existing_newline_style() -> None:
    original = "alpha\r\nbeta\r\ngamma"
    diff = " alpha\n-beta\n+delta\n gamma"

    result = apply_diff(original, diff)

    assert result == "alpha\r\ndelta\r\ngamma"


def test_diff_line_numbers_reports_real_update_offsets() -> None:
    original = "one\ntwo\nthree\nfour\nfive"
    diff = " three\n-four\n+FOUR\n five"

    result = diff_line_numbers(original, diff)

    assert result == [
        {"old": 3, "new": 3},
        {"old": 4, "new": None},
        {"old": None, "new": 4},
        {"old": 5, "new": 5},
    ]


def test_diff_line_numbers_tracks_line_delta_between_sections() -> None:
    original = "one\ntwo\nthree\nfour\nfive\nsix"
    diff = " one\n+one-and-half\n@@ four\n-five\n+FIVE"

    result = diff_line_numbers(original, diff)

    assert result == [
        {"old": 1, "new": 1},
        {"old": None, "new": 2},
        {"old": None, "new": None},
        {"old": 5, "new": None},
        {"old": None, "new": 6},
    ]


def test_diff_line_numbers_reports_create_offsets() -> None:
    diff = "+alpha\n+beta"

    result = diff_line_numbers("", diff, mode="create")

    assert result == [
        {"old": None, "new": 1},
        {"old": None, "new": 2},
    ]


def test_apply_diff_raises_for_context_mismatch() -> None:
    original = "alpha\nbeta\ngamma"
    diff = " alpha\n-missing\n+delta\n gamma"

    with pytest.raises(ValueError, match="Invalid Context"):
        apply_diff(original, diff)


def test_apply_diff_invalid_context_hints_for_literal_diff_prefix_lines() -> None:
    original = "- Apply-patch UI: old\n"
    diff = "- Apply-patch UI: old\n+- Apply-patch UI: new"

    with pytest.raises(ValueError) as exc_info:
        apply_diff(original, diff)

    message = str(exc_info.value)
    assert "Invalid Context" in message
    assert "first character of each diff line as the patch marker" in message
    assert "-- item" in message
    assert "+- item" in message
    assert " - item" in message
