from __future__ import annotations

from typing import Any

import pytest

from pbi_agent.tools.model_output import (
    render_background_task_output,
    render_error,
    render_generic,
    render_shell_output,
    render_sub_agent_output,
    render_tool_output,
)
from pbi_agent.tools.types import ToolSpec


@pytest.mark.parametrize(
    ("payload", "expected"),
    [
        (
            {"stdout": "hi\n", "stderr": "", "exit_code": 0, "duration_ms": 12},
            "exit 0\nhi",
        ),
        (
            {"stdout": "", "stderr": "", "exit_code": 0, "duration_ms": 2400},
            "exit 0 · 2.4s\n(no output)",
        ),
        (
            {"stdout": "out", "stderr": "boom", "exit_code": 1, "duration_ms": 5},
            "exit 1\nout\n[stderr]\nboom",
        ),
        (
            {
                "stdout": "partial",
                "stderr": "",
                "exit_code": None,
                "timed_out": True,
                "duration_ms": 30000,
                "error": "Command timed out after 30000ms.",
            },
            "timeout 30.0s\npartial",
        ),
        (
            {
                "stdout": "",
                "stderr": "",
                "exit_code": 130,
                "interrupted": True,
                "error": "Command interrupted by user.",
            },
            "interrupted\n(no output)",
        ),
        (
            {"background": True, "task_id": "bg-1", "status": "running"},
            "background bg-1",
        ),
        (
            {
                "stdout": "a ... b",
                "stderr": "",
                "exit_code": 0,
                "stdout_truncated": True,
                "stdout_compressed": True,
                "raw_output_path": "/tmp/raw.log",
                "notice": "long prose that is not sent",
            },
            "exit 0\na ... b\n[compressed; truncated; full: /tmp/raw.log]",
        ),
        (
            {
                "stdout": "",
                "stderr": "boom",
                "exit_code": 1,
                "error": "Shell execution failed: boom",
            },
            "exit 1\nerror: Shell execution failed: boom\n[stderr]\nboom",
        ),
        (
            {"error": "'command' must be a non-empty string."},
            "error: 'command' must be a non-empty string.",
        ),
    ],
)
def test_render_shell_output(payload: dict[str, Any], expected: str) -> None:
    assert render_shell_output(payload) == expected


@pytest.mark.parametrize(
    ("payload", "expected"),
    [
        ("plain text", "plain text"),
        (None, "ok"),
        ({}, "ok"),
        (
            {"status": "completed", "path": "a.py", "skipped": None, "flag": False},
            "status: completed\npath: a.py",
        ),
        ({"count": 3, "ok": True}, "count: 3\nok: true"),
        ({"body": "line1\nline2"}, "body:\nline1\nline2"),
        ({"meta": {"a": 1, "b": [1, 2]}}, 'meta: {"a":1,"b":[1,2]}'),
        (
            {"results": [{"title": "T", "url": "u"}, {"title": "S", "url": "v"}]},
            'results:\n{"title":"T","url":"u"}\n{"title":"S","url":"v"}',
        ),
        ([{"a": 1}, "x"], '{"a":1}\nx'),
        ([], "(none)"),
    ],
)
def test_render_generic(payload: Any, expected: str) -> None:
    assert render_generic(payload) == expected


def test_render_tool_output_uses_spec_renderer_and_marks_errors() -> None:
    spec = ToolSpec(name="t", description="t", render_output=lambda _: "custom")

    assert render_tool_output({"x": 1}, spec=spec) == "custom"
    assert (
        render_tool_output({"message": "bad"}, is_error=True) == "error: message: bad"
    )
    assert render_tool_output({"a": 1, "b": 2}, is_error=True) == "error\na: 1\nb: 2"
    assert render_tool_output("error: already", is_error=True) == "error: already"


def test_render_error() -> None:
    assert render_error("unknown_tool", "Tool 'x' is not registered.") == (
        "error unknown_tool: Tool 'x' is not registered."
    )


@pytest.mark.parametrize(
    ("payload", "expected"),
    [
        ({"status": "completed", "final_output": "done"}, "done"),
        ({"status": "completed", "final_output": ""}, "(no output)"),
        (
            {"background": True, "task_id": "bg-9", "status": "running"},
            "background bg-9",
        ),
        (
            {"status": "failed", "error": {"type": "boom", "message": "bad"}},
            "error boom: bad",
        ),
    ],
)
def test_render_sub_agent_output(payload: dict[str, Any], expected: str) -> None:
    assert render_sub_agent_output(payload) == expected


def test_render_background_task_output_list_and_output() -> None:
    assert render_background_task_output({"tasks": []}) == "(no background tasks)"
    assert (
        render_background_task_output(
            {
                "tasks": [
                    {
                        "task_id": "bg-1",
                        "status": "running",
                        "exit_code": None,
                        "elapsed_seconds": 12.0,
                        "intent": "Run tests",
                        "kind": "shell",
                    },
                    {
                        "task_id": "bg-2",
                        "status": "completed",
                        "exit_code": 0,
                        "elapsed_seconds": 0.2,
                        "command": "echo hi",
                        "kind": "shell",
                    },
                ]
            }
        )
        == "background bg-1 · 12.0s — Run tests\nbg-2 exit 0 — echo hi"
    )
    assert (
        render_background_task_output(
            {
                "task_id": "bg-1",
                "status": "completed",
                "exit_code": 2,
                "elapsed_seconds": 3.5,
                "command": "make",
                "stdout": "built",
                "stderr": "",
            }
        )
        == "bg-1 exit 2 · 3.5s\nbuilt"
    )
