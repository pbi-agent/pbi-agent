"""OpenAI Responses HTTP provider.

Uses direct synchronous HTTP calls to OpenAI's Responses API. Conversation
history is managed server-side via ``previous_response_id``.
"""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from typing import Any, TYPE_CHECKING

from pbi_agent import __version__
from pbi_agent.agent.system_prompt import get_system_prompt
from pbi_agent.agent.tool_runtime import (
    execute_tool_calls as _execute_tool_calls,
    to_function_call_output_items,
)
from pbi_agent.config import Settings
from pbi_agent.media import data_url_for_image
from pbi_agent.models.messages import (
    CompletedResponse,
    TokenUsage,
    ToolCall,
    UserTurnInput,
    WebSearchSource,
)
from pbi_agent.providers.base import Provider
from pbi_agent.session_store import MessageRecord
from pbi_agent.tools.catalog import ToolCatalog
from pbi_agent.tools.types import ParentContextSnapshot, ToolContext
from pbi_agent.display.protocol import DisplayProtocol

if TYPE_CHECKING:
    from pbi_agent.observability import RunTracer

_REQUEST_TIMEOUT_SECS = 3600.0
_RATE_LIMIT_MAX_RETRIES = 10
_HTTP_ERROR_TYPES = {
    429: "rate_limit_error",
    500: "server_error",
    503: "server_error",
}
_HTTP_ERROR_MESSAGES = {
    429: "Rate limit reached.",
    500: "The server had an error while processing your request.",
    503: "The engine is currently overloaded, please try again later.",
}


class OpenAIProvider(Provider):
    """Provider backed by OpenAI's synchronous Responses HTTP API."""

    def __init__(
        self,
        settings: Settings,
        *,
        system_prompt: str | None = None,
        excluded_tools: set[str] | None = None,
        tool_catalog: ToolCatalog | None = None,
    ) -> None:
        self._settings = settings
        self._tool_catalog = tool_catalog or ToolCatalog.from_builtin_registry()
        self._excluded_tools = set(excluded_tools or set())
        self._tools: list[dict[str, Any]] = []
        self.refresh_tools()
        self._instructions = system_prompt or get_system_prompt()
        self._previous_response_id: str | None = None
        self._branch_response_id: str | None = None
        self._restored_input_items: list[dict[str, Any]] = []

    @property
    def settings(self) -> Settings:
        return self._settings

    def set_previous_response_id(self, response_id: str | None) -> None:
        self._previous_response_id = response_id
        self._branch_response_id = response_id

    def get_conversation_checkpoint(self) -> str | None:
        return self._branch_response_id

    def connect(self) -> None:
        if not self._settings.api_key:
            raise ValueError(
                "Missing API key. Set PBI_AGENT_API_KEY in environment or pass "
                "--api-key."
            )

    def close(self) -> None:
        pass

    def reset_conversation(self) -> None:
        self._previous_response_id = None
        self._branch_response_id = None
        self._restored_input_items.clear()

    def set_system_prompt(self, system_prompt: str) -> None:
        self._instructions = system_prompt

    def refresh_tools(self) -> None:
        self._tools = self._tool_catalog.get_openai_tool_definitions(
            excluded_names=self._excluded_tools
        )
        if self._settings.web_search:
            self._tools.append({"type": "web_search"})

    def restore_messages(self, messages: list[MessageRecord]) -> None:
        self._restored_input_items = [
            {"role": message.role, "content": message.content}
            for message in messages
            if message.role in {"user", "assistant"} and message.content
        ]

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
        tracer: "RunTracer | None" = None,
    ) -> CompletedResponse:
        if user_input is None and user_message is not None:
            user_input = UserTurnInput(text=user_message)

        if user_input is not None:
            input_items = [_build_user_input_item(user_input)]
        elif tool_result_items is not None:
            input_items = tool_result_items
        else:
            raise ValueError("Either user_input or tool_result_items is required")

        result = self._http_request(
            input_items=input_items,
            instructions=instructions or self._instructions,
            display=display,
            tracer=tracer,
        )
        self._previous_response_id = result.response_id
        if not result.has_tool_calls:
            # Only completed assistant responses are safe to branch from.
            self._branch_response_id = result.response_id
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
        if isinstance(display_items, list):
            for item in display_items:
                if not isinstance(item, dict):
                    continue
                item_type = item.get("type")
                if item_type == "message":
                    text = item.get("text")
                    if isinstance(text, str) and text:
                        display.render_markdown(text)
                elif item_type == "web_search_call":
                    _display_web_search_result(
                        display,
                        item.get("sources", []),
                        queries=item.get("queries", []),
                    )
        else:
            if result.assistant_messages:
                for message in result.assistant_messages:
                    display.render_markdown(message)
            elif result.text:
                display.render_markdown(result.text)

            if result.had_web_search_call or result.web_search_sources:
                _display_web_search_result(display, result.web_search_sources)

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
        parent_context: ParentContextSnapshot | None = None,
        tracer: "RunTracer | None" = None,
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
                tool_catalog=self._tool_catalog,
                parent_context=parent_context,
                tracer=tracer,
            ),
        )

        for result in batch.results:
            call = _find_by_id(response.function_calls, result.call_id)
            if not (call and call.name == "sub_agent"):
                display.function_result(
                    name=call.name if call else "unknown",
                    success=not result.is_error,
                    call_id=result.call_id,
                    arguments=call.arguments if call else None,
                )
        if displayable_calls:
            display.tool_group_end()

        return to_function_call_output_items(batch.results), batch.had_errors

    def _http_request(
        self,
        *,
        input_items: list[dict[str, Any]],
        instructions: str,
        display: DisplayProtocol,
        tracer: "RunTracer | None" = None,
    ) -> CompletedResponse:
        display.wait_start(_waiting_message_for_input_items(input_items))

        request_body = self._build_request_body(
            input_items=input_items,
            instructions=instructions,
        )
        request_data = json.dumps(request_body).encode("utf-8")
        headers = {
            "Accept": "application/json",
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self._settings.api_key}",
            "User-Agent": f"pbi-agent/{__version__}",
        }

        max_retries = self._settings.max_retries
        rate_limit_max_retries = max(max_retries, _RATE_LIMIT_MAX_RETRIES)
        retry_notice_max_retries = max_retries
        last_error: Exception | None = None
        last_error_message: str | None = None
        retried_missing_previous_response = False

        for attempt in range(rate_limit_max_retries + 1):
            if attempt > 0:
                display.retry_notice(attempt, retry_notice_max_retries)

            req_start = time.perf_counter()
            try:
                req = urllib.request.Request(
                    self._settings.responses_url,
                    data=request_data,
                    headers=headers,
                    method="POST",
                )
                with urllib.request.urlopen(req, timeout=_REQUEST_TIMEOUT_SECS) as resp:
                    response_json = json.loads(resp.read().decode("utf-8"))

                _raise_if_response_failed(response_json)
                result = self._parse_response(response_json)
                _trace_provider_call(
                    tracer=tracer,
                    provider=self._settings.provider,
                    model=self._settings.model,
                    url=self._settings.responses_url,
                    request_config=self._settings.redacted(),
                    request_payload=_sanitize_request_payload_for_observability(
                        request_body
                    ),
                    response_payload=response_json,
                    duration_ms=_duration_ms(req_start),
                    prompt_tokens=result.usage.input_tokens,
                    completion_tokens=result.usage.output_tokens,
                    total_tokens=result.usage.total_tokens,
                    status_code=200,
                    success=True,
                    metadata={"attempt": attempt + 1},
                )
                display.wait_stop()
                return result
            except urllib.error.HTTPError as exc:
                error_body = _read_error_body(exc)
                error_payload = _normalize_http_error(exc, error_body)
                _trace_provider_call(
                    tracer=tracer,
                    provider=self._settings.provider,
                    model=self._settings.model,
                    url=self._settings.responses_url,
                    request_config=self._settings.redacted(),
                    request_payload=_sanitize_request_payload_for_observability(
                        request_body
                    ),
                    response_payload=error_payload or {"body": error_body},
                    duration_ms=_duration_ms(req_start),
                    status_code=exc.code,
                    success=False,
                    error_message=_format_error_message(
                        "OpenAI Responses API error",
                        error_payload,
                    ),
                    metadata={"attempt": attempt + 1},
                )

                # Rate limiting
                if exc.code == 429:
                    if not _should_retry_rate_limit(error_payload):
                        display.wait_stop()
                        raise RuntimeError(
                            _format_error_message(
                                "OpenAI Responses API error",
                                error_payload,
                            )
                        ) from exc
                    if attempt >= rate_limit_max_retries:
                        display.wait_stop()
                        raise RuntimeError(
                            _format_error_message(
                                "OpenAI rate limit exceeded after "
                                f"{rate_limit_max_retries + 1} attempts",
                                error_payload,
                            )
                        ) from exc
                    wait = _extract_retry_after(exc, attempt)
                    retry_notice_max_retries = rate_limit_max_retries
                    display.rate_limit_notice(
                        wait_seconds=wait,
                        attempt=attempt + 1,
                        max_retries=rate_limit_max_retries,
                    )
                    time.sleep(wait)
                    continue

                # Overloaded (503)
                if exc.code == 503:
                    if attempt >= max_retries:
                        display.wait_stop()
                        raise RuntimeError(
                            _format_error_message(
                                f"OpenAI API overloaded after {max_retries + 1} attempts",
                                error_payload,
                            )
                        ) from exc
                    wait = _extract_retry_after(exc, attempt)
                    retry_notice_max_retries = max_retries
                    display.overload_notice(
                        wait_seconds=wait,
                        attempt=attempt + 1,
                        max_retries=max_retries,
                    )
                    time.sleep(wait)
                    continue

                # Server errors (5xx) -- retry
                if exc.code >= 500:
                    last_error = exc
                    last_error_message = _format_error_message(
                        "OpenAI Responses API error",
                        error_payload,
                    )
                    if attempt >= max_retries:
                        break
                    retry_notice_max_retries = max_retries
                    continue

                # Client errors (4xx) -- don't retry
                if (
                    not retried_missing_previous_response
                    and self._previous_response_id
                    and self._restored_input_items
                    and _should_retry_missing_previous_response(error_payload)
                ):
                    self._previous_response_id = None
                    self._branch_response_id = None
                    request_body = self._build_request_body(
                        input_items=input_items,
                        instructions=instructions,
                    )
                    request_data = json.dumps(request_body).encode("utf-8")
                    retried_missing_previous_response = True
                    continue
                display.wait_stop()
                raise RuntimeError(
                    _format_error_message("OpenAI Responses API error", error_payload)
                ) from exc
            except urllib.error.URLError as exc:
                last_error = exc
                _trace_provider_call(
                    tracer=tracer,
                    provider=self._settings.provider,
                    model=self._settings.model,
                    url=self._settings.responses_url,
                    request_config=self._settings.redacted(),
                    request_payload=_sanitize_request_payload_for_observability(
                        request_body
                    ),
                    response_payload={"error": str(exc)},
                    duration_ms=_duration_ms(req_start),
                    success=False,
                    error_message=str(exc),
                    metadata={"attempt": attempt + 1},
                )
                if attempt >= max_retries:
                    break
                retry_notice_max_retries = max_retries
                continue

        display.wait_stop()
        if last_error is not None:
            raise RuntimeError(
                last_error_message
                or f"OpenAI request failed after {max_retries + 1} attempts: {last_error}"
            ) from last_error
        raise RuntimeError("OpenAI request failed after retries.")

    def _build_request_body(
        self,
        *,
        input_items: list[dict[str, Any]],
        instructions: str | None,
    ) -> dict[str, Any]:
        body: dict[str, Any] = {
            "model": self._settings.model,
            "max_output_tokens": self._settings.max_tokens,
            "input": (
                [*self._restored_input_items, *input_items]
                if self._restored_input_items and not self._previous_response_id
                else list(input_items)
            ),
            "tools": self._tools,
            "parallel_tool_calls": True,
            "store": True,
            "stream": False,
            "prompt_cache_retention": "24h",
            "context_management": [
                {
                    "type": "compaction",
                    "compact_threshold": self._settings.compact_threshold,
                }
            ],
            "reasoning": {
                "effort": self._settings.reasoning_effort,
                "summary": "auto",
            },
        }
        if instructions:
            body["instructions"] = instructions
        if self._previous_response_id:
            body["previous_response_id"] = self._previous_response_id
        if self._settings.service_tier:
            body["service_tier"] = self._settings.service_tier
        return body

    def _parse_response(self, response_json: dict[str, Any]) -> CompletedResponse:
        text_parts: list[str] = []
        assistant_messages: list[str] = []
        reasoning_summary_parts: list[str] = []
        reasoning_content_parts: list[str] = []
        function_calls: list[ToolCall] = []
        web_search_sources: list[WebSearchSource] = []
        had_web_search_call = False
        display_items: list[dict[str, Any]] = []

        output_items = response_json.get("output", [])
        if not isinstance(output_items, list):
            output_items = []

        for item in output_items:
            if not isinstance(item, dict):
                continue
            item_type = item.get("type")

            if item_type == "reasoning":
                reasoning_summary_parts.extend(
                    _extract_reasoning_summary_texts(item.get("summary"))
                )
                for content_entry in item.get("content", []):
                    if not isinstance(content_entry, dict):
                        continue
                    if content_entry.get("type") == "reasoning_text":
                        reasoning_text = content_entry.get("text", "")
                        if reasoning_text:
                            reasoning_content_parts.append(reasoning_text)

            elif item_type == "message":
                message_parts: list[str] = []
                for part in item.get("content", []):
                    if not isinstance(part, dict):
                        continue
                    if part.get("type") == "output_text":
                        text = part.get("text", "")
                        if text:
                            text_parts.append(text)
                            message_parts.append(text)
                        for annotation in part.get("annotations", []):
                            if not isinstance(annotation, dict):
                                continue
                            if annotation.get("type") == "url_citation":
                                web_search_sources.append(
                                    WebSearchSource(
                                        title=str(annotation.get("title", "")),
                                        url=str(annotation.get("url", "")),
                                    )
                                )
                message_text = "".join(message_parts).strip()
                if message_text:
                    assistant_messages.append(message_text)
                    display_items.append({"type": "message", "text": message_text})

            elif item_type == "function_call":
                function_calls.append(_parse_function_call(item))

            elif item_type == "web_search_call":
                had_web_search_call = True
                item_sources = _extract_web_search_sources(item)
                web_search_sources.extend(item_sources)
                display_items.append(
                    {
                        "type": "web_search_call",
                        "queries": _extract_web_search_queries(item),
                        "sources": [
                            {
                                "title": source.title,
                                "url": source.url,
                                "snippet": source.snippet,
                            }
                            for source in item_sources
                        ],
                    }
                )

        usage_obj = response_json.get("usage", {})
        input_tokens = int(_usage_value(usage_obj, "input_tokens"))
        output_tokens = int(_usage_value(usage_obj, "output_tokens"))
        total_tokens = int(_usage_value(usage_obj, "total_tokens"))
        input_details = usage_obj.get("input_tokens_details", {})
        output_details = usage_obj.get("output_tokens_details", {})

        cached_input_tokens = (
            int(
                input_details.get(
                    "cached_tokens",
                    input_details.get("cached_input_tokens", 0),
                )
                or 0
            )
            if isinstance(input_details, dict)
            else 0
        )
        reasoning_tokens = (
            int(output_details.get("reasoning_tokens", 0) or 0)
            if isinstance(output_details, dict)
            else 0
        )

        reasoning_summary = "\n\n".join(
            part for part in reasoning_summary_parts if part.strip()
        ).strip()
        reasoning_content = "\n\n".join(
            part for part in reasoning_content_parts if part.strip()
        ).strip()
        text = "".join(text_parts).strip()
        if not text:
            output_text = response_json.get("output_text")
            if isinstance(output_text, str):
                text = output_text.strip()

        return CompletedResponse(
            response_id=response_json.get("id"),
            text=text,
            assistant_messages=assistant_messages,
            usage=TokenUsage(
                input_tokens=input_tokens,
                cached_input_tokens=cached_input_tokens,
                output_tokens=output_tokens,
                reasoning_tokens=reasoning_tokens,
                context_tokens=total_tokens or (input_tokens + output_tokens),
                model=_response_model_name(response_json),
            ),
            function_calls=function_calls,
            reasoning_summary=reasoning_summary,
            reasoning_content=reasoning_content,
            provider_data={
                "reasoning": response_json.get("reasoning"),
                "display_items": display_items,
            },
            web_search_sources=web_search_sources,
            had_web_search_call=had_web_search_call,
        )


def _build_user_input_item(user_input: UserTurnInput) -> dict[str, Any]:
    if not user_input.images:
        return {"role": "user", "content": user_input.text}

    content: list[dict[str, Any]] = []
    if user_input.text:
        content.append({"type": "input_text", "text": user_input.text})
    for image in user_input.images:
        content.append(
            {
                "type": "input_image",
                "image_url": data_url_for_image(image),
                "detail": "original",
            }
        )
    return {"role": "user", "content": content}


def _extract_reasoning_summary_texts(raw_summary: Any) -> list[str]:
    if not isinstance(raw_summary, list):
        return []

    summary_parts: list[str] = []
    for entry in raw_summary:
        if isinstance(entry, dict):
            if entry.get("type") == "summary_text":
                text = entry.get("text", "")
                if text:
                    summary_parts.append(text)
        elif isinstance(entry, str) and entry:
            summary_parts.append(entry)
    return summary_parts


def _parse_function_call(item: dict[str, Any]) -> ToolCall:
    raw_args = item.get("arguments", "")
    arguments: dict[str, Any] | str | None
    if isinstance(raw_args, str):
        try:
            arguments = json.loads(raw_args) if raw_args else {}
        except json.JSONDecodeError:
            arguments = raw_args
    else:
        arguments = raw_args

    return ToolCall(
        call_id=str(item.get("call_id", "")),
        name=str(item.get("name", "")),
        arguments=arguments,
    )


def _find_by_id(calls: list[ToolCall], call_id: str) -> ToolCall | None:
    for call in calls:
        if call.call_id == call_id:
            return call
    return None


def _extract_web_search_sources(item: dict[str, Any]) -> list[WebSearchSource]:
    action = item.get("action")
    if not isinstance(action, dict):
        return []

    raw_sources = action.get("sources")
    if not isinstance(raw_sources, list):
        return []

    sources: list[WebSearchSource] = []
    for source in raw_sources:
        if not isinstance(source, dict):
            continue
        url = str(source.get("url", "")).strip()
        if not url:
            continue
        title = str(source.get("title", "")).strip() or url
        snippet = str(source.get("snippet", "")).strip()
        sources.append(
            WebSearchSource(
                title=title,
                url=url,
                snippet=snippet,
            )
        )
    return sources


def _extract_web_search_queries(item: dict[str, Any]) -> list[str]:
    action = item.get("action")
    if not isinstance(action, dict):
        return []

    raw_queries = action.get("queries")
    if isinstance(raw_queries, list):
        return [str(query).strip() for query in raw_queries if str(query).strip()]

    raw_query = action.get("query")
    if isinstance(raw_query, str) and raw_query.strip():
        return [raw_query.strip()]

    return []


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
        for source in sources
    ]
    display.function_start(1)
    display.function_result(
        name="web_search",
        success=True,
        call_id="",
        arguments={
            "queries": list(queries or []),
            "sources": normalized_sources,
        },
    )
    display.tool_group_end()


def _raise_if_response_failed(response_json: dict[str, Any]) -> None:
    error_obj = response_json.get("error")
    if isinstance(error_obj, dict):
        code = str(error_obj.get("code", "unknown_error"))
        message = str(error_obj.get("message", "No error message"))
        raise RuntimeError(f"OpenAI response failed ({code}): {message}")

    if response_json.get("status") == "failed":
        raise RuntimeError("OpenAI response failed without error details.")


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
    request_id = exc.headers.get("x-request-id") or exc.headers.get("request-id")
    if isinstance(request_id, str) and request_id.strip():
        return request_id.strip()
    return None


def _format_error_message(prefix: str, error_payload: dict[str, Any]) -> str:
    return f"{prefix}: {json.dumps(error_payload, sort_keys=True)}"


def _should_retry_rate_limit(error_payload: dict[str, Any]) -> bool:
    error = error_payload.get("error")
    if not isinstance(error, dict):
        return True
    error_type = error.get("type")
    if (
        isinstance(error_type, str)
        and error_type.strip().lower() == "insufficient_quota"
    ):
        return False
    return True


def _should_retry_missing_previous_response(error_payload: dict[str, Any]) -> bool:
    error = error_payload.get("error")
    if not isinstance(error, dict):
        return False
    message = error.get("message")
    if not isinstance(message, str):
        return False
    normalized = message.strip().lower()
    return "previous response with id" in normalized and "not found" in normalized


def _extract_retry_after(exc: urllib.error.HTTPError, attempt: int) -> float:
    try:
        retry_after = exc.headers.get("Retry-After") if exc.headers else None
        if retry_after:
            return max(0.1, min(float(retry_after), 60.0))
    except (TypeError, ValueError):
        pass
    return min(2.0 * (2**attempt), 30.0)


def _duration_ms(started_at: float) -> int:
    return max(0, int((time.perf_counter() - started_at) * 1000))


def _redact_inline_image_url(value: str) -> str:
    normalized = value.lower()
    if not normalized.startswith("data:image/"):
        return value
    prefix, separator, _ = value.partition(",")
    if not separator:
        return value
    return f"{prefix},<redacted>"


def _sanitize_request_payload_for_observability(value: Any) -> Any:
    if isinstance(value, dict):
        sanitized = {
            key: _sanitize_request_payload_for_observability(inner)
            for key, inner in value.items()
        }
        image_url = sanitized.get("image_url")
        if isinstance(image_url, str):
            sanitized["image_url"] = _redact_inline_image_url(image_url)
        return sanitized
    if isinstance(value, list):
        return [_sanitize_request_payload_for_observability(item) for item in value]
    if isinstance(value, tuple):
        return tuple(
            _sanitize_request_payload_for_observability(item) for item in value
        )
    return value


def _trace_provider_call(
    *,
    tracer,
    provider: str,
    model: str,
    url: str,
    request_config: dict[str, Any],
    request_payload: dict[str, Any],
    response_payload: dict[str, Any],
    duration_ms: int,
    prompt_tokens: int | None = None,
    completion_tokens: int | None = None,
    total_tokens: int | None = None,
    status_code: int | None = None,
    success: bool,
    error_message: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> None:
    if tracer is None:
        return
    tracer.log_model_call(
        provider=provider,
        model=model,
        url=url,
        request_config=request_config,
        request_payload=request_payload,
        response_payload=response_payload,
        duration_ms=duration_ms,
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        total_tokens=total_tokens,
        status_code=status_code,
        success=success,
        error_message=error_message,
        metadata=metadata,
    )


def _waiting_message_for_input_items(input_items: list[dict[str, Any]]) -> str:
    has_user_message = any(
        isinstance(item, dict) and item.get("role") == "user" for item in input_items
    )
    if has_user_message:
        return "analyzing your request..."

    has_tool_output = any(
        isinstance(item, dict) and item.get("type") == "function_call_output"
        for item in input_items
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
