from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Any, Protocol
from urllib.parse import urlparse, urlunparse

from pbi_agent.auth.providers.openai_chatgpt import OPENAI_CHATGPT_RESPONSES_URL
from pbi_agent.agent.tool_runtime import to_function_call_output_items
from pbi_agent.models.messages import CompletedResponse
from pbi_agent.providers.chatgpt_codex_transport import (
    CHATGPT_TURN_STATE_HEADER,
    ResponsesWebSocket,
)
from pbi_agent.providers.protocols.openai_responses import (
    response_history_item_for_input,
)
from pbi_agent.tools.types import ToolResult

CHATGPT_ORIGINATOR = "codex_cli_rs"
CHATGPT_CODEX_VERSION = "0.124.0"
CHATGPT_TERMINAL_USER_AGENT = "unknown"
CHATGPT_WEBSOCKET_BETA_HEADER = "responses_websockets=2026-02-06"


@dataclass(frozen=True)
class ResponsesRequestOptions:
    include_max_output_tokens: bool = True
    store: bool = True
    include_prompt_cache_retention: bool = True
    include_context_management: bool = True
    stream: bool = False
    tool_choice: str | None = None
    include: list[str] | None = None
    use_session_prompt_cache_key: bool = False


def chatgpt_user_agent() -> str:
    return f"{CHATGPT_ORIGINATOR}/{CHATGPT_CODEX_VERSION} ({os_name()} {os_release()}; {machine_arch()}) {CHATGPT_TERMINAL_USER_AGENT}"


def os_name() -> str:
    if os.name == "nt":
        return "Windows"
    uname = os.uname()
    if uname.sysname == "Darwin":
        return "Mac OS"
    return uname.sysname


def os_release() -> str:
    if os.name == "nt":
        return os.environ.get("OS", "unknown")
    return os.uname().release


def machine_arch() -> str:
    if os.name == "nt":
        return os.environ.get("PROCESSOR_ARCHITECTURE", "unknown")
    return os.uname().machine or "unknown"


class ChatGPTCodexBackendProtocol(Protocol):
    @property
    def enabled(self) -> bool: ...

    @property
    def websocket_url(self) -> str: ...

    def reset(self) -> None: ...

    def close_websocket(self) -> None: ...

    def clear_live_loop_state(self) -> None: ...

    def restore_conversation(self, items: list[dict[str, Any]]) -> None: ...

    def start_turn(self, input_items: list[dict[str, Any]]) -> None: ...

    def finish_turn(self) -> None: ...

    def record_exchange(
        self,
        input_items: list[dict[str, Any]],
        response: CompletedResponse,
    ) -> None: ...

    def serialize_tools(self, tools: list[dict[str, Any]]) -> list[dict[str, Any]]: ...

    def capture_response_headers(self, response: Any) -> None: ...

    def apply_headers(
        self, headers: dict[str, str], *, session_id: str | None
    ) -> None: ...

    def request_options(self) -> ResponsesRequestOptions: ...

    def build_input_payload(
        self,
        *,
        input_items: list[dict[str, Any]],
        live_followup: bool = False,
    ) -> list[dict[str, Any]]: ...

    def send_websocket_request(
        self,
        *,
        request_body: dict[str, Any],
        headers: dict[str, str],
        connect_timeout: float,
        idle_timeout: float,
        request_timeout: float,
    ) -> list[dict[str, Any]]: ...

    def tool_result_items_for_response(
        self,
        response: CompletedResponse,
        results: list[ToolResult],
    ) -> list[dict[str, Any]]: ...


class ChatGPTCodexBackend:
    def __new__(cls, *, responses_url: str) -> ChatGPTCodexBackendProtocol:
        if responses_url == OPENAI_CHATGPT_RESPONSES_URL:
            return _EnabledChatGPTCodexBackend(responses_url=responses_url)
        return _NullChatGPTCodexBackend(responses_url=responses_url)


class _NullChatGPTCodexBackend:
    def __init__(self, *, responses_url: str) -> None:
        self._responses_url = responses_url

    @property
    def enabled(self) -> bool:
        return False

    @property
    def websocket_url(self) -> str:
        return websocket_url_for_responses_url(self._responses_url)

    def reset(self) -> None:
        pass

    def close_websocket(self) -> None:
        pass

    def clear_live_loop_state(self) -> None:
        pass

    def restore_conversation(self, items: list[dict[str, Any]]) -> None:
        del items

    def start_turn(self, input_items: list[dict[str, Any]]) -> None:
        del input_items

    def finish_turn(self) -> None:
        pass

    def record_exchange(
        self,
        input_items: list[dict[str, Any]],
        response: CompletedResponse,
    ) -> None:
        del input_items, response

    def serialize_tools(self, tools: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return tools

    def capture_response_headers(self, response: Any) -> None:
        del response

    def apply_headers(self, headers: dict[str, str], *, session_id: str | None) -> None:
        del headers, session_id

    def request_options(self) -> ResponsesRequestOptions:
        return ResponsesRequestOptions()

    def build_input_payload(
        self,
        *,
        input_items: list[dict[str, Any]],
        live_followup: bool = False,
    ) -> list[dict[str, Any]]:
        del live_followup
        return [_clone_item(item) for item in input_items]

    def send_websocket_request(
        self,
        *,
        request_body: dict[str, Any],
        headers: dict[str, str],
        connect_timeout: float,
        idle_timeout: float,
        request_timeout: float,
    ) -> list[dict[str, Any]]:
        del request_body, headers, connect_timeout, idle_timeout, request_timeout
        raise RuntimeError("ChatGPT Codex WebSocket backend is not enabled")

    def tool_result_items_for_response(
        self,
        response: CompletedResponse,
        results: list[ToolResult],
    ) -> list[dict[str, Any]]:
        return to_function_call_output_items(results, response.function_calls)


class _EnabledChatGPTCodexBackend:
    def __init__(self, *, responses_url: str) -> None:
        self._responses_url = responses_url
        self._turn_state: str | None = None
        self._conversation = ResponsesConversationReplay()
        self._websocket: ResponsesWebSocket | None = None

    @property
    def enabled(self) -> bool:
        return True

    @property
    def websocket_url(self) -> str:
        return websocket_url_for_responses_url(self._responses_url)

    def reset(self) -> None:
        self.close_websocket()
        self._turn_state = None
        self._conversation.reset()

    def close_websocket(self) -> None:
        if self._websocket is not None:
            self._websocket.close()
            self._websocket = None

    def clear_live_loop_state(self) -> None:
        self.close_websocket()
        self._turn_state = None

    def restore_conversation(self, items: list[dict[str, Any]]) -> None:
        self._conversation.restore(items)

    def start_turn(self, input_items: list[dict[str, Any]]) -> None:
        del input_items
        self.clear_live_loop_state()
        self._conversation.start_turn()

    def finish_turn(self) -> None:
        self.clear_live_loop_state()
        self._conversation.finish_turn()

    def record_exchange(
        self,
        input_items: list[dict[str, Any]],
        response: CompletedResponse,
    ) -> None:
        self._conversation.record_exchange(input_items, response)

    def serialize_tools(self, tools: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return [dict(tool) for tool in tools]

    def capture_response_headers(self, response: Any) -> None:
        headers = getattr(response, "headers", None)
        if headers is None:
            return
        turn_state = headers.get(CHATGPT_TURN_STATE_HEADER)
        if isinstance(turn_state, str) and turn_state:
            self._turn_state = turn_state

    def apply_headers(self, headers: dict[str, str], *, session_id: str | None) -> None:
        headers["Accept"] = "application/json"
        headers["OpenAI-Beta"] = CHATGPT_WEBSOCKET_BETA_HEADER
        headers["originator"] = CHATGPT_ORIGINATOR
        headers["User-Agent"] = chatgpt_user_agent()
        if session_id:
            headers["session_id"] = session_id
        if self._turn_state:
            headers[CHATGPT_TURN_STATE_HEADER] = self._turn_state

    def request_options(self) -> ResponsesRequestOptions:
        return ResponsesRequestOptions(
            include_max_output_tokens=False,
            store=False,
            include_prompt_cache_retention=False,
            include_context_management=True,
            stream=True,
            tool_choice="auto",
            include=["reasoning.encrypted_content"],
            use_session_prompt_cache_key=True,
        )

    def build_input_payload(
        self,
        *,
        input_items: list[dict[str, Any]],
        live_followup: bool = False,
    ) -> list[dict[str, Any]]:
        if live_followup:
            return [_clone_item(item) for item in input_items]
        return self._conversation.build_input_payload(input_items)

    def send_websocket_request(
        self,
        *,
        request_body: dict[str, Any],
        headers: dict[str, str],
        connect_timeout: float,
        idle_timeout: float,
        request_timeout: float,
    ) -> list[dict[str, Any]]:
        websocket = self._ensure_websocket(
            headers=headers,
            connect_timeout=connect_timeout,
            idle_timeout=idle_timeout,
        )
        try:
            return websocket.send_response_create(
                request_body,
                idle_timeout=idle_timeout,
                request_timeout=request_timeout,
            )
        except Exception:
            self.close_websocket()
            raise

    def _ensure_websocket(
        self,
        *,
        headers: dict[str, str],
        connect_timeout: float,
        idle_timeout: float,
    ) -> ResponsesWebSocket:
        if self._websocket is None or self._websocket.closed:
            self._websocket = ResponsesWebSocket.connect(
                self.websocket_url,
                headers=headers,
                connect_timeout=connect_timeout,
                idle_timeout=idle_timeout,
            )
            turn_state = self._websocket.response_headers.get(CHATGPT_TURN_STATE_HEADER)
            if isinstance(turn_state, str) and turn_state:
                self._turn_state = turn_state
        return self._websocket

    def tool_result_items_for_response(
        self,
        response: CompletedResponse,
        results: list[ToolResult],
    ) -> list[dict[str, Any]]:
        return to_function_call_output_items(results, response.function_calls)


class ResponsesConversationReplay:
    def __init__(self) -> None:
        self._conversation_items: list[dict[str, Any]] = []
        self._active_turn_start: int | None = None

    def reset(self) -> None:
        self._conversation_items.clear()
        self._active_turn_start = None

    def restore(self, items: list[dict[str, Any]]) -> None:
        self._conversation_items = [_clone_item(item) for item in items]
        self._active_turn_start = None

    def start_turn(self) -> None:
        self._active_turn_start = len(self._conversation_items)

    def finish_turn(self) -> None:
        if self._active_turn_start is None:
            return
        before_turn = self._conversation_items[: self._active_turn_start]
        active_items = self._conversation_items[self._active_turn_start :]
        collapsed_items = _completed_turn_history_items(active_items)
        self._conversation_items = [*before_turn, *collapsed_items]
        self._active_turn_start = None

    def build_input_payload(
        self,
        input_items: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        return [
            *(_clone_item(item) for item in self._conversation_items),
            *(_clone_item(item) for item in input_items),
        ]

    def record_exchange(
        self,
        input_items: list[dict[str, Any]],
        response: CompletedResponse,
    ) -> None:
        self._conversation_items.extend(_clone_item(item) for item in input_items)
        self._conversation_items.extend(
            _sanitize_output_item(item) for item in output_items(response.provider_data)
        )


def websocket_url_for_responses_url(responses_url: str) -> str:
    parsed = urlparse(responses_url)
    scheme = "wss" if parsed.scheme == "https" else "ws"
    path = parsed.path.rstrip("/")
    if not path.endswith("/responses"):
        path = f"{path}/responses"
    return urlunparse((scheme, parsed.netloc, path, "", parsed.query, ""))


def output_items(provider_data: Any) -> list[dict[str, Any]]:
    if not isinstance(provider_data, dict):
        return []
    raw_items = provider_data.get("output_items")
    if not isinstance(raw_items, list):
        return []
    return [item for item in raw_items if isinstance(item, dict)]


def _clone_item(item: dict[str, Any]) -> dict[str, Any]:
    return json.loads(json.dumps(item))


def _sanitize_output_item(item: dict[str, Any]) -> dict[str, Any]:
    return response_history_item_for_input(item)


def _completed_turn_history_items(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    history_items: list[dict[str, Any]] = []
    last_assistant_item: dict[str, Any] | None = None
    for item in items:
        if item.get("role") == "user":
            history_items.append(_clone_item(item))
            continue
        assistant_item = _assistant_history_item(item)
        if assistant_item is not None:
            last_assistant_item = assistant_item
    if last_assistant_item is not None:
        history_items.append(last_assistant_item)
    return history_items


def _assistant_history_item(item: dict[str, Any]) -> dict[str, Any] | None:
    if item.get("role") == "assistant" and isinstance(item.get("content"), str):
        content = item["content"]
        return {"role": "assistant", "content": content} if content else None
    if item.get("type") != "message" or item.get("role") != "assistant":
        return None

    text_parts: list[str] = []
    raw_content = item.get("content")
    if isinstance(raw_content, list):
        for part in raw_content:
            if not isinstance(part, dict):
                continue
            if part.get("type") not in {"output_text", "input_text"}:
                continue
            text = part.get("text")
            if isinstance(text, str) and text:
                text_parts.append(text)
    elif isinstance(raw_content, str) and raw_content:
        text_parts.append(raw_content)

    content = "".join(text_parts)
    return {"role": "assistant", "content": content} if content else None
