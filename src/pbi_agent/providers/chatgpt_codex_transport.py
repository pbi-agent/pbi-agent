from __future__ import annotations

import base64
import json
import os
import socket
import ssl
import struct
import time
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlparse

CHATGPT_TURN_STATE_HEADER = "x-codex-turn-state"
WEBSOCKET_CONNECTION_LIMIT_REACHED_CODE = "websocket_connection_limit_reached"
PREVIOUS_RESPONSE_NOT_FOUND_CODE = "previous_response_not_found"
_RETRYABLE_WEBSOCKET_ERROR_MARKERS = {
    "api_error",
    "internal",
    "server_error",
    "server_is_overloaded",
    "service_unavailable",
    "unavailable",
    "overloaded_error",
}

_WS_OPCODE_CONTINUATION = 0x0
_WS_OPCODE_TEXT = 0x1
_WS_OPCODE_BINARY = 0x2
_WS_OPCODE_CLOSE = 0x8
_WS_OPCODE_PING = 0x9
_WS_OPCODE_PONG = 0xA
_WS_WRITE_TIMEOUT_SECS = 30.0
_WS_RESPONSE_START_TIMEOUT_SECS = 30.0
_WS_CLOSE_TIMEOUT_SECS = 1.0


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
        connect_timeout: float,
        idle_timeout: float,
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

        try:
            raw_sock = socket.create_connection((host, port), timeout=connect_timeout)
        except (OSError, TimeoutError, socket.timeout) as exc:
            raise ChatGPTCodexWebSocketError(
                f"WebSocket connect failed: {exc}", retryable=True
            ) from exc
        try:
            if parsed.scheme == "wss":
                context = ssl.create_default_context()
                sock = context.wrap_socket(raw_sock, server_hostname=host)
            else:
                sock = raw_sock
            sock.settimeout(idle_timeout)
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
            try:
                sock.sendall(request.encode("utf-8"))
                status, response_headers, body = _read_http_upgrade_response(sock)
            except (OSError, TimeoutError, socket.timeout) as exc:
                raise ChatGPTCodexWebSocketError(
                    f"WebSocket upgrade failed: {exc}", retryable=True
                ) from exc
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
        except ChatGPTCodexWebSocketError:
            raw_sock.close()
            raise
        except (OSError, TimeoutError, socket.timeout) as exc:
            raw_sock.close()
            raise ChatGPTCodexWebSocketError(
                f"WebSocket connect failed: {exc}", retryable=True
            ) from exc
        except Exception:
            raw_sock.close()
            raise

    def send_response_create(
        self,
        request_body: dict[str, Any],
        *,
        idle_timeout: float,
        request_timeout: float,
    ) -> list[dict[str, Any]]:
        if self.closed:
            raise ChatGPTCodexWebSocketError(
                "websocket connection is closed", retryable=True
            )
        deadline = time.monotonic() + request_timeout
        request_payload = {"type": "response.create", **request_body}
        try:
            self._set_phase_timeout(deadline, min(idle_timeout, _WS_WRITE_TIMEOUT_SECS))
            self._send_text(json.dumps(request_payload, separators=(",", ":")))
        except (OSError, TimeoutError, socket.timeout) as exc:
            self.close()
            raise ChatGPTCodexWebSocketError(
                f"WebSocket send failed: {exc}", retryable=True
            ) from exc
        events: list[dict[str, Any]] = []
        while True:
            try:
                read_timeout = (
                    idle_timeout
                    if events
                    else min(idle_timeout, _WS_RESPONSE_START_TIMEOUT_SECS)
                )
                self._set_phase_timeout(deadline, read_timeout)
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
                    self._set_phase_timeout(
                        deadline, min(idle_timeout, _WS_WRITE_TIMEOUT_SECS)
                    )
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

    def _set_phase_timeout(self, deadline: float, idle_timeout: float) -> None:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            self.close()
            raise ChatGPTCodexWebSocketError(
                "WebSocket request timed out", retryable=True
            )
        self._sock.settimeout(min(idle_timeout, remaining))

    def close(self) -> None:
        if self.closed:
            return
        self.closed = True
        try:
            self._sock.settimeout(_WS_CLOSE_TIMEOUT_SECS)
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
    error_type = _error_type(error.payload)
    message = _error_message(error.payload) or "WebSocket error"
    connection_limit = code == WEBSOCKET_CONNECTION_LIMIT_REACHED_CODE
    previous_response_not_found = code == PREVIOUS_RESPONSE_NOT_FOUND_CODE
    # Some ChatGPT websocket error events carry no HTTP status but do carry a
    # transient nested error marker, e.g. {"error": {"type": "server_error"}}.
    retryable_error_marker = error.status is None and (
        _is_retryable_error_marker(code) or _is_retryable_error_marker(error_type)
    )
    return ChatGPTCodexWebSocketError(
        message,
        status=error.status,
        payload=error.payload,
        retryable=(
            connection_limit
            or previous_response_not_found
            or retryable_error_marker
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


def _is_retryable_error_marker(value: str | None) -> bool:
    return (
        value is not None
        and value.strip().lower() in _RETRYABLE_WEBSOCKET_ERROR_MARKERS
    )


def _error_code(payload: dict[str, Any]) -> str | None:
    error = payload.get("error")
    if isinstance(error, dict):
        code = error.get("code")
        if isinstance(code, str):
            return code
    return None


def _error_type(payload: dict[str, Any]) -> str | None:
    error = payload.get("error")
    if isinstance(error, dict):
        error_type = error.get("type")
        if isinstance(error_type, str):
            return error_type
    return None


def _error_message(payload: dict[str, Any]) -> str | None:
    error = payload.get("error")
    if isinstance(error, dict):
        message = error.get("message")
        if isinstance(message, str):
            return message
    return None
