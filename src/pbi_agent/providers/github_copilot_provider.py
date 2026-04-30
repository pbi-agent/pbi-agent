"""GitHub Copilot HTTP provider."""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from dataclasses import replace
from typing import Any, TYPE_CHECKING

from pbi_agent import __version__
from pbi_agent.auth.service import build_runtime_request_auth
from pbi_agent.config import Settings
from pbi_agent.media import data_url_for_image
from pbi_agent.models.messages import CompletedResponse, TokenUsage, UserTurnInput
from pbi_agent.providers.base import Provider
from pbi_agent.providers.chatgpt_codex_backend import (
    ResponsesRequestOptions,
    ResponsesConversationReplay,
)
from pbi_agent.providers.generic_provider import (
    GenericProvider,
    _duration_ms,
    _extract_retry_after,
    _trace_provider_call,
)
from pbi_agent.providers.github_copilot_backend import (
    GITHUB_COPILOT_CHAT_COMPLETIONS_URL,
    github_copilot_backend_for_model,
)
from pbi_agent.providers.openai_provider import OpenAIProvider
from pbi_agent.providers.wait_messages import waiting_message_for_input
from pbi_agent.session_store import MessageRecord
from pbi_agent.tools.catalog import ToolCatalog
from pbi_agent.tools.types import ParentContextSnapshot
from pbi_agent.display.protocol import DisplayProtocol

if TYPE_CHECKING:
    from pbi_agent.observability import RunTracer


class GitHubCopilotProvider(Provider):
    def __init__(
        self,
        settings: Settings,
        *,
        system_prompt: str | None = None,
        excluded_tools: set[str] | None = None,
        tool_catalog: ToolCatalog | None = None,
    ) -> None:
        backend = github_copilot_backend_for_model(settings.model)
        if backend.mode == "responses":
            self._delegate: Provider = _GitHubCopilotResponsesProvider(
                settings,
                system_prompt=system_prompt,
                excluded_tools=excluded_tools,
                tool_catalog=tool_catalog,
            )
        else:
            self._delegate = _GitHubCopilotChatCompletionsProvider(
                settings,
                system_prompt=system_prompt,
                excluded_tools=excluded_tools,
                tool_catalog=tool_catalog,
            )

    @property
    def settings(self) -> Settings:
        return self._delegate.settings

    def connect(self) -> None:
        self._delegate.connect()

    def close(self) -> None:
        self._delegate.close()

    def reset_conversation(self) -> None:
        self._delegate.reset_conversation()

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
        return self._delegate.request_turn(
            user_message=user_message,
            user_input=user_input,
            tool_result_items=tool_result_items,
            instructions=instructions,
            session_id=session_id,
            display=display,
            session_usage=session_usage,
            turn_usage=turn_usage,
            tracer=tracer,
        )

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
        return self._delegate.execute_tool_calls(
            response,
            max_workers=max_workers,
            display=display,
            session_usage=session_usage,
            turn_usage=turn_usage,
            sub_agent_depth=sub_agent_depth,
            parent_context=parent_context,
            tracer=tracer,
        )

    def set_previous_response_id(self, response_id: str | None) -> None:
        self._delegate.set_previous_response_id(response_id)

    def get_conversation_checkpoint(self) -> str | None:
        return self._delegate.get_conversation_checkpoint()

    def restore_messages(self, messages: list[MessageRecord]) -> None:
        self._delegate.restore_messages(messages)

    def set_system_prompt(self, system_prompt: str) -> None:
        self._delegate.set_system_prompt(system_prompt)

    def refresh_tools(self) -> None:
        self._delegate.refresh_tools()


class _GitHubCopilotResponsesProvider(OpenAIProvider):
    def __init__(
        self,
        settings: Settings,
        *,
        system_prompt: str | None = None,
        excluded_tools: set[str] | None = None,
        tool_catalog: ToolCatalog | None = None,
    ) -> None:
        super().__init__(
            settings,
            system_prompt=system_prompt,
            excluded_tools=excluded_tools,
            tool_catalog=tool_catalog,
        )
        self._conversation = ResponsesConversationReplay()

    def _responses_request_options(self) -> ResponsesRequestOptions:
        return ResponsesRequestOptions(
            store=False,
            include_prompt_cache_retention=False,
            include_context_management=False,
            stream=True,
        )

    def reset_conversation(self) -> None:
        super().reset_conversation()
        self._conversation.reset()

    def restore_messages(self, messages: list[MessageRecord]) -> None:
        super().restore_messages(messages)
        self._conversation.restore(self._restored_input_items)

    def _build_request_body(
        self,
        *,
        input_items: list[dict[str, Any]],
        instructions: str | None,
        session_id: str | None = None,
        include_previous_response_id: bool = True,
    ) -> dict[str, Any]:
        body = super()._build_request_body(
            input_items=input_items,
            instructions=instructions,
            session_id=session_id,
            include_previous_response_id=include_previous_response_id,
        )
        body.pop("store", None)
        body.pop("prompt_cache_retention", None)
        body.pop("context_management", None)
        body["stream"] = True
        if self._settings.model.startswith("gpt"):
            body.pop("max_output_tokens", None)
        return body

    def _build_input_payload(
        self,
        input_items: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        return self._conversation.build_input_payload(input_items)

    def _supports_previous_response_id(self) -> bool:
        return False

    def _record_exchange(
        self,
        input_items: list[dict[str, Any]],
        response: CompletedResponse,
    ) -> None:
        self._conversation.record_exchange(input_items, response)

    def _request_headers(
        self,
        *,
        request_auth: Any,
        session_id: str | None,
        input_items: list[dict[str, Any]],
    ) -> dict[str, str]:
        headers = {
            "Accept": "text/event-stream",
            "Content-Type": "application/json",
            "User-Agent": f"pbi-agent/{__version__}",
            "Openai-Intent": "conversation-edits",
            "x-initiator": (
                "user" if _is_user_initiated_request(input_items) else "agent"
            ),
            **request_auth.headers,
        }
        if _has_image_inputs(input_items):
            headers["Copilot-Vision-Request"] = "true"
        if session_id:
            headers["session_id"] = session_id
        return headers

    def _decode_response_body(
        self,
        raw_body: str,
        *,
        streamed: bool,
    ) -> dict[str, Any]:
        return _decode_copilot_responses_body(raw_body, streamed=streamed)


class _GitHubCopilotChatCompletionsProvider(GenericProvider):
    def connect(self) -> None:
        if self._settings.auth is None:
            raise ValueError(
                "Missing authentication. Configure a saved GitHub Copilot account session."
            )

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
            input_value: str | list[dict[str, Any]] = user_input.text
            self._messages.append(_build_chat_completions_user_message(user_input))
        elif tool_result_items is not None:
            input_value = tool_result_items
            self._messages.extend(tool_result_items)
        else:
            raise ValueError("Either user_input or tool_result_items is required")

        result = self._http_request(
            input_value=input_value,
            instructions=instructions or self._system_prompt,
            display=display,
            tracer=tracer,
        )
        session_usage.add(result.usage)
        turn_usage.add(result.usage)
        display.session_usage(session_usage)

        if result.reasoning_summary or result.reasoning_content:
            display.render_thinking(
                result.reasoning_content or result.reasoning_summary,
                title=result.reasoning_summary or None,
            )

        assistant_message = result.provider_data.get("assistant_message")
        if isinstance(assistant_message, dict):
            self._messages.append(assistant_message)

        return result

    def _http_request(
        self,
        *,
        input_value: str | list[dict[str, Any]],
        instructions: str,
        display: DisplayProtocol,
        tracer: "RunTracer | None" = None,
    ) -> CompletedResponse:
        display.wait_start(waiting_message_for_input(input_value))

        messages: list[dict[str, Any]] = [{"role": "system", "content": instructions}]
        messages.extend(self._messages)

        body: dict[str, Any] = {
            "messages": messages,
            "tools": self._tools,
            "tool_choice": "auto",
            "max_tokens": self._settings.max_tokens,
            "stream": False,
        }
        if self._settings.model:
            body["model"] = self._settings.model

        request_data = json.dumps(body).encode("utf-8")
        max_retries = self._settings.max_retries
        last_error: Exception | None = None
        request_url = GITHUB_COPILOT_CHAT_COMPLETIONS_URL

        for attempt in range(max_retries + 1):
            if attempt > 0:
                display.retry_notice(attempt, max_retries)

            req_start = time.perf_counter()
            request_auth = build_runtime_request_auth(
                provider_kind=self._settings.provider,
                request_url=request_url,
                auth=self._settings.auth,
            )
            headers = _github_copilot_chat_completions_headers(
                request_auth_headers=request_auth.headers,
                has_image_inputs=_messages_include_image_inputs(messages),
                user_initiated=_messages_are_user_initiated(messages),
            )
            try:
                req = urllib.request.Request(
                    request_auth.request_url,
                    data=request_data,
                    headers=headers,
                    method="POST",
                )
                with urllib.request.urlopen(req, timeout=300) as resp:
                    response_json = json.loads(resp.read().decode("utf-8"))

                result = self._parse_response(response_json)
                _trace_provider_call(
                    tracer=tracer,
                    provider=self._settings.provider,
                    model=self._settings.model,
                    url=request_auth.request_url,
                    request_config=self._settings.redacted(),
                    request_payload=body,
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

                if result.text:
                    display.render_markdown(result.text)

                return result
            except urllib.error.HTTPError as exc:
                error_body = ""
                try:
                    error_body = exc.read().decode("utf-8", errors="replace")
                except Exception:
                    pass
                _trace_provider_call(
                    tracer=tracer,
                    provider=self._settings.provider,
                    model=self._settings.model,
                    url=request_auth.request_url,
                    request_config=self._settings.redacted(),
                    request_payload=body,
                    response_payload={"body": error_body},
                    duration_ms=_duration_ms(req_start),
                    status_code=exc.code,
                    success=False,
                    error_message=error_body or f"HTTP {exc.code}",
                    metadata={"attempt": attempt + 1},
                )

                if exc.code == 429:
                    if attempt >= max_retries:
                        display.wait_stop()
                        raise RuntimeError(
                            "GitHub Copilot rate limit exceeded after "
                            f"{max_retries + 1} attempts: {error_body}"
                        ) from exc
                    wait = _extract_retry_after(exc, attempt)
                    display.rate_limit_notice(
                        wait_seconds=wait,
                        attempt=attempt + 1,
                        max_retries=max_retries,
                    )
                    time.sleep(wait)
                    continue

                if exc.code >= 500:
                    last_error = exc
                    continue

                display.wait_stop()
                raise RuntimeError(
                    f"GitHub Copilot API error {exc.code}: {error_body}"
                ) from exc
            except urllib.error.URLError as exc:
                last_error = exc
                _trace_provider_call(
                    tracer=tracer,
                    provider=self._settings.provider,
                    model=self._settings.model,
                    url=request_auth.request_url,
                    request_config=self._settings.redacted(),
                    request_payload=body,
                    response_payload={"error": str(exc)},
                    duration_ms=_duration_ms(req_start),
                    success=False,
                    error_message=str(exc),
                    metadata={"attempt": attempt + 1},
                )
                continue

        display.wait_stop()
        if last_error is not None:
            raise RuntimeError(
                "GitHub Copilot chat-completions request failed after "
                f"{max_retries + 1} attempts: {last_error}"
            ) from last_error
        raise RuntimeError(
            "GitHub Copilot chat-completions request failed after retries."
        )

    def _parse_response(self, response_json: dict[str, Any]) -> CompletedResponse:
        response = super()._parse_response(response_json)
        message = _first_message_with_reasoning(response_json.get("choices", []))
        if message is None:
            return response
        reasoning_text = message.get("reasoning_text")
        if not isinstance(reasoning_text, str) or not reasoning_text.strip():
            return response
        provider_data = response.provider_data
        if not isinstance(provider_data, dict):
            provider_data = {}
        provider_data = {**provider_data, "reasoning_text": reasoning_text.strip()}
        return replace(
            response,
            reasoning_content=reasoning_text.strip(),
            provider_data=provider_data,
        )


def _build_chat_completions_user_message(user_input: UserTurnInput) -> dict[str, Any]:
    if not user_input.images:
        return {"role": "user", "content": user_input.text}

    content: list[dict[str, Any]] = []
    if user_input.text:
        content.append({"type": "text", "text": user_input.text})
    for image in user_input.images:
        content.append(
            {
                "type": "image_url",
                "image_url": {"url": data_url_for_image(image)},
            }
        )
    return {"role": "user", "content": content}


def _first_message_with_reasoning(choices: object) -> dict[str, Any] | None:
    if not isinstance(choices, list):
        return None
    for choice in choices:
        if not isinstance(choice, dict):
            continue
        message = choice.get("message", {})
        if not isinstance(message, dict):
            continue
        reasoning_text = message.get("reasoning_text")
        if isinstance(reasoning_text, str) and reasoning_text.strip():
            return message
    return None


def _github_copilot_chat_completions_headers(
    *,
    request_auth_headers: dict[str, str],
    has_image_inputs: bool,
    user_initiated: bool,
) -> dict[str, str]:
    headers = {
        "Accept": "application/json",
        "Content-Type": "application/json",
        "User-Agent": f"pbi-agent/{__version__}",
        "Openai-Intent": "conversation-edits",
        "x-initiator": "user" if user_initiated else "agent",
        **request_auth_headers,
    }
    if has_image_inputs:
        headers["Copilot-Vision-Request"] = "true"
    return headers


def _messages_include_image_inputs(messages: list[dict[str, Any]]) -> bool:
    for message in messages:
        content = message.get("content")
        if not isinstance(content, list):
            continue
        for part in content:
            if not isinstance(part, dict):
                continue
            if part.get("type") == "image_url":
                return True
    return False


def _messages_are_user_initiated(messages: list[dict[str, Any]]) -> bool:
    if not messages:
        return False
    last_message = messages[-1]
    return last_message.get("role") == "user"


def _is_user_initiated_request(input_items: list[dict[str, Any]]) -> bool:
    if not input_items:
        return False
    last_item = input_items[-1]
    return last_item.get("role") == "user"


def _has_image_inputs(input_items: list[dict[str, Any]]) -> bool:
    for item in input_items:
        content = item.get("content")
        if not isinstance(content, list):
            continue
        for part in content:
            if isinstance(part, dict) and part.get("type") == "input_image":
                return True
    return False


def _decode_copilot_responses_body(raw_body: str, *, streamed: bool) -> dict[str, Any]:
    normalized = raw_body.strip()
    if not streamed or normalized.startswith("{"):
        return json.loads(normalized)
    return _parse_copilot_sse_response(normalized)


def _parse_copilot_sse_response(raw_body: str) -> dict[str, Any]:
    event_name: str | None = None
    data_lines: list[str] = []
    last_response: dict[str, Any] | None = None
    last_error: dict[str, Any] | None = None
    response_meta: dict[str, Any] = {}
    output_items: dict[int, dict[str, Any]] = {}
    current_text_output_index: int | None = None
    current_reasoning_output_index: int | None = None

    def flush_event() -> None:
        nonlocal event_name, data_lines, last_response, last_error
        nonlocal current_text_output_index, current_reasoning_output_index
        if not data_lines:
            event_name = None
            return
        payload_text = "\n".join(data_lines).strip()
        data_lines = []
        if not payload_text:
            event_name = None
            return
        payload = json.loads(payload_text)
        event_type = event_name or payload.get("type")
        if event_type == "response.created":
            response = payload.get("response")
            if isinstance(response, dict):
                response_meta.update(response)
        elif event_type == "response.output_item.added":
            output_index = payload.get("output_index")
            item = payload.get("item")
            if isinstance(output_index, int) and isinstance(item, dict):
                normalized_item = _normalize_copilot_output_item(item)
                output_items[output_index] = normalized_item
                if normalized_item.get("type") == "message":
                    current_text_output_index = output_index
                elif normalized_item.get("type") == "reasoning":
                    current_reasoning_output_index = output_index
        elif event_type == "response.output_item.done":
            output_index = payload.get("output_index")
            item = payload.get("item")
            if isinstance(output_index, int) and isinstance(item, dict):
                normalized_item = _normalize_copilot_output_item(item)
                existing_item = output_items.get(output_index)
                if existing_item is not None:
                    output_items[output_index] = _merge_copilot_output_item(
                        existing_item, normalized_item
                    )
                else:
                    output_items[output_index] = normalized_item
                item_type = output_items[output_index].get("type")
                if item_type == "message":
                    current_text_output_index = None
                elif item_type == "reasoning":
                    current_reasoning_output_index = None
        elif event_type == "response.output_text.delta":
            delta = payload.get("delta")
            item_id = payload.get("item_id")
            if isinstance(delta, str):
                current_text_output_index = _append_copilot_message_delta(
                    output_items=output_items,
                    output_index=current_text_output_index,
                    item_id=item_id if isinstance(item_id, str) else None,
                    delta=delta,
                )
        elif event_type == "response.function_call_arguments.delta":
            output_index = payload.get("output_index")
            delta = payload.get("delta")
            item_id = payload.get("item_id")
            if isinstance(output_index, int) and isinstance(delta, str):
                _append_copilot_function_arguments_delta(
                    output_items=output_items,
                    output_index=output_index,
                    item_id=item_id if isinstance(item_id, str) else None,
                    delta=delta,
                )
        elif event_type == "response.reasoning_summary_part.added":
            summary_index = payload.get("summary_index", 0)
            if current_reasoning_output_index is not None and isinstance(
                summary_index, int
            ):
                _ensure_copilot_reasoning_summary_index(
                    output_items=output_items,
                    output_index=current_reasoning_output_index,
                    summary_index=summary_index,
                )
        elif event_type == "response.reasoning_summary_text.delta":
            delta = payload.get("delta")
            summary_index = payload.get("summary_index", 0)
            if (
                current_reasoning_output_index is not None
                and isinstance(delta, str)
                and isinstance(summary_index, int)
            ):
                _append_copilot_reasoning_summary_delta(
                    output_items=output_items,
                    output_index=current_reasoning_output_index,
                    summary_index=summary_index,
                    delta=delta,
                )
        if event_type in {"response.completed", "response.incomplete"}:
            response = payload.get("response")
            if isinstance(response, dict):
                last_response = response
        elif event_type == "response.failed":
            last_error = payload
        event_name = None

    for raw_line in raw_body.splitlines():
        line = raw_line.rstrip("\r")
        if not line:
            flush_event()
            continue
        if line.startswith(":"):
            continue
        if line.startswith("event:"):
            event_name = line[6:].strip()
            continue
        if line.startswith("data:"):
            data_lines.append(line[5:].lstrip())

    flush_event()

    if last_response is not None:
        merged_response = dict(response_meta)
        merged_response.update(last_response)
        ordered_output = [
            output_items[index]
            for index in sorted(output_items)
            if isinstance(output_items[index], dict)
        ]
        if ordered_output and not merged_response.get("output"):
            merged_response["output"] = ordered_output
        return merged_response
    if last_error is not None:
        return last_error
    raise ValueError("Stream ended without a response.completed event")


def _normalize_copilot_output_item(item: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(item)
    item_type = normalized.get("type")
    if item_type == "message":
        normalized.setdefault("role", "assistant")
        if not isinstance(normalized.get("content"), list):
            normalized["content"] = []
    elif item_type == "reasoning":
        if not isinstance(normalized.get("summary"), list):
            normalized["summary"] = []
    elif item_type == "function_call":
        normalized.setdefault("arguments", "")
    return normalized


def _merge_copilot_output_item(
    existing: dict[str, Any],
    new_item: dict[str, Any],
) -> dict[str, Any]:
    merged = dict(existing)
    for key, value in new_item.items():
        if key in {"content", "summary"} and isinstance(value, list) and not value:
            continue
        merged[key] = value
    return merged


def _append_copilot_message_delta(
    *,
    output_items: dict[int, dict[str, Any]],
    output_index: int | None,
    item_id: str | None,
    delta: str,
) -> int:
    resolved_index = output_index
    if resolved_index is None:
        resolved_index = max(output_items.keys(), default=-1) + 1
    item = output_items.get(resolved_index)
    if item is None:
        item = {
            "id": item_id or f"message_{resolved_index}",
            "type": "message",
            "role": "assistant",
            "content": [],
        }
        output_items[resolved_index] = item
    content = item.setdefault("content", [])
    if not content:
        content.append({"type": "output_text", "text": delta})
        return resolved_index
    first_part = content[0]
    if isinstance(first_part, dict) and first_part.get("type") == "output_text":
        first_part["text"] = f"{first_part.get('text', '')}{delta}"
    return resolved_index


def _append_copilot_function_arguments_delta(
    *,
    output_items: dict[int, dict[str, Any]],
    output_index: int,
    item_id: str | None,
    delta: str,
) -> None:
    item = output_items.get(output_index)
    if item is None:
        item = {
            "id": item_id or f"function_call_{output_index}",
            "type": "function_call",
            "call_id": item_id or f"call_{output_index}",
            "name": "",
            "arguments": "",
        }
        output_items[output_index] = item
    item["arguments"] = f"{item.get('arguments', '')}{delta}"


def _ensure_copilot_reasoning_summary_index(
    *,
    output_items: dict[int, dict[str, Any]],
    output_index: int,
    summary_index: int,
) -> None:
    item = output_items.get(output_index)
    if item is None:
        item = {"type": "reasoning", "summary": []}
        output_items[output_index] = item
    summary = item.setdefault("summary", [])
    while len(summary) <= summary_index:
        summary.append({"type": "summary_text", "text": ""})


def _append_copilot_reasoning_summary_delta(
    *,
    output_items: dict[int, dict[str, Any]],
    output_index: int,
    summary_index: int,
    delta: str,
) -> None:
    _ensure_copilot_reasoning_summary_index(
        output_items=output_items,
        output_index=output_index,
        summary_index=summary_index,
    )
    summary = output_items[output_index]["summary"]
    summary_item = summary[summary_index]
    if isinstance(summary_item, dict):
        summary_item["text"] = f"{summary_item.get('text', '')}{delta}"
