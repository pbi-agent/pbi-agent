from __future__ import annotations

import json
from collections.abc import Callable
from threading import Lock
from typing import Any

from pbi_agent.display.protocol import DisplayProtocol
from pbi_agent.display.protocol import PendingToolCall
from pbi_agent.models.messages import ToolCall
from pbi_agent.tools.apply_patch import (
    SPEC as APPLY_PATCH_SPEC,
    diff_line_numbers_metadata,
)
from pbi_agent.tools.types import ToolResult

_APPLY_PATCH_TOOL_NAME = APPLY_PATCH_SPEC.name


def display_tool_execution_start(
    display: DisplayProtocol,
    calls: list[ToolCall],
) -> None:
    display.tool_execution_start(
        [
            PendingToolCall(
                call_id=call.call_id,
                name=call.name,
                arguments=call.arguments,
            )
            for call in calls
        ]
    )


def display_tool_result(
    display: DisplayProtocol,
    call: ToolCall | None,
    result: ToolResult,
) -> None:
    """Render one completed tool call through the appropriate display hook."""
    if call is not None and call.name == _APPLY_PATCH_TOOL_NAME:
        _display_apply_patch_result(display, call, result)
        return
    _display_function_result(display, call, result)


def build_tool_result_callback(
    display: DisplayProtocol,
) -> Callable[[ToolCall, ToolResult], None]:
    """Build a per-tool completion renderer for streaming tool batches."""
    display_lock = Lock()

    def on_result(call: ToolCall, result: ToolResult) -> None:
        if call.name == "sub_agent":
            return
        with display_lock:
            display_tool_result(display, call, result)

    return on_result


def finalize_tool_execution(display: DisplayProtocol) -> None:
    """Finish the active tool-execution display after a streamed batch."""

    display.tool_execution_stop()


def _display_function_result(
    display: DisplayProtocol,
    call: ToolCall | None,
    result: ToolResult,
) -> None:
    display.function_result(
        name=call.name if call else "unknown",
        success=not result.is_error,
        call_id=result.call_id,
        arguments=call.arguments if call else None,
    )


def display_tool_results(
    display: DisplayProtocol,
    calls: list[ToolCall],
    results: list[ToolResult],
) -> None:
    """Render completed tool calls in original provider call order.

    Tool execution may finish in a different order when parallel workers are
    enabled. Displaying in model-call order keeps grouped UI output stable and
    still preserves unknown/unmatched results at the end.
    """
    pending = list(results)
    for call in calls:
        match_index = next(
            (
                index
                for index, result in enumerate(pending)
                if result.call_id == call.call_id
            ),
            -1,
        )
        if match_index < 0:
            continue
        result = pending.pop(match_index)
        if call.name == "sub_agent":
            continue
        display_tool_result(display, call, result)

    for result in pending:
        _display_function_result(display, None, result)
    display.tool_execution_stop()


def _display_apply_patch_result(
    display: DisplayProtocol,
    call: ToolCall,
    result: ToolResult,
) -> None:
    # The browser timeline needs the original V4A diff to render a proper
    # per-line patch view. The tool output only contains success/failure, so
    # carry the diff from the tool-call arguments into the display metadata.
    arguments = _arguments_dict(call.arguments)
    payload = _output_payload(result.output_json)
    success = _patch_success(result, payload)
    display_diff = result.display_metadata.get("diff")
    if not isinstance(display_diff, str):
        display_diff = str(arguments.get("diff") or "")
    display.patch_result(
        str(arguments.get("path") or "<missing path>"),
        str(arguments.get("operation_type") or "<missing operation_type>"),
        success,
        call_id=result.call_id,
        detail=_patch_detail(payload),
        diff=display_diff,
        diff_line_numbers=diff_line_numbers_metadata(
            result.display_metadata.get("diff_line_numbers")
        ),
    )


def _arguments_dict(arguments: dict[str, Any] | str | None) -> dict[str, Any]:
    if isinstance(arguments, dict):
        return arguments
    if isinstance(arguments, str) and arguments.strip():
        try:
            parsed = json.loads(arguments)
        except json.JSONDecodeError:
            return {}
        if isinstance(parsed, dict):
            return parsed
    return {}


def _output_payload(output_json: str) -> dict[str, Any]:
    try:
        parsed = json.loads(output_json)
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _patch_success(result: ToolResult, payload: dict[str, Any]) -> bool:
    if result.is_error or payload.get("ok") is False:
        return False
    result_payload = payload.get("result")
    if isinstance(result_payload, dict):
        status = str(result_payload.get("status") or "").strip().lower()
        if status == "failed":
            return False
        if result_payload.get("error") and not result_payload.get("message"):
            return False
    return True


def _patch_detail(payload: dict[str, Any]) -> str:
    result_payload = payload.get("result")
    if isinstance(result_payload, dict):
        status_value = result_payload.get("status")
        if (
            isinstance(status_value, str)
            and status_value.strip().lower() == "completed"
        ):
            return ""
        for key in ("error", "message"):
            value = result_payload.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()

    error_payload = payload.get("error")
    if isinstance(error_payload, dict):
        value = error_payload.get("message")
        if isinstance(value, str) and value.strip():
            return value.strip()
    if isinstance(error_payload, str) and error_payload.strip():
        return error_payload.strip()
    return ""
