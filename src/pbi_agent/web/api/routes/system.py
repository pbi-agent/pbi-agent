from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, File, Query, Response, UploadFile
from fastapi.responses import FileResponse

from pbi_agent.web.api.deps import (
    LimitQuery,
    MentionLimitQuery,
    MentionQuery,
    RunSessionIdPath,
    SessionIdPath,
    SessionManagerDep,
    UploadIdPath,
    model_from_payload,
)
from pbi_agent.web.api.errors import bad_request, not_found
from pbi_agent.web.api.schemas.common import ImageAttachmentModel
from pbi_agent.web.api.schemas.config import ActiveProfileRequest
from pbi_agent.web.api.schemas.system import (
    AllRunsResponse,
    AllRunsRunModel,
    BootstrapResponse,
    CreateSessionRequest,
    DailyBucketModel,
    DashboardOverviewModel,
    DashboardStatsResponse,
    ExpandInputRequest,
    ExpandInputResponse,
    FileMentionItemModel,
    FileMentionSearchResponse,
    ForkSessionRequest,
    HistoryItemModel,
    LiveSessionInputRequest,
    LiveSessionModel,
    LiveSessionResponse,
    LiveSessionShellCommandRequest,
    LiveSessionSnapshotModel,
    NewSessionRequest,
    ObservabilityEventModel,
    ProviderBreakdownModel,
    RunSessionDetailResponse,
    RunSessionModel,
    SessionDetailResponse,
    SessionImageUploadResponse,
    SessionRecordModel,
    SessionResponse,
    SessionRunsResponse,
    SessionsResponse,
    SlashCommandItemModel,
    SubmitQuestionResponseRequest,
    SlashCommandSearchResponse,
    UpdateSessionRequest,
)
from pbi_agent.web.input_mentions import expand_input_mentions
from pbi_agent.web.uploads import load_uploaded_image_record, uploaded_image_path

router = APIRouter(prefix="/api", tags=["system"])


@router.get("/bootstrap", response_model=BootstrapResponse)
def bootstrap(manager: SessionManagerDep) -> BootstrapResponse:
    return model_from_payload(BootstrapResponse, manager.bootstrap())


@router.get("/sessions", response_model=SessionsResponse)
def list_sessions(
    manager: SessionManagerDep,
    limit: LimitQuery = 30,
) -> SessionsResponse:
    return SessionsResponse(
        sessions=[
            model_from_payload(SessionRecordModel, item)
            for item in manager.list_sessions(limit=limit)
        ]
    )


@router.post("/sessions", response_model=SessionResponse)
def create_session(
    request: CreateSessionRequest,
    manager: SessionManagerDep,
) -> SessionResponse:
    try:
        session = manager.create_session_record(
            title=request.title,
            profile_id=request.profile_id,
        )
    except Exception as exc:
        raise bad_request(str(exc)) from exc
    return SessionResponse(session=model_from_payload(SessionRecordModel, session))


@router.get("/sessions/{session_id}", response_model=SessionDetailResponse)
def get_session_detail(
    session_id: SessionIdPath,
    manager: SessionManagerDep,
) -> SessionDetailResponse:
    try:
        payload = manager.get_session_detail(session_id)
    except KeyError as exc:
        raise not_found("Session not found.") from exc
    live_session = (
        model_from_payload(LiveSessionModel, payload["live_session"])
        if payload["live_session"] is not None
        else None
    )
    active_live_session = (
        model_from_payload(LiveSessionModel, payload["active_live_session"])
        if payload["active_live_session"] is not None
        else None
    )
    return SessionDetailResponse(
        session=model_from_payload(SessionRecordModel, payload["session"]),
        status=payload["status"],
        history_items=[
            model_from_payload(HistoryItemModel, item)
            for item in payload["history_items"]
        ],
        timeline=(
            model_from_payload(LiveSessionSnapshotModel, payload["timeline"])
            if payload["timeline"] is not None
            else None
        ),
        live_session=live_session,
        active_live_session=active_live_session,
        active_run=(
            model_from_payload(LiveSessionModel, payload["active_run"])
            if payload["active_run"] is not None
            else None
        ),
    )


@router.patch("/sessions/{session_id}", response_model=SessionResponse)
def update_session(
    session_id: SessionIdPath,
    payload: UpdateSessionRequest,
    manager: SessionManagerDep,
) -> SessionResponse:
    try:
        session = manager.update_session_title(session_id, payload.title)
    except KeyError as exc:
        raise not_found("Session not found.") from exc
    return SessionResponse(session=model_from_payload(SessionRecordModel, session))


@router.post("/sessions/{session_id}/fork", response_model=SessionResponse)
def fork_session(
    session_id: SessionIdPath,
    payload: ForkSessionRequest,
    manager: SessionManagerDep,
) -> SessionResponse:
    try:
        session = manager.fork_session(session_id, payload.message_id)
    except KeyError as exc:
        raise not_found("Session or fork point not found.") from exc
    except ValueError as exc:
        raise bad_request(str(exc)) from exc
    return SessionResponse(session=model_from_payload(SessionRecordModel, session))


@router.post("/sessions/{session_id}/messages", response_model=LiveSessionResponse)
def submit_session_message(
    session_id: SessionIdPath,
    request: LiveSessionInputRequest,
    manager: SessionManagerDep,
) -> LiveSessionResponse:
    try:
        session = manager.submit_saved_session_input(
            session_id,
            text=request.text,
            file_paths=request.file_paths,
            image_paths=request.image_paths,
            image_upload_ids=request.image_upload_ids,
            profile_id=request.profile_id,
            interactive_mode=request.interactive_mode,
        )
    except KeyError as exc:
        raise not_found("Session not found.") from exc
    except Exception as exc:
        raise bad_request(str(exc)) from exc
    return LiveSessionResponse(session=model_from_payload(LiveSessionModel, session))


@router.post("/sessions/{session_id}/runs", response_model=LiveSessionResponse)
def start_session_run(
    session_id: SessionIdPath,
    request: LiveSessionInputRequest,
    manager: SessionManagerDep,
) -> LiveSessionResponse:
    try:
        session = manager.submit_saved_session_input(
            session_id,
            text=request.text,
            file_paths=request.file_paths,
            image_paths=request.image_paths,
            image_upload_ids=request.image_upload_ids,
            profile_id=request.profile_id,
            interactive_mode=request.interactive_mode,
        )
    except KeyError as exc:
        raise not_found("Session not found.") from exc
    except Exception as exc:
        raise bad_request(str(exc)) from exc
    return LiveSessionResponse(session=model_from_payload(LiveSessionModel, session))


@router.post(
    "/sessions/{session_id}/question-response", response_model=LiveSessionResponse
)
def submit_session_question_response(
    session_id: SessionIdPath,
    request: SubmitQuestionResponseRequest,
    manager: SessionManagerDep,
) -> LiveSessionResponse:
    try:
        session = manager.submit_saved_session_question_response(
            session_id,
            prompt_id=request.prompt_id,
            answers=[answer.model_dump() for answer in request.answers],
        )
    except KeyError as exc:
        raise not_found("Active session run not found.") from exc
    except Exception as exc:
        raise bad_request(str(exc)) from exc
    return LiveSessionResponse(session=model_from_payload(LiveSessionModel, session))


@router.post("/sessions/{session_id}/shell-command", response_model=LiveSessionResponse)
def run_session_shell_command(
    session_id: SessionIdPath,
    request: LiveSessionShellCommandRequest,
    manager: SessionManagerDep,
) -> LiveSessionResponse:
    try:
        session = manager.run_saved_session_shell_command(
            session_id,
            command=request.command,
        )
    except KeyError as exc:
        raise not_found("Session not found.") from exc
    except Exception as exc:
        raise bad_request(str(exc)) from exc
    return LiveSessionResponse(session=model_from_payload(LiveSessionModel, session))


@router.post("/sessions/{session_id}/interrupt", response_model=LiveSessionResponse)
def interrupt_session_run(
    session_id: SessionIdPath,
    manager: SessionManagerDep,
) -> LiveSessionResponse:
    try:
        session = manager.interrupt_saved_session(session_id)
    except KeyError as exc:
        raise not_found("Active session run not found.") from exc
    except Exception as exc:
        raise bad_request(str(exc)) from exc
    return LiveSessionResponse(session=model_from_payload(LiveSessionModel, session))


@router.post("/sessions/{session_id}/images", response_model=SessionImageUploadResponse)
async def upload_saved_session_images(
    session_id: SessionIdPath,
    manager: SessionManagerDep,
    files: Annotated[list[UploadFile], File(description="One or more image files")],
) -> SessionImageUploadResponse:
    try:
        uploads = manager.upload_saved_session_images(
            session_id,
            files=[
                (upload.filename or "pasted-image.png", await upload.read())
                for upload in files
            ],
        )
    except KeyError as exc:
        raise not_found("Session not found.") from exc
    except Exception as exc:
        raise bad_request(str(exc)) from exc
    return SessionImageUploadResponse(
        uploads=[model_from_payload(ImageAttachmentModel, upload) for upload in uploads]
    )


@router.post("/sessions/{session_id}/new-session", response_model=LiveSessionResponse)
def request_session_new_session(
    session_id: SessionIdPath,
    request: NewSessionRequest,
    manager: SessionManagerDep,
) -> LiveSessionResponse:
    try:
        session = manager.request_saved_new_session(
            session_id,
            profile_id=request.profile_id,
        )
    except KeyError as exc:
        raise not_found("Session not found.") from exc
    except Exception as exc:
        raise bad_request(str(exc)) from exc
    return LiveSessionResponse(session=model_from_payload(LiveSessionModel, session))


@router.put("/sessions/{session_id}/profile", response_model=LiveSessionResponse)
def set_session_profile(
    session_id: SessionIdPath,
    request: ActiveProfileRequest,
    manager: SessionManagerDep,
) -> LiveSessionResponse:
    try:
        session = manager.set_saved_session_profile(
            session_id,
            profile_id=request.profile_id,
        )
    except KeyError as exc:
        raise not_found("Session not found.") from exc
    except Exception as exc:
        raise bad_request(str(exc)) from exc
    return LiveSessionResponse(session=model_from_payload(LiveSessionModel, session))


@router.get("/sessions/{session_id}/runs", response_model=SessionRunsResponse)
def list_session_runs(
    session_id: SessionIdPath,
    manager: SessionManagerDep,
) -> SessionRunsResponse:
    try:
        payload = manager.list_session_runs(session_id)
    except KeyError as exc:
        raise not_found("Session not found.") from exc
    return SessionRunsResponse(
        runs=[model_from_payload(RunSessionModel, item) for item in payload]
    )


ScopeQuery = Annotated[str, Query(pattern="^(workspace|global)$")]


@router.get("/runs/{run_session_id}", response_model=RunSessionDetailResponse)
def get_run_detail(
    run_session_id: RunSessionIdPath,
    manager: SessionManagerDep,
    scope: ScopeQuery = "workspace",
) -> RunSessionDetailResponse:
    try:
        payload = manager.get_run_detail(
            run_session_id, global_scope=(scope == "global")
        )
    except KeyError as exc:
        raise not_found("Run not found.") from exc
    return RunSessionDetailResponse(
        run=model_from_payload(RunSessionModel, payload["run"]),
        events=[
            model_from_payload(ObservabilityEventModel, item)
            for item in payload["events"]
        ],
    )


@router.get("/dashboard/stats", response_model=DashboardStatsResponse)
def get_dashboard_stats(
    manager: SessionManagerDep,
    start_date: Annotated[str | None, Query()] = None,
    end_date: Annotated[str | None, Query()] = None,
    scope: ScopeQuery = "workspace",
) -> DashboardStatsResponse:
    payload = manager.get_dashboard_stats(
        start_date=start_date,
        end_date=end_date,
        global_scope=scope == "global",
    )
    return DashboardStatsResponse(
        overview=model_from_payload(DashboardOverviewModel, payload["overview"]),
        breakdown=[
            model_from_payload(ProviderBreakdownModel, item)
            for item in payload["breakdown"]
        ],
        daily=[model_from_payload(DailyBucketModel, item) for item in payload["daily"]],
    )


@router.get("/runs", response_model=AllRunsResponse)
def list_all_runs(
    manager: SessionManagerDep,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
    status: Annotated[str | None, Query()] = None,
    provider: Annotated[str | None, Query()] = None,
    model: Annotated[str | None, Query()] = None,
    start_date: Annotated[str | None, Query()] = None,
    end_date: Annotated[str | None, Query()] = None,
    sort_by: Annotated[str, Query()] = "started_at",
    sort_dir: Annotated[str, Query(pattern="^(asc|desc)$")] = "desc",
    scope: ScopeQuery = "workspace",
) -> AllRunsResponse:
    payload = manager.list_all_runs(
        limit=limit,
        offset=offset,
        status=status,
        provider=provider,
        model=model,
        start_date=start_date,
        end_date=end_date,
        sort_by=sort_by,
        sort_dir=sort_dir,
        global_scope=scope == "global",
    )
    return AllRunsResponse(
        runs=[model_from_payload(AllRunsRunModel, item) for item in payload["runs"]],
        total_count=payload["total_count"],
    )


@router.delete("/sessions/{session_id}", status_code=204)
def delete_session(
    session_id: SessionIdPath,
    manager: SessionManagerDep,
) -> Response:
    try:
        manager.delete_session(session_id)
    except KeyError as exc:
        raise not_found("Session not found.") from exc
    except Exception as exc:
        raise bad_request(str(exc)) from exc
    return Response(status_code=204)


@router.get("/files/search", response_model=FileMentionSearchResponse)
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


@router.get("/slash-commands/search", response_model=SlashCommandSearchResponse)
def search_available_slash_commands(
    manager: SessionManagerDep,
    q: MentionQuery = "",
    limit: MentionLimitQuery = 8,
) -> SlashCommandSearchResponse:
    return SlashCommandSearchResponse(
        items=[
            model_from_payload(SlashCommandItemModel, item)
            for item in manager.search_slash_commands(q, limit=limit)
        ]
    )


@router.post("/sessions/expand-input", response_model=ExpandInputResponse)
def expand_session_input(
    request: ExpandInputRequest,
    manager: SessionManagerDep,
) -> ExpandInputResponse:
    expanded_text, file_paths, image_paths, warnings = expand_input_mentions(
        request.text,
        root=manager.workspace_root,
    )
    return ExpandInputResponse(
        text=expanded_text,
        file_paths=file_paths,
        image_paths=image_paths,
        warnings=warnings,
    )


@router.get("/uploads/{upload_id}")
def get_uploaded_image(upload_id: UploadIdPath) -> FileResponse:
    try:
        record = load_uploaded_image_record(upload_id)
        path = uploaded_image_path(upload_id)
    except KeyError as exc:
        raise not_found("Upload not found.") from exc
    return FileResponse(path, media_type=record.mime_type, filename=record.name)
