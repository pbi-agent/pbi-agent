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
    Header,
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

from pbi_agent.branding import startup_panel
from pbi_agent.config import (
    ConfigConflictError,
    ConfigError,
    ResolvedRuntime,
    Settings,
    resolve_web_runtime,
)
from pbi_agent.providers.capabilities import provider_supports_images
from pbi_agent.web.input_mentions import expand_input_mentions
from pbi_agent.web.session_manager import APP_EVENT_STREAM_ID, WebSessionManager
from pbi_agent.web.uploads import load_uploaded_image_record, uploaded_image_path

_WEB_DIR = Path(__file__).resolve().parent
_APP_STATIC_DIR = _WEB_DIR / "static" / "app"
_FAVICON_PATH = _WEB_DIR / "static" / "favicon.png"

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
ConfigRevisionHeader = Annotated[str, Header(alias="If-Match", min_length=1)]


class CreateChatSessionRequest(BaseModel):
    session_id: str | None = None
    resume_session_id: str | None = None
    live_session_id: str | None = None
    profile_id: str | None = None


class ChatInputRequest(BaseModel):
    text: str = ""
    file_paths: list[str] = Field(default_factory=list)
    image_paths: list[str] = Field(default_factory=list)
    image_upload_ids: list[str] = Field(default_factory=list)
    profile_id: str | None = None


class NewChatRequest(BaseModel):
    profile_id: str | None = None


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
    kind: Literal["local_command", "mode"]


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
    stage: str | None = None
    project_dir: str = "."
    session_id: str | None = None
    profile_id: str | None = None


class UpdateTaskRequest(BaseModel):
    title: NonEmptyString | None = None
    prompt: NonEmptyString | None = None
    stage: str | None = None
    position: Annotated[int, Field(ge=0)] | None = None
    project_dir: str | None = None
    session_id: str | None = None
    profile_id: str | None = None


class BoardStageModel(BaseModel):
    id: str
    name: str
    position: int
    profile_id: str | None
    mode_id: str | None
    auto_start: bool


class BoardStageUpdateModel(BaseModel):
    id: str | None = None
    name: NonEmptyString
    profile_id: str | None = None
    mode_id: str | None = None
    auto_start: bool = False


class BoardStagesResponse(BaseModel):
    board_stages: list[BoardStageModel]


class UpdateBoardStagesRequest(BaseModel):
    board_stages: list[BoardStageUpdateModel]


class SessionRecordModel(BaseModel):
    session_id: str
    directory: str
    provider: str
    provider_id: str | None
    model: str
    profile_id: str | None
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
    session_id: str | None
    resume_session_id: str | None = None
    task_id: str | None
    kind: Literal["chat", "task"]
    project_dir: str
    provider_id: str | None
    profile_id: str | None
    provider: str
    model: str
    reasoning_effort: str
    created_at: str
    status: SessionStatus
    exit_code: int | None
    fatal_error: str | None
    ended_at: str | None
    last_event_seq: int = 0


class ImageAttachmentModel(BaseModel):
    upload_id: str
    name: str
    mime_type: str
    byte_count: int
    preview_url: str


class ImageUploadResponse(BaseModel):
    uploads: list[ImageAttachmentModel]


class RuntimeSummaryModel(BaseModel):
    provider: str | None
    provider_id: str | None
    profile_id: str | None
    model: str | None
    reasoning_effort: str | None


class TaskRecordModel(BaseModel):
    task_id: str
    directory: str
    title: str
    prompt: str
    stage: str
    position: int
    project_dir: str
    session_id: str | None
    profile_id: str | None
    run_status: RunStatus
    last_result_summary: str
    created_at: str
    updated_at: str
    last_run_started_at: str | None
    last_run_finished_at: str | None
    runtime_summary: RuntimeSummaryModel


class BootstrapResponse(BaseModel):
    workspace_root: str
    provider: str | None
    provider_id: str | None
    profile_id: str | None
    model: str | None
    reasoning_effort: str | None
    supports_image_inputs: bool
    sessions: list[SessionRecordModel]
    tasks: list[TaskRecordModel]
    live_sessions: list[LiveSessionModel]
    board_stages: list[BoardStageModel]


class LiveSessionSnapshotModel(BaseModel):
    live_session_id: str
    session_id: str | None
    runtime: RuntimeSummaryModel | None
    input_enabled: bool
    wait_message: str | None
    session_usage: dict[str, Any] | None
    turn_usage: dict[str, Any] | None
    session_ended: bool
    fatal_error: str | None
    items: list[dict[str, Any]]
    sub_agents: dict[str, dict[str, str]]
    last_event_seq: int


class LiveSessionsResponse(BaseModel):
    live_sessions: list[LiveSessionModel]


class LiveSessionDetailResponse(BaseModel):
    live_session: LiveSessionModel
    snapshot: LiveSessionSnapshotModel


class SessionsResponse(BaseModel):
    sessions: list[SessionRecordModel]


class HistoryItemModel(BaseModel):
    item_id: str
    role: str
    content: str
    file_paths: list[str] = Field(default_factory=list)
    image_attachments: list[ImageAttachmentModel] = Field(default_factory=list)
    markdown: bool
    historical: bool
    created_at: str


class SessionDetailResponse(BaseModel):
    session: SessionRecordModel
    history_items: list[HistoryItemModel]
    live_session: LiveSessionModel | None
    active_live_session: LiveSessionModel | None


class ChatSessionResponse(BaseModel):
    session: LiveSessionModel


class TasksResponse(BaseModel):
    tasks: list[TaskRecordModel]


class TaskResponse(BaseModel):
    task: TaskRecordModel


class ProviderKindMetadataModel(BaseModel):
    default_model: str
    default_sub_agent_model: str | None
    default_responses_url: str | None
    default_generic_api_url: str | None
    supports_responses_url: bool
    supports_generic_api_url: bool
    supports_service_tier: bool
    supports_native_web_search: bool
    supports_image_inputs: bool


class ConfigOptionsModel(BaseModel):
    provider_kinds: list[str]
    reasoning_efforts: list[str]
    openai_service_tiers: list[str]
    provider_metadata: dict[str, ProviderKindMetadataModel]


class ProviderViewModel(BaseModel):
    id: str
    name: str
    kind: str
    responses_url: str | None
    generic_api_url: str | None
    secret_source: Literal["none", "plaintext", "env_var"]
    secret_env_var: str | None
    has_secret: bool


class ProviderMutationRequest(BaseModel):
    id: str | None = None
    name: NonEmptyString
    kind: NonEmptyString
    api_key: str | None = None
    api_key_env: str | None = None
    responses_url: str | None = None
    generic_api_url: str | None = None


class ProviderUpdateRequest(BaseModel):
    name: NonEmptyString | None = None
    kind: NonEmptyString | None = None
    api_key: str | None = None
    api_key_env: str | None = None
    responses_url: str | None = None
    generic_api_url: str | None = None


class ProviderListResponse(BaseModel):
    providers: list[ProviderViewModel]
    config_revision: str


class ProviderResponse(BaseModel):
    provider: ProviderViewModel
    config_revision: str


class ModelProfileProviderModel(BaseModel):
    id: str
    name: str
    kind: str


class ResolvedRuntimeViewModel(BaseModel):
    provider: str
    provider_id: str
    profile_id: str
    model: str
    sub_agent_model: str | None
    reasoning_effort: str
    max_tokens: int
    service_tier: str | None
    web_search: bool
    max_tool_workers: int
    max_retries: int
    compact_threshold: int
    responses_url: str
    generic_api_url: str
    supports_image_inputs: bool


class ModelProfileViewModel(BaseModel):
    id: str
    name: str
    provider_id: str
    provider: ModelProfileProviderModel
    model: str | None
    sub_agent_model: str | None
    reasoning_effort: str | None
    max_tokens: int | None
    service_tier: str | None
    web_search: bool | None
    max_tool_workers: int | None
    max_retries: int | None
    compact_threshold: int | None
    is_active_default: bool
    resolved_runtime: ResolvedRuntimeViewModel


class ModelProfileMutationRequest(BaseModel):
    id: str | None = None
    name: NonEmptyString
    provider_id: NonEmptyString
    model: str | None = None
    sub_agent_model: str | None = None
    reasoning_effort: str | None = None
    max_tokens: int | None = Field(default=None, ge=1)
    service_tier: str | None = None
    web_search: bool | None = None
    max_tool_workers: int | None = Field(default=None, ge=1)
    max_retries: int | None = Field(default=None, ge=0)
    compact_threshold: int | None = Field(default=None, ge=1)


class ModelProfileUpdateRequest(BaseModel):
    name: NonEmptyString | None = None
    provider_id: NonEmptyString | None = None
    model: str | None = None
    sub_agent_model: str | None = None
    reasoning_effort: str | None = None
    max_tokens: int | None = Field(default=None, ge=1)
    service_tier: str | None = None
    web_search: bool | None = None
    max_tool_workers: int | None = Field(default=None, ge=1)
    max_retries: int | None = Field(default=None, ge=0)
    compact_threshold: int | None = Field(default=None, ge=1)


class ModelProfileListResponse(BaseModel):
    model_profiles: list[ModelProfileViewModel]
    active_profile_id: str | None
    config_revision: str


class ModelProfileResponse(BaseModel):
    model_profile: ModelProfileViewModel
    config_revision: str


class ActiveProfileRequest(BaseModel):
    profile_id: str | None = None


class ActiveProfileResponse(BaseModel):
    active_profile_id: str | None
    config_revision: str


class ModeViewModel(BaseModel):
    id: str
    name: str
    slash_alias: str
    description: str
    instructions: str
    path: str


class ModeListResponse(BaseModel):
    modes: list[ModeViewModel]
    config_revision: str


class ConfigBootstrapResponse(BaseModel):
    providers: list[ProviderViewModel]
    model_profiles: list[ModelProfileViewModel]
    modes: list[ModeViewModel]
    active_profile_id: str | None
    config_revision: str
    options: ConfigOptionsModel


system_router = APIRouter(prefix="/api", tags=["system"])
config_router = APIRouter(prefix="/api/config", tags=["config"])
chat_router = APIRouter(prefix="/api/chat", tags=["chat"])
tasks_router = APIRouter(prefix="/api/tasks", tags=["tasks"])
board_router = APIRouter(prefix="/api/board", tags=["board"])
events_router = APIRouter(prefix="/api/events", tags=["events"])


def _get_session_manager(request: Request) -> WebSessionManager:
    return cast(WebSessionManager, request.app.state.manager)


SessionManagerDep = Annotated[WebSessionManager, Depends(_get_session_manager)]


def _model_from_payload[T: BaseModel](model_type: type[T], payload: Any) -> T:
    return model_type.model_validate(payload)


def _bad_request(detail: str) -> HTTPException:
    return HTTPException(status_code=400, detail=detail)


def _conflict(detail: str) -> HTTPException:
    return HTTPException(status_code=409, detail=detail)


def _not_found(detail: str) -> HTTPException:
    return HTTPException(status_code=404, detail=detail)


def _config_http_error(exc: Exception) -> HTTPException:
    detail = str(exc)
    if isinstance(exc, ConfigConflictError):
        return _conflict(detail)
    if (
        detail.startswith("Unknown provider ID")
        or detail.startswith("Unknown profile ID")
        or detail.startswith("Unknown mode ID")
    ):
        return _not_found(detail)
    if (
        "already exists" in detail
        or "still references it" in detail
        or detail.startswith("Mode alias '")
    ):
        return _conflict(detail)
    return _bad_request(detail)


@system_router.get("/bootstrap", response_model=BootstrapResponse)
def bootstrap(manager: SessionManagerDep) -> BootstrapResponse:
    return _model_from_payload(BootstrapResponse, manager.bootstrap())


@config_router.get("/bootstrap", response_model=ConfigBootstrapResponse)
def config_bootstrap(manager: SessionManagerDep) -> ConfigBootstrapResponse:
    return _model_from_payload(ConfigBootstrapResponse, manager.config_bootstrap())


@config_router.get("/providers", response_model=ProviderListResponse)
def list_providers(manager: SessionManagerDep) -> ProviderListResponse:
    payload = manager.config_bootstrap()
    return ProviderListResponse(
        providers=[
            _model_from_payload(ProviderViewModel, item)
            for item in payload["providers"]
        ],
        config_revision=str(payload["config_revision"]),
    )


@config_router.post("/providers", response_model=ProviderResponse)
def create_provider(
    request: ProviderMutationRequest,
    manager: SessionManagerDep,
    expected_revision: ConfigRevisionHeader,
) -> ProviderResponse:
    try:
        payload = manager.create_provider(
            provider_id=request.id,
            name=request.name,
            kind=request.kind,
            api_key=request.api_key,
            api_key_env=request.api_key_env,
            responses_url=request.responses_url,
            generic_api_url=request.generic_api_url,
            expected_revision=expected_revision,
        )
    except Exception as exc:
        raise _config_http_error(exc) from exc
    return ProviderResponse(
        provider=_model_from_payload(ProviderViewModel, payload["provider"]),
        config_revision=str(payload["config_revision"]),
    )


@config_router.patch("/providers/{provider_id}", response_model=ProviderResponse)
def update_provider(
    provider_id: str,
    request: ProviderUpdateRequest,
    manager: SessionManagerDep,
    expected_revision: ConfigRevisionHeader,
) -> ProviderResponse:
    try:
        payload = manager.update_provider(
            provider_id,
            name=request.name,
            kind=request.kind,
            api_key=request.api_key,
            api_key_env=request.api_key_env,
            responses_url=request.responses_url,
            generic_api_url=request.generic_api_url,
            fields_set=set(request.model_fields_set),
            expected_revision=expected_revision,
        )
    except Exception as exc:
        raise _config_http_error(exc) from exc
    return ProviderResponse(
        provider=_model_from_payload(ProviderViewModel, payload["provider"]),
        config_revision=str(payload["config_revision"]),
    )


@config_router.delete("/providers/{provider_id}", status_code=204)
def delete_provider(
    provider_id: str,
    manager: SessionManagerDep,
    expected_revision: ConfigRevisionHeader,
) -> Response:
    try:
        manager.delete_provider(provider_id, expected_revision=expected_revision)
    except Exception as exc:
        raise _config_http_error(exc) from exc
    return Response(status_code=204)


@config_router.get("/model-profiles", response_model=ModelProfileListResponse)
def list_model_profiles(manager: SessionManagerDep) -> ModelProfileListResponse:
    payload = manager.config_bootstrap()
    return ModelProfileListResponse(
        model_profiles=[
            _model_from_payload(ModelProfileViewModel, item)
            for item in payload["model_profiles"]
        ],
        active_profile_id=payload["active_profile_id"],
        config_revision=str(payload["config_revision"]),
    )


@config_router.post("/model-profiles", response_model=ModelProfileResponse)
def create_model_profile(
    request: ModelProfileMutationRequest,
    manager: SessionManagerDep,
    expected_revision: ConfigRevisionHeader,
) -> ModelProfileResponse:
    try:
        payload = manager.create_model_profile(
            profile_id=request.id,
            name=request.name,
            provider_id=request.provider_id,
            model=request.model,
            sub_agent_model=request.sub_agent_model,
            reasoning_effort=request.reasoning_effort,
            max_tokens=request.max_tokens,
            service_tier=request.service_tier,
            web_search=request.web_search,
            max_tool_workers=request.max_tool_workers,
            max_retries=request.max_retries,
            compact_threshold=request.compact_threshold,
            expected_revision=expected_revision,
        )
    except Exception as exc:
        raise _config_http_error(exc) from exc
    return ModelProfileResponse(
        model_profile=_model_from_payload(
            ModelProfileViewModel, payload["model_profile"]
        ),
        config_revision=str(payload["config_revision"]),
    )


@config_router.patch(
    "/model-profiles/{profile_id}", response_model=ModelProfileResponse
)
def update_model_profile(
    profile_id: str,
    request: ModelProfileUpdateRequest,
    manager: SessionManagerDep,
    expected_revision: ConfigRevisionHeader,
) -> ModelProfileResponse:
    try:
        payload = manager.update_model_profile(
            profile_id,
            name=request.name,
            provider_id=request.provider_id,
            model=request.model,
            sub_agent_model=request.sub_agent_model,
            reasoning_effort=request.reasoning_effort,
            max_tokens=request.max_tokens,
            service_tier=request.service_tier,
            web_search=request.web_search,
            max_tool_workers=request.max_tool_workers,
            max_retries=request.max_retries,
            compact_threshold=request.compact_threshold,
            fields_set=set(request.model_fields_set),
            expected_revision=expected_revision,
        )
    except Exception as exc:
        raise _config_http_error(exc) from exc
    return ModelProfileResponse(
        model_profile=_model_from_payload(
            ModelProfileViewModel, payload["model_profile"]
        ),
        config_revision=str(payload["config_revision"]),
    )


@config_router.delete("/model-profiles/{profile_id}", status_code=204)
def delete_model_profile(
    profile_id: str,
    manager: SessionManagerDep,
    expected_revision: ConfigRevisionHeader,
) -> Response:
    try:
        manager.delete_model_profile(
            profile_id,
            expected_revision=expected_revision,
        )
    except Exception as exc:
        raise _config_http_error(exc) from exc
    return Response(status_code=204)


@config_router.put(
    "/active-model-profile",
    response_model=ActiveProfileResponse,
)
def set_active_model_profile(
    request: ActiveProfileRequest,
    manager: SessionManagerDep,
    expected_revision: ConfigRevisionHeader,
) -> ActiveProfileResponse:
    try:
        payload = manager.set_active_model_profile(
            request.profile_id,
            expected_revision=expected_revision,
        )
    except Exception as exc:
        raise _config_http_error(exc) from exc
    return ActiveProfileResponse(
        active_profile_id=payload["active_profile_id"],
        config_revision=str(payload["config_revision"]),
    )


@config_router.get("/modes", response_model=ModeListResponse)
def list_modes(manager: SessionManagerDep) -> ModeListResponse:
    payload = manager.config_bootstrap()
    return ModeListResponse(
        modes=[_model_from_payload(ModeViewModel, item) for item in payload["modes"]],
        config_revision=str(payload["config_revision"]),
    )


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


@system_router.get("/sessions/{session_id}", response_model=SessionDetailResponse)
def get_session_detail(
    session_id: SessionIdPath,
    manager: SessionManagerDep,
) -> SessionDetailResponse:
    try:
        payload = manager.get_session_detail(session_id)
    except KeyError as exc:
        raise _not_found("Session not found.") from exc
    return SessionDetailResponse(
        session=_model_from_payload(SessionRecordModel, payload["session"]),
        history_items=[
            _model_from_payload(HistoryItemModel, item)
            for item in payload["history_items"]
        ],
        live_session=(
            _model_from_payload(LiveSessionModel, payload["live_session"])
            if payload["live_session"] is not None
            else None
        ),
        active_live_session=(
            _model_from_payload(LiveSessionModel, payload["active_live_session"])
            if payload["active_live_session"] is not None
            else None
        ),
    )


@system_router.get("/live-sessions", response_model=LiveSessionsResponse)
def list_live_sessions(manager: SessionManagerDep) -> LiveSessionsResponse:
    return LiveSessionsResponse(
        live_sessions=[
            _model_from_payload(LiveSessionModel, item)
            for item in manager.list_live_sessions()
        ]
    )


@system_router.get(
    "/live-sessions/{live_session_id}",
    response_model=LiveSessionDetailResponse,
)
def get_live_session_detail(
    live_session_id: LiveSessionIdPath,
    manager: SessionManagerDep,
) -> LiveSessionDetailResponse:
    try:
        payload = manager.get_live_session_detail(live_session_id)
    except KeyError as exc:
        raise _not_found("Live session not found.") from exc
    return LiveSessionDetailResponse(
        live_session=_model_from_payload(LiveSessionModel, payload["live_session"]),
        snapshot=_model_from_payload(LiveSessionSnapshotModel, payload["snapshot"]),
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
    manager: SessionManagerDep,
    q: MentionQuery = "",
    limit: MentionLimitQuery = 8,
) -> SlashCommandSearchResponse:
    return SlashCommandSearchResponse(
        items=[
            _model_from_payload(SlashCommandItemModel, item)
            for item in manager.search_slash_commands(q, limit=limit)
        ]
    )


@chat_router.post("/session", response_model=ChatSessionResponse)
def create_chat_session(
    request: CreateChatSessionRequest,
    manager: SessionManagerDep,
) -> ChatSessionResponse:
    try:
        session = manager.create_live_chat(
            session_id=request.session_id or request.resume_session_id,
            live_session_id=request.live_session_id,
            profile_id=request.profile_id,
        )
    except KeyError as exc:
        raise _not_found("Session not found.") from exc
    except ConfigError as exc:
        raise _config_http_error(exc) from exc
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
            profile_id=request.profile_id,
        )
    except KeyError as exc:
        raise _not_found("Live session not found.") from exc
    except ConfigError as exc:
        raise _config_http_error(exc) from exc
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
    request: NewChatRequest,
    manager: SessionManagerDep,
) -> ChatSessionResponse:
    try:
        session = manager.request_new_chat(
            live_session_id,
            profile_id=request.profile_id,
        )
    except KeyError as exc:
        raise _not_found("Live session not found.") from exc
    except ConfigError as exc:
        raise _config_http_error(exc) from exc
    except Exception as exc:
        raise _bad_request(str(exc)) from exc
    return ChatSessionResponse(
        session=_model_from_payload(LiveSessionModel, session),
    )


@chat_router.put(
    "/session/{live_session_id}/profile",
    response_model=ChatSessionResponse,
)
def set_chat_session_profile(
    live_session_id: LiveSessionIdPath,
    request: ActiveProfileRequest,
    manager: SessionManagerDep,
) -> ChatSessionResponse:
    try:
        session = manager.set_live_chat_profile(
            live_session_id,
            profile_id=request.profile_id,
        )
    except KeyError as exc:
        raise _not_found("Live session not found.") from exc
    except ConfigError as exc:
        raise _config_http_error(exc) from exc
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
            profile_id=request.profile_id,
        )
    except ConfigError as exc:
        raise _config_http_error(exc) from exc
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
            session_id_present="session_id" in request.model_fields_set,
            profile_id=request.profile_id,
            profile_id_present="profile_id" in request.model_fields_set,
        )
    except KeyError as exc:
        raise _not_found("Task not found.") from exc
    except ConfigError as exc:
        raise _config_http_error(exc) from exc
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
    except ConfigError as exc:
        raise _config_http_error(exc) from exc
    except Exception as exc:
        raise _bad_request(str(exc)) from exc
    return TaskResponse(task=_model_from_payload(TaskRecordModel, task))


@board_router.get("/stages", response_model=BoardStagesResponse)
def list_board_stages(manager: SessionManagerDep) -> BoardStagesResponse:
    return BoardStagesResponse(
        board_stages=[
            _model_from_payload(BoardStageModel, item)
            for item in manager.list_board_stages()
        ]
    )


@board_router.put("/stages", response_model=BoardStagesResponse)
def update_board_stages(
    request: UpdateBoardStagesRequest,
    manager: SessionManagerDep,
) -> BoardStagesResponse:
    try:
        stages = manager.replace_board_stages(
            stages=[item.model_dump() for item in request.board_stages],
        )
    except ConfigError as exc:
        raise _config_http_error(exc) from exc
    except Exception as exc:
        raise _bad_request(str(exc)) from exc
    return BoardStagesResponse(
        board_stages=[_model_from_payload(BoardStageModel, item) for item in stages]
    )


@events_router.websocket("/{stream_id}")
async def stream_events(websocket: WebSocket, stream_id: StreamIdPath) -> None:
    manager = cast(WebSessionManager, websocket.app.state.manager)
    try:
        stream = manager.get_event_stream(stream_id)
    except KeyError:
        await websocket.close(code=4404)
        return

    await websocket.accept()
    try:
        for event in stream.snapshot():
            await websocket.send_json(event)
    except WebSocketDisconnect:
        return
    except asyncio.CancelledError:
        return
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
    app.include_router(config_router)
    app.include_router(chat_router)
    app.include_router(tasks_router)
    app.include_router(board_router)
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
            "<p>Run <code>bun install</code> then <code>bun run web:build</code> "
            "to build the bundled frontend.</p></body></html>"
        )
    )


class PBIWebServer:
    def __init__(
        self,
        *,
        settings: Settings,
        runtime_args: argparse.Namespace | None = None,
        host: str = "127.0.0.1",
        port: int = 8000,
        title: str | None = None,
        public_url: str | None = None,
    ) -> None:
        self._settings = settings
        self._runtime_args = runtime_args
        self.host = host
        self.port = port
        self.title = title
        self.public_url = public_url
        self.console = Console(highlight=False)

    def serve(self, debug: bool = False) -> None:
        app = create_app(
            self._settings,
            runtime_args=self._runtime_args,
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
    try:
        runtime: Settings | ResolvedRuntime = resolve_web_runtime(verbose=args.verbose)
    except ConfigError:
        runtime = Settings(api_key="", provider="openai", model="gpt-5.4")
    PBIWebServer(
        settings=runtime,
        runtime_args=args,
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
        profile_id=None,
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
    args = _default_settings_namespace()
    try:
        runtime: Settings | ResolvedRuntime = resolve_web_runtime(verbose=args.verbose)
    except ConfigError:
        runtime = Settings(api_key="", provider="openai", model="gpt-5.4")
    return create_app(runtime, runtime_args=args)


app = _create_default_fastapi_app()
