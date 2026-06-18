from __future__ import annotations

from pathlib import Path
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
    AgentMentionItemModel,
    AgentMentionSearchResponse,
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
    PromptEnhancementRequest,
    PromptEnhancementResponse,
    ProviderBreakdownModel,
    RunSessionDetailResponse,
    RunFilterValuesResponse,
    RunSessionModel,
    SessionDetailResponse,
    SessionImageUploadResponse,
    SessionRecordModel,
    SessionResponse,
    SessionRunsResponse,
    SessionsResponse,
    SkillMentionItemModel,
    SkillMentionSearchResponse,
    SlashCommandItemModel,
    SubmitQuestionResponseRequest,
    SlashCommandSearchResponse,
    WorkspaceListResponse,
    WorkspaceFilePreviewResponse,
    WorkspaceFileDiffResponse,
    WorkspaceFileTreeItemModel,
    WorkspaceFileTreeResponse,
    WorkspacePickerResponse,
    WorkspaceRecordModel,
    WorkspaceSwitchRequest,
    WorkspaceSwitchResponse,
    UpdateSessionRequest,
)
from pbi_agent.web.git_files import workspace_git_diff, workspace_git_status
from pbi_agent.web.input_mentions import WorkspaceFileTreePayload, expand_input_mentions
from pbi_agent.web.session_manager import workspace_picker_available
from pbi_agent.web.uploads import load_uploaded_image_record, uploaded_image_path

router = APIRouter(prefix="/api", tags=["system"])

_FILE_PREVIEW_MAX_BYTES = 256 * 1024


@router.get("/bootstrap", response_model=BootstrapResponse)
def bootstrap(manager: SessionManagerDep) -> BootstrapResponse:
    return model_from_payload(BootstrapResponse, manager.bootstrap())


@router.get("/workspaces/recent", response_model=WorkspaceListResponse)
def list_recent_workspaces(manager: SessionManagerDep) -> WorkspaceListResponse:
    workspace_manager = manager  # coordinator-only methods are exposed at runtime.
    return WorkspaceListResponse(
        workspaces=[
            model_from_payload(WorkspaceRecordModel, item)
            for item in workspace_manager.list_recent_workspaces()  # pyright: ignore[reportAttributeAccessIssue]
        ],
        picker_available=workspace_picker_available(),
    )


@router.post("/workspaces/switch", response_model=WorkspaceSwitchResponse)
def switch_workspace(
    request: WorkspaceSwitchRequest,
    manager: SessionManagerDep,
) -> WorkspaceSwitchResponse:
    try:
        bootstrap_payload = manager.switch_to_recent_workspace(request.directory_key)  # pyright: ignore[reportAttributeAccessIssue]
    except KeyError as exc:
        raise not_found("Recent workspace not found.") from exc
    except Exception as exc:
        raise bad_request(str(exc)) from exc
    return WorkspaceSwitchResponse(
        bootstrap=model_from_payload(BootstrapResponse, bootstrap_payload)
    )


@router.post("/workspaces/pick", response_model=WorkspacePickerResponse)
def pick_workspace(manager: SessionManagerDep) -> WorkspacePickerResponse:
    try:
        payload = manager.choose_folder_and_switch()  # pyright: ignore[reportAttributeAccessIssue]
    except Exception as exc:
        return WorkspacePickerResponse(status="error", message=str(exc), bootstrap=None)
    return WorkspacePickerResponse(
        status=payload["status"],
        message=payload.get("message"),
        bootstrap=(
            model_from_payload(BootstrapResponse, payload["bootstrap"])
            if payload.get("bootstrap") is not None
            else None
        ),
    )


@router.get("/sessions", response_model=SessionsResponse)
def list_sessions(
    manager: SessionManagerDep,
    limit: LimitQuery = 30,
    q: Annotated[str | None, Query(max_length=200)] = None,
) -> SessionsResponse:
    search = q.strip() if q else None
    return SessionsResponse(
        sessions=[
            model_from_payload(SessionRecordModel, item)
            for item in manager.list_sessions(limit=limit, search=search)
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


@router.post("/prompt/enhance", response_model=PromptEnhancementResponse)
def enhance_prompt(
    request: PromptEnhancementRequest,
    manager: SessionManagerDep,
) -> PromptEnhancementResponse:
    try:
        payload = manager.enhance_prompt(
            text=request.text,
            session_id=request.session_id,
        )
    except KeyError as exc:
        raise not_found("Session not found.") from exc
    except Exception as exc:
        raise bad_request(str(exc)) from exc
    return model_from_payload(PromptEnhancementResponse, payload)


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
            include_tool_history=request.include_tool_history,
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
            include_tool_history=request.include_tool_history,
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


@router.get("/dashboard/run-filter-values", response_model=RunFilterValuesResponse)
def list_run_filter_values(
    manager: SessionManagerDep,
    start_date: Annotated[str | None, Query()] = None,
    end_date: Annotated[str | None, Query()] = None,
    scope: ScopeQuery = "workspace",
) -> RunFilterValuesResponse:
    payload = manager.list_run_filter_values(
        start_date=start_date,
        end_date=end_date,
        global_scope=scope == "global",
    )
    return model_from_payload(RunFilterValuesResponse, payload)


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
def search_file_mentions(
    manager: SessionManagerDep,
    q: MentionQuery = "",
    limit: MentionLimitQuery = 8,
) -> FileMentionSearchResponse:
    payload = manager.search_file_mentions(q, limit=limit)
    return FileMentionSearchResponse(
        items=[
            FileMentionItemModel(path=item.path, kind=item.kind)
            for item in payload.items
        ],
        scan_status=payload.scan_status,
        is_stale=payload.is_stale,
        file_count=payload.file_count,
        error=payload.error,
    )


@router.get("/files/tree", response_model=WorkspaceFileTreeResponse)
def workspace_file_tree(manager: SessionManagerDep) -> WorkspaceFileTreeResponse:
    payload = manager.workspace_file_tree()
    return _workspace_file_tree_response(manager, payload)


@router.post("/files/tree/refresh", response_model=WorkspaceFileTreeResponse)
def refresh_workspace_file_tree(
    manager: SessionManagerDep,
) -> WorkspaceFileTreeResponse:
    payload = manager.refresh_workspace_file_tree()
    return _workspace_file_tree_response(manager, payload)


def _workspace_file_tree_response(
    manager: SessionManagerDep,
    payload: WorkspaceFileTreePayload,
) -> WorkspaceFileTreeResponse:
    git_status = workspace_git_status(manager.workspace_root)
    items_by_path = {
        item.path: WorkspaceFileTreeItemModel(
            path=item.path,
            kind=item.kind,
            git_status=git_status.statuses.get(item.path),
        )
        for item in payload.items
    }
    for path, status in git_status.statuses.items():
        if path not in items_by_path:
            items_by_path[path] = WorkspaceFileTreeItemModel(
                path=path,
                kind="file",
                git_status=status,
            )
    return WorkspaceFileTreeResponse(
        items=sorted(items_by_path.values(), key=lambda item: item.path.lower()),
        scan_status=payload.scan_status,
        is_stale=payload.is_stale,
        file_count=payload.file_count,
        truncated=payload.truncated,
        error=payload.error,
        git_repository=git_status.is_repository,
        git_status_version=git_status.version,
        git_status_error=git_status.error,
    )


@router.get("/files/diff", response_model=WorkspaceFileDiffResponse)
def diff_workspace_file(
    manager: SessionManagerDep,
    path: Annotated[str, Query(min_length=1, max_length=4096)],
) -> WorkspaceFileDiffResponse:
    diff = workspace_git_diff(manager.workspace_root, path)
    return WorkspaceFileDiffResponse(path=diff.path, diff=diff.diff, error=diff.error)


@router.get("/files/preview", response_model=WorkspaceFilePreviewResponse)
def preview_workspace_file(
    manager: SessionManagerDep,
    path: Annotated[str, Query(min_length=1, max_length=4096)],
) -> WorkspaceFilePreviewResponse:
    clean_path = path.strip().replace("\\", "/")
    try:
        relative = Path(clean_path)
        if relative.is_absolute() or ".." in relative.parts:
            raise ValueError
        target = (manager.workspace_root / relative).resolve()
        target.relative_to(manager.workspace_root)
    except (OSError, ValueError):
        return WorkspaceFilePreviewResponse(path=clean_path, error="outside_workspace")

    if not target.exists() or not target.is_file():
        return WorkspaceFilePreviewResponse(path=clean_path, error="not_found")
    try:
        size_bytes = target.stat().st_size
        if size_bytes > _FILE_PREVIEW_MAX_BYTES:
            return WorkspaceFilePreviewResponse(
                path=clean_path,
                size_bytes=size_bytes,
                truncated=True,
                error="too_large",
            )
        raw = target.read_bytes()
    except OSError:
        return WorkspaceFilePreviewResponse(path=clean_path, error="read_failed")
    if b"\0" in raw:
        return WorkspaceFilePreviewResponse(
            path=clean_path,
            size_bytes=len(raw),
            error="binary",
        )
    try:
        content = raw.decode("utf-8")
    except UnicodeDecodeError:
        return WorkspaceFilePreviewResponse(
            path=clean_path,
            size_bytes=len(raw),
            error="binary",
        )
    return WorkspaceFilePreviewResponse(
        path=clean_path,
        content=content,
        size_bytes=len(raw),
    )


@router.get("/skills/search", response_model=SkillMentionSearchResponse)
def search_available_skills(
    manager: SessionManagerDep,
    q: MentionQuery = "",
    limit: MentionLimitQuery = 8,
) -> SkillMentionSearchResponse:
    return SkillMentionSearchResponse(
        items=[
            model_from_payload(SkillMentionItemModel, item)
            for item in manager.search_skill_mentions(q, limit=limit)
        ]
    )


@router.get("/agents/search", response_model=AgentMentionSearchResponse)
def search_available_agents(
    manager: SessionManagerDep,
    q: MentionQuery = "",
    limit: MentionLimitQuery = 8,
) -> AgentMentionSearchResponse:
    return AgentMentionSearchResponse(
        items=[
            model_from_payload(AgentMentionItemModel, item)
            for item in manager.search_agent_mentions(q, limit=limit)
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
