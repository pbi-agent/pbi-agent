from __future__ import annotations

import asyncio
from io import StringIO
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from rich.console import Console
from aiohttp import WSMsgType

from pbi_agent.branding import PBI_AGENT_NAME, PBI_AGENT_TAGLINE
from pbi_agent.web.serve import _FaviconServer, _PBIAppService


def test_favicon_server_startup_uses_pbi_agent_banner() -> None:
    server = _FaviconServer(command="uv run pbi-agent web")
    output = StringIO()
    server.console = Console(file=output, width=80, highlight=False)

    asyncio.run(server.on_startup(Mock()))

    rendered = output.getvalue()
    assert PBI_AGENT_NAME in rendered
    assert PBI_AGENT_TAGLINE in rendered
    assert "textual-serve" not in rendered
    assert server.public_url in rendered


def test_custom_template_installs_terminal_input_bridges() -> None:
    template = Path("src/pbi_agent/web/templates/app_index.html").read_text(
        encoding="utf-8"
    )

    assert "installTerminalInputBridges" in template
    assert "\\u001b[13;2u" in template
    assert "xterm-helper-textarea" in template
    assert "navigator.clipboard.readText" in template
    assert 'document.addEventListener(\n          "paste"' in template


def test_pbi_app_service_uses_repo_owned_web_driver() -> None:
    app_service = _PBIAppService(
        command="uv run pbi-agent web",
        write_bytes=AsyncMock(),
        write_str=AsyncMock(),
        close=AsyncMock(),
        download_manager=Mock(),
    )

    environment = app_service._build_environment(100, 40)

    assert (
        environment["TEXTUAL_DRIVER"] == "pbi_agent.web.textual_web_driver:PBIWebDriver"
    )
    assert environment["COLUMNS"] == "100"
    assert environment["ROWS"] == "40"


def test_favicon_server_process_messages_routes_paste_events() -> None:
    server = _FaviconServer(command="uv run pbi-agent web")
    websocket = _FakeWebSocket([_FakeMessage(["paste", "line one\nline two"])])
    app_service = SimpleNamespace(
        send_bytes=AsyncMock(),
        paste=AsyncMock(),
        set_terminal_size=AsyncMock(),
        blur=AsyncMock(),
        focus=AsyncMock(),
    )

    asyncio.run(server._process_messages(websocket, app_service))

    app_service.paste.assert_awaited_once_with("line one\nline two")
    app_service.send_bytes.assert_not_awaited()


def test_favicon_server_shutdown_stops_live_app_services() -> None:
    server = _FaviconServer(command="uv run pbi-agent web")
    app_service_one = _FakeTrackedAppService()
    app_service_two = _FakeTrackedAppService()
    server._app_services = {app_service_one, app_service_two}

    asyncio.run(server.on_shutdown(Mock()))

    app_service_one.stop.assert_awaited_once()
    app_service_two.stop.assert_awaited_once()


def test_pbi_app_service_force_stops_process_when_shutdown_is_cancelled() -> None:
    async def exercise_stop() -> None:
        download_manager = SimpleNamespace(cancel_app_downloads=AsyncMock())
        app_service = _PBIAppService(
            command="uv run pbi-agent web",
            write_bytes=AsyncMock(),
            write_str=AsyncMock(),
            close=AsyncMock(),
            download_manager=download_manager,
        )
        app_service.send_meta = AsyncMock(return_value=True)

        stop_blocker: asyncio.Future[None] = asyncio.Future()
        app_service._task = stop_blocker
        stdin = _FakeStreamWriter()
        process = _FakeProcess()
        app_service._stdin = stdin
        app_service._process = process

        stop_task = asyncio.create_task(app_service.stop())
        await asyncio.sleep(0)
        stop_task.cancel()

        with pytest.raises(asyncio.CancelledError):
            await stop_task

        download_manager.cancel_app_downloads.assert_awaited()
        assert app_service._stdin is None
        assert app_service._task is None
        assert app_service._process is None
        assert stop_blocker.cancelled()
        assert stdin.closed is True
        assert process._transport.closed is True

    asyncio.run(exercise_stop())


class _FakeMessage:
    def __init__(self, envelope: list[object]) -> None:
        self.type = WSMsgType.TEXT
        self._envelope = envelope

    def json(self) -> list[object]:
        return self._envelope


class _FakeWebSocket:
    def __init__(self, messages: list[_FakeMessage]) -> None:
        self._messages = iter(messages)
        self.send_json = AsyncMock()

    def __aiter__(self) -> "_FakeWebSocket":
        return self

    async def __anext__(self) -> _FakeMessage:
        try:
            return next(self._messages)
        except StopIteration as exc:
            raise StopAsyncIteration from exc


class _FakeStreamWriter:
    def __init__(self) -> None:
        self.closed = False
        self.wait_closed = AsyncMock()

    def close(self) -> None:
        self.closed = True


class _FakeProcess:
    def __init__(self) -> None:
        self.returncode: int | None = None
        self._transport = _FakeTransport(self)
        self.terminate = Mock(side_effect=self._terminate)
        self.kill = Mock(side_effect=self._kill)
        self.wait = AsyncMock(side_effect=self._wait)

    def _terminate(self) -> None:
        self.returncode = 0

    def _kill(self) -> None:
        self.returncode = -9

    async def _wait(self) -> int:
        return 0 if self.returncode is None else self.returncode


class _FakeTrackedAppService:
    def __init__(self) -> None:
        self.stop = AsyncMock()


class _FakeTransport:
    def __init__(self, process: _FakeProcess) -> None:
        self._process = process
        self.closed = False

    def close(self) -> None:
        self.closed = True
        if self._process.returncode is None:
            self._process.returncode = 0

    def is_closing(self) -> bool:
        return self.closed
