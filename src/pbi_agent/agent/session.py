from __future__ import annotations

import json
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
from pbi_agent.agent.tool_runtime import execute_tool_calls, to_function_call_output_items
from pbi_agent.agent.ws_client import ResponsesWebSocketClient
from pbi_agent.config import Settings
from pbi_agent.models.messages import AgentOutcome, CompletedResponse
from pbi_agent.tools.registry import get_openai_tool_definitions


def run_single_turn(prompt: str, settings: Settings) -> AgentOutcome:
    tools = get_openai_tool_definitions()
    instructions = get_system_prompt()
    with ResponsesWebSocketClient(settings.ws_url, settings.api_key) as ws:
        response = _request_turn(
            ws=ws,
            model=settings.model,
            tools=tools,
            input_items=[_build_user_input_item(prompt)],
            previous_response_id=None,
            stream_output=True,
            instructions=instructions,
        )
        response, had_tool_errors = _run_tool_iterations(
            ws=ws,
            model=settings.model,
            tools=tools,
            response=response,
            max_workers=settings.max_tool_workers,
        )
        return AgentOutcome(
            response_id=response.response_id,
            text=response.text,
            tool_errors=had_tool_errors,
        )


def run_chat_loop(settings: Settings) -> int:
    print("Interactive mode. Type 'exit' or 'quit' to stop.")
    tools = get_openai_tool_definitions()
    instructions = get_system_prompt()
    previous_response_id: str | None = None
    had_tool_errors = False

    with ResponsesWebSocketClient(settings.ws_url, settings.api_key) as ws:
        while True:
            user_input = input("you> ").strip()
            if user_input.lower() in {"exit", "quit"}:
                break
            if not user_input:
                continue

            print("assistant> ", end="", flush=True)
            response = _request_turn(
                ws=ws,
                model=settings.model,
                tools=tools,
                input_items=[_build_user_input_item(user_input)],
                previous_response_id=previous_response_id,
                stream_output=True,
                instructions=instructions,
            )
            response, loop_had_errors = _run_tool_iterations(
                ws=ws,
                model=settings.model,
                tools=tools,
                response=response,
                max_workers=settings.max_tool_workers,
            )
            had_tool_errors = had_tool_errors or loop_had_errors
            previous_response_id = response.response_id

    return 4 if had_tool_errors else 0


def _run_tool_iterations(
    *,
    ws: ResponsesWebSocketClient,
    model: str,
    tools: list[dict[str, Any]],
    response: CompletedResponse,
    max_workers: int,
) -> tuple[CompletedResponse, bool]:
    instructions = get_system_prompt()
    had_errors = False
    while response.has_tool_calls:
        print("tool> model requested tool execution")
        output_items: list[dict[str, Any]] = []

        if response.function_calls:
            for call in response.function_calls:
                args_preview = _to_compact_json(call.arguments)
                print(f"tool> function {call.name} ({call.call_id}) args={args_preview}")
            function_batch = execute_tool_calls(
                response.function_calls,
                max_workers=max_workers,
            )
            had_errors = had_errors or function_batch.had_errors
            for result in function_batch.results:
                state = "failed" if result.is_error else "completed"
                print(f"tool< function ({result.call_id}) {state}")
            output_items.extend(to_function_call_output_items(function_batch.results))

        if response.apply_patch_calls:
            for call in response.apply_patch_calls:
                operation_type = call.operation.get("type", "unknown")
                operation_path = call.operation.get("path", "<missing path>")
                print(
                    f"tool> apply_patch {operation_type} path={operation_path} ({call.call_id})"
                )
            apply_patch_items, apply_patch_had_errors = execute_apply_patch_calls(
                response.apply_patch_calls,
                workspace_root=Path.cwd(),
            )
            had_errors = had_errors or apply_patch_had_errors
            for item in apply_patch_items:
                status = item.get("status", "unknown")
                output = str(item.get("output", ""))
                print(
                    f"tool< apply_patch ({item.get('call_id', '')}) {status}: {_shorten(output)}"
                )
            output_items.extend(apply_patch_items)

        if response.shell_calls:
            for call in response.shell_calls:
                commands = call.action.get("commands")
                timeout_ms = call.action.get("timeout_ms", "default")
                working_directory = call.action.get("working_directory", ".")
                if isinstance(commands, list):
                    for idx, command in enumerate(commands, start=1):
                        print(
                            f"tool> shell ({call.call_id}) cmd#{idx} wd={working_directory} timeout_ms={timeout_ms}: {command}"
                        )
            shell_items, shell_had_errors = execute_shell_calls(
                response.shell_calls,
                workspace_root=Path.cwd(),
            )
            had_errors = had_errors or shell_had_errors
            for item in shell_items:
                statuses = _summarize_shell_outcomes(item.get("output"))
                print(f"tool< shell ({item.get('call_id', '')}) {statuses}")
            output_items.extend(shell_items)

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
        )
    return response, had_errors


def _to_compact_json(value: Any) -> str:
    try:
        return _shorten(json.dumps(value, separators=(",", ":"), ensure_ascii=False))
    except TypeError:
        return _shorten(str(value))


def _shorten(text: str, limit: int = 160) -> str:
    if len(text) <= limit:
        return text
    return text[: limit - 3] + "..."


def _summarize_shell_outcomes(output: Any) -> str:
    if not isinstance(output, list):
        return "failed: invalid output format"
    parts: list[str] = []
    for chunk in output:
        if not isinstance(chunk, dict):
            continue
        outcome = chunk.get("outcome")
        if not isinstance(outcome, dict):
            continue
        outcome_type = outcome.get("type")
        if outcome_type == "timeout":
            parts.append("timeout")
        elif outcome_type == "exit":
            parts.append(f"exit={outcome.get('exit_code')}")
    if not parts:
        return "completed"
    return ", ".join(parts)


def _request_turn(
    *,
    ws: ResponsesWebSocketClient,
    model: str,
    tools: list[dict[str, Any]],
    input_items: list[dict[str, Any]],
    previous_response_id: str | None,
    stream_output: bool,
    instructions: str | None,
) -> CompletedResponse:
    payload = build_response_create_payload(
        model=model,
        input_items=input_items,
        tools=tools,
        previous_response_id=previous_response_id,
        store=True,
        instructions=instructions,
    )
    ws.send_json(payload)
    return _read_one_response(ws, stream_output=stream_output)


def _read_one_response(
    ws: ResponsesWebSocketClient,
    *,
    stream_output: bool,
) -> CompletedResponse:
    streamed_text_parts: list[str] = []

    while True:
        event = ws.recv_json()
        event_type = event.get("type")

        if event_type == "response.output_text.delta":
            delta = event.get("delta", "")
            if delta:
                streamed_text_parts.append(delta)
                if stream_output:
                    print(delta, end="", flush=True)
        elif event_type == "response.completed":
            if stream_output:
                print()
            return parse_completed_response(event.get("response", {}), streamed_text_parts)
        elif event_type == "error":
            error = event.get("error", {})
            code = error.get("code", "unknown_error")
            message = error.get("message", "No error message")
            raise ProtocolError(f"{code}: {message}")


def _build_user_input_item(prompt: str) -> dict[str, Any]:
    return {
        "type": "message",
        "role": "user",
        "content": [{"type": "input_text", "text": prompt}],
    }
