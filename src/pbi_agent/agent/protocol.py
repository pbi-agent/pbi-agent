from __future__ import annotations

import json
from typing import Any

from pbi_agent.models.messages import (
    ApplyPatchCall,
    CompletedResponse,
    ShellCall,
    TokenUsage,
    ToolCall,
)


class ProtocolError(RuntimeError):
    """Raised when an unexpected protocol event is received."""


def build_response_create_payload(
    *,
    model: str,
    input_items: list[dict[str, Any]],
    tools: list[dict[str, Any]] | None = None,
    previous_response_id: str | None = None,
    store: bool = False,
    instructions: str | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "type": "response.create",
        "model": model,
        "store": store,
        "input": input_items,
        "tools": tools or [],
        "prompt_cache_retention": "24h",
    }
    if previous_response_id:
        payload["previous_response_id"] = previous_response_id
    if instructions:
        payload["instructions"] = instructions
    return payload


def parse_completed_response(response_obj: dict[str, Any], streamed_text_parts: list[str]) -> CompletedResponse:
    text_parts: list[str] = []
    function_calls: list[ToolCall] = []
    apply_patch_calls: list[ApplyPatchCall] = []
    shell_calls: list[ShellCall] = []

    for item in response_obj.get("output", []):
        item_type = item.get("type")

        if item_type == "message":
            for part in item.get("content", []):
                if part.get("type") == "output_text":
                    text = part.get("text", "")
                    if text:
                        text_parts.append(text)
        elif item_type == "function_call":
            raw_args = item.get("arguments", "")
            parsed_args: dict[str, Any] | str | None
            try:
                if isinstance(raw_args, str) and raw_args:
                    parsed_args = json.loads(raw_args)
                else:
                    parsed_args = raw_args
            except json.JSONDecodeError:
                parsed_args = raw_args

            function_calls.append(
                ToolCall(
                    call_id=item.get("call_id", ""),
                    name=item.get("name", ""),
                    arguments=parsed_args,
                )
            )
        elif item_type == "apply_patch_call":
            operation = item.get("operation")
            if isinstance(operation, dict):
                apply_patch_calls.append(
                    ApplyPatchCall(
                        call_id=item.get("call_id", ""),
                        operation=operation,
                    )
                )
        elif item_type == "shell_call":
            action = item.get("action")
            if isinstance(action, dict):
                shell_calls.append(
                    ShellCall(
                        call_id=item.get("call_id", ""),
                        action=action,
                    )
                )

    usage_obj = response_obj.get("usage", {})
    input_tokens = int(usage_obj.get("input_tokens", 0) or 0) if isinstance(usage_obj, dict) else 0
    output_tokens = int(usage_obj.get("output_tokens", 0) or 0) if isinstance(usage_obj, dict) else 0
    cached_input_tokens = 0
    if isinstance(usage_obj, dict):
        input_details = usage_obj.get("input_tokens_details", {})
        if isinstance(input_details, dict):
            cached_input_tokens = int(
                input_details.get("cached_tokens", input_details.get("cached_input_tokens", 0)) or 0
            )

    final_text = "".join(text_parts).strip() or "".join(streamed_text_parts).strip()
    return CompletedResponse(
        response_id=response_obj.get("id"),
        text=final_text,
        usage=TokenUsage(
            input_tokens=input_tokens,
            cached_input_tokens=cached_input_tokens,
            output_tokens=output_tokens,
        ),
        function_calls=function_calls,
        apply_patch_calls=apply_patch_calls,
        shell_calls=shell_calls,
    )
