from __future__ import annotations

import json

from pbi_agent.agent import tool_runtime
from pbi_agent.models.messages import ToolCall
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
