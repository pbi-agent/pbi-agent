from __future__ import annotations

import time
from pathlib import Path
from typing import Any

from pbi_agent.agent.apply_patch_runtime import execute_apply_patch_calls
from pbi_agent.agent.protocol import (
    ProtocolError,
    build_response_create_payload,
    parse_completed_response,
)
from pbi_agent.agent.shell_runtime import execute_shell_calls
from pbi_agent.agent.system_prompt import get_system_prompt
from pbi_agent.agent.tool_runtime import (
    execute_tool_calls,
    to_function_call_output_items,
)
from pbi_agent.agent.ws_client import (
    ResponsesWebSocketClient,
    WebSocketClientError,
    WebSocketClientTransientError,
)
from pbi_agent.config import Settings
from pbi_agent.display import Display
from pbi_agent.models.messages import AgentOutcome, CompletedResponse, TokenUsage
from pbi_agent.tools.registry import get_openai_tool_definitions


# ---------------------------------------------------------------------------
# Public entry-points
# ---------------------------------------------------------------------------


def run_single_turn(
    prompt: str,
    settings: Settings,
    display: Display,
    *,
    single_turn_hint: str | None = None,
) -> AgentOutcome:
    display.welcome(
        interactive=False,
        model=settings.model,
        reasoning_effort=settings.reasoning_effort,
        single_turn_hint=single_turn_hint,
    )
    tools = get_openai_tool_definitions()
    instructions = get_system_prompt()
    session_usage = TokenUsage()
    session_start = time.monotonic()
    with ResponsesWebSocketClient(settings.ws_url, settings.api_key) as ws:
        response = _request_turn(
            ws=ws,
            model=settings.model,
            tools=tools,
            input_items=[_build_user_input_item(prompt)],
            previous_response_id=None,
            stream_output=True,
            instructions=instructions,
            reasoning_effort=settings.reasoning_effort,
            compact_threshold=settings.compact_threshold,
            ws_max_retries=settings.ws_max_retries,
            display=display,
            session_usage=session_usage,
        )
        response, had_tool_errors = _run_tool_iterations(
            ws=ws,
            model=settings.model,
            tools=tools,
            response=response,
            max_workers=settings.max_tool_workers,
            ws_max_retries=settings.ws_max_retries,
            compact_threshold=settings.compact_threshold,
            display=display,
            session_usage=session_usage,
        )
        elapsed = time.monotonic() - session_start
        display.session_usage(session_usage, elapsed)
        return AgentOutcome(
            response_id=response.response_id,
            text=response.text,
            tool_errors=had_tool_errors,
        )


def run_chat_loop(settings: Settings, display: Display) -> int:
    display.welcome(
        model=settings.model,
        reasoning_effort=settings.reasoning_effort,
    )
    tools = get_openai_tool_definitions()
    instructions = get_system_prompt()
    previous_response_id: str | None = None
    had_tool_errors = False
    session_usage = TokenUsage()

    with ResponsesWebSocketClient(settings.ws_url, settings.api_key) as ws:
        while True:
            user_input = display.user_prompt().strip()
            if user_input.lower() in {"exit", "quit"}:
                break
            if not user_input:
                continue

            turn_start = time.monotonic()
            display.assistant_start()
            response = _request_turn(
                ws=ws,
                model=settings.model,
                tools=tools,
                input_items=[_build_user_input_item(user_input)],
                previous_response_id=previous_response_id,
                stream_output=True,
                instructions=instructions,
                reasoning_effort=settings.reasoning_effort,
                compact_threshold=settings.compact_threshold,
                ws_max_retries=settings.ws_max_retries,
                display=display,
                session_usage=session_usage,
            )
            response, loop_had_errors = _run_tool_iterations(
                ws=ws,
                model=settings.model,
                tools=tools,
                response=response,
                max_workers=settings.max_tool_workers,
                ws_max_retries=settings.ws_max_retries,
                compact_threshold=settings.compact_threshold,
                display=display,
                session_usage=session_usage,
            )
            had_tool_errors = had_tool_errors or loop_had_errors
            previous_response_id = response.response_id
            elapsed = time.monotonic() - turn_start
            display.session_usage(session_usage, elapsed)

    return 4 if had_tool_errors else 0


# ---------------------------------------------------------------------------
# Tool iteration loop
# ---------------------------------------------------------------------------


def _run_tool_iterations(
    *,
    ws: ResponsesWebSocketClient,
    model: str,
    tools: list[dict[str, Any]],
    response: CompletedResponse,
    max_workers: int,
    ws_max_retries: int,
    compact_threshold: int,
    display: Display,
    session_usage: TokenUsage,
) -> tuple[CompletedResponse, bool]:
    instructions = get_system_prompt()
    had_errors = False

    while response.has_tool_calls:
        display.debug("model requested tool execution")
        output_items: list[dict[str, Any]] = []

        # --- function calls ------------------------------------------------
        if response.function_calls:
            display.function_start(len(response.function_calls))
            function_batch = execute_tool_calls(
                response.function_calls,
                max_workers=max_workers,
            )
            had_errors = had_errors or function_batch.had_errors
            for result in function_batch.results:
                call = _find_function_call(response.function_calls, result.call_id)
                display.function_result(
                    name=call.name if call else "unknown",
                    success=not result.is_error,
                    call_id=result.call_id,
                    arguments=call.arguments if call else None,
                )
            output_items.extend(to_function_call_output_items(function_batch.results))
            display.tool_group_end()

        # --- apply_patch calls ---------------------------------------------
        if response.apply_patch_calls:
            display.patch_start(len(response.apply_patch_calls))
            apply_patch_items, apply_patch_had_errors = execute_apply_patch_calls(
                response.apply_patch_calls,
                workspace_root=Path.cwd(),
            )
            had_errors = had_errors or apply_patch_had_errors
            for call, item in zip(response.apply_patch_calls, apply_patch_items):
                status = item.get("status", "unknown")
                output = str(item.get("output", ""))
                display.patch_result(
                    path=call.operation.get("path", "<missing>"),
                    operation=call.operation.get("type", "update"),
                    success=(status != "failed" and status != "error"),
                    call_id=item.get("call_id", ""),
                    detail=output,
                )
            output_items.extend(apply_patch_items)
            display.tool_group_end()

        # --- shell calls ---------------------------------------------------
        if response.shell_calls:
            all_commands = _collect_shell_commands(response.shell_calls)
            display.shell_start(all_commands)

            shell_items, shell_had_errors = execute_shell_calls(
                response.shell_calls,
                workspace_root=Path.cwd(),
            )
            had_errors = had_errors or shell_had_errors

            for call, item in zip(response.shell_calls, shell_items):
                commands = call.action.get("commands", [])
                timeout_ms = call.action.get("timeout_ms", "default")
                working_directory = call.action.get("working_directory", ".")
                outcomes = _extract_shell_outcomes(item.get("output"))
                for idx, command in enumerate(commands):
                    exit_code, timed_out = (
                        outcomes[idx] if idx < len(outcomes) else (None, False)
                    )
                    display.shell_command(
                        command=command,
                        exit_code=exit_code,
                        timed_out=timed_out,
                        call_id=call.call_id,
                        working_directory=working_directory,
                        timeout_ms=timeout_ms,
                    )
            output_items.extend(shell_items)
            display.tool_group_end()

        if not output_items:
            break

        response = _request_turn(
            ws=ws,
            model=model,
            tools=tools,
            input_items=output_items,
            previous_response_id=response.response_id,
            stream_output=True,
            instructions=instructions,
            reasoning_effort="xhigh",
            compact_threshold=compact_threshold,
            ws_max_retries=ws_max_retries,
            display=display,
            session_usage=session_usage,
        )
    return response, had_errors


# ---------------------------------------------------------------------------
# Request / response helpers
# ---------------------------------------------------------------------------


def _request_turn(
    *,
    ws: ResponsesWebSocketClient,
    model: str,
    tools: list[dict[str, Any]],
    input_items: list[dict[str, Any]],
    previous_response_id: str | None,
    stream_output: bool,
    instructions: str | None,
    reasoning_effort: str,
    compact_threshold: int,
    ws_max_retries: int,
    display: Display,
    session_usage: TokenUsage,
) -> CompletedResponse:
    payload = build_response_create_payload(
        model=model,
        input_items=input_items,
        tools=tools,
        previous_response_id=previous_response_id,
        store=True,
        instructions=instructions,
        reasoning_effort=reasoning_effort,
        compact_threshold=compact_threshold,
    )
    last_error: Exception | None = None
    for attempt in range(ws_max_retries + 1):
        if attempt > 0:
            display.retry_notice(attempt, ws_max_retries)
            ws.reconnect()
        try:
            ws.send_json(payload)
            response = _read_one_response(
                ws,
                stream_output=stream_output,
                display=display,
                waiting_message=_waiting_message_for_input_items(input_items),
            )
            session_usage.add(response.usage)
            return response
        except WebSocketClientTransientError as exc:
            # Treat receive/decode failures as transient: reconnect and retry the full
            # request. This favors resiliency over strict "exactly-once" semantics.
            last_error = exc
            continue
        except WebSocketClientError:
            raise

    if last_error is not None:
        raise WebSocketClientError(str(last_error)) from last_error
    raise WebSocketClientError("WebSocket request failed after retries.")


def _read_one_response(
    ws: ResponsesWebSocketClient,
    *,
    stream_output: bool,
    display: Display,
    waiting_message: str,
) -> CompletedResponse:
    streamed_text_parts: list[str] = []
    if stream_output:
        display.wait_start(waiting_message)

    try:
        while True:
            event = ws.recv_json()
            event_type = event.get("type")

            if event_type == "response.output_text.delta":
                delta = event.get("delta", "")
                if delta:
                    streamed_text_parts.append(delta)
                    if stream_output:
                        display.stream_delta(delta)
            elif event_type == "response.completed":
                if stream_output:
                    display.stream_end()
                return parse_completed_response(
                    event.get("response", {}), streamed_text_parts
                )
            elif event_type == "error":
                error = event.get("error", {})
                code = error.get("code", "unknown_error")
                message = error.get("message", "No error message")
                raise ProtocolError(f"{code}: {message}")
    except Exception:
        if stream_output:
            display.stream_abort()
        raise


# ---------------------------------------------------------------------------
# Internal utilities
# ---------------------------------------------------------------------------


def _build_user_input_item(prompt: str) -> dict[str, Any]:
    return {
        "type": "message",
        "role": "user",
        "content": [{"type": "input_text", "text": prompt}],
    }


def _find_function_call(calls: list, call_id: str):  # type: ignore[type-arg]
    """Look up the original ToolCall by call_id."""
    for c in calls:
        if c.call_id == call_id:
            return c
    return None


def _collect_shell_commands(shell_calls: list) -> list[str]:  # type: ignore[type-arg]
    """Flatten all commands across shell calls for counting."""
    commands: list[str] = []
    for call in shell_calls:
        cmds = call.action.get("commands", [])
        if isinstance(cmds, list):
            commands.extend(cmds)
    return commands


def _waiting_message_for_input_items(input_items: list[dict[str, Any]]) -> str:
    """Choose a spinner subtitle based on what the model is processing."""
    item_types = {
        item.get("type")
        for item in input_items
        if isinstance(item, dict) and isinstance(item.get("type"), str)
    }
    if "message" in item_types:
        return "analyzing your request..."
    if item_types & {
        "function_call_output",
        "apply_patch_call_output",
        "shell_call_output",
    }:
        return "integrating tool results..."
    return "processing..."


def _extract_shell_outcomes(output: Any) -> list[tuple[int | None, bool]]:
    """Parse shell output into a list of (exit_code, timed_out) tuples."""
    if not isinstance(output, list):
        return []
    results: list[tuple[int | None, bool]] = []
    for chunk in output:
        if not isinstance(chunk, dict):
            results.append((None, False))
            continue
        outcome = chunk.get("outcome")
        if not isinstance(outcome, dict):
            results.append((None, False))
            continue
        outcome_type = outcome.get("type")
        if outcome_type == "timeout":
            results.append((None, True))
        elif outcome_type == "exit":
            results.append((outcome.get("exit_code"), False))
        else:
            results.append((None, False))
    return results
