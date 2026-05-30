from __future__ import annotations

from pathlib import Path
import urllib.request

from pbi_agent.stt.base import ResolvedSttProvider, SttProviderError
from pbi_agent.stt.http_client import (
    MultipartFile,
    encode_multipart_form_data,
    json_response,
    request_headers,
    request_with_retry,
)
from pbi_agent.stt.registry import register_stt_backend

OPENAI_TRANSCRIPTIONS_URL = "https://api.openai.com/v1/audio/transcriptions"
DEFAULT_OPENAI_STT_MODEL = "gpt-4o-transcribe"


class OpenAiSttBackend:
    kind = "openai"

    def transcribe(self, wav_path: Path, provider: ResolvedSttProvider) -> str:
        audio_bytes = wav_path.read_bytes()
        body, content_type = encode_multipart_form_data(
            fields={
                "model": DEFAULT_OPENAI_STT_MODEL,
                "response_format": "json",
            },
            files=[
                MultipartFile(
                    field_name="file",
                    filename=wav_path.name,
                    content_type="audio/wav",
                    content=audio_bytes,
                )
            ],
        )

        def request_factory() -> urllib.request.Request:
            return urllib.request.Request(
                OPENAI_TRANSCRIPTIONS_URL,
                data=body,
                headers=request_headers(
                    {
                        "Authorization": f"Bearer {provider.api_key}",
                        "Content-Type": content_type,
                    }
                ),
                method="POST",
            )

        payload = json_response(
            request_with_retry(request_factory, provider_name="OpenAI"),
            provider_name="OpenAI",
        )
        return extract_transcript_text(payload)


def extract_transcript_text(payload: dict[str, object]) -> str:
    text = payload.get("text")
    if isinstance(text, str):
        return text
    raise SttProviderError("OpenAI returned a response without transcript text.")


register_stt_backend(OpenAiSttBackend())
