from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

from pbi_agent.web.api.schemas.common import ImageAttachmentModel
from pbi_agent.web.api.schemas.system import (
    LiveSessionModel,
    MessagePartIdsModel,
    PendingUserQuestionsModel,
    ProcessingStateModel,
    SessionRecordModel,
)
from pbi_agent.web.api.schemas.tasks import BoardStageModel, TaskRecordModel


class EmptyPayloadModel(BaseModel):
    pass


class EventIdentityPayloadModel(BaseModel):
    live_session_id: str | None = None
    session_id: str | None = None
    resume_session_id: str | None = None


class SseEventBaseModel(BaseModel):
    seq: int
    created_at: str


class ServerConnectedSseEventModel(SseEventBaseModel):
    type: Literal["server.connected"]
    payload: EmptyPayloadModel


class ServerHeartbeatSseEventModel(SseEventBaseModel):
    type: Literal["server.heartbeat"]
    payload: EmptyPayloadModel


class ServerReplayIncompleteSseEventPayloadModel(BaseModel):
    reason: Literal["cursor_too_old", "cursor_ahead", "subscriber_queue_overflow"]
    requested_since: int
    resolved_since: int
    oldest_available_seq: int | None = None
    latest_seq: int
    snapshot_required: bool


class ServerReplayIncompleteSseEventModel(SseEventBaseModel):
    type: Literal["server.replay_incomplete"]
    payload: ServerReplayIncompleteSseEventPayloadModel


class SessionResetSseEventModel(SseEventBaseModel):
    type: Literal["session_reset"]
    payload: EmptyPayloadModel


class SessionIdentitySseEventPayloadModel(EventIdentityPayloadModel):
    pass


class SessionIdentitySseEventModel(SseEventBaseModel):
    type: Literal["session_identity"]
    payload: SessionIdentitySseEventPayloadModel


class InputStateSseEventPayloadModel(EventIdentityPayloadModel):
    enabled: bool


class InputStateSseEventModel(SseEventBaseModel):
    type: Literal["input_state"]
    payload: InputStateSseEventPayloadModel


class WaitStateSseEventPayloadModel(EventIdentityPayloadModel):
    active: bool
    message: str | None = None


class WaitStateSseEventModel(SseEventBaseModel):
    type: Literal["wait_state"]
    payload: WaitStateSseEventPayloadModel


class ProcessingStateSseEventModel(SseEventBaseModel):
    type: Literal["processing_state"]
    payload: ProcessingStateModel


class UserQuestionsRequestedSseEventModel(SseEventBaseModel):
    type: Literal["user_questions_requested"]
    payload: PendingUserQuestionsModel


class UserQuestionsResolvedSseEventPayloadModel(EventIdentityPayloadModel):
    prompt_id: str


class UserQuestionsResolvedSseEventModel(SseEventBaseModel):
    type: Literal["user_questions_resolved"]
    payload: UserQuestionsResolvedSseEventPayloadModel


class TokenUsagePayloadModel(BaseModel):
    input_tokens: int
    cached_input_tokens: int
    cache_write_tokens: int
    cache_write_1h_tokens: int
    output_tokens: int
    reasoning_tokens: int
    tool_use_tokens: int
    provider_total_tokens: int
    sub_agent_input_tokens: int
    sub_agent_output_tokens: int
    sub_agent_reasoning_tokens: int
    sub_agent_tool_use_tokens: int
    sub_agent_provider_total_tokens: int
    sub_agent_cost_usd: float
    context_tokens: int
    total_tokens: int
    estimated_cost_usd: float
    main_agent_total_tokens: int
    sub_agent_total_tokens: int
    model: str
    service_tier: str


class UsageUpdatedSseEventPayloadModel(EventIdentityPayloadModel):
    scope: Literal["session", "turn"]
    usage: TokenUsagePayloadModel
    elapsed_seconds: float | None = None
    sub_agent_id: str | None = None


class UsageUpdatedSseEventModel(SseEventBaseModel):
    type: Literal["usage_updated"]
    payload: UsageUpdatedSseEventPayloadModel


MessageRole = Literal["user", "assistant", "notice", "error", "debug"]


class MessageAddedSseEventPayloadModel(EventIdentityPayloadModel):
    item_id: str
    role: MessageRole
    content: str
    markdown: bool = False
    message_id: str | None = None
    part_ids: MessagePartIdsModel | None = None
    file_paths: list[str] = Field(default_factory=list)
    image_attachments: list[ImageAttachmentModel] = Field(default_factory=list)
    historical: bool | None = None
    created_at: str | None = None
    sub_agent_id: str | None = None


class MessageAddedSseEventModel(SseEventBaseModel):
    type: Literal["message_added"]
    payload: MessageAddedSseEventPayloadModel


class MessageRekeyedSseEventPayloadModel(EventIdentityPayloadModel):
    old_item_id: str
    item: MessageAddedSseEventPayloadModel


class MessageRekeyedSseEventModel(SseEventBaseModel):
    type: Literal["message_rekeyed"]
    payload: MessageRekeyedSseEventPayloadModel


class MessageRemovedSseEventPayloadModel(EventIdentityPayloadModel):
    item_id: str
    restore_input: str | None = None


class MessageRemovedSseEventModel(SseEventBaseModel):
    type: Literal["message_removed"]
    payload: MessageRemovedSseEventPayloadModel


class ThinkingUpdatedSseEventPayloadModel(EventIdentityPayloadModel):
    item_id: str
    title: str
    content: str
    sub_agent_id: str | None = None


class ThinkingUpdatedSseEventModel(SseEventBaseModel):
    type: Literal["thinking_updated"]
    payload: ThinkingUpdatedSseEventPayloadModel


class DiffLineNumberModel(BaseModel):
    old: int | None = None
    new: int | None = None


class ToolCallMetadataModel(BaseModel):
    tool_name: str | None = None
    path: str | None = None
    operation: str | None = None
    success: bool | None = None
    detail: str | None = None
    diff: str | None = None
    diff_line_numbers: list[DiffLineNumberModel] | None = None
    call_id: str | None = None
    status: Literal["running", "completed", "failed"] | None = None
    arguments: dict[str, Any] | str | None = None
    result: dict[str, Any] | str | None = None
    error: Any = None
    command: str | None = None
    working_directory: str | None = None
    timeout_ms: int | str | None = None
    exit_code: int | None = None
    timed_out: bool | None = None


class ToolGroupEntryModel(BaseModel):
    text: str
    classes: str = ""
    metadata: ToolCallMetadataModel | None = None


class ToolGroupAddedSseEventPayloadModel(EventIdentityPayloadModel):
    item_id: str
    label: str
    status: Literal["running", "completed"] | None = None
    items: list[ToolGroupEntryModel] = Field(default_factory=list)
    sub_agent_id: str | None = None


class ToolGroupAddedSseEventModel(SseEventBaseModel):
    type: Literal["tool_group_added"]
    payload: ToolGroupAddedSseEventPayloadModel


class SubAgentStateSseEventPayloadModel(EventIdentityPayloadModel):
    sub_agent_id: str
    title: str
    status: str


class SubAgentStateSseEventModel(SseEventBaseModel):
    type: Literal["sub_agent_state"]
    payload: SubAgentStateSseEventPayloadModel


class SessionStateSseEventPayloadModel(EventIdentityPayloadModel):
    state: Literal["starting", "running", "ended"]
    exit_code: int | None = None
    fatal_error: str | None = None


class SessionStateSseEventModel(SseEventBaseModel):
    type: Literal["session_state"]
    payload: SessionStateSseEventPayloadModel


class SessionRuntimeUpdatedSseEventPayloadModel(EventIdentityPayloadModel):
    provider_id: str | None = None
    profile_id: str | None = None
    provider: str
    model: str
    reasoning_effort: str
    compact_threshold: int


class SessionRuntimeUpdatedSseEventModel(SseEventBaseModel):
    type: Literal["session_runtime_updated"]
    payload: SessionRuntimeUpdatedSseEventPayloadModel


class WelcomeSseEventPayloadModel(EventIdentityPayloadModel):
    interactive: bool
    model: str | None = None
    reasoning_effort: str | None = None
    single_turn_hint: str | None = None


class WelcomeSseEventModel(SseEventBaseModel):
    type: Literal["welcome"]
    payload: WelcomeSseEventPayloadModel


class SessionCreatedSseEventPayloadModel(BaseModel):
    session: SessionRecordModel


class SessionCreatedSseEventModel(SseEventBaseModel):
    type: Literal["session_created"]
    payload: SessionCreatedSseEventPayloadModel


class SessionUpdatedSseEventPayloadModel(BaseModel):
    session: SessionRecordModel


class SessionUpdatedSseEventModel(SseEventBaseModel):
    type: Literal["session_updated"]
    payload: SessionUpdatedSseEventPayloadModel


class BoardStagesUpdatedSseEventPayloadModel(BaseModel):
    board_stages: list[BoardStageModel]


class BoardStagesUpdatedSseEventModel(SseEventBaseModel):
    type: Literal["board_stages_updated"]
    payload: BoardStagesUpdatedSseEventPayloadModel


class TaskUpdatedSseEventPayloadModel(BaseModel):
    task: TaskRecordModel


class TaskUpdatedSseEventModel(SseEventBaseModel):
    type: Literal["task_updated"]
    payload: TaskUpdatedSseEventPayloadModel


class TaskDeletedSseEventPayloadModel(BaseModel):
    task_id: str


class TaskDeletedSseEventModel(SseEventBaseModel):
    type: Literal["task_deleted"]
    payload: TaskDeletedSseEventPayloadModel


class LiveSessionLifecycleSseEventPayloadModel(BaseModel):
    live_session: LiveSessionModel


class LiveSessionStartedSseEventModel(SseEventBaseModel):
    type: Literal["live_session_started"]
    payload: LiveSessionLifecycleSseEventPayloadModel


class LiveSessionUpdatedSseEventModel(SseEventBaseModel):
    type: Literal["live_session_updated"]
    payload: LiveSessionLifecycleSseEventPayloadModel


class LiveSessionBoundSseEventModel(SseEventBaseModel):
    type: Literal["live_session_bound"]
    payload: LiveSessionLifecycleSseEventPayloadModel


class LiveSessionEndedSseEventModel(SseEventBaseModel):
    type: Literal["live_session_ended"]
    payload: LiveSessionLifecycleSseEventPayloadModel


CONTROL_SSE_EVENT_MODELS = [
    ServerConnectedSseEventModel,
    ServerHeartbeatSseEventModel,
    ServerReplayIncompleteSseEventModel,
]

SESSION_SSE_EVENT_MODELS = [
    SessionResetSseEventModel,
    SessionIdentitySseEventModel,
    InputStateSseEventModel,
    WaitStateSseEventModel,
    ProcessingStateSseEventModel,
    UserQuestionsRequestedSseEventModel,
    UserQuestionsResolvedSseEventModel,
    UsageUpdatedSseEventModel,
    MessageAddedSseEventModel,
    MessageRekeyedSseEventModel,
    MessageRemovedSseEventModel,
    ThinkingUpdatedSseEventModel,
    ToolGroupAddedSseEventModel,
    SubAgentStateSseEventModel,
    SessionStateSseEventModel,
    SessionRuntimeUpdatedSseEventModel,
    WelcomeSseEventModel,
]

APP_SSE_EVENT_MODELS = [
    SessionCreatedSseEventModel,
    SessionUpdatedSseEventModel,
    BoardStagesUpdatedSseEventModel,
    TaskUpdatedSseEventModel,
    TaskDeletedSseEventModel,
    LiveSessionStartedSseEventModel,
    LiveSessionUpdatedSseEventModel,
    LiveSessionBoundSseEventModel,
    LiveSessionEndedSseEventModel,
]

EXTRA_API_TYPE_MODELS = [
    *CONTROL_SSE_EVENT_MODELS,
    *SESSION_SSE_EVENT_MODELS,
    *APP_SSE_EVENT_MODELS,
]

API_TYPE_ALIASES = {
    "SseControlEventModel": [model.__name__ for model in CONTROL_SSE_EVENT_MODELS],
    "SessionSseEventModel": [model.__name__ for model in SESSION_SSE_EVENT_MODELS],
    "AppSseEventModel": [model.__name__ for model in APP_SSE_EVENT_MODELS],
    "SseEventModel": [
        model.__name__
        for model in [
            *CONTROL_SSE_EVENT_MODELS,
            *SESSION_SSE_EVENT_MODELS,
            *APP_SSE_EVENT_MODELS,
        ]
    ],
}
