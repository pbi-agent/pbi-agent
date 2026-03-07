from __future__ import annotations

import pytest

from pbi_agent.tools.apply_diff import apply_diff


def test_apply_diff_create_mode_builds_new_file_content() -> None:
    diff = "+alpha\n+beta\n+gamma"

    result = apply_diff("", diff, mode="create")

    assert result == "alpha\nbeta\ngamma"


def test_apply_diff_update_mode_preserves_existing_newline_style() -> None:
    original = "alpha\r\nbeta\r\ngamma"
    diff = " alpha\n-beta\n+delta\n gamma"

    result = apply_diff(original, diff)

    assert result == "alpha\r\ndelta\r\ngamma"


def test_apply_diff_raises_for_context_mismatch() -> None:
    original = "alpha\nbeta\ngamma"
    diff = " alpha\n-missing\n+delta\n gamma"

    with pytest.raises(ValueError, match="Invalid Context"):
        apply_diff(original, diff)
