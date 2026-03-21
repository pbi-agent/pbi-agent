"""Google Gemini Interactions HTTP provider.

Uses direct synchronous HTTP calls to the Gemini Interactions API.
Conversation history is managed server-side via ``previous_interaction_id``.
"""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from typing import Any

from pbi_agent import __version__
from pbi_agent.agent.system_prompt import get_system_prompt
from pbi_agent.agent.tool_runtime import execute_tool_calls as _execute_tool_calls
from pbi_agent.config import Settings, missing_api_key_message
from pbi_agent.models.messages import (
    CompletedResponse,
    ImageAttachment,
    TokenUsage,
    ToolCall,
    UserTurnInput,
    WebSearchSource,
)
from pbi_agent.providers.base import Provider
from pbi_agent.tools.registry import get_openai_tool_definitions
from pbi_agent.tools.types import ToolContext
from pbi_agent.ui.display_protocol import DisplayProtocol

_REQUEST_TIMEOUT_SECS = 3600.0
_THINKING_LEVEL_MAP: dict[str, str] = {
    "low": "low",
    "medium": "medium",
    "high": "high",
    "xhigh": "high",
}

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


class GoogleProvider(Provider):
    """Provider backed by the Gemini Interactions HTTP API."""

    def __init__(
        self,
        settings: Settings,
        *,
        system_prompt: str | None = None,
        excluded_tools: set[str] | None = None,
    ) -> None:
        self._settings = settings
        self._tools = _google_tool_definitions(excluded_names=excluded_tools)
        if settings.web_search:
            self._tools.append({"type": "google_search"})
        self._instructions = system_prompt or get_system_prompt()
        self._previous_interaction_id: str | None = None

    @property
    def settings(self) -> Settings:
        return self._settings

    def set_previous_response_id(self, response_id: str | None) -> None:
        self._previous_interaction_id = response_id

    def connect(self) -> None:
        if not self._settings.api_key:
            raise ValueError(missing_api_key_message("google"))

    def close(self) -> None:
        pass

    def reset_conversation(self) -> None:
        self._previous_interaction_id = None

    def request_turn(
        self,
        *,
        user_message: str | None = None,
        user_input: UserTurnInput | None = None,
        tool_result_items: list[dict[str, Any]] | None = None,
        instructions: str | None = None,
        display: DisplayProtocol,
        session_usage: TokenUsage,
        turn_usage: TokenUsage,
    ) -> CompletedResponse:
        if user_input is None and user_message is not None:
            user_input = UserTurnInput(text=user_message)

        if user_input is not None:
            input_value = _google_user_input_value(user_input)
        elif tool_result_items is not None:
            input_value = tool_result_items
        else:
            raise ValueError("Either user_input or tool_result_items is required")

        result = self._http_request(
            input_value=input_value,
            instructions=instructions or self._instructions,
            display=display,
        )
        self._previous_interaction_id = result.response_id
        session_usage.add(result.usage)
        turn_usage.add(result.usage)
        display.session_usage(session_usage)

        if result.reasoning_summary or result.reasoning_content:
            display.render_thinking(
                _reasoning_body_text(
                    result.reasoning_content,
                    result.reasoning_summary,
                ),
                title=result.reasoning_summary or None,
            )

        display_items = result.provider_data.get("display_items")
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
                    _display_web_search_result(
                        display,
                        item.get("sources", []),
                        queries=item.get("queries", []),
                    )
        else:
            if result.web_search_sources:
                _display_web_search_result(
                    display,
                    result.web_search_sources,
                    queries=result.provider_data.get("web_search_queries", []),
                )
            if result.text:
                display.render_markdown(result.text)

        return result

    def execute_tool_calls(
        self,
        response: CompletedResponse,
        *,
        max_workers: int,
        display: DisplayProtocol,
        session_usage: TokenUsage,
        turn_usage: TokenUsage,
        sub_agent_depth: int = 0,
    ) -> tuple[list[dict[str, Any]], bool]:
        if not response.function_calls:
            return [], False

        displayable_calls = [
            call for call in response.function_calls if call.name != "sub_agent"
        ]
        if displayable_calls:
            display.function_start(len(displayable_calls))
        batch = _execute_tool_calls(
            response.function_calls,
            max_workers=max_workers,
            context=ToolContext(
                settings=self._settings,
                display=display,
                session_usage=session_usage,
                turn_usage=turn_usage,
                sub_agent_depth=sub_agent_depth,
            ),
        )

        tool_result_items: list[dict[str, Any]] = []
        for result in batch.results:
            call = _find_by_id(response.function_calls, result.call_id)
            if not (call and call.name == "sub_agent"):
                display.function_result(
                    name=call.name if call else "unknown",
                    success=not result.is_error,
                    call_id=result.call_id,
                    arguments=call.arguments if call else None,
                )
            item: dict[str, Any] = {
                "type": "function_result",
                "name": call.name if call else "",
                "call_id": result.call_id,
                "result": _google_function_result_value(result),
            }
            if result.is_error:
                item["is_error"] = True
            tool_result_items.append(item)
        if displayable_calls:
            display.tool_group_end()

        return tool_result_items, batch.had_errors

    def _http_request(
        self,
        *,
        input_value: str | list[dict[str, Any]],
        instructions: str,
        display: DisplayProtocol,
    ) -> CompletedResponse:
        display.wait_start(_waiting_message_for_input(input_value))

        body = self._build_request_body(
            input_value=input_value,
            instructions=instructions,
        )
        request_data = json.dumps(body).encode("utf-8")
        headers = {
            "Accept": "application/json",
            "Content-Type": "application/json",
            "x-goog-api-key": self._settings.api_key,
            "User-Agent": f"pbi-agent/{__version__}",
        }

        max_retries = self._settings.max_retries
        last_error: Exception | None = None
        last_error_message: str | None = None

        for attempt in range(max_retries + 1):
            if attempt > 0:
                display.retry_notice(attempt, max_retries)

            try:
                req = urllib.request.Request(
                    self._settings.responses_url,
                    data=request_data,
                    headers=headers,
                    method="POST",
                )
                with urllib.request.urlopen(req, timeout=_REQUEST_TIMEOUT_SECS) as resp:
                    response_json = json.loads(resp.read().decode("utf-8"))

                _raise_if_interaction_failed(response_json)
                result = self._parse_response(response_json)
                display.wait_stop()
                return result
            except urllib.error.HTTPError as exc:
                error_body = _read_error_body(exc)
                error_payload = _normalize_http_error(exc, error_body)
                if exc.code == 429:
                    if attempt >= max_retries:
                        display.wait_stop()
                        raise RuntimeError(
                            _format_error_message(
                                f"Google rate limit exceeded after {max_retries + 1} attempts",
                                error_payload,
                            )
                        ) from exc
                    wait = _extract_retry_after(exc, attempt)
                    display.rate_limit_notice(
                        wait_seconds=wait,
                        attempt=attempt + 1,
                        max_retries=max_retries,
                    )
                    time.sleep(wait)
                    continue

                if exc.code == 503:
                    if attempt >= max_retries:
                        display.wait_stop()
                        raise RuntimeError(
                            _format_error_message(
                                f"Google API overloaded after {max_retries + 1} attempts",
                                error_payload,
                            )
                        ) from exc
                    wait = min(2.0 * (2**attempt), 30.0) + 1.0
                    display.overload_notice(
                        wait_seconds=wait,
                        attempt=attempt + 1,
                        max_retries=max_retries,
                    )
                    time.sleep(wait)
                    continue

                if exc.code >= 500:
                    last_error = exc
                    last_error_message = _format_error_message(
                        f"Google request failed after {max_retries + 1} attempts",
                        error_payload,
                    )
                    continue

                display.wait_stop()
                raise RuntimeError(
                    _format_error_message(
                        f"Google Interactions API error {exc.code}",
                        error_payload,
                    )
                ) from exc
            except urllib.error.URLError as exc:
                last_error = exc
                last_error_message = None
                continue

        display.wait_stop()
        if last_error is not None:
            if last_error_message:
                raise RuntimeError(last_error_message) from last_error
            raise RuntimeError(
                f"Google request failed after {max_retries + 1} attempts: {last_error}"
            ) from last_error
        raise RuntimeError("Google request failed after retries.")

    def _build_request_body(
        self,
        *,
        input_value: str | list[dict[str, Any]],
        instructions: str | None,
    ) -> dict[str, Any]:
        body: dict[str, Any] = {
            "model": self._settings.model,
            "input": input_value,
            "tools": self._tools,
            "stream": False,
            "store": True,
            "generation_config": {
                "thinking_level": _THINKING_LEVEL_MAP.get(
                    self._settings.reasoning_effort,
                    "high",
                ),
                "thinking_summaries": "auto",
                "max_output_tokens": self._settings.max_tokens,
            },
        }
        if instructions:
            body["system_instruction"] = instructions
        if self._previous_interaction_id:
            body["previous_interaction_id"] = self._previous_interaction_id
        return body

    def _parse_response(self, response_json: dict[str, Any]) -> CompletedResponse:
        text_parts: list[str] = []
        thought_summary_parts: list[str] = []
        thought_signatures: list[str] = []
        function_calls: list[ToolCall] = []
        display_items: list[dict[str, Any]] = []
        saw_google_search_result = False
        pending_google_search_queries: dict[str, list[str]] = {}

        output_items = response_json.get("outputs", [])
        if not isinstance(output_items, list):
            output_items = []

        for item in output_items:
            if not isinstance(item, dict):
                continue
            item_type = item.get("type")

            if item_type == "text":
                text = item.get("text", "")
                if isinstance(text, str) and text:
                    text_parts.append(text)
                    display_items.append({"type": "text", "text": text})

            elif item_type == "thought":
                summary_text = _extract_thought_summary_text(item.get("summary"))
                if summary_text:
                    thought_summary_parts.append(summary_text)
                signature = item.get("signature")
                if isinstance(signature, str) and signature:
                    thought_signatures.append(signature)

            elif item_type == "function_call":
                function_calls.append(
                    ToolCall(
                        call_id=str(item.get("id", "")),
                        name=str(item.get("name", "")),
                        arguments=item.get("arguments"),
                    )
                )
            elif item_type == "google_search_call":
                call_id = str(item.get("id", ""))
                if call_id:
                    pending_google_search_queries[call_id] = (
                        _extract_google_search_call_queries(item)
                    )
            elif item_type == "google_search_result":
                saw_google_search_result = True
                display_items.append(
                    {
                        "type": "google_search_result",
                        "queries": pending_google_search_queries.get(
                            str(item.get("call_id", "")),
                            _extract_google_search_queries(item, response_json),
                        ),
                        "sources": _extract_google_search_result_sources(
                            item,
                            response_json,
                        ),
                    }
                )

        web_search_queries = _extract_google_search_queries(None, response_json)
        web_search_sources = _extract_google_search_sources(response_json)
        if web_search_sources and not saw_google_search_result:
            insert_at = next(
                (
                    index
                    for index, item in enumerate(display_items)
                    if isinstance(item, dict) and item.get("type") == "text"
                ),
                len(display_items),
            )
            display_items.insert(
                insert_at,
                {
                    "type": "google_search_result",
                    "queries": web_search_queries,
                    "sources": web_search_sources,
                },
            )

        usage_obj = response_json.get("usage", {})
        input_tokens = int(_usage_value(usage_obj, "total_input_tokens"))
        cached_input_tokens = int(_usage_value(usage_obj, "total_cached_tokens"))
        output_tokens = int(_usage_value(usage_obj, "total_output_tokens"))
        reasoning_tokens = int(_usage_value(usage_obj, "total_thought_tokens"))
        tool_use_tokens = int(_usage_value(usage_obj, "total_tool_use_tokens"))
        provider_total_tokens = int(_usage_value(usage_obj, "total_tokens"))

        return CompletedResponse(
            response_id=response_json.get("id"),
            text="\n\n".join(part for part in text_parts if part.strip()).strip(),
            usage=TokenUsage(
                input_tokens=input_tokens,
                cached_input_tokens=cached_input_tokens,
                output_tokens=output_tokens,
                reasoning_tokens=reasoning_tokens,
                tool_use_tokens=tool_use_tokens,
                provider_total_tokens=provider_total_tokens,
                context_tokens=provider_total_tokens,
                model=_response_model_name(response_json),
            ),
            function_calls=function_calls,
            reasoning_content="\n\n".join(
                part for part in thought_summary_parts if part.strip()
            ).strip(),
            provider_data={
                "status": response_json.get("status"),
                "thought_signatures": thought_signatures,
                "display_items": display_items,
                "web_search_queries": web_search_queries,
            },
            web_search_sources=web_search_sources,
        )


def _extract_google_search_sources(
    response_json: dict[str, Any],
) -> list[WebSearchSource]:
    """Extract web search sources from Google Interactions and grounding metadata."""
    sources: list[WebSearchSource] = []

    output_items = response_json.get("outputs", [])
    if isinstance(output_items, list):
        for item in output_items:
            if not isinstance(item, dict) or item.get("type") != "google_search_result":
                continue
            sources.extend(_extract_google_search_result_sources(item, response_json))

    if sources:
        return sources

    sources.extend(_extract_google_text_annotation_sources(response_json))
    if sources:
        return sources

    metadata = _extract_google_grounding_metadata(response_json)
    if not metadata:
        return []
    chunks = metadata.get("groundingChunks", [])
    if not isinstance(chunks, list):
        return []
    for chunk in chunks:
        if not isinstance(chunk, dict):
            continue
        web = chunk.get("web")
        if not isinstance(web, dict):
            continue
        url = str(web.get("uri", ""))
        if not url:
            continue
        sources.append(
            WebSearchSource(
                title=str(web.get("title", "")),
                url=url,
            )
        )
    return sources


def _extract_google_search_result_sources(
    item: dict[str, Any],
    response_json: dict[str, Any],
) -> list[WebSearchSource]:
    results = item.get("result", [])
    sources: list[WebSearchSource] = []
    if isinstance(results, list):
        for entry in results:
            if not isinstance(entry, dict):
                continue
            url = str(entry.get("url", ""))
            if not url:
                continue
            sources.append(
                WebSearchSource(
                    title=str(entry.get("title", "")),
                    url=url,
                )
            )
    if sources:
        return sources
    return _extract_google_text_annotation_sources(response_json)


def _extract_google_text_annotation_sources(
    response_json: dict[str, Any],
) -> list[WebSearchSource]:
    output_items = response_json.get("outputs", [])
    if not isinstance(output_items, list):
        return []
    sources: list[WebSearchSource] = []
    for item in output_items:
        if not isinstance(item, dict) or item.get("type") != "text":
            continue
        annotations = item.get("annotations", [])
        if not isinstance(annotations, list):
            continue
        for annotation in annotations:
            if not isinstance(annotation, dict):
                continue
            if annotation.get("type") != "url_citation":
                continue
            url = str(annotation.get("url", ""))
            if not url:
                continue
            sources.append(
                WebSearchSource(
                    title=str(annotation.get("title", "")),
                    url=url,
                )
            )
    return sources
    return sources


def _extract_google_grounding_metadata(
    response_json: dict[str, Any],
) -> dict[str, Any] | None:
    metadata = response_json.get("groundingMetadata")
    if isinstance(metadata, dict):
        return metadata

    candidates = response_json.get("candidates")
    if isinstance(candidates, list):
        for candidate in candidates:
            if not isinstance(candidate, dict):
                continue
            metadata = candidate.get("groundingMetadata")
            if isinstance(metadata, dict):
                return metadata

    output_items = response_json.get("outputs", [])
    if isinstance(output_items, list):
        for item in output_items:
            if not isinstance(item, dict):
                continue
            metadata = item.get("groundingMetadata")
            if isinstance(metadata, dict):
                return metadata

    return None


def _extract_google_search_queries(
    item: dict[str, Any] | None,
    response_json: dict[str, Any],
) -> list[str]:
    if isinstance(item, dict):
        raw_queries = item.get("web_search_queries") or item.get("webSearchQueries")
        if isinstance(raw_queries, list):
            queries = [
                str(query).strip() for query in raw_queries if str(query).strip()
            ]
            if queries:
                return queries

    metadata = _extract_google_grounding_metadata(response_json)
    if not metadata:
        return []
    raw_queries = metadata.get("webSearchQueries", [])
    if not isinstance(raw_queries, list):
        return []
    return [str(query).strip() for query in raw_queries if str(query).strip()]


def _extract_google_search_call_queries(item: dict[str, Any]) -> list[str]:
    arguments = item.get("arguments")
    if not isinstance(arguments, dict):
        return []
    raw_queries = arguments.get("queries", [])
    if not isinstance(raw_queries, list):
        return []
    return [str(query).strip() for query in raw_queries if str(query).strip()]


def _display_web_search_result(
    display: DisplayProtocol,
    sources: list[WebSearchSource] | list[dict[str, Any]],
    *,
    queries: list[str] | None = None,
) -> None:
    normalized_sources = [
        source
        if isinstance(source, dict)
        else {"title": source.title, "url": source.url, "snippet": source.snippet}
        for source in (sources or [])
    ]
    display.function_start(1)
    display.function_result(
        name="web_search",
        success=True,
        call_id="",
        arguments={
            "sources": normalized_sources,
            "queries": list(queries or []),
        },
    )
    display.tool_group_end()


def _find_by_id(calls: list[ToolCall], call_id: str) -> ToolCall | None:
    for call in calls:
        if call.call_id == call_id:
            return call
    return None


def _google_user_input_value(
    user_input: UserTurnInput,
) -> str | list[dict[str, Any]]:
    if not user_input.images:
        return user_input.text

    content: list[dict[str, Any]] = []
    if user_input.text:
        content.append({"type": "text", "text": user_input.text})
    for image in user_input.images:
        content.append(_google_image_part(image))
    return content


def _google_function_result_value(result) -> str | list[dict[str, Any]]:
    if not result.attachments:
        return result.output_json

    content = [{"type": "text", "text": result.output_json}]
    content.extend(_google_image_part(image) for image in result.attachments)
    return content


def _google_image_part(image: ImageAttachment) -> dict[str, Any]:
    return {
        "type": "image",
        "mime_type": image.mime_type,
        "data": image.data_base64,
    }


def _google_tool_definitions(
    *, excluded_names: set[str] | None = None
) -> list[dict[str, Any]]:
    return [
        _normalize_google_tool_definition(tool)
        for tool in get_openai_tool_definitions(excluded_names=excluded_names)
    ]


def _normalize_google_tool_definition(tool: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(tool)
    parameters = normalized.get("parameters")
    if isinstance(parameters, dict):
        normalized["parameters"] = _normalize_google_schema(parameters)
    return normalized


def _normalize_google_schema(value: Any) -> Any:
    if isinstance(value, dict):
        normalized: dict[str, Any] = {}
        for key, child in value.items():
            if key == "required" and isinstance(child, list) and not child:
                continue
            normalized[key] = _normalize_google_schema(child)
        return normalized
    if isinstance(value, list):
        return [_normalize_google_schema(item) for item in value]
    return value


def _raise_if_interaction_failed(response_json: dict[str, Any]) -> None:
    status = response_json.get("status")
    if status in {"failed", "cancelled", "incomplete"}:
        error_obj = response_json.get("error")
        if isinstance(error_obj, dict):
            code = str(error_obj.get("code", "unknown_error"))
            message = str(error_obj.get("message", "No error message"))
            raise RuntimeError(f"Google interaction failed ({code}): {message}")
        raise RuntimeError(f"Google interaction failed with status {status}.")
    if status == "in_progress":
        raise RuntimeError(
            "Google interaction returned in_progress for a non-background request."
        )


def _extract_thought_summary_text(summary: Any) -> str:
    if isinstance(summary, str):
        return summary.strip()
    if isinstance(summary, dict):
        return _extract_text_content(summary).strip()
    if not isinstance(summary, list):
        return ""

    parts: list[str] = []
    for item in summary:
        if isinstance(item, str):
            if item.strip():
                parts.append(item.strip())
            continue
        if isinstance(item, dict):
            text = _extract_text_content(item).strip()
            if text:
                parts.append(text)
    return "\n\n".join(parts).strip()


def _extract_text_content(item: dict[str, Any]) -> str:
    if item.get("type") == "text":
        text = item.get("text", "")
        return text if isinstance(text, str) else ""
    content = item.get("content")
    if isinstance(content, list):
        parts: list[str] = []
        for child in content:
            if not isinstance(child, dict):
                continue
            text = _extract_text_content(child)
            if text:
                parts.append(text)
        return "\n\n".join(parts)
    return ""


def _usage_value(usage_obj: Any, key: str) -> int:
    if not isinstance(usage_obj, dict):
        return 0
    return int(usage_obj.get(key, 0) or 0)


def _response_model_name(response_json: dict[str, Any]) -> str:
    model = response_json.get("model")
    return model if isinstance(model, str) else ""


def _read_error_body(exc: urllib.error.HTTPError) -> str:
    try:
        return exc.read().decode("utf-8", errors="replace")
    except Exception:
        return ""


def _normalize_http_error(
    exc: urllib.error.HTTPError,
    error_body: str,
) -> dict[str, Any]:
    payload = _parse_error_payload(error_body)
    error_type = _HTTP_ERROR_TYPES.get(exc.code)
    message = _HTTP_ERROR_MESSAGES.get(exc.code, f"HTTP {exc.code}")
    request_id = _request_id_from_headers(exc)

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


def _parse_error_payload(error_body: str) -> dict[str, Any] | None:
    stripped = error_body.strip()
    if not stripped.startswith("{"):
        return None
    try:
        payload = json.loads(stripped)
    except json.JSONDecodeError:
        return None
    return payload if isinstance(payload, dict) else None


def _request_id_from_headers(exc: urllib.error.HTTPError) -> str | None:
    if not exc.headers:
        return None
    for header in ("x-request-id", "request-id", "x-goog-request-id"):
        request_id = exc.headers.get(header)
        if isinstance(request_id, str) and request_id.strip():
            return request_id.strip()
    return None


def _format_error_message(prefix: str, error_payload: dict[str, Any]) -> str:
    return f"{prefix}: {json.dumps(error_payload, sort_keys=True)}"


def _extract_retry_after(exc: urllib.error.HTTPError, attempt: int) -> float:
    try:
        retry_after = exc.headers.get("Retry-After") if exc.headers else None
        if retry_after:
            return max(0.1, min(float(retry_after), 60.0)) + 1.0
    except (TypeError, ValueError):
        pass
    return min(2.0 * (2**attempt), 30.0) + 1.0


def _waiting_message_for_input(input_value: str | list[dict[str, Any]]) -> str:
    if isinstance(input_value, str):
        return "analyzing your request..."

    has_tool_output = any(
        isinstance(item, dict) and item.get("type") == "function_result"
        for item in input_value
    )
    if has_tool_output:
        return "integrating tool results..."

    return "processing..."


def _reasoning_body_text(reasoning_text: str, summary_text: str) -> str | None:
    if reasoning_text.strip():
        return reasoning_text
    body = _summary_body_text(summary_text)
    return body if body.strip() else None


def _summary_body_text(summary_text: str) -> str:
    lines = summary_text.splitlines()
    first_non_empty_index = next(
        (idx for idx, line in enumerate(lines) if line.strip()),
        None,
    )
    if first_non_empty_index is None:
        return ""
    remaining_non_empty = any(
        line.strip() for line in lines[first_non_empty_index + 1 :]
    )
    if not remaining_non_empty:
        return ""
    return "\n".join(lines[first_non_empty_index + 1 :]).lstrip("\r\n")
