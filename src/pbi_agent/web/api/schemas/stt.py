from __future__ import annotations

from pydantic import BaseModel


class SttTranscriptionResponse(BaseModel):
    text: str
