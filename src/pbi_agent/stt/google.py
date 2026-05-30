from __future__ import annotations

import base64
import json
import urllib.request
from pathlib import Path
from typing import Any

from pbi_agent.stt.base import ResolvedSttProvider, SttProviderError
from pbi_agent.stt.http_client import (
    json_response,
    request_headers,
    request_with_retry,
)
from pbi_agent.stt.registry import register_stt_backend

DEFAULT_GOOGLE_STT_MODEL = "gemini-3.5-flash"
GOOGLE_GENERATE_CONTENT_URL = (
    "https://generativelanguage.googleapis.com/v1beta/models/"
    f"{DEFAULT_GOOGLE_STT_MODEL}:generateContent"
)
GOOGLE_TRANSCRIPTION_PROMPT = 'Generate a transcript of the speech. Remove filler words (e.g. "uh", "um", "er") and return only the transcript text.'


class GoogleSttBackend:
    kind = "google"

    def transcribe(self, wav_path: Path, provider: ResolvedSttProvider) -> str:
        body = json.dumps(
            {
                "contents": [
                    {
                        "parts": [
                            {"text": GOOGLE_TRANSCRIPTION_PROMPT},
                            {
                                "inline_data": {
                                    "mime_type": "audio/wav",
                                    "data": base64.b64encode(
                                        wav_path.read_bytes()
                                    ).decode("ascii"),
                                }
                            },
                        ]
                    }
                ]
            },
            separators=(",", ":"),
        ).encode("utf-8")

        def request_factory() -> urllib.request.Request:
            return urllib.request.Request(
                GOOGLE_GENERATE_CONTENT_URL,
                data=body,
                headers=request_headers(
                    {
                        "x-goog-api-key": provider.api_key,
                        "Content-Type": "application/json",
                    }
                ),
                method="POST",
            )

        payload = json_response(
            request_with_retry(request_factory, provider_name="Google"),
            provider_name="Google",
        )
        return extract_transcript_text(payload)


def extract_transcript_text(payload: dict[str, Any]) -> str:
    candidates = payload.get("candidates")
    if not isinstance(candidates, list):
        raise SttProviderError("Google returned a response without candidates.")

    parts_text: list[str] = []
    for candidate in candidates:
        if not isinstance(candidate, dict):
            continue
        content = candidate.get("content")
        if not isinstance(content, dict):
            continue
        parts = content.get("parts")
        if not isinstance(parts, list):
            continue
        for part in parts:
            if not isinstance(part, dict):
                continue
            text = part.get("text")
            if isinstance(text, str) and text.strip():
                parts_text.append(text.strip())
    return "\n".join(parts_text)


register_stt_backend(GoogleSttBackend())
