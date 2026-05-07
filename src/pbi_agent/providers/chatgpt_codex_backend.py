from __future__ import annotations

import base64
import json
import os
import socket
import ssl
import struct
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlparse, urlunparse

from pbi_agent.auth.providers.openai_chatgpt import OPENAI_CHATGPT_RESPONSES_URL
from pbi_agent.agent.tool_runtime import to_function_call_output_items
from pbi_agent.models.messages import CompletedResponse
from pbi_agent.tools.types import ToolResult

CHATGPT_ORIGINATOR = "codex_cli_rs"
CHATGPT_CODEX_VERSION = "0.124.0"
CHATGPT_TERMINAL_USER_AGENT = "unknown"
CHATGPT_TURN_STATE_HEADER = "x-codex-turn-state"
CHATGPT_WEBSOCKET_BETA_HEADER = "responses_websockets=2026-02-06"
WEBSOCKET_CONNECTION_LIMIT_REACHED_CODE = "websocket_connection_limit_reached"
PREVIOUS_RESPONSE_NOT_FOUND_CODE = "previous_response_not_found"

_WS_OPCODE_CONTINUATION = 0x0
_WS_OPCODE_TEXT = 0x1
_WS_OPCODE_BINARY = 0x2
_WS_OPCODE_CLOSE = 0x8
_WS_OPCODE_PING = 0x9
_WS_OPCODE_PONG = 0xA


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


@dataclass(frozen=True)
class WebSocketErrorPayload:
    status: int | None
    payload: dict[str, Any]


class ChatGPTCodexWebSocketError(RuntimeError):
    def __init__(
        self,
        message: str,
        *,
        status: int | None = None,
        payload: dict[str, Any] | None = None,
        retryable: bool = False,
        connection_limit: bool = False,
        previous_response_not_found: bool = False,
    ) -> None:
        self.status = status
        self.payload = payload or {}
        self.retryable = retryable
        self.connection_limit = connection_limit
        self.previous_response_not_found = previous_response_not_found
        super().__init__(message)


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


class ChatGPTCodexBackend:
    def __init__(self, *, responses_url: str) -> None:
        self._responses_url = responses_url
        self._enabled = responses_url == OPENAI_CHATGPT_RESPONSES_URL
        self._turn_state: str | None = None
        self._conversation = ResponsesConversationReplay()
        self._websocket: ResponsesWebSocket | None = None

    @property
    def enabled(self) -> bool:
        return self._enabled

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
        if not self._enabled:
            return
        self._conversation.restore(items)

    def start_turn(self, input_items: list[dict[str, Any]]) -> None:
        if not self._enabled:
            return
        del input_items
        self.clear_live_loop_state()
        self._conversation.start_turn()

    def finish_turn(self) -> None:
        if not self._enabled:
            return
        self.clear_live_loop_state()
        self._conversation.finish_turn()

    def record_exchange(
        self,
        input_items: list[dict[str, Any]],
        response: CompletedResponse,
    ) -> None:
        if not self._enabled:
            return
        self._conversation.record_exchange(input_items, response)

    def serialize_tools(self, tools: list[dict[str, Any]]) -> list[dict[str, Any]]:
        if not self._enabled:
            return tools
        return _serialize_chatgpt_tools(tools)

    def capture_response_headers(self, response: Any) -> None:
        if not self._enabled:
            return
        headers = getattr(response, "headers", None)
        if headers is None:
            return
        turn_state = headers.get(CHATGPT_TURN_STATE_HEADER)
        if isinstance(turn_state, str) and turn_state:
            self._turn_state = turn_state

    def apply_headers(self, headers: dict[str, str], *, session_id: str | None) -> None:
        if not self._enabled:
            return
        headers["Accept"] = "application/json"
        headers["OpenAI-Beta"] = CHATGPT_WEBSOCKET_BETA_HEADER
        headers["originator"] = CHATGPT_ORIGINATOR
        headers["User-Agent"] = chatgpt_user_agent()
        if session_id:
            headers["session_id"] = session_id
        if self._turn_state:
            headers[CHATGPT_TURN_STATE_HEADER] = self._turn_state

    def request_options(self) -> ResponsesRequestOptions:
        if not self._enabled:
            return ResponsesRequestOptions()
        return ResponsesRequestOptions(
            include_max_output_tokens=False,
            store=False,
            include_prompt_cache_retention=False,
            include_context_management=True,
            stream=True,
            tool_choice="auto",
            include=[],
            use_session_prompt_cache_key=True,
        )

    def build_input_payload(
        self,
        *,
        input_items: list[dict[str, Any]],
        live_followup: bool = False,
    ) -> list[dict[str, Any]]:
        if not self._enabled or live_followup:
            return [_clone_item(item) for item in input_items]
        return self._conversation.build_input_payload(input_items)

    def send_websocket_request(
        self,
        *,
        request_body: dict[str, Any],
        headers: dict[str, str],
        timeout: float,
    ) -> list[dict[str, Any]]:
        if not self._enabled:
            raise RuntimeError("ChatGPT Codex WebSocket backend is not enabled")
        websocket = self._ensure_websocket(headers=headers, timeout=timeout)
        try:
            return websocket.send_response_create(request_body, timeout=timeout)
        except Exception:
            self.close_websocket()
            raise

    def _ensure_websocket(
        self,
        *,
        headers: dict[str, str],
        timeout: float,
    ) -> ResponsesWebSocket:
        if self._websocket is None or self._websocket.closed:
            self._websocket = ResponsesWebSocket.connect(
                self.websocket_url,
                headers=headers,
                timeout=timeout,
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
        del response
        return to_function_call_output_items(results)


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


class ResponsesWebSocket:
    def __init__(
        self,
        sock: socket.socket,
        *,
        response_headers: dict[str, str],
        buffered: bytes = b"",
    ) -> None:
        self._sock = sock
        self.response_headers = response_headers
        self.closed = False
        self._buffer = buffered

    @classmethod
    def connect(
        cls,
        url: str,
        *,
        headers: dict[str, str],
        timeout: float,
    ) -> ResponsesWebSocket:
        parsed = urlparse(url)
        if parsed.scheme not in {"ws", "wss"}:
            raise ChatGPTCodexWebSocketError(
                f"Unsupported WebSocket URL scheme: {parsed.scheme}"
            )
        host = parsed.hostname
        if not host:
            raise ChatGPTCodexWebSocketError("WebSocket URL is missing a host")
        port = parsed.port or (443 if parsed.scheme == "wss" else 80)
        path = parsed.path or "/"
        if parsed.query:
            path = f"{path}?{parsed.query}"

        raw_sock = socket.create_connection((host, port), timeout=timeout)
        try:
            if parsed.scheme == "wss":
                context = ssl.create_default_context()
                sock = context.wrap_socket(raw_sock, server_hostname=host)
            else:
                sock = raw_sock
            sock.settimeout(timeout)
            key = base64.b64encode(os.urandom(16)).decode("ascii")
            request_headers = {
                "Host": parsed.netloc,
                **headers,
                "Upgrade": "websocket",
                "Connection": "Upgrade",
                "Sec-WebSocket-Key": key,
                "Sec-WebSocket-Version": "13",
            }
            request = "\r\n".join(
                [f"GET {path} HTTP/1.1"]
                + [f"{name}: {value}" for name, value in request_headers.items()]
                + ["", ""]
            )
            sock.sendall(request.encode("utf-8"))
            status, response_headers, body = _read_http_upgrade_response(sock)
            if status != 101:
                body_text = body.decode("utf-8", errors="replace")
                payload = _json_object(body_text) or {"body": body_text}
                raise ChatGPTCodexWebSocketError(
                    f"WebSocket upgrade failed with status {status}",
                    status=status,
                    payload=_normalize_error_payload(status, payload),
                    retryable=_is_retryable_status(status),
                )
            return cls(sock, response_headers=response_headers, buffered=body)
        except Exception:
            raw_sock.close()
            raise

    def send_response_create(
        self,
        request_body: dict[str, Any],
        *,
        timeout: float,
    ) -> list[dict[str, Any]]:
        if self.closed:
            raise ChatGPTCodexWebSocketError(
                "websocket connection is closed", retryable=True
            )
        self._sock.settimeout(timeout)
        request_payload = {"type": "response.create", **request_body}
        try:
            self._send_text(json.dumps(request_payload, separators=(",", ":")))
        except (OSError, TimeoutError, socket.timeout) as exc:
            self.close()
            raise ChatGPTCodexWebSocketError(
                f"WebSocket send failed: {exc}", retryable=True
            ) from exc
        events: list[dict[str, Any]] = []
        while True:
            try:
                opcode, payload = self._recv_frame()
            except (OSError, TimeoutError, socket.timeout) as exc:
                self.close()
                raise ChatGPTCodexWebSocketError(
                    f"WebSocket read failed: {exc}", retryable=True
                ) from exc
            if opcode == _WS_OPCODE_CLOSE:
                self.close()
                raise ChatGPTCodexWebSocketError(
                    "websocket closed by server before response.completed",
                    retryable=True,
                )
            if opcode == _WS_OPCODE_PING:
                try:
                    self._send_frame(_WS_OPCODE_PONG, payload)
                except (OSError, TimeoutError, socket.timeout) as exc:
                    self.close()
                    raise ChatGPTCodexWebSocketError(
                        f"WebSocket send failed: {exc}", retryable=True
                    ) from exc
                continue
            if opcode == _WS_OPCODE_PONG:
                continue
            if opcode == _WS_OPCODE_BINARY:
                self.close()
                raise ChatGPTCodexWebSocketError(
                    "unexpected binary websocket event", retryable=True
                )
            if opcode not in {_WS_OPCODE_TEXT, _WS_OPCODE_CONTINUATION}:
                continue
            text = payload.decode("utf-8")
            event = _json_object(text)
            if event is None:
                continue
            error = _wrapped_error(event)
            if error is not None:
                self.close()
                raise _websocket_error_from_payload(error)
            events.append(event)
            if event.get("type") in {"response.completed", "response.incomplete"}:
                return events
            if event.get("type") == "response.failed":
                return events

    def close(self) -> None:
        if self.closed:
            return
        self.closed = True
        try:
            self._send_frame(_WS_OPCODE_CLOSE, b"")
        except OSError:
            pass
        try:
            self._sock.close()
        except OSError:
            pass

    def _send_text(self, text: str) -> None:
        self._send_frame(_WS_OPCODE_TEXT, text.encode("utf-8"))

    def _send_frame(self, opcode: int, payload: bytes) -> None:
        first = 0x80 | opcode
        length = len(payload)
        mask_bit = 0x80
        if length < 126:
            header = struct.pack("!BB", first, mask_bit | length)
        elif length < 65536:
            header = struct.pack("!BBH", first, mask_bit | 126, length)
        else:
            header = struct.pack("!BBQ", first, mask_bit | 127, length)
        mask = os.urandom(4)
        masked = bytes(byte ^ mask[index % 4] for index, byte in enumerate(payload))
        self._sock.sendall(header + mask + masked)

    def _recv_frame(self) -> tuple[int, bytes]:
        chunks: list[bytes] = []
        first_opcode: int | None = None
        while True:
            header = self._recv_exact(2)
            first, second = header[0], header[1]
            fin = bool(first & 0x80)
            opcode = first & 0x0F
            masked = bool(second & 0x80)
            length = second & 0x7F
            if length == 126:
                length = struct.unpack("!H", self._recv_exact(2))[0]
            elif length == 127:
                length = struct.unpack("!Q", self._recv_exact(8))[0]
            mask = self._recv_exact(4) if masked else b""
            payload = self._recv_exact(length) if length else b""
            if masked:
                payload = bytes(
                    byte ^ mask[index % 4] for index, byte in enumerate(payload)
                )
            if opcode in {_WS_OPCODE_TEXT, _WS_OPCODE_BINARY}:
                first_opcode = opcode
                chunks = [payload]
            elif opcode == _WS_OPCODE_CONTINUATION and first_opcode is not None:
                chunks.append(payload)
            else:
                return opcode, payload
            if fin:
                return first_opcode, b"".join(chunks)

    def _recv_exact(self, length: int) -> bytes:
        data = b""
        if self._buffer:
            data = self._buffer[:length]
            self._buffer = self._buffer[length:]
        while len(data) < length:
            chunk = self._sock.recv(length - len(data))
            if not chunk:
                raise ConnectionError("websocket closed")
            data += chunk
        return data


def output_items(provider_data: Any) -> list[dict[str, Any]]:
    if not isinstance(provider_data, dict):
        return []
    raw_items = provider_data.get("output_items")
    if not isinstance(raw_items, list):
        return []
    return [item for item in raw_items if isinstance(item, dict)]


def _read_http_upgrade_response(
    sock: socket.socket,
) -> tuple[int, dict[str, str], bytes]:
    data = b""
    while b"\r\n\r\n" not in data:
        chunk = sock.recv(4096)
        if not chunk:
            break
        data += chunk
        if len(data) > 65536:
            break
    header_bytes, _, body_bytes = data.partition(b"\r\n\r\n")
    header_text = header_bytes.decode("iso-8859-1")
    lines = header_text.split("\r\n")
    status = 0
    if lines:
        parts = lines[0].split()
        if len(parts) >= 2:
            try:
                status = int(parts[1])
            except ValueError:
                status = 0
    headers: dict[str, str] = {}
    for line in lines[1:]:
        name, sep, value = line.partition(":")
        if sep:
            headers[name.strip().lower()] = value.strip()
    return status, headers, body_bytes


def _recv_exact(sock: socket.socket, length: int) -> bytes:
    data = b""
    while len(data) < length:
        chunk = sock.recv(length - len(data))
        if not chunk:
            raise ConnectionError("websocket closed")
        data += chunk
    return data


def _json_object(text: str) -> dict[str, Any] | None:
    try:
        value = json.loads(text)
    except json.JSONDecodeError:
        return None
    return value if isinstance(value, dict) else None


def _wrapped_error(event: dict[str, Any]) -> WebSocketErrorPayload | None:
    if event.get("type") != "error":
        return None
    status = event.get("status", event.get("status_code"))
    status_int = status if isinstance(status, int) else None
    return WebSocketErrorPayload(
        status=status_int,
        payload=_normalize_error_payload(status_int, event),
    )


def _websocket_error_from_payload(
    error: WebSocketErrorPayload,
) -> ChatGPTCodexWebSocketError:
    code = _error_code(error.payload)
    message = _error_message(error.payload) or "WebSocket error"
    connection_limit = code == WEBSOCKET_CONNECTION_LIMIT_REACHED_CODE
    previous_response_not_found = code == PREVIOUS_RESPONSE_NOT_FOUND_CODE
    return ChatGPTCodexWebSocketError(
        message,
        status=error.status,
        payload=error.payload,
        retryable=(
            connection_limit
            or previous_response_not_found
            or _is_retryable_status(error.status)
        ),
        connection_limit=connection_limit,
        previous_response_not_found=previous_response_not_found,
    )


def _normalize_error_payload(
    status: int | None,
    payload: dict[str, Any],
) -> dict[str, Any]:
    if isinstance(payload.get("error"), dict):
        return payload
    error: dict[str, Any] = {}
    for key in ("code", "message", "type"):
        value = payload.get(key)
        if isinstance(value, str):
            error[key] = value
    if status is not None:
        error.setdefault("type", _status_error_type(status))
    return {"error": error or payload}


def _status_error_type(status: int) -> str:
    if status == 429:
        return "rate_limit_error"
    if status >= 500:
        return "server_error"
    return "api_error"


def _is_retryable_status(status: int | None) -> bool:
    return status == 503 or (status is not None and status >= 500)


def _error_code(payload: dict[str, Any]) -> str | None:
    error = payload.get("error")
    if isinstance(error, dict):
        code = error.get("code")
        if isinstance(code, str):
            return code
    return None


def _error_message(payload: dict[str, Any]) -> str | None:
    error = payload.get("error")
    if isinstance(error, dict):
        message = error.get("message")
        if isinstance(message, str):
            return message
    return None


def _clone_item(item: dict[str, Any]) -> dict[str, Any]:
    return json.loads(json.dumps(item))


def _sanitize_output_item(item: dict[str, Any]) -> dict[str, Any]:
    cloned = _clone_item(item)
    return _strip_backend_ids(cloned)


def _completed_turn_history_items(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    history_items: list[dict[str, Any]] = []
    for item in items:
        if item.get("role") == "user":
            history_items.append(_clone_item(item))
            continue
        assistant_item = _assistant_history_item(item)
        if assistant_item is not None:
            history_items.append(assistant_item)
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


def _strip_backend_ids(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            key: _strip_backend_ids(item) for key, item in value.items() if key != "id"
        }
    if isinstance(value, list):
        return [_strip_backend_ids(item) for item in value]
    return value


def _serialize_chatgpt_tools(tools: list[dict[str, Any]]) -> list[dict[str, Any]]:
    serialized: list[dict[str, Any]] = []
    for tool in tools:
        if tool.get("type") == "function":
            parameters = tool.get("parameters")
            serialized.append(
                {
                    **tool,
                    "parameters": (
                        _to_chatgpt_strict_schema(parameters)
                        if isinstance(parameters, dict)
                        else parameters
                    ),
                    "strict": True,
                }
            )
            continue
        serialized.append(dict(tool))
    return serialized


def _to_chatgpt_strict_schema(schema: dict[str, Any]) -> dict[str, Any]:
    transformed: dict[str, Any] = {}
    for key, value in schema.items():
        if key == "properties" and isinstance(value, dict):
            transformed[key] = {
                prop_name: (
                    _to_chatgpt_strict_schema(prop_schema)
                    if isinstance(prop_schema, dict)
                    else prop_schema
                )
                for prop_name, prop_schema in value.items()
            }
            continue
        if key in {"items", "additionalProperties"} and isinstance(value, dict):
            transformed[key] = _to_chatgpt_strict_schema(value)
            continue
        if key in {"anyOf", "allOf", "oneOf"} and isinstance(value, list):
            transformed[key] = [
                _to_chatgpt_strict_schema(item) if isinstance(item, dict) else item
                for item in value
            ]
            continue
        transformed[key] = value

    properties = transformed.get("properties")
    if not isinstance(properties, dict):
        return transformed

    original_required = transformed.get("required")
    required = (
        [str(item) for item in original_required if isinstance(item, str)]
        if isinstance(original_required, list)
        else []
    )

    for prop_name, prop_schema in list(properties.items()):
        if prop_name in required or not isinstance(prop_schema, dict):
            continue
        properties[prop_name] = {
            "anyOf": [
                prop_schema,
                {"type": "null"},
            ]
        }

    transformed["required"] = list(properties.keys())
    return transformed
