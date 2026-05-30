from __future__ import annotations

from pathlib import Path
from typing import Any
import urllib.request

from pbi_agent.stt.audio import (
    convert_wav_to_pcm_s16le_16k_mono,
)
from pbi_agent.stt.base import ResolvedSttProvider
from pbi_agent.stt.http_client import (
    MultipartFile,
    encode_multipart_form_data,
    json_response,
    request_headers,
    request_with_retry,
)
from pbi_agent.stt.registry import register_stt_backend

ELEVENLABS_STT_URL = "https://api.elevenlabs.io/v1/speech-to-text"
DEFAULT_ELEVENLABS_STT_MODEL = "scribe_v2"


class ElevenLabsSttBackend:
    kind = "elevenlabs"

    def transcribe(self, wav_path: Path, provider: ResolvedSttProvider) -> str:
        pcm_path = wav_path.with_suffix(".pcm")
        convert_wav_to_pcm_s16le_16k_mono(wav_path, pcm_path)
        pcm_bytes = pcm_path.read_bytes()
        body, content_type = encode_multipart_form_data(
            fields={
                "model_id": DEFAULT_ELEVENLABS_STT_MODEL,
                "file_format": "pcm_s16le_16",
                "timestamps_granularity": "none",
                "diarize": "false",
                "tag_audio_events": "false",
                "no_verbatim": "true",
            },
            files=[
                MultipartFile(
                    field_name="file",
                    filename=pcm_path.name,
                    content_type="application/octet-stream",
                    content=pcm_bytes,
                )
            ],
        )

        def request_factory() -> urllib.request.Request:
            return urllib.request.Request(
                ELEVENLABS_STT_URL,
                data=body,
                headers=request_headers(
                    {
                        "xi-api-key": provider.api_key,
                        "Content-Type": content_type,
                    }
                ),
                method="POST",
            )

        payload = json_response(
            request_with_retry(request_factory, provider_name="ElevenLabs"),
            provider_name="ElevenLabs",
        )
        return extract_transcript_text(payload)


def extract_transcript_text(payload: dict[str, Any]) -> str:
    text = payload.get("text")
    if isinstance(text, str):
        return text

    transcripts = payload.get("transcripts")
    if isinstance(transcripts, list):
        return "\n".join(_transcript_texts(transcripts))
    if isinstance(transcripts, dict):
        return "\n".join(_transcript_texts(transcripts.values()))

    transcript = payload.get("transcript")
    if isinstance(transcript, str):
        return transcript
    return ""


def _transcript_texts(items: Any) -> list[str]:
    parts: list[str] = []
    for item in items:
        if isinstance(item, dict):
            text = item.get("text")
            if isinstance(text, str) and text.strip():
                parts.append(text.strip())
    return parts


register_stt_backend(ElevenLabsSttBackend())
