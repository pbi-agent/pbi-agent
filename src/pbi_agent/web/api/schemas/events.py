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


class UsageUpdatedSseEventPayloadModel(EventIdentityPayloadModel):
    scope: Literal["session", "turn"]
    usage: dict[str, Any]
    elapsed_seconds: float | None = None
    sub_agent_id: str | None = None


class UsageUpdatedSseEventModel(SseEventBaseModel):
    type: Literal["usage_updated"]
    payload: UsageUpdatedSseEventPayloadModel


class MessageAddedSseEventPayloadModel(EventIdentityPayloadModel):
    item_id: str
    role: str
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


class ToolGroupEntryModel(BaseModel):
    text: str
    classes: str = ""
    metadata: dict[str, Any] | None = None


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
