from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

from pbi_agent.web.api.deps import NonEmptyString
from pbi_agent.web.api.schemas.common import ImageAttachmentModel, RuntimeSummaryModel
from pbi_agent.web.api.schemas.tasks import BoardStageModel, TaskRecordModel

SessionLifecycleStatus = Literal[
    "idle", "starting", "running", "waiting_for_input", "ended", "failed", "stale"
]
RunSessionStatus = Literal[
    "started",
    "completed",
    "interrupted",
    "failed",
    "starting",
    "running",
    "waiting_for_input",
    "ended",
    "stale",
]


class FileMentionItemModel(BaseModel):
    path: str
    kind: Literal["file", "image"]


ScanStatus = Literal["idle", "scanning", "ready", "failed"]


class FileMentionSearchResponse(BaseModel):
    items: list[FileMentionItemModel]
    scan_status: ScanStatus
    is_stale: bool
    file_count: int
    error: str | None = None


class SlashCommandItemModel(BaseModel):
    name: str
    description: str
    kind: Literal["local_command", "command"]


class SlashCommandSearchResponse(BaseModel):
    items: list[SlashCommandItemModel]


class SkillMentionItemModel(BaseModel):
    name: str
    description: str
    path: str


class SkillMentionSearchResponse(BaseModel):
    items: list[SkillMentionItemModel]


class ExpandInputRequest(BaseModel):
    text: str = ""


class ExpandInputResponse(BaseModel):
    text: str
    file_paths: list[str] = Field(default_factory=list)
    image_paths: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


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
    is_fork: bool = False
    forked_from_session_id: str | None = None
    forked_from_message_id: str | None = None
    fork_created_at: str | None = None
    created_at: str
    updated_at: str
    status: SessionLifecycleStatus = "idle"
    active_run_id: str | None = None
    active_live_session_id: str | None = None
    task_id: str | None = None


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
    compact_threshold: int
    created_at: str
    status: SessionLifecycleStatus
    exit_code: int | None
    fatal_error: str | None
    ended_at: str | None
    last_event_seq: int = 0


class BootstrapResponse(BaseModel):
    workspace_root: str
    workspace_key: str
    workspace_display_path: str
    is_sandbox: bool
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


ProcessingPhase = Literal[
    "starting",
    "model_wait",
    "tool_execution",
    "finalizing",
    "interrupting",
    "retry_wait",
]


class ProcessingStateModel(BaseModel):
    active: bool
    phase: ProcessingPhase | None = None
    message: str | None = None
    active_tool_count: int | None = None


class PendingUserQuestionModel(BaseModel):
    question_id: str
    question: str
    suggestions: list[str]
    recommended_suggestion_index: Literal[0] = 0


class PendingUserQuestionsModel(BaseModel):
    prompt_id: str
    questions: list[PendingUserQuestionModel]


class UsageSnapshotModel(BaseModel):
    usage: dict[str, Any] | None
    elapsed_seconds: float | None = None


class SubAgentSnapshotModel(BaseModel):
    title: str
    status: str
    wait_message: str | None = Field(
        default=None,
        exclude_if=lambda value: value is None,
    )
    processing: ProcessingStateModel | None = Field(
        default=None,
        exclude_if=lambda value: value is None,
    )
    session_usage: dict[str, Any] | None = Field(
        default=None,
        exclude_if=lambda value: value is None,
    )
    turn_usage: UsageSnapshotModel | None = Field(
        default=None,
        exclude_if=lambda value: value is None,
    )


class LiveSessionSnapshotModel(BaseModel):
    live_session_id: str
    session_id: str | None
    runtime: RuntimeSummaryModel | None
    input_enabled: bool
    wait_message: str | None
    processing: ProcessingStateModel | None
    session_usage: dict[str, Any] | None
    turn_usage: dict[str, Any] | None
    session_ended: bool
    fatal_error: str | None
    pending_user_questions: PendingUserQuestionsModel | None
    items: list[dict[str, Any]]
    sub_agents: dict[str, SubAgentSnapshotModel]
    last_event_seq: int


class SessionsResponse(BaseModel):
    sessions: list[SessionRecordModel]


class CreateSessionRequest(BaseModel):
    title: str = ""
    profile_id: str | None = None


class UpdateSessionRequest(BaseModel):
    title: NonEmptyString


class ForkSessionRequest(BaseModel):
    message_id: NonEmptyString


class QuestionAnswerRequest(BaseModel):
    question_id: str
    answer: str
    selected_suggestion_index: int | None = None
    custom: bool = False
    custom_note: str | None = None


class SubmitQuestionResponseRequest(BaseModel):
    prompt_id: str
    answers: list[QuestionAnswerRequest] = Field(default_factory=list)


class LiveSessionInputRequest(BaseModel):
    text: str = ""
    file_paths: list[str] = Field(default_factory=list)
    image_paths: list[str] = Field(default_factory=list)
    image_upload_ids: list[str] = Field(default_factory=list)
    profile_id: str | None = None
    interactive_mode: bool = False


class LiveSessionShellCommandRequest(BaseModel):
    command: str = ""


class NewSessionRequest(BaseModel):
    profile_id: str | None = None


class LiveSessionResponse(BaseModel):
    session: LiveSessionModel


class SessionResponse(BaseModel):
    session: SessionRecordModel


class SessionImageUploadResponse(BaseModel):
    uploads: list[ImageAttachmentModel]


class MessagePartIdsModel(BaseModel):
    content: str
    file_paths: list[str] = Field(default_factory=list)
    image_attachments: list[str] = Field(default_factory=list)


class HistoryItemModel(BaseModel):
    item_id: str
    message_id: str
    part_ids: MessagePartIdsModel
    role: str
    content: str
    file_paths: list[str] = Field(default_factory=list)
    image_attachments: list[ImageAttachmentModel] = Field(default_factory=list)
    markdown: bool
    historical: bool
    created_at: str


class SessionDetailResponse(BaseModel):
    session: SessionRecordModel
    status: SessionLifecycleStatus = "idle"
    history_items: list[HistoryItemModel]
    timeline: LiveSessionSnapshotModel | None = None
    live_session: LiveSessionModel | None = None
    active_live_session: LiveSessionModel | None = None
    active_run: LiveSessionModel | None = None


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
    status: RunSessionStatus
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
    kind: str = "cli"
    task_id: str | None = None
    project_dir: str | None = None
    last_event_seq: int = 0
    snapshot: Any | None = None
    exit_code: int | None = None
    fatal_error: str | None = None
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
