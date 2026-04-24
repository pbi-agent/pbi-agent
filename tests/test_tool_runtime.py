from __future__ import annotations

import json
import subprocess
from pathlib import Path
from unittest.mock import Mock

from pbi_agent.agent import tool_runtime
from pbi_agent.models.messages import ToolCall
from pbi_agent.tools import apply_patch as apply_patch_tool
from pbi_agent.tools import read_file as read_file_tool
from pbi_agent.tools import shell as shell_tool
from pbi_agent.tools.output import MAX_OUTPUT_CHARS
from pbi_agent.tools.types import ToolContext


def test_execute_tool_calls_reports_unknown_tool_error(monkeypatch) -> None:
    monkeypatch.setattr(tool_runtime, "get_tool_handler", lambda name: None)

    batch = tool_runtime.execute_tool_calls(
        [ToolCall(call_id="call_1", name="missing_tool", arguments={})],
        max_workers=1,
    )

    assert batch.had_errors is True
    assert len(batch.results) == 1
    assert json.loads(batch.results[0].output_json) == {
        "ok": False,
        "error": {
            "type": "unknown_tool",
            "message": "Tool 'missing_tool' is not registered.",
        },
        "tool": "missing_tool",
    }


def test_execute_tool_calls_rejects_invalid_json_arguments(monkeypatch) -> None:
    invoked = False

    def fake_handler(
        arguments: dict[str, object], context: ToolContext
    ) -> dict[str, object]:
        del arguments, context
        nonlocal invoked
        invoked = True
        return {}

    monkeypatch.setattr(tool_runtime, "get_tool_handler", lambda name: fake_handler)

    batch = tool_runtime.execute_tool_calls(
        [ToolCall(call_id="call_1", name="shell", arguments="[]")],
        max_workers=1,
    )

    assert invoked is False
    assert batch.had_errors is True
    assert json.loads(batch.results[0].output_json) == {
        "ok": False,
        "error": {
            "type": "invalid_arguments",
            "message": "tool arguments must decode to a JSON object",
        },
        "tool": "shell",
    }


def test_execute_tool_calls_wraps_success_payload_and_output_items(monkeypatch) -> None:
    seen: list[tuple[dict[str, object], bool]] = []

    def fake_handler(
        arguments: dict[str, object],
        context: ToolContext,
    ) -> dict[str, object]:
        seen.append((arguments, isinstance(context, ToolContext)))
        return {"echo": arguments["value"]}

    monkeypatch.setattr(tool_runtime, "get_tool_handler", lambda name: fake_handler)

    batch = tool_runtime.execute_tool_calls(
        [ToolCall(call_id="call_1", name="shell", arguments='{"value": 7}')],
        max_workers=1,
    )

    assert batch.had_errors is False
    assert seen == [({"value": 7}, True)]
    assert json.loads(batch.results[0].output_json) == {
        "ok": True,
        "result": {"echo": 7},
    }
    assert tool_runtime.to_function_call_output_items(batch.results) == [
        {
            "type": "function_call_output",
            "call_id": "call_1",
            "output": batch.results[0].output_json,
        }
    ]


def test_execute_tool_calls_wraps_handler_exceptions(monkeypatch) -> None:
    def fake_handler(
        arguments: dict[str, object],
        context: ToolContext,
    ) -> dict[str, object]:
        del arguments, context
        raise RuntimeError("boom")

    monkeypatch.setattr(tool_runtime, "get_tool_handler", lambda name: fake_handler)

    batch = tool_runtime.execute_tool_calls(
        [ToolCall(call_id="call_1", name="shell", arguments={})],
        max_workers=1,
    )

    assert batch.had_errors is True
    assert json.loads(batch.results[0].output_json) == {
        "ok": False,
        "error": {
            "type": "tool_execution_failed",
            "message": "boom",
        },
        "tool": "shell",
    }


def test_execute_tool_calls_serializes_truncated_shell_output(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    stdout = f"stdout-start-{'a' * (shell_tool.MAX_STDOUT_CHARS + 50)}-stdout-end"
    stderr = f"stderr-start-{'b' * (shell_tool.MAX_STDERR_CHARS + 50)}-stderr-end"

    def fake_run(*args: object, **kwargs: object) -> subprocess.CompletedProcess[bytes]:
        del args, kwargs
        return subprocess.CompletedProcess(
            args="python",
            returncode=0,
            stdout=stdout.encode("utf-8"),
            stderr=stderr.encode("utf-8"),
        )

    monkeypatch.setattr(shell_tool.subprocess, "run", fake_run)
    monkeypatch.setattr(
        tool_runtime,
        "get_tool_handler",
        lambda name: shell_tool.handle if name == "shell" else None,
    )

    batch = tool_runtime.execute_tool_calls(
        [ToolCall(call_id="call_1", name="shell", arguments={"command": "python"})],
        max_workers=1,
    )

    payload = json.loads(batch.results[0].output_json)
    result = payload["result"]

    assert payload["ok"] is True
    assert result["exit_code"] == 0
    assert result["stdout_truncated"] is True
    assert result["stderr_truncated"] is True
    assert len(result["stdout"]) <= shell_tool.MAX_STDOUT_CHARS
    assert len(result["stderr"]) <= shell_tool.MAX_STDERR_CHARS
    assert result["stdout"].startswith("stdout-start-")
    assert result["stdout"].endswith("-stdout-end")
    assert result["stderr"].startswith("stderr-start-")
    assert result["stderr"].endswith("-stderr-end")
    assert "chars omitted" in result["stdout"]
    assert "chars omitted" in result["stderr"]


def test_execute_tool_calls_serializes_truncated_apply_patch_error(
    monkeypatch,
) -> None:
    def raise_long_error(path: Path, diff: str | None) -> None:
        del path, diff
        raise ValueError(f"start-{'x' * (MAX_OUTPUT_CHARS + 200)}-end")

    monkeypatch.setattr(apply_patch_tool, "_create_file", raise_long_error)
    monkeypatch.setattr(
        tool_runtime,
        "get_tool_handler",
        lambda name: apply_patch_tool.handle if name == "apply_patch" else None,
    )

    batch = tool_runtime.execute_tool_calls(
        [
            ToolCall(
                call_id="call_1",
                name="apply_patch",
                arguments={
                    "operation_type": "create_file",
                    "path": "notes/example.txt",
                    "diff": "+hello",
                },
            )
        ],
        max_workers=1,
    )

    payload = json.loads(batch.results[0].output_json)
    result = payload["result"]

    assert payload["ok"] is True
    assert result["status"] == "failed"
    assert len(result["error"]) <= MAX_OUTPUT_CHARS
    assert result["error"].startswith("start-")
    assert result["error"].endswith("-end")
    assert "chars omitted" in result["error"]


def test_execute_tool_calls_serializes_tabular_read_file_output(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / "dataset.csv").write_text(
        "ordered_at,value\n2025-01-01,1\n2025-01-02,2\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(
        tool_runtime,
        "get_tool_handler",
        lambda name: read_file_tool.handle if name == "read_file" else None,
    )

    batch = tool_runtime.execute_tool_calls(
        [
            ToolCall(
                call_id="call_1",
                name="read_file",
                arguments={"path": "dataset.csv"},
            )
        ],
        max_workers=1,
    )

    payload = json.loads(batch.results[0].output_json)

    assert payload["ok"] is True
    assert payload["result"]["shape"] == {"rows": 2, "columns": 2}
    assert (
        payload["result"]["preview"] == "ordered_at,value\n2025-01-01,1\n2025-01-02,2\n"
    )


def test_execute_tool_calls_passes_runtime_context_to_handler(monkeypatch) -> None:
    captured_context: list[ToolContext] = []

    def fake_handler(
        arguments: dict[str, object],
        context: ToolContext,
    ) -> dict[str, object]:
        del arguments
        captured_context.append(context)
        return {"ok": True}

    monkeypatch.setattr(tool_runtime, "get_tool_handler", lambda name: fake_handler)

    batch = tool_runtime.execute_tool_calls(
        [ToolCall(call_id="call_1", name="shell", arguments={})],
        max_workers=1,
        context=ToolContext(sub_agent_depth=1),
    )

    assert batch.had_errors is False
    assert len(captured_context) == 1
    assert captured_context[0].sub_agent_depth == 1


def test_execute_tool_calls_records_observability_events(monkeypatch) -> None:
    tracer = Mock()

    def fake_handler(
        arguments: dict[str, object],
        context: ToolContext,
    ) -> dict[str, object]:
        del context
        return {"echo": arguments["value"]}

    monkeypatch.setattr(tool_runtime, "get_tool_handler", lambda name: fake_handler)

    batch = tool_runtime.execute_tool_calls(
        [ToolCall(call_id="call_1", name="shell", arguments={"value": 7})],
        max_workers=1,
        context=ToolContext(tracer=tracer),
    )

    assert batch.had_errors is False
    tracer.log_tool_call.assert_called_once()
    kwargs = tracer.log_tool_call.call_args.kwargs
    assert kwargs["tool_name"] == "shell"
    assert kwargs["tool_call_id"] == "call_1"
    assert kwargs["tool_input"] == {"value": 7}
    assert kwargs["success"] is True
