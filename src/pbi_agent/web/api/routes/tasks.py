from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, File, Response, UploadFile

from pbi_agent.config import ConfigError
from pbi_agent.web.api.deps import SessionManagerDep, TaskIdPath, model_from_payload
from pbi_agent.web.api.errors import bad_request, config_http_error, not_found
from pbi_agent.web.api.schemas.tasks import (
    CreateTaskRequest,
    TaskImageUploadResponse,
    TaskRecordModel,
    TaskResponse,
    TasksResponse,
    UpdateTaskRequest,
)
from pbi_agent.web.api.schemas.common import ImageAttachmentModel

router = APIRouter(prefix="/api/tasks", tags=["tasks"])


@router.post("/images", response_model=TaskImageUploadResponse)
async def upload_task_images(
    manager: SessionManagerDep,
    files: Annotated[list[UploadFile], File(description="One or more image files")],
) -> TaskImageUploadResponse:
    try:
        uploads = manager.upload_task_images(
            files=[
                (upload.filename or "task-image.png", await upload.read())
                for upload in files
            ],
        )
    except Exception as exc:
        raise bad_request(str(exc)) from exc
    return TaskImageUploadResponse(
        uploads=[model_from_payload(ImageAttachmentModel, upload) for upload in uploads]
    )


@router.get("", response_model=TasksResponse)
def list_tasks(manager: SessionManagerDep) -> TasksResponse:
    return TasksResponse(
        tasks=[
            model_from_payload(TaskRecordModel, item) for item in manager.list_tasks()
        ]
    )


@router.post("", response_model=TaskResponse)
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
            image_upload_ids=request.image_upload_ids,
        )
    except ConfigError as exc:
        raise config_http_error(exc) from exc
    except Exception as exc:
        raise bad_request(str(exc)) from exc
    return TaskResponse(task=model_from_payload(TaskRecordModel, task))


@router.patch("/{task_id}", response_model=TaskResponse)
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
            image_upload_ids=request.image_upload_ids,
            image_upload_ids_present="image_upload_ids" in request.model_fields_set,
        )
    except KeyError as exc:
        raise not_found("Task not found.") from exc
    except ConfigError as exc:
        raise config_http_error(exc) from exc
    except Exception as exc:
        raise bad_request(str(exc)) from exc
    return TaskResponse(task=model_from_payload(TaskRecordModel, task))


@router.delete("/{task_id}", status_code=204)
def delete_task(
    task_id: TaskIdPath,
    manager: SessionManagerDep,
) -> Response:
    try:
        manager.delete_task(task_id)
    except KeyError as exc:
        raise not_found("Task not found.") from exc
    except Exception as exc:
        raise bad_request(str(exc)) from exc
    return Response(status_code=204)


@router.post("/{task_id}/run", response_model=TaskResponse)
def run_task(
    task_id: TaskIdPath,
    manager: SessionManagerDep,
) -> TaskResponse:
    try:
        task = manager.run_task(task_id)
    except KeyError as exc:
        raise not_found("Task not found.") from exc
    except ConfigError as exc:
        raise config_http_error(exc) from exc
    except Exception as exc:
        raise bad_request(str(exc)) from exc
    return TaskResponse(task=model_from_payload(TaskRecordModel, task))
