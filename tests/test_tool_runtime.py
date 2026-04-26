from __future__ import annotations

import json
import subprocess
import threading
from pathlib import Path
from unittest.mock import Mock

from pbi_agent.agent import tool_runtime
from pbi_agent.agent.tool_display import display_tool_results
from pbi_agent.models.messages import ToolCall
from pbi_agent.tools import apply_patch as apply_patch_tool
from pbi_agent.tools import read_file as read_file_tool
from pbi_agent.tools import shell as shell_tool
from pbi_agent.tools.output import MAX_OUTPUT_CHARS
from pbi_agent.tools.types import ToolContext, ToolResult


def _tool_call(call_id: str, name: str = "shell") -> ToolCall:
    return ToolCall(call_id=call_id, name=name, arguments={})


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


def test_execute_tool_calls_serial_callback_fires_after_each_call(monkeypatch) -> None:
    def fake_handler(arguments: dict[str, object], context: ToolContext) -> str:
        del arguments, context
        return threading.current_thread().name

    monkeypatch.setattr(tool_runtime, "get_tool_handler", lambda name: fake_handler)
    calls = [_tool_call("call_1"), _tool_call("call_2")]
    streamed: list[tuple[str, str]] = []

    batch = tool_runtime.execute_tool_calls(
        calls,
        max_workers=1,
        on_result=lambda call, result: streamed.append((call.call_id, result.call_id)),
    )

    assert streamed == [("call_1", "call_1"), ("call_2", "call_2")]
    assert [result.call_id for result in batch.results] == ["call_1", "call_2"]


def test_execute_tool_calls_parallel_callback_uses_completion_order(
    monkeypatch,
) -> None:
    first_started = threading.Event()
    allow_first_finish = threading.Event()

    def fake_handler(arguments: dict[str, object], context: ToolContext) -> str:
        del arguments, context
        call_id = threading.current_thread().name
        if "call_1" in call_id:
            first_started.set()
            assert allow_first_finish.wait(timeout=2)
            return "slow"
        assert first_started.wait(timeout=2)
        return "fast"

    # ThreadPoolExecutor does not name threads by call, so close over a queue
    # keyed by an argument that lets each worker decide its artificial delay.
    def keyed_handler(arguments: dict[str, object], context: ToolContext) -> str:
        del context
        if arguments["delay"] == "slow":
            first_started.set()
            assert allow_first_finish.wait(timeout=2)
            return "slow"
        assert first_started.wait(timeout=2)
        return "fast"

    del fake_handler
    monkeypatch.setattr(tool_runtime, "get_tool_handler", lambda name: keyed_handler)
    calls = [
        ToolCall(call_id="call_1", name="shell", arguments={"delay": "slow"}),
        ToolCall(call_id="call_2", name="shell", arguments={"delay": "fast"}),
    ]
    streamed: list[str] = []

    def on_result(call: ToolCall, result: ToolResult) -> None:
        streamed.append(call.call_id)
        if call.call_id == "call_2":
            allow_first_finish.set()

    batch = tool_runtime.execute_tool_calls(
        calls,
        max_workers=2,
        on_result=on_result,
    )

    assert streamed == ["call_2", "call_1"]
    assert [result.call_id for result in batch.results] == ["call_1", "call_2"]


def test_execute_tool_calls_parallel_callback_exceptions_propagate(
    monkeypatch,
) -> None:
    def fake_handler(arguments: dict[str, object], context: ToolContext) -> str:
        del arguments, context
        return "ok"

    monkeypatch.setattr(tool_runtime, "get_tool_handler", lambda name: fake_handler)

    def on_result(call: ToolCall, result: ToolResult) -> None:
        del call, result
        raise RuntimeError("display failed")

    try:
        tool_runtime.execute_tool_calls(
            [_tool_call("call_1"), _tool_call("call_2")],
            max_workers=2,
            on_result=on_result,
        )
    except RuntimeError as exc:
        assert str(exc) == "display failed"
    else:  # pragma: no cover - assertion path
        raise AssertionError("callback exception was not propagated")


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


def test_execute_tool_calls_keeps_apply_patch_display_metadata_out_of_output(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    target = tmp_path / "notes.txt"
    target.write_text("alpha\nbeta\ngamma", encoding="utf-8")
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
                    "operation_type": "update_file",
                    "path": "notes.txt",
                    "diff": " beta\n-gamma\n+GAMMA",
                },
            )
        ],
        max_workers=1,
    )

    payload = json.loads(batch.results[0].output_json)

    assert "diff_line_numbers" not in payload["result"]
    assert batch.results[0].display_metadata == {
        "diff": " beta\n-gamma\n+GAMMA",
        "diff_line_numbers": [
            {"old": 2, "new": 2},
            {"old": 3, "new": None},
            {"old": None, "new": 3},
        ],
    }


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


def test_display_tool_results_routes_apply_patch_with_diff_to_patch_display(
    display_spy,
) -> None:
    call = ToolCall(
        call_id="call_patch_1",
        name="apply_patch",
        arguments={
            "operation_type": "update_file",
            "path": "TODO.md",
            "diff": "-[ ] Old\n+[X] New",
        },
    )

    result = ToolResult(
        call_id="call_patch_1",
        output_json=json.dumps(
            {"ok": True, "result": {"status": "completed", "message": "ok"}}
        ),
    )

    display_tool_results(display_spy, [call], [result])

    assert display_spy.function_results == [
        {
            "name": "apply_patch",
            "success": True,
            "call_id": "call_patch_1",
            "arguments": {
                "path": "TODO.md",
                "operation_type": "update_file",
                "detail": "",
                "diff": "-[ ] Old\n+[X] New",
            },
        }
    ]


def test_display_tool_results_forwards_apply_patch_line_numbers(
    display_spy,
) -> None:
    call = ToolCall(
        call_id="call_patch_1",
        name="apply_patch",
        arguments={
            "operation_type": "update_file",
            "path": "TODO.md",
            "diff": "-[ ] Old\n+[X] New",
        },
    )

    result = ToolResult(
        call_id="call_patch_1",
        output_json=json.dumps(
            {"ok": True, "result": {"status": "completed", "message": "ok"}}
        ),
        display_metadata={
            "diff_line_numbers": [
                {"old": 12, "new": None},
                {"old": None, "new": 12},
            ],
        },
    )

    display_tool_results(display_spy, [call], [result])

    assert display_spy.function_results == [
        {
            "name": "apply_patch",
            "success": True,
            "call_id": "call_patch_1",
            "arguments": {
                "path": "TODO.md",
                "operation_type": "update_file",
                "detail": "",
                "diff": "-[ ] Old\n+[X] New",
                "diff_line_numbers": [
                    {"old": 12, "new": None},
                    {"old": None, "new": 12},
                ],
            },
        }
    ]
