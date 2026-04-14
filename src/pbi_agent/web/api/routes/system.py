from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Query, Response

from pbi_agent.web.api.deps import (
    LimitQuery,
    MentionLimitQuery,
    MentionQuery,
    RunSessionIdPath,
    SessionIdPath,
    SessionManagerDep,
    model_from_payload,
)
from pbi_agent.web.api.errors import bad_request, not_found
from pbi_agent.web.api.schemas.system import (
    AllRunsResponse,
    AllRunsRunModel,
    BootstrapResponse,
    DailyBucketModel,
    DashboardOverviewModel,
    DashboardStatsResponse,
    FileMentionItemModel,
    FileMentionSearchResponse,
    HistoryItemModel,
    LiveSessionDetailResponse,
    LiveSessionModel,
    LiveSessionSnapshotModel,
    LiveSessionsResponse,
    ObservabilityEventModel,
    ProviderBreakdownModel,
    RunSessionDetailResponse,
    RunSessionModel,
    SessionDetailResponse,
    SessionRecordModel,
    SessionRunsResponse,
    SessionsResponse,
    SlashCommandItemModel,
    SlashCommandSearchResponse,
)

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


@router.get("/sessions/{session_id}", response_model=SessionDetailResponse)
def get_session_detail(
    session_id: SessionIdPath,
    manager: SessionManagerDep,
) -> SessionDetailResponse:
    try:
        payload = manager.get_session_detail(session_id)
    except KeyError as exc:
        raise not_found("Session not found.") from exc
    return SessionDetailResponse(
        session=model_from_payload(SessionRecordModel, payload["session"]),
        history_items=[
            model_from_payload(HistoryItemModel, item)
            for item in payload["history_items"]
        ],
        live_session=(
            model_from_payload(LiveSessionModel, payload["live_session"])
            if payload["live_session"] is not None
            else None
        ),
        active_live_session=(
            model_from_payload(LiveSessionModel, payload["active_live_session"])
            if payload["active_live_session"] is not None
            else None
        ),
    )


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


@router.get("/live-sessions", response_model=LiveSessionsResponse)
def list_live_sessions(manager: SessionManagerDep) -> LiveSessionsResponse:
    return LiveSessionsResponse(
        live_sessions=[
            model_from_payload(LiveSessionModel, item)
            for item in manager.list_live_sessions()
        ]
    )


@router.get(
    "/live-sessions/{live_session_id}",
    response_model=LiveSessionDetailResponse,
)
def get_live_session_detail(
    live_session_id: str,
    manager: SessionManagerDep,
) -> LiveSessionDetailResponse:
    try:
        payload = manager.get_live_session_detail(live_session_id)
    except KeyError as exc:
        raise not_found("Live session not found.") from exc
    return LiveSessionDetailResponse(
        live_session=model_from_payload(LiveSessionModel, payload["live_session"]),
        snapshot=model_from_payload(LiveSessionSnapshotModel, payload["snapshot"]),
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
