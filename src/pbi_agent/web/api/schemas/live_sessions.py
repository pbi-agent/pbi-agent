from __future__ import annotations

from pydantic import BaseModel, Field

from pbi_agent.web.api.schemas.common import ImageAttachmentModel
from pbi_agent.web.api.schemas.system import LiveSessionModel


class CreateLiveSessionRequest(BaseModel):
    session_id: str | None = None
    resume_session_id: str | None = None
    live_session_id: str | None = None
    profile_id: str | None = None


class LiveSessionInputRequest(BaseModel):
    text: str = ""
    file_paths: list[str] = Field(default_factory=list)
    image_paths: list[str] = Field(default_factory=list)
    image_upload_ids: list[str] = Field(default_factory=list)
    profile_id: str | None = None


class NewSessionRequest(BaseModel):
    profile_id: str | None = None


class ExpandInputRequest(BaseModel):
    text: str = ""


class ExpandInputResponse(BaseModel):
    text: str
    file_paths: list[str] = Field(default_factory=list)
    image_paths: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class ImageUploadResponse(BaseModel):
    uploads: list[ImageAttachmentModel]


class LiveSessionResponse(BaseModel):
    session: LiveSessionModel
