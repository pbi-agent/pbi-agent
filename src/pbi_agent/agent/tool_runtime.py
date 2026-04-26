from __future__ import annotations

import json
import logging
import time
from collections.abc import Callable
from concurrent.futures import Future, ThreadPoolExecutor, as_completed
from dataclasses import dataclass, replace
from typing import Any

from pbi_agent.media import data_url_for_image
from pbi_agent.models.messages import ToolCall
from pbi_agent.tools.catalog import ToolCatalog
from pbi_agent.tools.registry import get_tool_handler
from pbi_agent.tools.types import ToolContext, ToolOutput, ToolResult

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
    on_result: Callable[[ToolCall, ToolResult], None] | None = None,
) -> ToolExecutionBatch:
    if not calls:
        return ToolExecutionBatch(results=[], had_errors=False)

    tool_catalog = context.tool_catalog if context is not None else None

    if len(calls) == 1 or max_workers == 1:
        results: list[ToolResult] = []
        for call in calls:
            result = _execute_one_tool_call(
                call,
                tool_catalog=tool_catalog,
                context=context,
            )
            results.append(result)
            if on_result is not None:
                on_result(call, result)
        return ToolExecutionBatch(
            results=results, had_errors=any(r.is_error for r in results)
        )

    results: list[ToolResult | None] = [None] * len(calls)
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures: dict[Future[ToolResult], tuple[int, ToolCall]] = {}
        for idx, call in enumerate(calls):
            futures[
                executor.submit(
                    _execute_one_tool_call,
                    call,
                    tool_catalog,
                    context,
                )
            ] = (idx, call)
        for future in as_completed(futures):
            idx, call = futures[future]
            result = future.result()
            results[idx] = result
            if on_result is not None:
                on_result(call, result)

    ordered_results = [result for result in results if result is not None]
    return ToolExecutionBatch(
        results=ordered_results,
        had_errors=any(result.is_error for result in ordered_results),
    )


def to_function_call_output_items(results: list[ToolResult]) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for result in results:
        output: str | list[dict[str, Any]] = result.output_json
        if result.attachments:
            output = [{"type": "input_text", "text": result.output_json}]
            for attachment in result.attachments:
                output.append(
                    {
                        "type": "input_image",
                        "image_url": data_url_for_image(attachment),
                    }
                )
        items.append(
            {
                "type": "function_call_output",
                "call_id": result.call_id,
                "output": output,
            }
        )
    return items


def _execute_one_tool_call(
    call: ToolCall,
    tool_catalog: ToolCatalog | None = None,
    context: ToolContext | None = None,
) -> ToolResult:
    start = time.monotonic()
    tracer = context.tracer if context is not None else None
    _log.debug("Starting tool call %s (%s)", call.call_id, call.name)
    handler = (
        tool_catalog.get_handler(call.name) if tool_catalog is not None else None
    ) or get_tool_handler(call.name)
    if handler is None:
        result = _error_result(
            call, "unknown_tool", f"Tool '{call.name}' is not registered."
        )
        _log_tool_call(
            tracer=tracer,
            call=call,
            output_payload=json.loads(result.output_json),
            duration_ms=_duration_ms(start),
            success=False,
            error_message=f"Tool '{call.name}' is not registered.",
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
        _log_tool_call(
            tracer=tracer,
            call=call,
            output_payload=json.loads(result.output_json),
            duration_ms=_duration_ms(start),
            success=False,
            error_message=args_or_error,
        )
        _log.debug(
            "Finished tool call %s (%s) in %.3fs with error",
            call.call_id,
            call.name,
            time.monotonic() - start,
        )
        return result

    try:
        tool_context = _tool_context_for_call(context)
        output = handler(args_or_error, tool_context)
        attachments = []
        display_metadata = dict(tool_context.display_metadata)
        if isinstance(output, ToolOutput):
            payload = {"ok": True, "result": output.result}
            attachments = list(output.attachments)
            display_metadata.update(output.display_metadata)
        else:
            payload = {"ok": True, "result": output}
        result = ToolResult(
            call_id=call.call_id,
            output_json=json.dumps(payload),
            is_error=False,
            attachments=attachments,
            display_metadata=display_metadata,
        )
        _log_tool_call(
            tracer=tracer,
            call=call,
            output_payload=payload,
            duration_ms=_duration_ms(start),
            success=True,
            metadata={"attachment_count": len(attachments)},
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
        _log_tool_call(
            tracer=tracer,
            call=call,
            output_payload=json.loads(result.output_json),
            duration_ms=_duration_ms(start),
            success=False,
            error_message=str(exc),
        )
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


def _tool_context_for_call(context: ToolContext | None) -> ToolContext:
    if context is None:
        return ToolContext()
    return replace(context, display_metadata={})


def _duration_ms(start: float) -> int:
    return max(0, int((time.monotonic() - start) * 1000))


def _log_tool_call(
    *,
    tracer,
    call: ToolCall,
    output_payload: dict[str, Any],
    duration_ms: int,
    success: bool,
    error_message: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> None:
    if tracer is None:
        return
    tracer.log_tool_call(
        tool_name=call.name,
        tool_call_id=call.call_id,
        tool_input=call.arguments,
        tool_output=output_payload,
        duration_ms=duration_ms,
        success=success,
        error_message=error_message,
        metadata=metadata,
    )
