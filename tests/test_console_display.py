from __future__ import annotations

import io

import pytest

from pbi_agent.models.messages import TokenUsage
from pbi_agent.ui.console_display import ConsoleDisplay


def _display(
    *, verbose: bool = False
) -> tuple[ConsoleDisplay, io.StringIO, io.StringIO]:
    stdout = io.StringIO()
    stderr = io.StringIO()
    return (
        ConsoleDisplay(verbose=verbose, stdout=stdout, stderr=stderr),
        stdout,
        stderr,
    )


def test_render_markdown_outputs_to_stdout() -> None:
    display, stdout, _ = _display()

    display.render_markdown("# Hello\n\nBody text")

    output = stdout.getvalue()
    assert "Hello" in output
    assert "Body text" in output


def test_error_outputs_to_stderr() -> None:
    display, stdout, stderr = _display()

    display.error("boom")

    assert stdout.getvalue() == ""
    assert "Error: boom" in stderr.getvalue()


def test_tool_group_end_prints_tool_summary_lines() -> None:
    display, stdout, _ = _display()

    display.function_start(2)
    display.function_result(
        "shell",
        True,
        arguments={
            "command": "pwd",
            "working_directory": "/tmp/report",
            "timeout_ms": 5000,
        },
    )
    display.function_result(
        "apply_patch",
        False,
        arguments={
            "path": "report.md",
            "operation_type": "update",
            "diff": "--- a/report.md\n+++ b/report.md",
        },
    )
    display.tool_group_end()

    output = stdout.getvalue()
    assert "Tool calls (2)" in output
    assert "pwd" in output
    assert "/tmp/report" in output
    assert "report.md" in output
    assert "FAILED" in output


def test_user_prompt_raises_runtime_error() -> None:
    display, _, _ = _display()

    with pytest.raises(RuntimeError, match="does not support interactive user input"):
        display.user_prompt()


@pytest.mark.parametrize(
    ("verbose", "expected"),
    [(False, ""), (True, "debug message")],
)
def test_debug_honors_verbose_flag(verbose: bool, expected: str) -> None:
    display, stdout, _ = _display(verbose=verbose)

    display.debug("debug message")

    assert stdout.getvalue() == expected or expected in stdout.getvalue()


def test_usage_section_is_rendered_at_end() -> None:
    display, stdout, _ = _display()
    session_usage = TokenUsage(input_tokens=8, output_tokens=3, model="gpt-5")
    turn_usage = TokenUsage(input_tokens=8, output_tokens=3, model="gpt-5")

    display.session_usage(TokenUsage(model="gpt-5"))
    display.turn_usage(turn_usage, 5.0)
    display.session_usage(session_usage)

    output = stdout.getvalue()
    assert "Usage" in output
    assert "Turn" in output
    assert "Session 11 tokens" in output
