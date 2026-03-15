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


def test_overload_notice_outputs_to_stdout() -> None:
    display, stdout, _ = _display()

    display.overload_notice(wait_seconds=3.0, attempt=1, max_retries=2)

    assert "Provider overloaded. Retrying in 3s (1/2)" in stdout.getvalue()


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


def test_read_file_tool_summary_tolerates_invalid_line_arguments() -> None:
    display, stdout, _ = _display()

    display.function_start(1)
    display.function_result(
        "read_file",
        False,
        arguments={
            "path": "notes.txt",
            "start_line": "oops",
            "max_lines": None,
            "encoding": "utf-8",
        },
    )
    display.tool_group_end()

    output = stdout.getvalue()
    assert "notes.txt" in output
    assert "1–200" in output
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
    turn_usage = TokenUsage(input_tokens=8, output_tokens=3, model="gpt-5")

    display.session_usage(TokenUsage(model="gpt-5"))
    display.turn_usage(turn_usage, 5.0)
    display.session_usage(TokenUsage(input_tokens=8, output_tokens=3, model="gpt-5"))

    output = stdout.getvalue()
    assert "Usage" in output
    assert "Turn" in output
    # Single-turn: session subtitle is suppressed to avoid duplicate numbers
    assert "Session" not in output


def test_session_subtitle_shown_after_multiple_turns() -> None:
    display, stdout, _ = _display()
    turn1 = TokenUsage(input_tokens=4, output_tokens=2, model="gpt-5")
    turn2 = TokenUsage(input_tokens=4, output_tokens=1, model="gpt-5")
    session = TokenUsage(input_tokens=8, output_tokens=3, model="gpt-5")

    display.session_usage(TokenUsage(model="gpt-5"))
    display.turn_usage(turn1, 3.0)
    display.session_usage(session)
    display.turn_usage(turn2, 2.0)
    display.session_usage(session)

    output = stdout.getvalue()
    assert "Usage" in output
    assert "Turn" in output
    assert "11 tok" in output


def test_render_thinking_uses_title_as_body_when_text_missing() -> None:
    display, stdout, _ = _display()
    summary = (
        "I need to summarize the content, possibly mentioning if there are any "
        "continuities present. I'm also checking whether the hidden tail survives."
    )

    display.render_thinking(title=summary)

    output = stdout.getvalue()
    assert "Thinking..." in output
    assert "hidden tail survives." in output


def test_render_thinking_uses_title_as_body_when_text_is_ellipsis() -> None:
    display, stdout, _ = _display()
    summary = (
        "I need to summarize the content, possibly mentioning if there are any "
        "continuities present. I'm also checking whether the fallback beats dots."
    )

    display.render_thinking("...", title=summary)

    output = stdout.getvalue()
    assert "Thinking..." in output
    assert "fallback beats dots." in output


def test_render_thinking_renders_markdown_content() -> None:
    display, stdout, _ = _display()

    display.render_thinking("This has **bold** text.")

    output = stdout.getvalue()
    assert "bold" in output
    assert "**bold**" not in output


def test_sub_agent_section_renders_summary_status_and_logs() -> None:
    display, stdout, _ = _display()

    sub_display = display.begin_sub_agent(
        task_instruction="Inspect the workspace and summarize key files.",
        reasoning_effort="low",
    )
    sub_display.render_markdown("Child result")
    sub_display.finish_sub_agent(status="completed")

    output = stdout.getvalue()
    assert "sub_agent" in output
    assert "Inspect the workspace" in output
    assert "Child result" in output
    assert "completed" in output
