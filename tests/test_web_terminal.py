from __future__ import annotations

import json
import os
import time
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from pbi_agent.web.api.routes.terminals import origin_allowed, router
from pbi_agent.web.terminal import TerminalManager, resolve_terminal_shell

pytestmark = pytest.mark.skipif(os.name == "nt", reason="PTY terminals are POSIX-only")


@pytest.fixture
def app(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("PBI_AGENT_SHELL_EXECUTABLE", "/bin/sh")
    monkeypatch.setenv("PS1", "$ ")
    monkeypatch.delenv("PBI_AGENT_SHELL_BOOTSTRAP", raising=False)
    application = FastAPI()
    application.state.terminals = TerminalManager(lambda: tmp_path)
    application.state.debug = False
    application.include_router(router)
    yield application
    application.state.terminals.shutdown()


def _read_until(ws, needle: bytes, timeout: float = 10.0) -> bytes:
    buffer = b""
    deadline = time.monotonic() + timeout
    while needle not in buffer:
        assert time.monotonic() < deadline, buffer
        message = ws.receive()
        if message.get("bytes"):
            buffer += message["bytes"]
    return buffer


@pytest.mark.parametrize(
    ("origin", "host", "debug", "expected"),
    [
        (None, "127.0.0.1:8000", False, True),
        ("http://127.0.0.1:8000", "127.0.0.1:8000", False, True),
        ("http://evil.example", "127.0.0.1:8000", False, False),
        ("http://localhost:5173", "127.0.0.1:8000", True, True),
        ("http://localhost:5173", "127.0.0.1:8000", False, False),
        ("http://localhost:8000", "localhost:8000", False, True),
        # DNS rebinding: attacker name resolves to loopback, Origin == Host.
        ("http://evil.example:8000", "evil.example:8000", False, False),
        (None, "evil.example:8000", False, False),
        ("http://[::1]:8000", "[::1]:8000", False, True),
    ],
)
def test_origin_allowed(origin, host, debug, expected) -> None:
    assert origin_allowed(origin, host, debug=debug) is expected


def test_origin_allowed_accepts_configured_public_host() -> None:
    assert origin_allowed(
        "https://agent.example",
        "agent.example",
        debug=False,
        public_url="https://agent.example",
    )


def test_manager_prunes_exited_detached_terminals(tmp_path) -> None:
    from pbi_agent.web.terminal import TerminalManager

    manager = TerminalManager(lambda: tmp_path)
    try:
        first = manager.get_or_create(None)
        first.write(b"exit\r")
        deadline = time.monotonic() + 5
        while not first.closed and time.monotonic() < deadline:
            time.sleep(0.05)
        assert first.closed
        manager.get_or_create(None)
        assert first.terminal_id not in manager._terminals
    finally:
        manager.shutdown()


def test_resolve_terminal_shell_prefers_agent_shell(monkeypatch) -> None:
    monkeypatch.setenv("PBI_AGENT_SHELL_EXECUTABLE", "/bin/bash")
    assert resolve_terminal_shell() == ["/bin/bash", "-i"]


def test_terminal_runs_commands_and_accepts_interactive_input(app, tmp_path) -> None:
    client = TestClient(
        app, base_url="http://127.0.0.1:8000", headers={"host": "127.0.0.1:8000"}
    )
    with client.websocket_connect("/api/terminals/ws?cols=100&rows=30") as ws:
        ready = json.loads(ws.receive_text())
        assert ready["type"] == "ready"
        ws.send_text(json.dumps({"type": "input", "data": "pwd\r"}))
        _read_until(ws, str(tmp_path).encode())
        # A prompt waiting for confirmation receives a later keystroke.
        ws.send_text(
            json.dumps({"type": "input", "data": 'read -r a; echo "got-$a"\r'})
        )
        time.sleep(0.2)
        ws.send_text(json.dumps({"type": "input", "data": "y\r"}))
        _read_until(ws, b"got-y")
        ws.send_text(json.dumps({"type": "resize", "cols": 120, "rows": 40}))


def test_terminal_reattach_replays_scrollback(app) -> None:
    client = TestClient(
        app, base_url="http://127.0.0.1:8000", headers={"host": "127.0.0.1:8000"}
    )
    with client.websocket_connect("/api/terminals/ws") as ws:
        terminal_id = json.loads(ws.receive_text())["terminal_id"]
        ws.send_text(json.dumps({"type": "input", "data": "echo marker-$((40+2))\r"}))
        _read_until(ws, b"marker-42")
    with client.websocket_connect(f"/api/terminals/ws?terminal_id={terminal_id}") as ws:
        assert json.loads(ws.receive_text())["terminal_id"] == terminal_id
        _read_until(ws, b"marker-42")


def test_terminal_rejects_cross_origin(app) -> None:
    client = TestClient(
        app, base_url="http://127.0.0.1:8000", headers={"host": "127.0.0.1:8000"}
    )
    from starlette.websockets import WebSocketDisconnect

    with pytest.raises(WebSocketDisconnect):
        with client.websocket_connect(
            "/api/terminals/ws", headers={"origin": "http://evil.example"}
        ) as ws:
            ws.receive_text()


def test_uvicorn_websocket_backend_is_installed() -> None:
    """The web terminal needs a WebSocket protocol for plain (non-[standard]) uvicorn."""
    import importlib.util

    from uvicorn.config import Config

    assert importlib.util.find_spec("websockets") is not None
    config = Config(app="pbi_agent.web.serve:app", ws="auto")
    config.load()
    assert config.ws_protocol_class is not None
