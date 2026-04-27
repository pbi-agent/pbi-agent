from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, File, Response, UploadFile
from fastapi.responses import FileResponse

from pbi_agent.config import ConfigError
from pbi_agent.providers.capabilities import provider_supports_images
from pbi_agent.web.api.deps import (
    LiveSessionIdPath,
    SessionManagerDep,
    UploadIdPath,
    model_from_payload,
)
from pbi_agent.web.api.errors import bad_request, config_http_error, not_found
from pbi_agent.web.api.schemas.live_sessions import (
    LiveSessionInputRequest,
    LiveSessionResponse,
    LiveSessionShellCommandRequest,
    CreateLiveSessionRequest,
    ExpandInputRequest,
    ExpandInputResponse,
    ImageUploadResponse,
    NewSessionRequest,
)
from pbi_agent.web.api.schemas.common import ImageAttachmentModel
from pbi_agent.web.api.schemas.config import ActiveProfileRequest
from pbi_agent.web.api.schemas.system import LiveSessionModel
from pbi_agent.web.input_mentions import expand_input_mentions
from pbi_agent.web.uploads import load_uploaded_image_record, uploaded_image_path

router = APIRouter(prefix="/api/live-sessions", tags=["live-sessions"])


@router.post("", response_model=LiveSessionResponse)
def create_live_session(
    request: CreateLiveSessionRequest,
    manager: SessionManagerDep,
) -> LiveSessionResponse:
    try:
        session = manager.create_live_session(
            session_id=request.session_id or request.resume_session_id,
            live_session_id=request.live_session_id,
            profile_id=request.profile_id,
        )
    except KeyError as exc:
        raise not_found("Session not found.") from exc
    except ConfigError as exc:
        raise config_http_error(exc) from exc
    except Exception as exc:
        raise bad_request(str(exc)) from exc
    return LiveSessionResponse(
        session=model_from_payload(LiveSessionModel, session),
    )


@router.post("/{live_session_id}/input", response_model=LiveSessionResponse)
def submit_session_input(
    live_session_id: LiveSessionIdPath,
    request: LiveSessionInputRequest,
    manager: SessionManagerDep,
) -> LiveSessionResponse:
    try:
        session = manager.submit_session_input(
            live_session_id,
            text=request.text,
            file_paths=request.file_paths,
            image_paths=request.image_paths,
            image_upload_ids=request.image_upload_ids,
            profile_id=request.profile_id,
        )
    except KeyError as exc:
        raise not_found("Live session not found.") from exc
    except ConfigError as exc:
        raise config_http_error(exc) from exc
    except Exception as exc:
        raise bad_request(str(exc)) from exc
    return LiveSessionResponse(
        session=model_from_payload(LiveSessionModel, session),
    )


@router.post("/{live_session_id}/shell-command", response_model=LiveSessionResponse)
def run_shell_command(
    live_session_id: LiveSessionIdPath,
    request: LiveSessionShellCommandRequest,
    manager: SessionManagerDep,
) -> LiveSessionResponse:
    try:
        session = manager.run_shell_command(
            live_session_id,
            command=request.command,
        )
    except KeyError as exc:
        raise not_found("Live session not found.") from exc
    except Exception as exc:
        raise bad_request(str(exc)) from exc
    return LiveSessionResponse(
        session=model_from_payload(LiveSessionModel, session),
    )


@router.post("/{live_session_id}/interrupt", response_model=LiveSessionResponse)
def interrupt_live_session(
    live_session_id: LiveSessionIdPath,
    manager: SessionManagerDep,
) -> LiveSessionResponse:
    try:
        session = manager.interrupt_live_session(live_session_id)
    except KeyError as exc:
        raise not_found("Live session not found.") from exc
    except Exception as exc:
        raise bad_request(str(exc)) from exc
    return LiveSessionResponse(
        session=model_from_payload(LiveSessionModel, session),
    )


@router.post(
    "/{live_session_id}/images",
    response_model=ImageUploadResponse,
)
async def upload_session_images(
    live_session_id: LiveSessionIdPath,
    manager: SessionManagerDep,
    files: Annotated[list[UploadFile], File(description="One or more image files")],
) -> ImageUploadResponse:
    try:
        uploads = manager.upload_session_images(
            live_session_id,
            files=[
                (upload.filename or "pasted-image.png", await upload.read())
                for upload in files
            ],
        )
    except KeyError as exc:
        raise not_found("Live session not found.") from exc
    except Exception as exc:
        raise bad_request(str(exc)) from exc
    return ImageUploadResponse(
        uploads=[model_from_payload(ImageAttachmentModel, upload) for upload in uploads]
    )


@router.post("/expand-input", response_model=ExpandInputResponse)
def expand_session_input(
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


@router.post(
    "/{live_session_id}/new-session",
    response_model=LiveSessionResponse,
)
def request_new_session(
    live_session_id: LiveSessionIdPath,
    request: NewSessionRequest,
    manager: SessionManagerDep,
) -> LiveSessionResponse:
    try:
        session = manager.request_new_session(
            live_session_id,
            profile_id=request.profile_id,
        )
    except KeyError as exc:
        raise not_found("Live session not found.") from exc
    except ConfigError as exc:
        raise config_http_error(exc) from exc
    except Exception as exc:
        raise bad_request(str(exc)) from exc
    return LiveSessionResponse(
        session=model_from_payload(LiveSessionModel, session),
    )


@router.put(
    "/{live_session_id}/profile",
    response_model=LiveSessionResponse,
)
def set_live_session_profile(
    live_session_id: LiveSessionIdPath,
    request: ActiveProfileRequest,
    manager: SessionManagerDep,
) -> LiveSessionResponse:
    try:
        session = manager.set_live_session_profile(
            live_session_id,
            profile_id=request.profile_id,
        )
    except KeyError as exc:
        raise not_found("Live session not found.") from exc
    except ConfigError as exc:
        raise config_http_error(exc) from exc
    except Exception as exc:
        raise bad_request(str(exc)) from exc
    return LiveSessionResponse(
        session=model_from_payload(LiveSessionModel, session),
    )


@router.get("/uploads/{upload_id}")
def get_uploaded_session_image(upload_id: UploadIdPath) -> Response:
    try:
        record = load_uploaded_image_record(upload_id)
    except KeyError as exc:
        raise not_found("Uploaded image not found.") from exc
    return FileResponse(uploaded_image_path(upload_id), media_type=record.mime_type)
