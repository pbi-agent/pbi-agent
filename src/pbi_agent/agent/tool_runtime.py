from __future__ import annotations

import json
import logging
import time
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass
from typing import Any

from pbi_agent.models.messages import ToolCall
from pbi_agent.tools.registry import get_tool_handler
from pbi_agent.tools.types import ToolContext, ToolResult

_log = logging.getLogger(__name__)


@dataclass(slots=True)
class ToolExecutionBatch:
    results: list[ToolResult]
    had_errors: bool = False


def execute_tool_calls(
    calls: list[ToolCall],
    *,
    max_workers: int,
    context: ToolContext | None = None,
) -> ToolExecutionBatch:
    if not calls:
        return ToolExecutionBatch(results=[], had_errors=False)

    if len(calls) == 1 or max_workers == 1:
        results = [_execute_one_tool_call(call, context=context) for call in calls]
        return ToolExecutionBatch(
            results=results, had_errors=any(r.is_error for r in results)
        )

    results: list[ToolResult | None] = [None] * len(calls)
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures: dict[Future[ToolResult], int] = {}
        for idx, call in enumerate(calls):
            futures[executor.submit(_execute_one_tool_call, call, context)] = idx
        for future, idx in futures.items():
            results[idx] = future.result()

    ordered_results = [result for result in results if result is not None]
    return ToolExecutionBatch(
        results=ordered_results,
        had_errors=any(result.is_error for result in ordered_results),
    )


def to_function_call_output_items(results: list[ToolResult]) -> list[dict[str, Any]]:
    return [
        {
            "type": "function_call_output",
            "call_id": result.call_id,
            "output": result.output_json,
        }
        for result in results
    ]


def _execute_one_tool_call(
    call: ToolCall,
    context: ToolContext | None = None,
) -> ToolResult:
    start = time.monotonic()
    _log.debug("Starting tool call %s (%s)", call.call_id, call.name)
    handler = get_tool_handler(call.name)
    if handler is None:
        result = _error_result(
            call, "unknown_tool", f"Tool '{call.name}' is not registered."
        )
        _log.debug(
            "Finished tool call %s (%s) in %.3fs with error",
            call.call_id,
            call.name,
            time.monotonic() - start,
        )
        return result

    args_or_error = _normalize_arguments(call.arguments)
    if isinstance(args_or_error, str):
        result = _error_result(call, "invalid_arguments", args_or_error)
        _log.debug(
            "Finished tool call %s (%s) in %.3fs with error",
            call.call_id,
            call.name,
            time.monotonic() - start,
        )
        return result

    try:
        output = handler(args_or_error, context or ToolContext())
        if isinstance(output, str):
            payload = {"ok": True, "result": output}
        else:
            payload = {"ok": True, "result": output}
        result = ToolResult(
            call_id=call.call_id, output_json=json.dumps(payload), is_error=False
        )
        _log.debug(
            "Finished tool call %s (%s) in %.3fs",
            call.call_id,
            call.name,
            time.monotonic() - start,
        )
        return result
    except Exception as exc:
        result = _error_result(call, "tool_execution_failed", str(exc))
        _log.debug(
            "Finished tool call %s (%s) in %.3fs with exception: %s",
            call.call_id,
            call.name,
            time.monotonic() - start,
            exc,
        )
        return result


def _normalize_arguments(
    arguments: dict[str, Any] | str | None,
) -> dict[str, Any] | str:
    if arguments is None:
        return {}
    if isinstance(arguments, dict):
        return arguments
    if isinstance(arguments, str):
        if not arguments.strip():
            return {}
        try:
            parsed = json.loads(arguments)
        except json.JSONDecodeError:
            return "tool arguments must be a JSON object"
        if not isinstance(parsed, dict):
            return "tool arguments must decode to a JSON object"
        return parsed
    return "tool arguments must be a JSON object"


def _error_result(call: ToolCall, error_type: str, message: str) -> ToolResult:
    payload = {
        "ok": False,
        "error": {"type": error_type, "message": message},
        "tool": call.name,
    }
    return ToolResult(
        call_id=call.call_id,
        output_json=json.dumps(payload),
        is_error=True,
    )
