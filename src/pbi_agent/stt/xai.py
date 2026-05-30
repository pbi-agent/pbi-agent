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

XAI_STT_URL = "https://api.x.ai/v1/stt"


class XaiSttBackend:
    kind = "xai"

    def transcribe(self, wav_path: Path, provider: ResolvedSttProvider) -> str:
        audio_bytes = wav_path.read_bytes()
        body, content_type = encode_multipart_form_data(
            fields={},
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
                XAI_STT_URL,
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
            request_with_retry(request_factory, provider_name="xAI"),
            provider_name="xAI",
        )
        return extract_transcript_text(payload)


def extract_transcript_text(payload: dict[str, object]) -> str:
    text = payload.get("text")
    if isinstance(text, str):
        return text
    raise SttProviderError("xAI returned a response without transcript text.")


register_stt_backend(XaiSttBackend())
