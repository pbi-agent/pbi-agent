from __future__ import annotations

from pathlib import Path
from typing import Any

from pbi_agent.agent.apply_patch_runtime import execute_apply_patch_calls
from pbi_agent.agent.protocol import (
    ProtocolError,
    build_response_create_payload,
    parse_completed_response,
)
from pbi_agent.agent.shell_runtime import execute_shell_calls
from pbi_agent.agent.tool_runtime import execute_tool_calls, to_function_call_output_items
from pbi_agent.agent.ws_client import ResponsesWebSocketClient
from pbi_agent.config import Settings
from pbi_agent.models.messages import AgentOutcome, CompletedResponse
from pbi_agent.tools.registry import get_openai_tool_definitions


def run_single_turn(prompt: str, settings: Settings) -> AgentOutcome:
    tools = get_openai_tool_definitions()
    with ResponsesWebSocketClient(settings.ws_url, settings.api_key) as ws:
        response = _request_turn(
            ws=ws,
            model=settings.model,
            tools=tools,
            input_items=[_build_user_input_item(prompt)],
            previous_response_id=None,
            stream_output=True,
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
    had_errors = False
    while response.has_tool_calls:
        output_items: list[dict[str, Any]] = []

        if response.function_calls:
            function_batch = execute_tool_calls(
                response.function_calls,
                max_workers=max_workers,
            )
            had_errors = had_errors or function_batch.had_errors
            output_items.extend(to_function_call_output_items(function_batch.results))

        if response.apply_patch_calls:
            apply_patch_items, apply_patch_had_errors = execute_apply_patch_calls(
                response.apply_patch_calls,
                workspace_root=Path.cwd(),
            )
            had_errors = had_errors or apply_patch_had_errors
            output_items.extend(apply_patch_items)

        if response.shell_calls:
            shell_items, shell_had_errors = execute_shell_calls(
                response.shell_calls,
                workspace_root=Path.cwd(),
            )
            had_errors = had_errors or shell_had_errors
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
        )
    return response, had_errors


def _request_turn(
    *,
    ws: ResponsesWebSocketClient,
    model: str,
    tools: list[dict[str, Any]],
    input_items: list[dict[str, Any]],
    previous_response_id: str | None,
    stream_output: bool,
) -> CompletedResponse:
    payload = build_response_create_payload(
        model=model,
        input_items=input_items,
        tools=tools,
        previous_response_id=previous_response_id,
        store=False,
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
