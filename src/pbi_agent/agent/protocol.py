from __future__ import annotations

import json
import re
from typing import Any

from pbi_agent.models.messages import (
    CompletedResponse,
    TokenUsage,
    ToolCall,
)


class ProtocolError(RuntimeError):
    """Raised when an unexpected protocol event is received."""


class RateLimitError(ProtocolError):
    """Raised when the API rejects a request due to rate limits."""

    def __init__(
        self,
        *,
        code: str,
        message: str,
        retry_after_seconds: float | None = None,
    ) -> None:
        super().__init__(f"{code}: {message}")
        self.code = code
        self.message = message
        self.retry_after_seconds = retry_after_seconds


_RETRY_AFTER_SECONDS_RE = re.compile(
    r"(?:try again in|retry after)\s+([0-9]*\.?[0-9]+)\s*(ms|s)\b",
    re.IGNORECASE,
)


def parse_error_event(event: dict[str, Any]) -> ProtocolError:
    """Convert an API ``error`` event into a typed protocol exception."""
    error_obj = event.get("error", {})
    if not isinstance(error_obj, dict):
        return ProtocolError("unknown_error: No error message")

    code = str(error_obj.get("code", "unknown_error"))
    message = str(error_obj.get("message", "No error message"))

    if code in {"rate_limit_exceeded", "rate_limit_error"}:
        return RateLimitError(
            code=code,
            message=message,
            retry_after_seconds=_extract_retry_after_seconds(error_obj, message),
        )

    return ProtocolError(f"{code}: {message}")


def _extract_retry_after_seconds(
    error_obj: dict[str, Any], message: str
) -> float | None:
    for key in ("retry_after_seconds", "retry_after"):
        parsed = _parse_positive_float(error_obj.get(key))
        if parsed is not None:
            return parsed

    retry_after_ms = _parse_positive_float(error_obj.get("retry_after_ms"))
    if retry_after_ms is not None:
        return retry_after_ms / 1000.0

    match = _RETRY_AFTER_SECONDS_RE.search(message)
    if match:
        value = float(match.group(1))
        unit = match.group(2).lower()
        if value > 0:
            return value / 1000.0 if unit == "ms" else value

    return None


def _parse_positive_float(value: Any) -> float | None:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed > 0 else None


def build_response_create_payload(
    *,
    model: str,
    input_items: list[dict[str, Any]],
    tools: list[dict[str, Any]] | None = None,
    previous_response_id: str | None = None,
    store: bool = False,
    instructions: str | None = None,
    reasoning_effort: str = "xhigh",
    compact_threshold: int = 200000,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "type": "response.create",
        "model": model,
        "store": store,
        "input": input_items,
        "tools": tools or [],
        "prompt_cache_retention": "24h",
        "context_management": [
            {"type": "compaction", "compact_threshold": compact_threshold}
        ],
    }
    payload["reasoning"] = {"effort": reasoning_effort, "summary": "auto"}
    if previous_response_id:
        payload["previous_response_id"] = previous_response_id
    if instructions:
        payload["instructions"] = instructions
    return payload


def parse_completed_response(
    response_obj: dict[str, Any], streamed_text_parts: list[str]
) -> CompletedResponse:
    text_parts: list[str] = []
    reasoning_summary_parts: list[str] = []
    reasoning_content_parts: list[str] = []
    function_calls: list[ToolCall] = []

    for item in response_obj.get("output", []):
        item_type = item.get("type")

        if item_type == "reasoning":
            # Extract summary text(s) and detailed reasoning text(s) from the
            # reasoning output item.
            for summary_entry in item.get("summary", []):
                if summary_entry.get("type") == "summary_text":
                    summary_text = summary_entry.get("text", "")
                    if summary_text:
                        reasoning_summary_parts.append(summary_text)
            for content_entry in item.get("content", []):
                if content_entry.get("type") == "reasoning_text":
                    reasoning_text = content_entry.get("text", "")
                    if reasoning_text:
                        reasoning_content_parts.append(reasoning_text)
        elif item_type == "message":
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

    usage_obj = response_obj.get("usage", {})
    input_tokens = (
        int(usage_obj.get("input_tokens", 0) or 0) if isinstance(usage_obj, dict) else 0
    )
    output_tokens = (
        int(usage_obj.get("output_tokens", 0) or 0)
        if isinstance(usage_obj, dict)
        else 0
    )
    cached_input_tokens = 0
    reasoning_tokens = 0
    if isinstance(usage_obj, dict):
        input_details = usage_obj.get("input_tokens_details", {})
        if isinstance(input_details, dict):
            cached_input_tokens = int(
                input_details.get(
                    "cached_tokens", input_details.get("cached_input_tokens", 0)
                )
                or 0
            )
        output_details = usage_obj.get("output_tokens_details", {})
        if isinstance(output_details, dict):
            reasoning_tokens = int(output_details.get("reasoning_tokens", 0) or 0)

    final_text = "".join(text_parts).strip() or "".join(streamed_text_parts).strip()
    reasoning_summary = "\n\n".join(reasoning_summary_parts)
    if not reasoning_summary.strip():
        reasoning_summary = ""
    reasoning_content = "\n\n".join(reasoning_content_parts)
    if not reasoning_content.strip():
        reasoning_content = ""
    return CompletedResponse(
        response_id=response_obj.get("id"),
        text=final_text,
        reasoning_summary=reasoning_summary,
        reasoning_content=reasoning_content,
        usage=TokenUsage(
            input_tokens=input_tokens,
            cached_input_tokens=cached_input_tokens,
            output_tokens=output_tokens,
            reasoning_tokens=reasoning_tokens,
        ),
        function_calls=function_calls,
    )
