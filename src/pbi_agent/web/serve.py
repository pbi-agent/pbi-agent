"""Custom web server that extends textual-serve with favicon support.

This module subclasses ``textual_serve.server.Server`` to:

1. Use a project-local HTML template (with a ``<link rel="icon">`` tag).
2. Serve a custom favicon at ``/favicon.ico``.

It is invoked as ``python -m pbi_agent.web.serve <command> [options]`` by
:func:`pbi_agent.cli._handle_web_command`.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from aiohttp import web
from textual_serve.server import Server

from pbi_agent.branding import startup_panel

_WEB_DIR = Path(__file__).resolve().parent
_TEMPLATES_DIR = str(_WEB_DIR / "templates")
_FAVICON_PATH = _WEB_DIR / "static" / "favicon.png"


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

    # ------------------------------------------------------------------
    async def _make_app(self) -> web.Application:  # type: ignore[override]
        app = await super()._make_app()
        app.router.add_get("/favicon.ico", self._handle_favicon)
        return app

    async def on_startup(self, app: web.Application) -> None:
        del app
        self.console.print(startup_panel(), highlight=False)
        self.console.print(f"  Serving on [bold]{self.public_url}[/bold]")
        self.console.print("[cyan]  Press Ctrl+C to quit[/cyan]")

    async def _handle_favicon(self, _request: web.Request) -> web.FileResponse:
        return web.FileResponse(
            _FAVICON_PATH,
            headers={"Content-Type": "image/png"},
        )


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
