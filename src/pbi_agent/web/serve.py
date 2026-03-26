"""Custom web server that extends textual-serve with favicon support.

This module subclasses ``textual_serve.server.Server`` to:

1. Use a project-local HTML template (with a ``<link rel="icon">`` tag).
2. Serve a custom favicon at ``/favicon.ico``.

It is invoked as ``python -m pbi_agent.web.serve <command> [options]`` by
:func:`pbi_agent.cli._handle_web_command`.
"""

from __future__ import annotations

import argparse
import asyncio
import os
from contextlib import suppress
from pathlib import Path

from aiohttp import web
from aiohttp import WSMsgType
from textual_serve.app_service import AppService
from textual_serve.server import Server, log

from importlib.metadata import version

from pbi_agent.branding import startup_panel

_WEB_DIR = Path(__file__).resolve().parent
_TEMPLATES_DIR = str(_WEB_DIR / "templates")
_FAVICON_PATH = _WEB_DIR / "static" / "favicon.png"


class _PBIAppService(AppService):
    """App service that uses the repo-owned Textual web driver."""

    async def stop(self) -> None:
        """Stop the app process, forcing cleanup if shutdown is interrupted."""
        if self._task is None and self._process is None:
            return

        stop_task = asyncio.create_task(self._graceful_stop())
        try:
            await asyncio.shield(stop_task)
        except asyncio.CancelledError:
            stop_task.cancel()
            await self._force_stop()
            with suppress(asyncio.CancelledError):
                await stop_task
            raise

    async def _graceful_stop(self) -> None:
        if self._task is not None:
            await self._download_manager.cancel_app_downloads(
                app_service_id=self.app_service_id
            )
            await self.send_meta({"type": "quit"})
            await self._task
            self._task = None

        await self._close_stdin()
        await self._close_process_transport()

    async def _force_stop(self) -> None:
        await self._download_manager.cancel_app_downloads(
            app_service_id=self.app_service_id
        )

        task = self._task

        await self._close_stdin()
        await self._close_process_transport()

        if task is not None:
            task.cancel()
            with suppress(asyncio.CancelledError):
                await task

        self._task = None
        self._process = None

    async def _close_stdin(self) -> None:
        stdin = self._stdin
        self._stdin = None
        if stdin is not None:
            stdin.close()
            with suppress(Exception):
                await stdin.wait_closed()

    async def _close_process_transport(self) -> None:
        process = self._process
        if process is None:
            return

        transport = getattr(process, "_transport", None)
        if transport is not None and not transport.is_closing():
            transport.close()

        try:
            await asyncio.wait_for(process.wait(), timeout=1)
        except asyncio.TimeoutError:
            if process.returncode is None:
                with suppress(ProcessLookupError):
                    process.kill()
                with suppress(ProcessLookupError):
                    await process.wait()

        self._process = None

    def _build_environment(self, width: int = 80, height: int = 24) -> dict[str, str]:
        environment = dict(os.environ.copy())
        environment["TEXTUAL_DRIVER"] = "pbi_agent.web.textual_web_driver:PBIWebDriver"
        environment["TEXTUAL_FPS"] = "60"
        environment["TEXTUAL_COLOR_SYSTEM"] = "truecolor"
        environment["TERM_PROGRAM"] = "textual"
        environment["TERM_PROGRAM_VERSION"] = version("textual-serve")
        environment["COLUMNS"] = str(width)
        environment["ROWS"] = str(height)
        if self.debug:
            environment["TEXTUAL"] = "debug,devtools"
            environment["TEXTUAL_LOG"] = "textual.log"
        return environment

    async def paste(self, text: str) -> None:
        await self.send_meta({"type": "paste", "text": text})


class _FaviconServer(Server):
    """A ``textual-serve`` server with custom branding, template, and favicon."""

    def __init__(
        self,
        command: str,
        host: str = "localhost",
        port: int = 8000,
        title: str | None = None,
        public_url: str | None = None,
    ) -> None:
        super().__init__(
            command,
            host=host,
            port=port,
            title=title,
            public_url=public_url,
            templates_path=_TEMPLATES_DIR,
        )
        self._app_services: set[_PBIAppService] = set()

    # ------------------------------------------------------------------
    async def _make_app(self) -> web.Application:  # type: ignore[override]
        app = await super()._make_app()
        app.router.add_get("/favicon.ico", self._handle_favicon)
        app.router.add_get("/logo.png", self._handle_logo)
        return app

    async def on_startup(self, app: web.Application) -> None:
        del app
        self.console.print(startup_panel(), highlight=False)
        self.console.print(f"  Serving on [bold]{self.public_url}[/bold]")
        self.console.print("[cyan]  Press Ctrl+C to quit[/cyan]")

    async def on_shutdown(self, app: web.Application) -> None:
        del app
        await asyncio.gather(
            *(asyncio.shield(app_service.stop()) for app_service in self._app_services),
            return_exceptions=True,
        )

    async def _handle_favicon(self, _request: web.Request) -> web.FileResponse:
        return web.FileResponse(
            _FAVICON_PATH,
            headers={"Content-Type": "image/png"},
        )

    async def _handle_logo(self, _request: web.Request) -> web.FileResponse:
        return web.FileResponse(
            _FAVICON_PATH,
            headers={
                "Content-Type": "image/png",
                "Cache-Control": "public, max-age=86400",
            },
        )

    async def _process_messages(
        self, websocket: web.WebSocketResponse, app_service: _PBIAppService
    ) -> None:
        text_type = WSMsgType.TEXT

        async for message in websocket:
            if message.type != text_type:
                continue
            envelope = message.json()
            assert isinstance(envelope, list)
            type_ = envelope[0]
            if type_ == "stdin":
                data = envelope[1]
                await app_service.send_bytes(data.encode("utf-8"))
            elif type_ == "paste":
                data = envelope[1]
                if isinstance(data, str):
                    await app_service.paste(data)
            elif type_ == "resize":
                data = envelope[1]
                await app_service.set_terminal_size(data["width"], data["height"])
            elif type_ == "ping":
                data = envelope[1]
                await websocket.send_json(["pong", data])
            elif type_ == "blur":
                await app_service.blur()
            elif type_ == "focus":
                await app_service.focus()

    async def handle_websocket(self, request: web.Request) -> web.WebSocketResponse:
        websocket = web.WebSocketResponse(heartbeat=15)

        width = _to_int(request.query.get("width", "80"), 80)
        height = _to_int(request.query.get("height", "24"), 24)

        app_service: _PBIAppService | None = None
        try:
            await websocket.prepare(request)
            app_service = _PBIAppService(
                self.command,
                write_bytes=websocket.send_bytes,
                write_str=websocket.send_str,
                close=websocket.close,
                download_manager=self.download_manager,
                debug=self.debug,
            )
            self._app_services.add(app_service)
            await app_service.start(width, height)
            try:
                await self._process_messages(websocket, app_service)
            finally:
                await app_service.stop()

        except asyncio.CancelledError:
            await websocket.close()

        except Exception as error:
            log.exception(error)

        finally:
            if app_service is not None:
                self._app_services.discard(app_service)
                await app_service.stop()

        return websocket


def _to_int(value: str, default: int) -> int:
    try:
        return int(value)
    except ValueError:
        return default


# -- CLI entry-point ----------------------------------------------------


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="pbi-agent web server")
    parser.add_argument("command", help="Shell command to run the Textual app")
    parser.add_argument("--host", default="localhost")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--title", default=None)
    parser.add_argument("--url", default=None, dest="public_url")
    parser.add_argument("--dev", action="store_true", default=False)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    args = _parse_args(argv)
    server = _FaviconServer(
        command=args.command,
        host=args.host,
        port=args.port,
        title=args.title,
        public_url=args.public_url,
    )
    server.serve(debug=args.dev)


if __name__ == "__main__":
    main()
