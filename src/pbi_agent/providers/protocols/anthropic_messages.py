"""Anthropic Messages protocol helpers."""

from __future__ import annotations

from typing import Any
import urllib.error

from pbi_agent.config import Settings
from pbi_agent.display.protocol import DisplayProtocol
from pbi_agent.models.messages import CompletedResponse
from pbi_agent.providers import retry as provider_retry

ANTHROPIC_VERSION = "2023-06-01"

_EFFORT_MAP: dict[str, str] = {
    "low": "low",
    "medium": "medium",
    "high": "high",
    "xhigh": "max",
}

_HTTP_ERROR_TYPES: dict[int, str] = {
    400: "invalid_request_error",
    401: "authentication_error",
    403: "permission_error",
    404: "not_found_error",
    413: "request_too_large",
    429: "rate_limit_error",
    500: "api_error",
    529: "overloaded_error",
}

_HTTP_ERROR_MESSAGES: dict[int, str] = {
    400: "There was an issue with the format or content of your request.",
    401: "There's an issue with your API key.",
    403: "Your API key does not have permission to use the specified resource.",
    404: "The requested resource could not be found.",
    413: "Request exceeds the maximum allowed number of bytes.",
    429: "Your account has hit a rate limit.",
    500: "An unexpected error has occurred internal to Anthropic's systems.",
    529: "The API is temporarily overloaded.",
}


def build_messages_body(
    *,
    settings: Settings,
    tools: list[dict[str, Any]],
    messages: list[dict[str, Any]],
    system_prompt: str | None,
) -> dict[str, Any]:
    """Build an Anthropic Messages request body."""
    body: dict[str, Any] = {
        "model": settings.model,
        "max_tokens": settings.max_tokens,
        "cache_control": {"type": "ephemeral"},
        "tools": tools,
        "messages": messages,
    }

    if supports_adaptive_thinking(settings.model):
        body["thinking"] = {"type": "adaptive"}
        effort = _EFFORT_MAP.get(settings.reasoning_effort, "high")
        body["output_config"] = {"effort": effort}

    if system_prompt:
        body["system"] = system_prompt
    return body


def render_messages_response(
    display: DisplayProtocol,
    response: CompletedResponse,
) -> None:
    """Render parsed Anthropic response display items."""
    pdata = response.provider_data or {}
    if isinstance(pdata, dict):
        for thinking_text in pdata.get("thinking_parts", []):
            display.render_thinking(thinking_text)
        if pdata.get("has_redacted_thinking"):
            display.render_redacted_thinking()

    display_items = pdata.get("display_items", []) if isinstance(pdata, dict) else []
    if isinstance(display_items, list) and display_items:
        for item in display_items:
            if not isinstance(item, dict):
                continue
            item_type = item.get("type")
            if item_type == "text":
                text = item.get("text")
                if isinstance(text, str) and text:
                    display.render_markdown(text)
            elif item_type == "web_search":
                display_web_search_result(
                    display,
                    item.get("sources", []),
                    queries=item.get("queries", []),
                )
        return

    if response.text:
        display.render_markdown(response.text)

    if response.web_search_sources:
        display.web_search_sources(response.web_search_sources)


def display_web_search_result(
    display: DisplayProtocol,
    sources: list[dict[str, Any]],
    *,
    queries: list[str] | None = None,
) -> None:
    """Render Anthropic native web-search output as a tool result."""
    display.function_start(1)
    display.function_result(
        name="web_search",
        success=True,
        call_id="",
        arguments={
            "queries": list(queries or []),
            "sources": list(sources),
        },
    )
    display.tool_group_end()


def normalize_http_error(
    exc: urllib.error.HTTPError,
    error_body: str,
) -> dict[str, Any]:
    """Normalize Anthropic HTTP errors to a stable structured payload."""
    payload = provider_retry.parse_error_payload(error_body)
    error_type = _HTTP_ERROR_TYPES.get(exc.code)
    message = _HTTP_ERROR_MESSAGES.get(exc.code, f"HTTP {exc.code}")
    request_id = provider_retry.request_id_from_headers(
        exc,
        header_names=("request-id",),
    )

    if payload is not None:
        payload_request_id = payload.get("request_id")
        if isinstance(payload_request_id, str) and payload_request_id.strip():
            request_id = payload_request_id.strip()

        error_value = payload.get("error")
        if isinstance(error_value, dict):
            payload_type = error_value.get("type")
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


def supports_adaptive_thinking(model: str) -> bool:
    """Return whether the model supports Anthropic adaptive thinking fields."""
    normalized = model.strip().lower()
    return not normalized.startswith("claude-haiku")
