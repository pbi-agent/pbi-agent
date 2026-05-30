from __future__ import annotations

from pathlib import Path
from typing import Any
import urllib.request

from pbi_agent.stt.base import ResolvedSttProvider
from pbi_agent.stt.http_client import (
    json_response,
    request_headers,
    request_with_retry,
)
from pbi_agent.stt.registry import register_stt_backend

DEEPGRAM_LISTEN_URL = (
    "https://api.deepgram.com/v1/listen?model=nova-3&smart_format=true"
)


class DeepgramSttBackend:
    kind = "deepgram"

    def transcribe(self, wav_path: Path, provider: ResolvedSttProvider) -> str:
        audio_bytes = wav_path.read_bytes()

        def request_factory() -> urllib.request.Request:
            return urllib.request.Request(
                DEEPGRAM_LISTEN_URL,
                data=audio_bytes,
                headers=request_headers(
                    {
                        "Authorization": f"Token {provider.api_key}",
                        "Content-Type": "audio/wav",
                    }
                ),
                method="POST",
            )

        payload = json_response(
            request_with_retry(request_factory, provider_name="Deepgram"),
            provider_name="Deepgram",
        )
        return extract_transcript_text(payload)


def extract_transcript_text(payload: dict[str, Any]) -> str:
    results = payload.get("results")
    if not isinstance(results, dict):
        return ""
    channels = results.get("channels")
    if not isinstance(channels, list):
        return ""

    transcripts: list[str] = []
    for channel in channels:
        if not isinstance(channel, dict):
            continue
        alternatives = channel.get("alternatives")
        if not isinstance(alternatives, list) or not alternatives:
            continue
        first = alternatives[0]
        if not isinstance(first, dict):
            continue
        transcript = first.get("transcript")
        if isinstance(transcript, str) and transcript.strip():
            transcripts.append(transcript.strip())
    return "\n".join(transcripts)


register_stt_backend(DeepgramSttBackend())
