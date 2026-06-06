"""Google Gemini Interactions protocol helpers."""

from __future__ import annotations

from typing import Any
import urllib.error

from pbi_agent.display.protocol import DisplayProtocol
from pbi_agent.models.messages import CompletedResponse, WebSearchSource
from pbi_agent.providers import retry as provider_retry
from pbi_agent.providers.transport import SemanticResponseError

_HTTP_ERROR_TYPES: dict[int, str] = {
    400: "invalid_argument",
    403: "permission_denied",
    404: "not_found",
    429: "resource_exhausted",
    500: "internal",
    503: "unavailable",
    504: "deadline_exceeded",
}

_HTTP_ERROR_MESSAGES: dict[int, str] = {
    400: "The request body is malformed.",
    403: "Your API key doesn't have the required permissions.",
    404: "The requested resource wasn't found.",
    429: "You've exceeded the rate limit.",
    500: "An unexpected error occurred on Google's side.",
    503: "The service may be temporarily overloaded or down.",
    504: "The service is unable to finish processing within the deadline.",
}


def validate_interaction_status(response_json: dict[str, Any]) -> None:
    """Raise a retry-aware semantic error for failed Interactions responses."""
    status = response_json.get("status")
    if status in {"failed", "cancelled", "incomplete"}:
        error_obj = response_json.get("error")
        if isinstance(error_obj, dict):
            code = str(error_obj.get("code", "unknown_error"))
            message = str(error_obj.get("message", "No error message"))
            raise _semantic_error(
                status=str(status),
                code=code,
                message=message,
                payload=response_json,
            )
        raise _semantic_error(
            status=str(status),
            code=None,
            message="",
            payload=response_json,
        )
    if status == "in_progress":
        raise _semantic_error(
            status="in_progress",
            code=None,
            message="Google interaction returned in_progress for a non-background request.",
            payload=response_json,
        )


def render_interactions_response(
    display: DisplayProtocol,
    response: CompletedResponse,
) -> None:
    """Render parsed Google Interactions response display items."""
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
            if item_type == "text":
                text = item.get("text")
                if isinstance(text, str) and text:
                    display.render_markdown(text)
            elif item_type == "google_search_result":
                display_web_search_result(
                    display,
                    item.get("sources", []),
                    queries=item.get("queries", []),
                )
        return

    if response.web_search_sources:
        display_web_search_result(
            display,
            response.web_search_sources,
            queries=response.provider_data.get("web_search_queries", []),
        )
    if response.text:
        display.render_markdown(response.text)


def display_web_search_result(
    display: DisplayProtocol,
    sources: list[WebSearchSource] | list[dict[str, Any]],
    *,
    queries: list[str] | None = None,
) -> None:
    """Render Google native search output as a tool result."""
    display.function_start(1)
    serialized_sources = [
        {
            "title": source.title,
            "url": source.url,
            "snippet": source.snippet,
        }
        if isinstance(source, WebSearchSource)
        else dict(source)
        for source in sources
    ]
    display.function_result(
        name="web_search",
        success=True,
        call_id="",
        arguments={
            "queries": list(queries or []),
            "sources": serialized_sources,
        },
    )
    display.tool_group_end()


def normalize_http_error(
    exc: urllib.error.HTTPError,
    error_body: str,
) -> dict[str, Any]:
    """Normalize Google Interactions HTTP errors."""
    payload = provider_retry.parse_error_payload(error_body)
    error_type = _HTTP_ERROR_TYPES.get(exc.code)
    message = _HTTP_ERROR_MESSAGES.get(exc.code, f"HTTP {exc.code}")
    request_id = provider_retry.request_id_from_headers(
        exc,
        header_names=("x-request-id", "request-id", "x-goog-request-id"),
    )

    if payload is not None:
        error_value = payload.get("error")
        if isinstance(error_value, dict):
            payload_type = error_value.get("status")
            if isinstance(payload_type, str) and payload_type.strip():
                error_type = payload_type.strip().lower()
            payload_message = error_value.get("message")
            if isinstance(payload_message, str) and payload_message.strip():
                message = payload_message.strip()
            payload_request_id = error_value.get("request_id")
            if isinstance(payload_request_id, str) and payload_request_id.strip():
                request_id = payload_request_id.strip()

    if error_type is None:
        if 400 <= exc.code < 500:
            error_type = "invalid_argument"
        else:
            error_type = "internal"

    normalized: dict[str, Any] = {
        "type": "error",
        "status": exc.code,
        "error": {
            "type": error_type,
            "message": message,
        },
    }
    if request_id:
        normalized["request_id"] = request_id
    return normalized


def _semantic_error(
    *,
    status: str,
    code: str | None,
    message: str,
    payload: dict[str, Any],
) -> SemanticResponseError:
    return SemanticResponseError(
        _google_interaction_error_message(status, code, message),
        payload=payload,
        retryable=provider_retry.is_retryable_semantic_status(status)
        or provider_retry.is_retryable_semantic_error_code(code),
        metadata={"interaction_status": status},
    )


def _google_interaction_error_message(
    status: str,
    code: str | None,
    message: str,
) -> str:
    if code:
        return f"Google interaction failed ({code}): {message}"
    if status == "in_progress" and message:
        return message
    return f"Google interaction failed with status {status}."


def _reasoning_body_text(
    reasoning_content: str | None,
    reasoning_summary: str | None,
) -> str | None:
    parts = [part for part in (reasoning_content, reasoning_summary) if part]
    if not parts:
        return None
    return "\n\n".join(parts)
