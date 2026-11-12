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

posix_only = pytest.mark.skipif(os.name == "nt", reason="POSIX shell syntax")
windows_only = pytest.mark.skipif(os.name != "nt", reason="ConPTY is Windows-only")


@pytest.fixture
def app(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    if os.name == "nt":
        monkeypatch.setenv("PBI_AGENT_SHELL_EXECUTABLE", "cmd.exe")
    else:
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


@posix_only
def test_resolve_terminal_shell_prefers_agent_shell(monkeypatch) -> None:
    monkeypatch.setenv("PBI_AGENT_SHELL_EXECUTABLE", "/bin/bash")
    assert resolve_terminal_shell() == ["/bin/bash", "-i"]


@posix_only
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


@posix_only
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


@windows_only
def test_windows_terminal_echoes_typing_and_accepts_interactive_input(app) -> None:
    client = TestClient(
        app, base_url="http://127.0.0.1:8000", headers={"host": "127.0.0.1:8000"}
    )
    with client.websocket_connect("/api/terminals/ws?cols=100&rows=30") as ws:
        terminal_id = json.loads(ws.receive_text())["terminal_id"]
        # Keystrokes are echoed before Enter: this is what a pipe-backed
        # shell never did, leaving the terminal apparently dead.
        ws.send_text(json.dumps({"type": "input", "data": "echo typed-"}))
        _read_until(ws, b"echo typed-")
        ws.send_text(json.dumps({"type": "input", "data": "%OS%\r"}))
        _read_until(ws, b"typed-Windows_NT")
        # A prompt waiting for confirmation receives a later keystroke.
        ws.send_text(json.dumps({"type": "input", "data": "set /p a=confirm? \r"}))
        _read_until(ws, b"confirm? ")
        ws.send_text(json.dumps({"type": "input", "data": "y\r"}))
        ws.send_text(json.dumps({"type": "input", "data": "echo got-%a%\r"}))
        _read_until(ws, b"got-y")
        ws.send_text(json.dumps({"type": "resize", "cols": 120, "rows": 40}))
    with client.websocket_connect(f"/api/terminals/ws?terminal_id={terminal_id}") as ws:
        assert json.loads(ws.receive_text())["terminal_id"] == terminal_id
        _read_until(ws, b"got-y")


@windows_only
def test_windows_scrollback_drops_conpty_queries(app) -> None:
    client = TestClient(
        app, base_url="http://127.0.0.1:8000", headers={"host": "127.0.0.1:8000"}
    )
    with client.websocket_connect("/api/terminals/ws") as ws:
        terminal_id = json.loads(ws.receive_text())["terminal_id"]
        ws.send_text(json.dumps({"type": "input", "data": "echo marker-%OS%\r"}))
        _read_until(ws, b"marker-Windows_NT")
    with client.websocket_connect(f"/api/terminals/ws?terminal_id={terminal_id}") as ws:
        ws.receive_text()
        replay = _read_until(ws, b"marker-Windows_NT")
    # A replayed device-attributes query would make xterm type its answer.
    assert b"\x1b[c" not in replay
    assert b"0011Ignore" not in replay


@windows_only
def test_windows_close_kills_processes_started_in_terminal(tmp_path) -> None:
    import subprocess

    def children(pid: int) -> str:
        return subprocess.run(
            [
                "powershell",
                "-NoProfile",
                "-Command",
                f'(Get-CimInstance Win32_Process -Filter "ParentProcessId={pid}").Name',
            ],
            capture_output=True,
            text=True,
            check=False,
        ).stdout

    manager = TerminalManager(lambda: tmp_path)
    try:
        terminal = manager.get_or_create(None)
        assert terminal._conpty is not None
        shell_pid = terminal._conpty.pid
        assert shell_pid is not None
        terminal.write(b"ping -t 127.0.0.1\r")
        deadline = time.monotonic() + 15
        while "PING" not in children(shell_pid).upper():
            assert time.monotonic() < deadline
            time.sleep(0.2)
        assert manager.close(terminal.terminal_id)
        deadline = time.monotonic() + 10
        while not terminal.closed and time.monotonic() < deadline:
            time.sleep(0.05)
        assert terminal.closed
        assert "PING" not in children(shell_pid).upper()
    finally:
        manager.shutdown()


@windows_only
def test_resolve_terminal_shell_windows(monkeypatch) -> None:
    monkeypatch.setenv("PBI_AGENT_SHELL_EXECUTABLE", r"C:\Git\bin\bash.exe")
    assert resolve_terminal_shell() == [r"C:\Git\bin\bash.exe", "-i"]
    monkeypatch.setenv("PBI_AGENT_SHELL_EXECUTABLE", "cmd.exe")
    assert resolve_terminal_shell() == ["cmd.exe"]


def test_terminal_reports_unstartable_shell(app, monkeypatch) -> None:
    monkeypatch.setenv("PBI_AGENT_SHELL_EXECUTABLE", "no-such-shell-xyz")
    client = TestClient(
        app, base_url="http://127.0.0.1:8000", headers={"host": "127.0.0.1:8000"}
    )
    with client.websocket_connect("/api/terminals/ws") as ws:
        message = json.loads(ws.receive_text())
    assert message["type"] == "error"
    assert "no-such-shell-xyz" in message["message"]


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
