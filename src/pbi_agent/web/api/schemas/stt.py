from __future__ import annotations

from typing import Literal

from pydantic import BaseModel


class SttTranscriptionResponse(BaseModel):
    text: str


class LocalSttStatusResponse(BaseModel):
    state: Literal["unsupported", "missing", "downloading", "ready", "failed"]
    downloaded_bytes: int
    total_bytes: int
    error: str | None
