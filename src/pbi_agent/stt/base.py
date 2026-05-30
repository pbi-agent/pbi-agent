from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol


DEFAULT_STT_HTTP_TIMEOUT_SECONDS = 300.0
DEFAULT_STT_MAX_RETRIES = 2


class SttError(RuntimeError):
    """Base error for speech-to-text backend failures."""

    status_code = 500

    def __init__(self, message: str, *, status_code: int | None = None) -> None:
        super().__init__(message)
        if status_code is not None:
            self.status_code = status_code


class SttConfigurationError(SttError):
    """Raised when STT provider configuration is missing or invalid."""

    status_code = 400


class SttInputError(SttError):
    """Raised when the uploaded audio cannot be accepted."""

    status_code = 400


class SttProviderError(SttError):
    """Raised when a configured STT provider fails."""

    status_code = 502


@dataclass(frozen=True, slots=True)
class ResolvedSttProvider:
    provider_id: str
    kind: str
    api_key: str


class SttBackend(Protocol):
    kind: str

    def transcribe(self, wav_path: Path, provider: ResolvedSttProvider) -> str:
        """Transcribe a validated WAV file and return transcript text."""
        ...
