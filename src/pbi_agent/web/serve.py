from __future__ import annotations

import argparse
import asyncio
import contextlib
import signal
import threading
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated, Any, Literal, cast

from fastapi import (
    APIRouter,
    Depends,
    File,
    FastAPI,
    HTTPException,
    Path as FastAPIPath,
    Query,
    Request,
    Response,
    UploadFile,
    WebSocket,
    WebSocketDisconnect,
)
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, StringConstraints
from rich.console import Console
import uvicorn
import uvicorn.server

from pbi_agent.config import ConfigError
from pbi_agent.branding import startup_panel
from pbi_agent.config import Settings, resolve_settings
from pbi_agent.providers.capabilities import provider_supports_images
from pbi_agent.web.command_registry import search_slash_commands
from pbi_agent.web.input_mentions import expand_input_mentions
from pbi_agent.web.session_manager import APP_EVENT_STREAM_ID, WebSessionManager
from pbi_agent.web.uploads import load_uploaded_image_record, uploaded_image_path

_WEB_DIR = Path(__file__).resolve().parent
_APP_STATIC_DIR = _WEB_DIR / "static" / "app"
_FAVICON_PATH = _WEB_DIR / "static" / "favicon.png"

BoardStage = Literal["backlog", "plan", "processing", "review"]
RunStatus = Literal["idle", "running", "completed", "failed"]
SessionStatus = Literal["starting", "running", "ended"]
NonEmptyString = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
LimitQuery = Annotated[int, Query(ge=1, le=200)]
MentionQuery = Annotated[str, Query(max_length=200)]
MentionLimitQuery = Annotated[int, Query(ge=1, le=50)]
LiveSessionIdPath = Annotated[
    str,
    FastAPIPath(min_length=1, description="The live chat session identifier."),
]
TaskIdPath = Annotated[
    str,
    FastAPIPath(min_length=1, description="The task identifier."),
]
StreamIdPath = Annotated[
    str,
    FastAPIPath(min_length=1, description="The event stream identifier."),
]
SessionIdPath = Annotated[
    str,
    FastAPIPath(min_length=1, description="The saved session identifier."),
]
UploadIdPath = Annotated[
    str,
    FastAPIPath(min_length=1, description="The uploaded image identifier."),
]


class CreateChatSessionRequest(BaseModel):
    resume_session_id: str | None = None
    live_session_id: str | None = None


class ChatInputRequest(BaseModel):
    text: str = ""
    file_paths: list[str] = Field(default_factory=list)
    image_paths: list[str] = Field(default_factory=list)
    image_upload_ids: list[str] = Field(default_factory=list)


class ExpandInputRequest(BaseModel):
    text: str = ""


class FileMentionItemModel(BaseModel):
    path: str
    kind: Literal["file", "image"]


class FileMentionSearchResponse(BaseModel):
    items: list[FileMentionItemModel]


class SlashCommandItemModel(BaseModel):
    name: str
    description: str


class SlashCommandSearchResponse(BaseModel):
    items: list[SlashCommandItemModel]


class ExpandInputResponse(BaseModel):
    text: str
    file_paths: list[str] = Field(default_factory=list)
    image_paths: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class CreateTaskRequest(BaseModel):
    title: NonEmptyString
    prompt: NonEmptyString
    stage: BoardStage = "backlog"
    project_dir: str = "."
    session_id: str | None = None


class UpdateTaskRequest(BaseModel):
    title: NonEmptyString | None = None
    prompt: NonEmptyString | None = None
    stage: BoardStage | None = None
    position: Annotated[int, Field(ge=0)] | None = None
    project_dir: str | None = None
    session_id: str | None = None
    clear_session_id: bool = False


class SessionRecordModel(BaseModel):
    session_id: str
    directory: str
    provider: str
    model: str
    previous_id: str | None
    title: str
    total_tokens: int
    input_tokens: int
    output_tokens: int
    cost_usd: float
    created_at: str
    updated_at: str


class LiveSessionModel(BaseModel):
    live_session_id: str
    resume_session_id: str | None
    created_at: str
    status: SessionStatus
    exit_code: int | None
    fatal_error: str | None
    ended_at: str | None


class ImageAttachmentModel(BaseModel):
    upload_id: str
    name: str
    mime_type: str
    byte_count: int
    preview_url: str


class ImageUploadResponse(BaseModel):
    uploads: list[ImageAttachmentModel]


class TaskRecordModel(BaseModel):
    task_id: str
    directory: str
    title: str
    prompt: str
    stage: BoardStage
    position: int
    project_dir: str
    session_id: str | None
    run_status: RunStatus
    last_result_summary: str
    created_at: str
    updated_at: str
    last_run_started_at: str | None
    last_run_finished_at: str | None


class BootstrapResponse(BaseModel):
    workspace_root: str
    provider: str
    model: str
    reasoning_effort: str
    supports_image_inputs: bool
    sessions: list[SessionRecordModel]
    tasks: list[TaskRecordModel]
    live_sessions: list[LiveSessionModel]
    board_stages: list[BoardStage]


class SessionsResponse(BaseModel):
    sessions: list[SessionRecordModel]


class ChatSessionResponse(BaseModel):
    session: LiveSessionModel


class TasksResponse(BaseModel):
    tasks: list[TaskRecordModel]


class TaskResponse(BaseModel):
    task: TaskRecordModel


system_router = APIRouter(prefix="/api", tags=["system"])
chat_router = APIRouter(prefix="/api/chat", tags=["chat"])
tasks_router = APIRouter(prefix="/api/tasks", tags=["tasks"])
events_router = APIRouter(prefix="/api/events", tags=["events"])


def _get_session_manager(request: Request) -> WebSessionManager:
    return cast(WebSessionManager, request.app.state.manager)


SessionManagerDep = Annotated[WebSessionManager, Depends(_get_session_manager)]


def _model_from_payload[T: BaseModel](model_type: type[T], payload: Any) -> T:
    return model_type.model_validate(payload)


def _bad_request(detail: str) -> HTTPException:
    return HTTPException(status_code=400, detail=detail)


def _not_found(detail: str) -> HTTPException:
    return HTTPException(status_code=404, detail=detail)


@system_router.get("/bootstrap", response_model=BootstrapResponse)
def bootstrap(manager: SessionManagerDep) -> BootstrapResponse:
    return _model_from_payload(BootstrapResponse, manager.bootstrap())


@system_router.get("/sessions", response_model=SessionsResponse)
def list_sessions(
    manager: SessionManagerDep,
    limit: LimitQuery = 30,
) -> SessionsResponse:
    return SessionsResponse(
        sessions=[
            _model_from_payload(SessionRecordModel, item)
            for item in manager.list_sessions(limit=limit)
        ]
    )


@system_router.delete("/sessions/{session_id}", status_code=204)
def delete_session(
    session_id: SessionIdPath,
    manager: SessionManagerDep,
) -> Response:
    try:
        manager.delete_session(session_id)
    except KeyError as exc:
        raise _not_found("Session not found.") from exc
    except Exception as exc:
        raise _bad_request(str(exc)) from exc
    return Response(status_code=204)


@system_router.get("/files/search", response_model=FileMentionSearchResponse)
def search_workspace_files(
    manager: SessionManagerDep,
    q: MentionQuery = "",
    limit: MentionLimitQuery = 8,
) -> FileMentionSearchResponse:
    return FileMentionSearchResponse(
        items=[
            FileMentionItemModel(path=item.path, kind=item.kind)
            for item in manager.search_file_mentions(
                q,
                limit=limit,
            )
        ]
    )


@system_router.get("/slash-commands/search", response_model=SlashCommandSearchResponse)
def search_available_slash_commands(
    q: MentionQuery = "",
    limit: MentionLimitQuery = 8,
) -> SlashCommandSearchResponse:
    return SlashCommandSearchResponse(
        items=[
            SlashCommandItemModel(name=item.name, description=item.description)
            for item in search_slash_commands(q, limit=limit)
        ]
    )


@chat_router.post("/session", response_model=ChatSessionResponse)
def create_chat_session(
    request: CreateChatSessionRequest,
    manager: SessionManagerDep,
) -> ChatSessionResponse:
    try:
        session = manager.create_live_chat(
            resume_session_id=request.resume_session_id,
            live_session_id=request.live_session_id,
        )
    except Exception as exc:
        raise _bad_request(str(exc)) from exc
    return ChatSessionResponse(
        session=_model_from_payload(LiveSessionModel, session),
    )


@chat_router.post(
    "/session/{live_session_id}/input", response_model=ChatSessionResponse
)
def submit_chat_input(
    live_session_id: LiveSessionIdPath,
    request: ChatInputRequest,
    manager: SessionManagerDep,
) -> ChatSessionResponse:
    try:
        session = manager.submit_chat_input(
            live_session_id,
            text=request.text,
            file_paths=request.file_paths,
            image_paths=request.image_paths,
            image_upload_ids=request.image_upload_ids,
        )
    except KeyError as exc:
        raise _not_found("Live session not found.") from exc
    except Exception as exc:
        raise _bad_request(str(exc)) from exc
    return ChatSessionResponse(
        session=_model_from_payload(LiveSessionModel, session),
    )


@chat_router.post(
    "/session/{live_session_id}/images",
    response_model=ImageUploadResponse,
)
async def upload_chat_images(
    live_session_id: LiveSessionIdPath,
    manager: SessionManagerDep,
    files: Annotated[list[UploadFile], File(description="One or more image files")],
) -> ImageUploadResponse:
    try:
        uploads = manager.upload_chat_images(
            live_session_id,
            files=[
                (upload.filename or "pasted-image.png", await upload.read())
                for upload in files
            ],
        )
    except KeyError as exc:
        raise _not_found("Live session not found.") from exc
    except Exception as exc:
        raise _bad_request(str(exc)) from exc
    return ImageUploadResponse(
        uploads=[
            _model_from_payload(ImageAttachmentModel, upload) for upload in uploads
        ]
    )


@chat_router.post("/expand-input", response_model=ExpandInputResponse)
def expand_chat_input(
    request: ExpandInputRequest,
    manager: SessionManagerDep,
) -> ExpandInputResponse:
    expanded_text, file_paths, image_paths, warnings = expand_input_mentions(
        request.text,
        root=manager.workspace_root,
    )
    if image_paths and not provider_supports_images(manager.settings.provider):
        warnings = [
            *warnings,
            "Image mentions are not supported by the current provider.",
        ]
        image_paths = []
    return ExpandInputResponse(
        text=expanded_text,
        file_paths=file_paths,
        image_paths=image_paths,
        warnings=warnings,
    )


@chat_router.post(
    "/session/{live_session_id}/new-chat",
    response_model=ChatSessionResponse,
)
def request_new_chat(
    live_session_id: LiveSessionIdPath,
    manager: SessionManagerDep,
) -> ChatSessionResponse:
    try:
        session = manager.request_new_chat(live_session_id)
    except KeyError as exc:
        raise _not_found("Live session not found.") from exc
    except Exception as exc:
        raise _bad_request(str(exc)) from exc
    return ChatSessionResponse(
        session=_model_from_payload(LiveSessionModel, session),
    )


@chat_router.get("/uploads/{upload_id}")
def get_uploaded_chat_image(upload_id: UploadIdPath) -> Response:
    try:
        record = load_uploaded_image_record(upload_id)
    except KeyError as exc:
        raise _not_found("Uploaded image not found.") from exc
    return FileResponse(uploaded_image_path(upload_id), media_type=record.mime_type)


@tasks_router.get("", response_model=TasksResponse)
def list_tasks(manager: SessionManagerDep) -> TasksResponse:
    return TasksResponse(
        tasks=[
            _model_from_payload(TaskRecordModel, item) for item in manager.list_tasks()
        ]
    )


@tasks_router.post("", response_model=TaskResponse)
def create_task(
    request: CreateTaskRequest,
    manager: SessionManagerDep,
) -> TaskResponse:
    try:
        task = manager.create_task(
            title=request.title,
            prompt=request.prompt,
            stage=request.stage,
            project_dir=request.project_dir,
            session_id=request.session_id,
        )
    except Exception as exc:
        raise _bad_request(str(exc)) from exc
    return TaskResponse(task=_model_from_payload(TaskRecordModel, task))


@tasks_router.patch("/{task_id}", response_model=TaskResponse)
def update_task(
    task_id: TaskIdPath,
    request: UpdateTaskRequest,
    manager: SessionManagerDep,
) -> TaskResponse:
    try:
        task = manager.update_task(
            task_id,
            title=request.title,
            prompt=request.prompt,
            stage=request.stage,
            position=request.position,
            project_dir=request.project_dir,
            session_id=request.session_id,
            clear_session_id=request.clear_session_id,
        )
    except KeyError as exc:
        raise _not_found("Task not found.") from exc
    except Exception as exc:
        raise _bad_request(str(exc)) from exc
    return TaskResponse(task=_model_from_payload(TaskRecordModel, task))


@tasks_router.delete("/{task_id}", status_code=204)
def delete_task(
    task_id: TaskIdPath,
    manager: SessionManagerDep,
) -> Response:
    try:
        manager.delete_task(task_id)
    except KeyError as exc:
        raise _not_found("Task not found.") from exc
    except Exception as exc:
        raise _bad_request(str(exc)) from exc
    return Response(status_code=204)


@tasks_router.post("/{task_id}/run", response_model=TaskResponse)
def run_task(
    task_id: TaskIdPath,
    manager: SessionManagerDep,
) -> TaskResponse:
    try:
        task = manager.run_task(task_id)
    except KeyError as exc:
        raise _not_found("Task not found.") from exc
    except Exception as exc:
        raise _bad_request(str(exc)) from exc
    return TaskResponse(task=_model_from_payload(TaskRecordModel, task))


@events_router.websocket("/{stream_id}")
async def stream_events(websocket: WebSocket, stream_id: StreamIdPath) -> None:
    manager = cast(WebSessionManager, websocket.app.state.manager)
    try:
        stream = manager.get_event_stream(stream_id)
    except KeyError:
        await websocket.close(code=4404)
        return

    await websocket.accept()
    for event in stream.snapshot():
        await websocket.send_json(event)
    subscriber_id, queue = stream.subscribe()
    try:
        while True:
            event = await queue.get()
            await websocket.send_json(event)
    except WebSocketDisconnect:
        return
    except asyncio.CancelledError:
        return
    finally:
        stream.unsubscribe(subscriber_id)


def create_app(
    settings: Settings,
    *,
    debug: bool = False,
    title: str | None = None,
    public_url: str | None = None,
) -> FastAPI:
    manager = WebSessionManager(settings)

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

    assets_dir = _APP_STATIC_DIR / "assets"
    if assets_dir.exists():
        app.mount("/assets", StaticFiles(directory=str(assets_dir)), name="assets")

    @app.get("/favicon.ico")
    def favicon_ico() -> FileResponse:
        return FileResponse(_FAVICON_PATH, media_type="image/png")

    @app.get("/favicon.png")
    def favicon_png() -> FileResponse:
        return FileResponse(_FAVICON_PATH, media_type="image/png")

    @app.get("/logo.png")
    def logo() -> FileResponse:
        return FileResponse(_FAVICON_PATH, media_type="image/png")

    app.include_router(system_router)
    app.include_router(chat_router)
    app.include_router(tasks_router)
    app.include_router(events_router)

    @app.get("/", response_class=HTMLResponse)
    def index() -> Response:
        return _spa_index_response(title or "PBI Agent")

    @app.get("/{full_path:path}", response_class=HTMLResponse)
    def spa_fallback(full_path: str) -> Response:
        if full_path.startswith("api/"):
            raise HTTPException(status_code=404, detail="Not found.")
        if full_path == APP_EVENT_STREAM_ID:
            raise HTTPException(status_code=404, detail="Not found.")
        return _spa_index_response(title or "PBI Agent")

    return app


def _spa_index_response(title: str) -> Response:
    index_path = _APP_STATIC_DIR / "index.html"
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
            "<p>Run <code>npm install</code> then <code>npm run web:build</code> "
            "to build the bundled frontend.</p></body></html>"
        )
    )


class PBIWebServer:
    def __init__(
        self,
        *,
        settings: Settings,
        host: str = "127.0.0.1",
        port: int = 8000,
        title: str | None = None,
        public_url: str | None = None,
    ) -> None:
        self._settings = settings
        self.host = host
        self.port = port
        self.title = title
        self.public_url = public_url
        self.console = Console(highlight=False)

    def serve(self, debug: bool = False) -> None:
        app = create_app(
            self._settings,
            debug=debug,
            title=self.title,
            public_url=self.public_url,
        )
        target = self.public_url or f"http://{self.host}:{self.port}"
        self.console.print(startup_panel(), highlight=False)
        self.console.print(f"  Serving on [bold]{target}[/bold]")
        self.console.print("[cyan]  Press Ctrl+C to quit[/cyan]")
        server = _GracefulUvicornServer(
            uvicorn.Config(
                app=app,
                host=self.host,
                port=self.port,
                log_level="info" if debug else "warning",
            )
        )
        try:
            server.run()
        except KeyboardInterrupt:
            return


class _GracefulUvicornServer(uvicorn.Server):
    @contextlib.contextmanager
    def capture_signals(self):
        if threading.current_thread() is not threading.main_thread():
            yield
            return

        handled_signals = getattr(
            uvicorn.server,
            "HANDLED_SIGNALS",
            (signal.SIGINT, signal.SIGTERM),
        )
        original_handlers = {
            sig: signal.signal(sig, self.handle_exit) for sig in handled_signals
        }
        try:
            yield
        finally:
            for sig, handler in original_handlers.items():
                signal.signal(sig, handler)


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="pbi-agent web server")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--title", default=None)
    parser.add_argument("--url", default=None, dest="public_url")
    parser.add_argument("--dev", action="store_true", default=False)
    parser.add_argument("--api-key", required=True)
    parser.add_argument("--provider", default="openai")
    parser.add_argument("--model", default="gpt-5.4")
    parser.add_argument("--sub-agent-model", default="gpt-5.4-mini")
    parser.add_argument(
        "--responses-url", default="https://api.openai.com/v1/responses"
    )
    parser.add_argument(
        "--generic-api-url", default="https://openrouter.ai/api/v1/chat/completions"
    )
    parser.add_argument("--reasoning-effort", default="xhigh")
    parser.add_argument("--max-tool-workers", type=int, default=4)
    parser.add_argument("--max-retries", type=int, default=3)
    parser.add_argument("--compact-threshold", type=int, default=150000)
    parser.add_argument("--max-tokens", type=int, default=16384)
    parser.add_argument("--verbose", action="store_true")
    parser.add_argument("--service-tier", default=None)
    parser.add_argument("--no-web-search", action="store_true", default=False)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    args = _parse_args(argv)
    settings = Settings(
        api_key=args.api_key,
        provider=args.provider,
        model=args.model,
        sub_agent_model=args.sub_agent_model,
        responses_url=args.responses_url,
        generic_api_url=args.generic_api_url,
        reasoning_effort=args.reasoning_effort,
        max_tool_workers=args.max_tool_workers,
        max_retries=args.max_retries,
        compact_threshold=args.compact_threshold,
        max_tokens=args.max_tokens,
        verbose=args.verbose,
        service_tier=args.service_tier,
        web_search=not args.no_web_search,
    )
    PBIWebServer(
        settings=settings,
        host=args.host,
        port=args.port,
        title=args.title,
        public_url=args.public_url,
    ).serve(debug=args.dev)


if __name__ == "__main__":
    main()


def _default_settings_namespace() -> argparse.Namespace:
    return argparse.Namespace(
        api_key=None,
        provider=None,
        responses_url=None,
        generic_api_url=None,
        model=None,
        sub_agent_model=None,
        max_tokens=None,
        verbose=False,
        max_tool_workers=None,
        max_retries=None,
        reasoning_effort=None,
        compact_threshold=None,
        service_tier=None,
        no_web_search=False,
    )


def _create_default_fastapi_app() -> FastAPI:
    try:
        settings = resolve_settings(_default_settings_namespace())
        settings.validate()
    except ConfigError as error:
        app = FastAPI(
            title="PBI Agent", docs_url=None, redoc_url=None, openapi_url=None
        )
        detail = str(error)

        @app.get("/")
        def configuration_error() -> dict[str, str]:
            raise HTTPException(status_code=500, detail=detail)

        return app
    return create_app(settings)


app = _create_default_fastapi_app()
