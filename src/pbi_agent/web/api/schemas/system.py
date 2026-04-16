from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

from pbi_agent.web.api.schemas.common import ImageAttachmentModel, RuntimeSummaryModel
from pbi_agent.web.api.schemas.tasks import BoardStageModel, TaskRecordModel

SessionStatus = Literal["starting", "running", "ended"]


class FileMentionItemModel(BaseModel):
    path: str
    kind: Literal["file", "image"]


class FileMentionSearchResponse(BaseModel):
    items: list[FileMentionItemModel]


class SlashCommandItemModel(BaseModel):
    name: str
    description: str
    kind: Literal["local_command", "command"]


class SlashCommandSearchResponse(BaseModel):
    items: list[SlashCommandItemModel]


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
    kind: Literal["session", "task"]
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


class RunSessionModel(BaseModel):
    run_session_id: str
    session_id: str | None
    parent_run_session_id: str | None
    agent_name: str | None
    agent_type: str | None
    provider: str | None
    provider_id: str | None
    profile_id: str | None
    model: str | None
    status: str
    started_at: str
    ended_at: str | None
    total_duration_ms: int | None
    input_tokens: int
    cached_input_tokens: int
    cache_write_tokens: int
    cache_write_1h_tokens: int
    output_tokens: int
    reasoning_tokens: int
    tool_use_tokens: int
    provider_total_tokens: int
    estimated_cost_usd: float
    total_tool_calls: int
    total_api_calls: int
    error_count: int
    metadata: Any | None


class ObservabilityEventModel(BaseModel):
    run_session_id: str
    session_id: str | None
    step_index: int
    event_type: str
    timestamp: str
    duration_ms: int | None
    provider: str | None
    model: str | None
    url: str | None
    request_config: Any | None
    request_payload: Any | None
    response_payload: Any | None
    tool_name: str | None
    tool_call_id: str | None
    tool_input: Any | None
    tool_output: Any | None
    tool_duration_ms: int | None
    prompt_tokens: int | None
    completion_tokens: int | None
    total_tokens: int | None
    status_code: int | None
    success: bool | None
    error_message: str | None
    metadata: Any | None


class SessionRunsResponse(BaseModel):
    runs: list[RunSessionModel]


class RunSessionDetailResponse(BaseModel):
    run: RunSessionModel
    events: list[ObservabilityEventModel]


# -- Dashboard / observability aggregation --------------------------------


class DailyBucketModel(BaseModel):
    date: str
    runs: int
    tokens: int
    cost: float
    errors: int


class ProviderBreakdownModel(BaseModel):
    provider: str | None
    model: str | None
    run_count: int
    total_tokens: int
    total_cost: float
    avg_duration_ms: float | None
    error_count: int
    total_api_calls: int
    total_tool_calls: int


class DashboardOverviewModel(BaseModel):
    total_sessions: int
    total_runs: int
    total_input_tokens: int
    total_cached_tokens: int
    total_output_tokens: int
    total_reasoning_tokens: int
    total_cost: float
    total_api_calls: int
    total_tool_calls: int
    total_errors: int
    avg_duration_ms: float | None
    completed_runs: int
    failed_runs: int


class DashboardStatsResponse(BaseModel):
    overview: DashboardOverviewModel
    breakdown: list[ProviderBreakdownModel]
    daily: list[DailyBucketModel]


class AllRunsRunModel(RunSessionModel):
    session_title: str | None = None


class AllRunsResponse(BaseModel):
    runs: list[AllRunsRunModel]
    total_count: int
