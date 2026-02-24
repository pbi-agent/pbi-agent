from __future__ import annotations

import json
from typing import Any

from websocket import WebSocket, create_connection


class WebSocketClientError(RuntimeError):
    """Raised when websocket interactions fail."""


class ResponsesWebSocketClient:
    def __init__(self, ws_url: str, api_key: str):
        self._ws_url = ws_url
        self._api_key = api_key
        self._ws: WebSocket | None = None

    def connect(self) -> None:
        if self._ws is not None:
            return
        try:
            self._ws = create_connection(
                self._ws_url,
                header=[f"Authorization: Bearer {self._api_key}"],
            )
        except Exception as exc:  # pragma: no cover - network-specific
            raise WebSocketClientError(f"Failed to connect websocket: {exc}") from exc

    def close(self) -> None:
        if self._ws is None:
            return
        self._ws.close()
        self._ws = None

    def send_json(self, payload: dict[str, Any]) -> None:
        if self._ws is None:
            raise WebSocketClientError("WebSocket is not connected.")
        self._ws.send(json.dumps(payload))

    def recv_json(self) -> dict[str, Any]:
        if self._ws is None:
            raise WebSocketClientError("WebSocket is not connected.")
        try:
            return json.loads(self._ws.recv())
        except Exception as exc:  # pragma: no cover - network-specific
            raise WebSocketClientError(f"Failed to receive websocket event: {exc}") from exc

    def __enter__(self) -> "ResponsesWebSocketClient":
        self.connect()
        return self

    def __exit__(self, *_: object) -> None:
        self.close()
