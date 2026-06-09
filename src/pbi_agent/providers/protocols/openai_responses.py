"""OpenAI Responses protocol helpers shared by Responses-style providers."""

from __future__ import annotations

from collections.abc import Callable
import json
from typing import Any
import urllib.error

from pbi_agent.agent.tool_runtime import to_function_call_output_items
from pbi_agent.display.protocol import DisplayProtocol
from pbi_agent.models.messages import CompletedResponse, WebSearchSource
from pbi_agent.providers import retry as provider_retry
from pbi_agent.tools.types import ToolResult

_XAI_HTTP_ERROR_TYPES: dict[int, str] = {
    400: "invalid_request_error",
    401: "authentication_error",
    403: "permission_error",
    404: "not_found_error",
    405: "invalid_request_error",
    415: "invalid_request_error",
    422: "invalid_request_error",
    429: "rate_limit_error",
}

_XAI_HTTP_ERROR_MESSAGES: dict[int, str] = {
    400: "Request body or URL contains invalid input.",
    401: "No authorization header or an invalid authorization token was provided.",
    403: "API key or team lacks permission to perform this action.",
    404: "The requested model or endpoint could not be found.",
    405: "HTTP method is not allowed for this endpoint.",
    415: "Request body is missing or Content-Type is not application/json.",
    422: "Request body contains an invalid field format.",
    429: "Too many requests. Reduce request rate or increase your rate limit.",
}

ENCRYPTED_REASONING_INCLUDE = "reasoning.encrypted_content"


def responses_include(values: list[str] | None = None) -> list[str]:
    """Return Responses include values with encrypted reasoning content enabled."""
    include: list[str] = []
    for value in values or []:
        if value not in include:
            include.append(value)
    if ENCRYPTED_REASONING_INCLUDE not in include:
        include.append(ENCRYPTED_REASONING_INCLUDE)
    return include


def response_history_item_for_input(item: dict[str, Any]) -> dict[str, Any]:
    """Return a Responses output/history item in request-input-safe form."""
    cloned = _clone_json_dict(item)
    item_type = cloned.get("type")
    if item_type == "message":
        return _sanitize_message_history_item(cloned)
    if item_type == "reasoning":
        return _sanitize_known_item(
            cloned,
            ("type", "summary", "content", "encrypted_content"),
        )
    if item_type == "function_call":
        return _sanitize_known_item(
            cloned,
            ("type", "call_id", "name", "arguments"),
        )
    if item_type == "custom_tool_call":
        return _sanitize_known_item(
            cloned,
            ("type", "call_id", "name", "input"),
        )
    if item_type in {"function_call_output", "custom_tool_call_output"}:
        return _sanitize_known_item(cloned, ("type", "call_id", "output"))
    return _strip_response_output_metadata(cloned)


def render_responses_display(
    display: DisplayProtocol,
    response: CompletedResponse,
    *,
    web_search_renderer: (
        Callable[[DisplayProtocol, list[WebSearchSource] | list[dict[str, Any]]], None]
        | None
    ) = None,
) -> None:
    """Render common Responses-style display fields."""
    if response.reasoning_summary or response.reasoning_content:
        display.render_thinking(
            _reasoning_body_text(
                response.reasoning_content,
                response.reasoning_summary,
            ),
            title=response.reasoning_summary or None,
        )

    display_items = response.provider_data.get("display_items")
    if isinstance(display_items, list) and display_items:
        for item in display_items:
            if not isinstance(item, dict):
                continue
            item_type = item.get("type")
            if item_type == "message":
                text = item.get("text")
                if isinstance(text, str) and text:
                    display.render_markdown(text)
            elif item_type == "web_search_call" and web_search_renderer is not None:
                web_search_renderer(display, item.get("sources", []))
        return

    if response.text:
        display.render_markdown(response.text)

    if web_search_renderer is not None and (
        response.had_web_search_call or response.web_search_sources
    ):
        web_search_renderer(display, response.web_search_sources)


def serialize_function_call_output(result: ToolResult) -> dict[str, Any]:
    """Serialize one normal Responses function-call output item."""
    return to_function_call_output_items([result])[0]


def _sanitize_known_item(
    item: dict[str, Any],
    allowed_keys: tuple[str, ...],
) -> dict[str, Any]:
    return {key: _clone_json_value(item[key]) for key in allowed_keys if key in item}


def _sanitize_message_history_item(item: dict[str, Any]) -> dict[str, Any]:
    sanitized = _sanitize_known_item(item, ("type", "role"))
    if "content" in item:
        sanitized["content"] = _sanitize_message_content(item["content"])
    return sanitized


def _sanitize_message_content(content: Any) -> Any:
    if isinstance(content, str):
        return content
    if not isinstance(content, list):
        return _clone_json_value(content)
    sanitized_parts: list[Any] = []
    for part in content:
        if not isinstance(part, dict):
            sanitized_parts.append(_clone_json_value(part))
            continue
        part_type = part.get("type")
        if part_type in {"input_text", "output_text"}:
            sanitized_parts.append(_sanitize_known_item(part, ("type", "text")))
        elif part_type == "input_image":
            sanitized_parts.append(
                _sanitize_known_item(
                    part,
                    ("type", "image_url", "file_id", "detail"),
                )
            )
        elif part_type == "refusal":
            sanitized_parts.append(_sanitize_known_item(part, ("type", "refusal")))
        else:
            sanitized_parts.append(_strip_response_output_metadata(part))
    return sanitized_parts


def _strip_response_output_metadata(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            key: _strip_response_output_metadata(inner)
            for key, inner in value.items()
            if key not in {"id", "status", "phase", "logprobs"}
        }
    if isinstance(value, list):
        return [_strip_response_output_metadata(item) for item in value]
    return value


def _clone_json_dict(item: dict[str, Any]) -> dict[str, Any]:
    cloned = _clone_json_value(item)
    return cloned if isinstance(cloned, dict) else dict(item)


def _clone_json_value(value: Any) -> Any:
    return json.loads(json.dumps(value))


def normalize_xai_http_error(
    exc: urllib.error.HTTPError,
    error_body: str,
) -> dict[str, Any]:
    """Normalize xAI HTTP errors to a stable structured payload."""
    payload = provider_retry.parse_error_payload(error_body)
    error_type = _XAI_HTTP_ERROR_TYPES.get(exc.code)
    message = _XAI_HTTP_ERROR_MESSAGES.get(exc.code, f"HTTP {exc.code}")
    request_id = provider_retry.request_id_from_headers(
        exc,
        header_names=("request-id", "x-request-id"),
    )

    if payload is not None:
        payload_request_id = payload.get("request_id") or payload.get("requestId")
        if isinstance(payload_request_id, str) and payload_request_id.strip():
            request_id = payload_request_id.strip()

        error_value = payload.get("error")
        if isinstance(error_value, dict):
            payload_type = error_value.get("type") or error_value.get("code")
            if isinstance(payload_type, str) and payload_type.strip():
                error_type = payload_type.strip()
            payload_message = error_value.get("message")
            if isinstance(payload_message, str) and payload_message.strip():
                message = payload_message.strip()
        elif isinstance(error_value, str) and error_value.strip():
            message = error_value.strip()

    if error_type is None:
        if 400 <= exc.code < 500:
            error_type = "invalid_request_error"
        else:
            error_type = "api_error"

    return {
        "type": "error",
        "status": exc.code,
        "error": {
            "type": error_type,
            "message": message,
        },
        **({"request_id": request_id} if request_id else {}),
    }


def _reasoning_body_text(
    reasoning_content: str | None,
    reasoning_summary: str | None,
) -> str | None:
    parts = [part for part in (reasoning_content, reasoning_summary) if part]
    if not parts:
        return None
    return "\n\n".join(parts)
