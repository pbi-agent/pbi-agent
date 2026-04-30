"""Shared provider wait-message helpers."""

from __future__ import annotations

from typing import Any

_TOOL_OUTPUT_TYPES = frozenset(
    {
        "function_result",
        "function_call_output",
        "tool_result",
    }
)


def waiting_message_for_input(input_value: str | list[dict[str, Any]]) -> str:
    if isinstance(input_value, str):
        return "analyzing your request..."

    has_user_message = any(
        isinstance(item, dict) and item.get("role") == "user" for item in input_value
    )
    if has_user_message:
        return "analyzing your request..."

    has_tool_output = any(
        isinstance(item, dict)
        and (item.get("type") in _TOOL_OUTPUT_TYPES or item.get("role") == "tool")
        for item in input_value
    )
    if has_tool_output:
        return "waiting for model to process tool results..."

    return "processing..."
