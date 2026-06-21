"""Anthropic Messages API provider.

Uses direct HTTP calls (``urllib.request``) to the Anthropic Messages API.
Conversation history is managed client-side by maintaining a full
``messages`` list that is sent with every request.

Advertised local tools are provider-policy filtered function tools.
"""

from __future__ import annotations
import json
import time
from typing import Any, TYPE_CHECKING

from pbi_agent.agent.system_prompt import get_system_prompt
from pbi_agent.agent.tool_runtime import execute_tool_calls as _execute_tool_calls
from pbi_agent.config import Settings
from pbi_agent.models.messages import (
    CompletedResponse,
    ImageAttachment,
    TokenUsage,
    ToolCall,
    UserTurnInput,
    WebSearchSource,
)
from pbi_agent.providers.auth_strategies import anthropic_headers
from pbi_agent.providers.base import Provider
from pbi_agent.providers.endpoints import anthropic_messages_url
from pbi_agent.providers.protocols.anthropic_messages import (
    ANTHROPIC_VERSION,
    build_messages_body,
    normalize_http_error,
    render_messages_response,
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
from pbi_agent.web.uploads import load_uploaded_image
from pbi_agent.display.protocol import DisplayProtocol

if TYPE_CHECKING:
    from pbi_agent.observability import RunTracer

ANTHROPIC_API_URL = "https://api.anthropic.com/v1/messages"


class AnthropicProvider(Provider):
    """Provider backed by the Anthropic Messages HTTP API."""

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
        self._system_prompt = system_prompt or get_system_prompt(
            settings=self._settings,
            excluded_tools=self._excluded_tools,
        )
        # Client-side conversation history — full messages list.
        self._messages: list[dict[str, Any]] = []
        self._transport = JsonModelTransport()

    @property
    def settings(self) -> Settings:
        return self._settings

    # -- lifecycle -----------------------------------------------------------

    def connect(self) -> None:
        # HTTP is stateless; nothing to connect.  We validate the API key
        # eagerly so errors surface early.
        if not self._settings.api_key:
            raise ValueError(
                "Missing API key. Set PBI_AGENT_API_KEY in environment or pass "
                "--api-key."
            )

    def close(self) -> None:
        pass

    def reset_conversation(self) -> None:
        self._messages.clear()

    def set_system_prompt(self, system_prompt: str) -> None:
        self._system_prompt = system_prompt

    def refresh_tools(self) -> None:
        excluded_tools = effective_excluded_tool_names(
            self._settings, self._excluded_tools
        )
        self._tools = self._tool_catalog.get_anthropic_tool_definitions(
            excluded_names=excluded_tools
        )

    def restore_messages(self, messages: list[MessageRecord]) -> None:
        self._messages = [
            _anthropic_message_record_to_message(message)
            for message in messages
            if _anthropic_message_record_can_restore(message)
        ]

    def restore_history_items(self, items: list[dict[str, Any]]) -> None:
        self._messages = [
            restored
            for item in items
            if (restored := _history_item_to_message(item)) is not None
        ]

    # -- request_turn --------------------------------------------------------

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
        # Build the new message to append to history.
        if user_input is None and user_message is not None:
            user_input = UserTurnInput(text=user_message)

        if user_input is not None:
            input_value: str | list[dict[str, Any]] = user_input.text
            self._messages.append(
                {
                    "role": "user",
                    "content": _anthropic_user_content_blocks(user_input),
                }
            )
        elif tool_result_items is not None:
            input_value = tool_result_items
            # Tool results are sent as a user message containing tool_result
            # content blocks.
            self._messages.append(
                {
                    "role": "user",
                    "content": tool_result_items,
                }
            )
        else:
            raise ValueError("Either user_input or tool_result_items is required")

        system_prompt = instructions or self._system_prompt

        response = self._http_request(
            input_value=input_value,
            system_prompt=system_prompt,
            display=display,
            tracer=tracer,
        )
        record_response_usage(
            response,
            display=display,
            session_usage=session_usage,
            turn_usage=turn_usage,
        )
        return response

    # -- execute_tool_calls --------------------------------------------------

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
        """Execute all tool calls in the response.

        All ``tool_use`` content blocks are routed through the registered
        function tool handlers via ``tool_runtime.execute_tool_calls``.
        """
        # The raw content blocks are stored in provider_data.
        pdata = response.provider_data or {}
        content_blocks: list[dict[str, Any]] = (
            pdata.get("content_blocks", []) if isinstance(pdata, dict) else pdata
        )
        tool_use_blocks = [b for b in content_blocks if b.get("type") == "tool_use"]

        if not tool_use_blocks:
            return [], False

        # Convert Anthropic tool_use blocks to ToolCall objects so we can
        # reuse the existing tool_runtime.
        fn_calls = [
            ToolCall(
                call_id=b.get("id", ""),
                name=b.get("name", ""),
                arguments=b.get("input"),
            )
            for b in tool_use_blocks
        ]

        return execute_provider_tool_calls(
            fn_calls,
            max_workers=max_workers,
            settings=self._settings,
            display=display,
            session_usage=session_usage,
            turn_usage=turn_usage,
            tool_catalog=self._tool_catalog,
            excluded_tools=self._excluded_tools,
            serialize_result=_anthropic_tool_result_item,
            sub_agent_depth=sub_agent_depth,
            parent_context=parent_context,
            tracer=tracer,
            tool_availability_overridden=getattr(
                self, "_tool_availability_overridden", False
            ),
            workspace_root=getattr(self, "_workspace_root", None),
            workspace_directory_key=getattr(self, "_workspace_directory_key", None),
            execute_calls=_execute_tool_calls,
        )

    # -- HTTP transport ------------------------------------------------------

    def _http_request(
        self,
        *,
        input_value: str | list[dict[str, Any]],
        system_prompt: str | None,
        display: DisplayProtocol,
        tracer: "RunTracer | None" = None,
    ) -> CompletedResponse:
        """Send the current messages to the Anthropic Messages API."""
        body = build_messages_body(
            settings=self._settings,
            tools=self._tools,
            messages=self._messages,
            system_prompt=system_prompt,
        )
        response = self._transport.post(
            JsonRequestSpec(
                provider=self._settings.provider,
                model=self._settings.model,
                url=anthropic_messages_url(
                    self._settings,
                    default_url=ANTHROPIC_API_URL,
                ),
                headers=anthropic_headers(
                    api_key=self._settings.api_key,
                    anthropic_version=ANTHROPIC_VERSION,
                ),
                body=body,
                request_config=self._settings.redacted(),
                wait_input=input_value,
                timeout=300,
                error_policy=JsonErrorPolicy(
                    api_error_label="Anthropic API error",
                    rate_limit_exhausted_label="Anthropic rate limit exceeded",
                    overload_exhausted_label="Anthropic API overloaded",
                    request_failed_label="Anthropic request failed",
                    normalize_http_error=normalize_http_error,
                    format_error=json_error_message,
                ),
                sleep=time.sleep,
            ),
            settings=self._settings,
            display=display,
            tracer=tracer,
            parse_response=self._parse_response,
        )

        render_messages_response(display, response)
        self._messages.append(
            {
                "role": "assistant",
                "content": response.provider_data.get("content_blocks", []),
            }
        )
        return response

    # -- response parsing ----------------------------------------------------

    def _parse_response(self, response_json: dict[str, Any]) -> CompletedResponse:
        """Parse an Anthropic Messages API response into a CompletedResponse."""
        content_blocks: list[dict[str, Any]] = response_json.get("content", [])

        text_parts: list[str] = []
        thinking_parts: list[str] = []
        has_redacted_thinking: bool = False
        function_calls: list[ToolCall] = []
        web_search_sources: list[WebSearchSource] = []
        display_items: list[dict[str, Any]] = []
        pending_web_search_queries: dict[str, list[str]] = {}

        for block in content_blocks:
            block_type = block.get("type")

            if block_type == "thinking":
                thinking_text = block.get("thinking", "")
                if thinking_text:
                    thinking_parts.append(thinking_text)

            elif block_type == "redacted_thinking":
                has_redacted_thinking = True

            elif block_type == "text":
                text = block.get("text", "")
                if text:
                    text_parts.append(text)
                    display_items.append({"type": "text", "text": text})

            elif block_type == "tool_use":
                name = block.get("name", "")
                function_calls.append(
                    ToolCall(
                        call_id=block.get("id", ""),
                        name=name,
                        arguments=block.get("input"),
                    )
                )

            elif block_type == "server_tool_use":
                if str(block.get("name", "")).startswith("web_search"):
                    pending_web_search_queries[block.get("id", "")] = (
                        _extract_anthropic_web_search_queries(block)
                    )

            elif block_type == "web_search_tool_result":
                sources_for_block: list[dict[str, str]] = []
                for entry in block.get("content", []):
                    if not isinstance(entry, dict):
                        continue
                    if entry.get("type") == "web_search_result":
                        source = WebSearchSource(
                            title=str(entry.get("title", "")),
                            url=str(entry.get("url", "")),
                            snippet=str(entry.get("page_snippet", "")),
                        )
                        web_search_sources.append(source)
                        sources_for_block.append(
                            {
                                "title": source.title,
                                "url": source.url,
                                "snippet": source.snippet,
                            }
                        )
                display_items.append(
                    {
                        "type": "web_search",
                        "queries": pending_web_search_queries.get(
                            str(block.get("tool_use_id", "")),
                            [],
                        ),
                        "sources": sources_for_block,
                    }
                )

        # Parse usage
        usage_obj = response_json.get("usage", {})
        base_input_tokens = int(usage_obj.get("input_tokens", 0) or 0)
        output_tokens = int(usage_obj.get("output_tokens", 0) or 0)
        cache_read_tokens = int(usage_obj.get("cache_read_input_tokens", 0) or 0)
        cache_creation_tokens = int(
            usage_obj.get("cache_creation_input_tokens", 0) or 0
        )

        # Break down cache creation by TTL (default is 5-minute).
        cache_creation_obj = usage_obj.get("cache_creation", {})
        if isinstance(cache_creation_obj, dict):
            cache_1h = int(cache_creation_obj.get("ephemeral_1h_input_tokens", 0) or 0)
        else:
            cache_1h = 0
        cache_5m = max(cache_creation_tokens - cache_1h, 0)

        # Total input for display (base + cache reads + cache writes).
        total_input = base_input_tokens + cache_read_tokens + cache_creation_tokens

        return CompletedResponse(
            response_id=response_json.get("id"),
            text="\n\n".join(text_parts).strip(),
            usage=TokenUsage(
                input_tokens=total_input,
                cached_input_tokens=cache_read_tokens,
                cache_write_tokens=cache_5m,
                cache_write_1h_tokens=cache_1h,
                output_tokens=output_tokens,
                context_tokens=total_input + output_tokens,
            ),
            function_calls=function_calls,
            # Store raw content blocks so execute_tool_calls can access the
            # full tool_use data (including input parameters), plus parsed
            # thinking data for display.
            provider_data={
                "content_blocks": content_blocks,
                "thinking_parts": thinking_parts,
                "has_redacted_thinking": has_redacted_thinking,
                "display_items": display_items,
            },
            web_search_sources=web_search_sources,
        )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _anthropic_user_content_blocks(user_input: UserTurnInput) -> list[dict[str, Any]]:
    blocks: list[dict[str, Any]] = []
    for image in user_input.images:
        blocks.append(_anthropic_image_block(image))
    if user_input.text:
        blocks.append({"type": "text", "text": user_input.text})
    return blocks or [{"type": "text", "text": ""}]


def _anthropic_message_record_can_restore(message: MessageRecord) -> bool:
    if message.role not in {"user", "assistant"}:
        return False
    return bool(message.content or message.image_attachments)


def _anthropic_message_record_to_message(
    message: MessageRecord,
) -> dict[str, Any]:
    if message.role == "user" and message.image_attachments:
        return {
            "role": message.role,
            "content": _anthropic_user_content_blocks(
                UserTurnInput(
                    text=message.content,
                    images=[
                        load_uploaded_image(attachment.upload_id)
                        for attachment in message.image_attachments
                    ],
                )
            ),
        }
    return {
        "role": message.role,
        "content": [{"type": "text", "text": message.content}],
    }


def _history_item_to_message(item: dict[str, Any]) -> dict[str, Any] | None:
    item_type = item.get("type")
    if item_type == "message":
        message = item.get("message")
        if isinstance(message, MessageRecord) and _anthropic_message_record_can_restore(
            message
        ):
            return _anthropic_message_record_to_message(message)
        return None
    if item_type == "tool_call":
        call_id = str(item.get("call_id") or "")
        name = str(item.get("name") or "")
        if not call_id or not name:
            return None
        return {
            "role": "assistant",
            "content": [
                {
                    "type": "tool_use",
                    "id": call_id,
                    "name": name,
                    "input": item.get("arguments") or {},
                }
            ],
        }
    if item_type == "tool_call_group":
        tool_use_blocks: list[dict[str, Any]] = []
        for call in item.get("calls", []):
            if not isinstance(call, dict):
                continue
            call_id = str(call.get("call_id") or "")
            name = str(call.get("name") or "")
            if not call_id or not name:
                continue
            tool_use_blocks.append(
                {
                    "type": "tool_use",
                    "id": call_id,
                    "name": name,
                    "input": call.get("arguments") or {},
                }
            )
        if not tool_use_blocks:
            return None
        return {"role": "assistant", "content": tool_use_blocks}
    if item_type == "tool_result":
        call_id = str(item.get("call_id") or "")
        if not call_id:
            return None
        output = item.get("output")
        result_content = output if isinstance(output, str) else json.dumps(output)
        result_block: dict[str, Any] = {
            "type": "tool_result",
            "tool_use_id": call_id,
            "content": result_content,
        }
        if item.get("is_error"):
            result_block["is_error"] = True
        return {"role": "user", "content": [result_block]}
    if item_type == "tool_result_group":
        result_blocks: list[dict[str, Any]] = []
        for result_item in item.get("results", []):
            if not isinstance(result_item, dict):
                continue
            call_id = str(result_item.get("call_id") or "")
            if not call_id:
                continue
            output = result_item.get("output")
            grouped_result_block: dict[str, Any] = {
                "type": "tool_result",
                "tool_use_id": call_id,
                "content": output if isinstance(output, str) else json.dumps(output),
            }
            if result_item.get("is_error"):
                grouped_result_block["is_error"] = True
            result_blocks.append(grouped_result_block)
        if not result_blocks:
            return None
        return {"role": "user", "content": result_blocks}
    return None


def _anthropic_tool_result_content(result) -> str | list[dict[str, Any]]:
    if not result.attachments:
        return result.output_json

    blocks = [_anthropic_image_block(image) for image in result.attachments]
    blocks.append({"type": "text", "text": result.output_json})
    return blocks


def _anthropic_tool_result_item(result) -> dict[str, Any]:
    return {
        "type": "tool_result",
        "tool_use_id": result.call_id,
        "content": _anthropic_tool_result_content(result),
        **({"is_error": True} if result.is_error else {}),
    }


def _anthropic_image_block(image: ImageAttachment) -> dict[str, Any]:
    return {
        "type": "image",
        "source": {
            "type": "base64",
            "media_type": image.mime_type,
            "data": image.data_base64,
        },
    }


def _extract_anthropic_web_search_queries(block: dict[str, Any]) -> list[str]:
    raw_input = block.get("input")
    if not isinstance(raw_input, dict):
        return []
    raw_query = raw_input.get("query")
    if isinstance(raw_query, str) and raw_query.strip():
        return [raw_query.strip()]
    return []
