from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, Field

from pbi_agent.web.api.deps import NonEmptyString
from pbi_agent.web.api.schemas.common import ImageAttachmentModel, RuntimeSummaryModel

RunStatus = Literal["idle", "running", "completed", "failed"]


class CreateTaskRequest(BaseModel):
    title: NonEmptyString
    prompt: NonEmptyString
    stage: str | None = None
    project_dir: str = "."
    session_id: str | None = None
    profile_id: str | None = None
    image_upload_ids: list[str] = Field(default_factory=list)


class UpdateTaskRequest(BaseModel):
    title: NonEmptyString | None = None
    prompt: NonEmptyString | None = None
    stage: str | None = None
    position: Annotated[int, Field(ge=0)] | None = None
    project_dir: str | None = None
    session_id: str | None = None
    profile_id: str | None = None
    image_upload_ids: list[str] | None = None


class BoardStageModel(BaseModel):
    id: str
    name: str
    position: int
    profile_id: str | None = None
    command_id: str | None = None
    auto_start: bool


class BoardStageUpdateModel(BaseModel):
    id: str | None = None
    name: NonEmptyString
    profile_id: str | None = None
    command_id: str | None = None
    auto_start: bool = False


class BoardStagesResponse(BaseModel):
    board_stages: list[BoardStageModel]


class UpdateBoardStagesRequest(BaseModel):
    board_stages: list[BoardStageUpdateModel]


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
    image_attachments: list[ImageAttachmentModel] = Field(default_factory=list)
    runtime_summary: RuntimeSummaryModel


class TaskImageUploadResponse(BaseModel):
    uploads: list[ImageAttachmentModel]


class TasksResponse(BaseModel):
    tasks: list[TaskRecordModel]


class TaskResponse(BaseModel):
    task: TaskRecordModel
