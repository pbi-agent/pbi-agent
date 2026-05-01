from __future__ import annotations

from pydantic import BaseModel


class ImageAttachmentModel(BaseModel):
    upload_id: str
    name: str
    mime_type: str
    byte_count: int
    preview_url: str


class RuntimeSummaryModel(BaseModel):
    provider: str | None
    provider_id: str | None
    profile_id: str | None
    model: str | None
    reasoning_effort: str | None
    compact_threshold: int | None = None
