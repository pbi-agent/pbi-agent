from __future__ import annotations

import asyncio
import ipaddress
import json
from typing import Any, cast
from urllib.parse import urlsplit

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from pbi_agent.web.terminal import TerminalManager

router = APIRouter(prefix="/api/terminals", tags=["terminals"])

_DEV_ORIGINS = {
    "http://127.0.0.1:5173",
    "http://localhost:5173",
    "http://127.0.0.1:4173",
    "http://localhost:4173",
}


def host_trusted(host: str | None, *, public_url: str | None = None) -> bool:
    """Accept only Host values a DNS-rebinding attacker cannot control.

    IP literals and ``localhost`` cannot be rebound; any other name must match
    the explicitly configured public URL.
    """
    if not host:
        return False
    hostname = urlsplit(f"//{host}").hostname
    if not hostname:
        return False
    if hostname == "localhost" or hostname.endswith(".localhost"):
        return True
    try:
        ipaddress.ip_address(hostname)
        return True
    except ValueError:
        pass
    if public_url:
        return urlsplit(public_url).hostname == hostname
    return False


def origin_allowed(
    origin: str | None,
    host: str | None,
    *,
    debug: bool,
    public_url: str | None = None,
) -> bool:
    """Reject cross-site and DNS-rebound WebSocket connections (shell access)."""
    if not host_trusted(host, public_url=public_url):
        return False
    if not origin:
        return True  # non-browser clients do not send Origin
    if debug and origin in _DEV_ORIGINS:
        return True
    return urlsplit(origin).netloc == host


def _clamp(raw: str | None, default: int) -> int:
    try:
        value = int(raw) if raw is not None else default
    except ValueError:
        return default
    return min(max(value, 1), 1000)


@router.websocket("/ws")
async def terminal_socket(websocket: WebSocket) -> None:
    app = websocket.app
    if not origin_allowed(
        websocket.headers.get("origin"),
        websocket.headers.get("host"),
        debug=bool(getattr(app.state, "debug", False)),
        public_url=getattr(app.state, "public_url", None),
    ):
        await websocket.close(code=1008)
        return
    manager = cast(TerminalManager, app.state.terminals)
    params = websocket.query_params
    await websocket.accept()
    try:
        terminal = manager.get_or_create(
            params.get("terminal_id") or None,
            cols=_clamp(params.get("cols"), 80),
            rows=_clamp(params.get("rows"), 24),
        )
    except OSError as exc:
        await websocket.send_text(json.dumps({"type": "error", "message": str(exc)}))
        await websocket.close(code=1011)
        return

    loop = asyncio.get_running_loop()
    queue: asyncio.Queue[bytes | dict[str, Any]] = asyncio.Queue()

    def on_output(data: bytes) -> None:
        loop.call_soon_threadsafe(queue.put_nowait, data)

    def on_exit(code: int | None) -> None:
        loop.call_soon_threadsafe(queue.put_nowait, {"type": "exit", "code": code})

    scrollback = terminal.attach(on_output, on_exit)
    await websocket.send_text(
        json.dumps({"type": "ready", "terminal_id": terminal.terminal_id})
    )
    if scrollback:
        await websocket.send_bytes(scrollback)
    if terminal.closed:
        queue.put_nowait({"type": "exit", "code": terminal.exit_code})

    async def pump_output() -> None:
        while True:
            item = await queue.get()
            if isinstance(item, bytes):
                await websocket.send_bytes(item)
            else:
                await websocket.send_text(json.dumps(item))

    pump = asyncio.create_task(pump_output())
    try:
        while True:
            message = await websocket.receive_text()
            try:
                payload = json.loads(message)
            except json.JSONDecodeError:
                continue
            if not isinstance(payload, dict):
                continue
            payload = cast(dict[str, Any], payload)
            kind = payload.get("type")
            if kind == "input" and isinstance(payload.get("data"), str):
                await asyncio.to_thread(terminal.write, payload["data"].encode())
            elif kind == "resize":
                terminal.resize(
                    _clamp(str(payload.get("cols")), 80),
                    _clamp(str(payload.get("rows")), 24),
                )
            elif kind == "close":
                manager.close(terminal.terminal_id)
                break
    except (WebSocketDisconnect, RuntimeError):
        pass
    finally:
        terminal.detach(on_output, on_exit)
        pump.cancel()
