from __future__ import annotations

import argparse
import asyncio
import threading
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles

from pbi_agent.config import ResolvedRuntime, Settings
from pbi_agent.web.api import (
    board_router,
    config_router,
    events_router,
    live_sessions_router,
    system_router,
    tasks_router,
)
from pbi_agent.web.session_manager import APP_EVENT_STREAM_ID, WebSessionManager

WEB_DIR = Path(__file__).resolve().parent
APP_STATIC_DIR = WEB_DIR / "static" / "app"
FAVICON_PATH = WEB_DIR / "static" / "favicon.png"


def create_app(
    settings: Settings | ResolvedRuntime,
    *,
    runtime_args: argparse.Namespace | None = None,
    debug: bool = False,
    title: str | None = None,
    public_url: str | None = None,
) -> FastAPI:
    manager = WebSessionManager(settings, runtime_args=runtime_args)

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        threading.Thread(
            target=manager.warm_file_mentions_cache,
            daemon=True,
            name="pbi-agent-web-mention-cache",
        ).start()
        try:
            yield
        except asyncio.CancelledError:
            pass
        finally:
            manager.shutdown()

    app = FastAPI(
        title=title or "PBI Agent",
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
        lifespan=lifespan,
    )
    app.state.manager = manager
    app.state.public_url = public_url
    app.state.debug = debug

    if debug:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=[
                "http://127.0.0.1:5173",
                "http://localhost:5173",
                "http://127.0.0.1:4173",
                "http://localhost:4173",
            ],
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )

    assets_dir = APP_STATIC_DIR / "assets"
    if assets_dir.exists():
        app.mount("/assets", StaticFiles(directory=str(assets_dir)), name="assets")

    @app.get("/favicon.ico")
    def favicon_ico() -> FileResponse:
        return FileResponse(FAVICON_PATH, media_type="image/png")

    @app.get("/favicon.png")
    def favicon_png() -> FileResponse:
        return FileResponse(FAVICON_PATH, media_type="image/png")

    @app.get("/logo.png")
    def logo() -> FileResponse:
        return FileResponse(FAVICON_PATH, media_type="image/png")

    app.include_router(system_router)
    app.include_router(config_router)
    app.include_router(live_sessions_router)
    app.include_router(tasks_router)
    app.include_router(board_router)
    app.include_router(events_router)

    @app.get("/", response_class=HTMLResponse)
    def index() -> Response:
        return spa_index_response(title or "PBI Agent")

    @app.get("/{full_path:path}", response_class=HTMLResponse)
    def spa_fallback(full_path: str) -> Response:
        if full_path.startswith("api/"):
            raise HTTPException(status_code=404, detail="Not found.")
        if full_path == APP_EVENT_STREAM_ID:
            raise HTTPException(status_code=404, detail="Not found.")
        return spa_index_response(title or "PBI Agent")

    return app


def spa_index_response(title: str) -> Response:
    index_path = APP_STATIC_DIR / "index.html"
    if index_path.exists():
        return FileResponse(index_path)
    return HTMLResponse(
        (
            "<!doctype html><html><head><meta charset='utf-8'>"
            f"<title>{title}</title>"
            "<meta name='viewport' content='width=device-width, initial-scale=1'>"
            "<style>body{font-family:system-ui,sans-serif;background:#0b1020;"
            "color:#eef2ff;padding:40px}code{background:#111827;padding:2px 6px;"
            "border-radius:6px}</style></head><body>"
            "<h1>PBI Agent Web UI assets are missing.</h1>"
            "<p>Run <code>bun install</code> then <code>bun run web:build</code> "
            "to build the bundled frontend.</p></body></html>"
        )
    )
