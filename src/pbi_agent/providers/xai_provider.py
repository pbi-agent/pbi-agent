"""xAI Responses HTTP provider.

Uses direct synchronous HTTP calls to xAI's Responses API. Conversation
history is managed server-side via ``previous_response_id``.
"""

from __future__ import annotations

import json
import re
import time
import urllib.parse
from datetime import datetime, timedelta, timezone
from typing import Any, TYPE_CHECKING, cast

from pbi_agent.agent.system_prompt import get_system_prompt
from pbi_agent.agent.tool_runtime import execute_tool_calls as _execute_tool_calls
from pbi_agent.auth.models import OAuthSessionAuth, RequestAuthConfig
from pbi_agent.auth.service import build_runtime_request_auth, refresh_runtime_auth
from pbi_agent.config import Settings
from pbi_agent.models.messages import (
    CompletedResponse,
    TokenUsage,
    ToolCall,
    UserTurnInput,
    WebSearchSource,
)
from pbi_agent.providers.auth_strategies import json_model_headers
from pbi_agent.providers.base import Provider
from pbi_agent.providers.endpoints import responses_url
from pbi_agent.providers.protocols.openai_responses import (
    normalize_xai_http_error,
    response_history_item_for_input,
    responses_include,
    serialize_function_call_output,
)
from pbi_agent.providers.runtime import record_response_usage
from pbi_agent.providers.tool_execution import execute_provider_tool_calls
from pbi_agent.providers.transport import (
    JsonErrorPolicy,
    JsonModelTransport,
    JsonRequestSpec,
    json_error_message,
)
from pbi_agent.session_store import MessageRecord
from pbi_agent.tools.availability import (
    default_excluded_tool_names,
    effective_excluded_tool_names,
)
from pbi_agent.tools.catalog import ToolCatalog
from pbi_agent.tools.types import ParentContextSnapshot
from pbi_agent.display.protocol import DisplayProtocol

if TYPE_CHECKING:
    from pbi_agent.hooks.runtime import HookRuntime
    from pbi_agent.observability import RunTracer

_REQUEST_TIMEOUT_SECS = 3600.0
_OAUTH_REFRESH_SKEW_SECS = 3600
_REASONING_EFFORT_MODELS = ("grok-3-mini",)
_EFFORT_MAP: dict[str, str] = {
    "low": "low",
    "medium": "high",
    "high": "high",
    "xhigh": "high",
}


class XAIProvider(Provider):
    """Provider backed by xAI's synchronous Responses HTTP API."""

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
        self._excluded_tools = default_excluded_tool_names(excluded_tools)
        self._tools: list[dict[str, Any]] = []
        self.refresh_tools()
        self._instructions = system_prompt or get_system_prompt(
            settings=self._settings,
            excluded_tools=self._excluded_tools,
        )
        self._previous_response_id: str | None = None
        self._restored_input_items: list[dict[str, Any]] = []
        self._transport = JsonModelTransport()

    @property
    def settings(self) -> Settings:
        return self._settings

    def set_previous_response_id(self, response_id: str | None) -> None:
        self._previous_response_id = response_id

    def get_conversation_checkpoint(self) -> str | None:
        return self._previous_response_id

    def connect(self) -> None:
        if self._settings.auth is None:
            raise ValueError(
                "Missing authentication. Configure an xAI API key or X account session."
            )

    def close(self) -> None:
        pass

    def reset_conversation(self) -> None:
        self._previous_response_id = None
        self._restored_input_items.clear()

    def set_system_prompt(self, system_prompt: str) -> None:
        self._instructions = system_prompt

    def refresh_tools(self) -> None:
        excluded_tools = effective_excluded_tool_names(
            self._settings, self._excluded_tools
        )
        self._tools = self._tool_catalog.get_openai_tool_definitions(
            excluded_names=excluded_tools
        )

    def restore_messages(self, messages: list[MessageRecord]) -> None:
        self._restored_input_items = [
            {"role": message.role, "content": message.content}
            for message in messages
            if message.role in {"user", "assistant"} and message.content
        ]

    def restore_history_items(self, items: list[dict[str, Any]]) -> None:
        self._restored_input_items = _history_items_to_input_items(items)

    def request_turn(
        self,
        *,
        user_message: str | None = None,
        user_input: UserTurnInput | None = None,
        tool_result_items: list[dict[str, Any]] | None = None,
        instructions: str | None = None,
        session_id: str | None = None,
        display: DisplayProtocol,
        session_usage: TokenUsage,
        turn_usage: TokenUsage,
        tracer: "RunTracer | None" = None,
    ) -> CompletedResponse:
        del session_id
        if user_input is None and user_message is not None:
            user_input = UserTurnInput(text=user_message)

        if user_input is not None:
            if user_input.images:
                raise ValueError("xAI image inputs are not enabled in this build.")
            input_items = [_build_user_input_item(user_input.text)]
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
        record_response_usage(
            result,
            display=display,
            session_usage=session_usage,
            turn_usage=turn_usage,
        )

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
            if result.text:
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
        hook_runtime: "HookRuntime | None" = None,
    ) -> tuple[list[dict[str, Any]], bool]:
        if not response.function_calls:
            return [], False

        return execute_provider_tool_calls(
            response.function_calls,
            max_workers=max_workers,
            settings=self._settings,
            display=display,
            session_usage=session_usage,
            turn_usage=turn_usage,
            tool_catalog=self._tool_catalog,
            excluded_tools=self._excluded_tools,
            serialize_result=serialize_function_call_output,
            sub_agent_depth=sub_agent_depth,
            parent_context=parent_context,
            tracer=tracer,
            hook_runtime=hook_runtime,
            tool_availability_overridden=getattr(
                self, "_tool_availability_overridden", False
            ),
            workspace_root=getattr(self, "_workspace_root", None),
            workspace_directory_key=getattr(self, "_workspace_directory_key", None),
            execute_calls=_execute_tool_calls,
        )

    def _http_request(
        self,
        *,
        input_items: list[dict[str, Any]],
        instructions: str,
        display: DisplayProtocol,
        tracer: "RunTracer | None" = None,
    ) -> CompletedResponse:
        request_body = self._build_request_body(
            input_items=input_items,
            instructions=instructions,
        )
        request_auth = self._request_auth(responses_url(self._settings))
        headers = json_model_headers()
        headers.update(request_auth.headers)

        return self._transport.post(
            JsonRequestSpec(
                provider=self._settings.provider,
                model=self._settings.model,
                url=request_auth.request_url,
                headers=headers,
                body=request_body,
                request_config=self._settings.redacted(),
                wait_input=input_items,
                timeout=_REQUEST_TIMEOUT_SECS,
                error_policy=JsonErrorPolicy(
                    api_error_label="xAI Responses API error",
                    rate_limit_exhausted_label="xAI rate limit exceeded",
                    overload_exhausted_label="xAI API overloaded",
                    request_failed_label="xAI request failed",
                    normalize_http_error=normalize_xai_http_error,
                    format_error=json_error_message,
                ),
                sleep=time.sleep,
            ),
            settings=self._settings,
            display=display,
            tracer=tracer,
            parse_response=self._parse_response,
        )

    def _request_auth(self, request_url: str) -> RequestAuthConfig:
        auth = self._settings.auth
        if isinstance(auth, OAuthSessionAuth) and _oauth_refresh_due(auth):
            self._settings.auth = refresh_runtime_auth(
                provider_kind=self._settings.provider,
                auth=auth,
            )
            auth = self._settings.auth
        return build_runtime_request_auth(
            provider_kind=self._settings.provider,
            request_url=request_url,
            auth=auth,
        )

    def _build_request_body(
        self,
        *,
        input_items: list[dict[str, Any]],
        instructions: str | None,
    ) -> dict[str, Any]:
        request_input_items = (
            [*self._restored_input_items, *input_items]
            if self._restored_input_items and not self._previous_response_id
            else list(input_items)
        )
        if instructions and not self._previous_response_id:
            request_input_items.insert(0, _build_system_input_item(instructions))

        body: dict[str, Any] = {
            "model": self._settings.model,
            "max_output_tokens": self._settings.max_tokens,
            "input": request_input_items,
            "tools": self._tools,
            "parallel_tool_calls": True,
            "stream": False,
        }
        if self._previous_response_id:
            body["previous_response_id"] = self._previous_response_id

        body["include"] = _response_include()

        reasoning = _reasoning_request(
            self._settings.model,
            self._settings.reasoning_effort,
        )
        if reasoning:
            body["reasoning"] = reasoning

        return body

    def _parse_response(self, response_json: dict[str, Any]) -> CompletedResponse:
        assistant_messages: list[str] = []
        reasoning_summary_parts: list[str] = []
        reasoning_content_parts: list[str] = []
        encrypted_reasoning_parts: list[str] = []
        function_calls: list[ToolCall] = []
        web_search_sources: list[WebSearchSource] = []
        had_web_search_call = False
        display_items: list[dict[str, Any]] = []
        last_web_search_index: int | None = None

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
                encrypted_content = item.get("encrypted_content")
                if isinstance(encrypted_content, str) and encrypted_content:
                    encrypted_reasoning_parts.append(encrypted_content)

                for content_entry in item.get("content", []):
                    if not isinstance(content_entry, dict):
                        continue
                    if content_entry.get("type") == "reasoning_text":
                        reasoning_text = content_entry.get("text", "")
                        if reasoning_text:
                            reasoning_content_parts.append(reasoning_text)

            elif item_type == "message":
                message_text_parts: list[str] = []
                message_annotation_sources: list[WebSearchSource] = []
                for part in item.get("content", []):
                    if not isinstance(part, dict):
                        continue
                    if part.get("type") == "output_text":
                        text = part.get("text", "")
                        if text:
                            message_text_parts.append(text)
                        for annotation in part.get("annotations", []):
                            if not isinstance(annotation, dict):
                                continue
                            if annotation.get("type") == "url_citation":
                                source = _annotation_web_search_source(annotation)
                                if source is not None:
                                    message_annotation_sources.append(source)
                if message_annotation_sources:
                    if last_web_search_index is None:
                        display_items.append(
                            {
                                "type": "web_search_call",
                                "queries": [],
                                "sources": _serialize_web_search_sources(
                                    message_annotation_sources
                                ),
                            }
                        )
                        last_web_search_index = len(display_items) - 1
                    else:
                        existing_sources = _deserialize_web_search_sources(
                            display_items[last_web_search_index].get("sources", [])
                        )
                        display_items[last_web_search_index]["sources"] = (
                            _serialize_web_search_sources(
                                _merge_web_search_sources(
                                    existing_sources,
                                    message_annotation_sources,
                                )
                            )
                        )
                    web_search_sources = _merge_web_search_sources(
                        web_search_sources,
                        message_annotation_sources,
                    )
                message_text = "".join(message_text_parts).strip()
                if message_text:
                    assistant_messages.append(message_text)
                    display_items.append({"type": "message", "text": message_text})

            elif item_type == "function_call":
                function_calls.append(_parse_function_call(item))

            elif item_type == "web_search_call":
                had_web_search_call = True
                item_sources = _extract_web_search_sources(item)
                item_queries = _extract_web_search_queries(item)
                web_search_sources = _merge_web_search_sources(
                    web_search_sources,
                    item_sources,
                )
                if (
                    last_web_search_index is not None
                    and last_web_search_index == len(display_items) - 1
                    and display_items[last_web_search_index].get("type")
                    == "web_search_call"
                    and display_items[last_web_search_index].get("queries", [])
                    == item_queries
                ):
                    existing_sources = _deserialize_web_search_sources(
                        display_items[last_web_search_index].get("sources", [])
                    )
                    display_items[last_web_search_index]["sources"] = (
                        _serialize_web_search_sources(
                            _merge_web_search_sources(existing_sources, item_sources)
                        )
                    )
                else:
                    display_items.append(
                        {
                            "type": "web_search_call",
                            "queries": item_queries,
                            "sources": _serialize_web_search_sources(item_sources),
                        }
                    )
                    last_web_search_index = len(display_items) - 1

        usage_obj = response_json.get("usage", {})
        input_tokens = int(_usage_value(usage_obj, "input_tokens"))
        output_tokens = int(_usage_value(usage_obj, "output_tokens"))
        total_tokens = int(_usage_value(usage_obj, "total_tokens"))
        input_details = usage_obj.get("input_tokens_details", {})
        output_details = usage_obj.get("output_tokens_details", {})

        cached_input_tokens = (
            int(input_details.get("cached_tokens", 0) or 0)
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
        text = assistant_messages[-1] if assistant_messages else ""
        if not text:
            output_text = response_json.get("output_text")
            if isinstance(output_text, str):
                text = output_text.strip()

        return CompletedResponse(
            response_id=response_json.get("id"),
            text=text,
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
                "encrypted_reasoning_content": encrypted_reasoning_parts,
                "reasoning": response_json.get("reasoning"),
                "display_items": display_items,
            },
            web_search_sources=web_search_sources,
            had_web_search_call=had_web_search_call,
        )


def _build_user_input_item(prompt: str) -> dict[str, Any]:
    return {"role": "user", "content": prompt}


def _oauth_refresh_due(auth: OAuthSessionAuth) -> bool:
    if auth.expires_at is None:
        return False
    refresh_at = datetime.fromtimestamp(auth.expires_at, timezone.utc) - timedelta(
        seconds=_OAUTH_REFRESH_SKEW_SECS
    )
    return datetime.now(timezone.utc) >= refresh_at


def _history_items_to_input_items(
    items: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    restored_items: list[dict[str, Any]] = []
    for item in items:
        if item.get("type") == "tool_call_group":
            child_items = item.get("calls", [])
        elif item.get("type") == "tool_result_group":
            child_items = item.get("results", [])
        else:
            child_items = None

        if child_items is not None:
            for child in child_items:
                if (
                    isinstance(child, dict)
                    and (restored := _history_item_to_input_item(child)) is not None
                ):
                    restored_items.append(restored)
            continue
        if (restored := _history_item_to_input_item(item)) is not None:
            restored_items.append(restored)
    return restored_items


def _history_item_to_input_item(item: dict[str, Any]) -> dict[str, Any] | None:
    item_type = item.get("type")
    if item_type == "provider_input_item":
        raw_item = item.get("item")
        if item.get("format") == "openai_responses" and isinstance(raw_item, dict):
            return _response_history_item_for_input(raw_item)
        return None
    if item_type == "message":
        message = item.get("message")
        if (
            isinstance(message, MessageRecord)
            and message.role in {"user", "assistant"}
            and message.content
        ):
            return {"role": message.role, "content": message.content}
        return None
    if item_type == "tool_call":
        call_id = str(item.get("call_id") or "")
        name = str(item.get("name") or "")
        if not call_id or not name:
            return None
        arguments = item.get("arguments")
        return {
            "type": "function_call",
            "call_id": call_id,
            "name": name,
            "arguments": (
                arguments if isinstance(arguments, str) else json.dumps(arguments or {})
            ),
        }
    if item_type == "tool_result":
        call_id = str(item.get("call_id") or "")
        if not call_id:
            return None
        output = item.get("output")
        return {
            "type": "function_call_output",
            "call_id": call_id,
            "output": output if isinstance(output, str) else json.dumps(output),
        }
    return None


def _build_system_input_item(prompt: str) -> dict[str, Any]:
    return {"role": "system", "content": prompt}


def _response_history_item_for_input(item: dict[str, Any]) -> dict[str, Any]:
    return response_history_item_for_input(item)


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
        title = _normalize_web_search_source_title(
            str(source.get("title", "")),
            url,
        )
        snippet = str(source.get("snippet", "")).strip()
        sources.append(
            WebSearchSource(
                title=title,
                url=url,
                snippet=snippet,
            )
        )
    return sources


def _display_web_search_result(
    display: DisplayProtocol,
    sources: list[WebSearchSource] | list[dict[str, str]],
    *,
    queries: list[str] | None = None,
) -> None:
    display.function_start(1)
    display.function_result(
        name="web_search",
        success=True,
        call_id="",
        arguments={
            "queries": [query for query in (queries or []) if query],
            "sources": (
                sources
                if sources and isinstance(sources[0], dict)
                else [
                    {
                        "title": source.title,
                        "url": source.url,
                        "snippet": source.snippet,
                    }
                    for source in cast(list[WebSearchSource], sources)
                ]
            ),
        },
    )
    display.tool_group_end()


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


def _annotation_web_search_source(
    annotation: dict[str, Any],
) -> WebSearchSource | None:
    url = str(annotation.get("url", "")).strip()
    if not url:
        return None
    return WebSearchSource(
        title=_normalize_web_search_source_title(str(annotation.get("title", "")), url),
        url=url,
    )


def _normalize_web_search_source_title(title: str, url: str) -> str:
    stripped = title.strip()
    if stripped and not _is_placeholder_web_search_title(stripped):
        return stripped
    parsed = urllib.parse.urlparse(url)
    host = parsed.netloc.strip().removeprefix("www.")
    return host or url


def _is_placeholder_web_search_title(title: str) -> bool:
    stripped = title.strip()
    if not stripped:
        return True
    return re.fullmatch(r"\[?\d+\]?", stripped) is not None


def _merge_web_search_sources(
    existing: list[WebSearchSource],
    incoming: list[WebSearchSource],
) -> list[WebSearchSource]:
    merged: list[WebSearchSource] = []
    by_url: dict[str, int] = {}

    for source in [*existing, *incoming]:
        url = source.url.strip()
        if not url:
            continue
        normalized = WebSearchSource(
            title=_normalize_web_search_source_title(source.title, url),
            url=url,
            snippet=source.snippet.strip(),
        )
        index = by_url.get(url)
        if index is None:
            by_url[url] = len(merged)
            merged.append(normalized)
            continue
        current = merged[index]
        current_title = _normalize_web_search_source_title(current.title, url)
        new_title = _normalize_web_search_source_title(normalized.title, url)
        merged[index] = WebSearchSource(
            title=current_title
            if not _is_placeholder_web_search_title(current_title)
            else new_title,
            url=url,
            snippet=current.snippet or normalized.snippet,
        )

    return merged


def _serialize_web_search_sources(
    sources: list[WebSearchSource],
) -> list[dict[str, str]]:
    return [
        {"title": source.title, "url": source.url, "snippet": source.snippet}
        for source in sources
    ]


def _deserialize_web_search_sources(raw_sources: Any) -> list[WebSearchSource]:
    if not isinstance(raw_sources, list):
        return []
    sources: list[WebSearchSource] = []
    for source in raw_sources:
        if not isinstance(source, dict):
            continue
        url = str(source.get("url", "")).strip()
        if not url:
            continue
        sources.append(
            WebSearchSource(
                title=_normalize_web_search_source_title(
                    str(source.get("title", "")),
                    url,
                ),
                url=url,
                snippet=str(source.get("snippet", "")).strip(),
            )
        )
    return sources


def _response_include() -> list[str]:
    return responses_include(["web_search_call.action.sources"])


def _reasoning_request(model: str, effort: str) -> dict[str, Any]:
    if any(model.startswith(prefix) for prefix in _REASONING_EFFORT_MODELS):
        return {"effort": _EFFORT_MAP.get(effort, "high")}
    return {}


def _usage_value(usage_obj: Any, key: str) -> int:
    if not isinstance(usage_obj, dict):
        return 0
    return int(usage_obj.get(key, 0) or 0)


def _response_model_name(response_json: dict[str, Any]) -> str:
    model = response_json.get("model")
    return model if isinstance(model, str) else ""


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
