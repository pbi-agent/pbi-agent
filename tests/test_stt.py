from __future__ import annotations

import io
import json
import urllib.error
import urllib.request
import wave
from email.message import Message
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient
import pytest

from pbi_agent.config import (
    InternalConfig,
    ProviderConfig,
    Settings,
    WebConfig,
    create_provider_config,
    save_internal_config,
    select_stt_provider,
)
from pbi_agent.stt import http_client
from pbi_agent.stt.audio import (
    convert_wav_to_pcm_s16le_16k_mono,
    convert_wav_to_wav_s16le_16k_mono,
)
from pbi_agent.stt.elevenlabs import extract_transcript_text as extract_elevenlabs_text
from pbi_agent.web.serve import create_app


class _FakeResponse:
    def __init__(self, payload: dict[str, Any], *, status: int = 200) -> None:
        self.status = status
        self.code = status
        self._body = json.dumps(payload).encode("utf-8")

    def read(self) -> bytes:
        return self._body

    def __enter__(self) -> "_FakeResponse":
        return self

    def __exit__(self, *args: object) -> None:
        return None


def _settings() -> Settings:
    return Settings(api_key="test-key", provider="openai", model="gpt-5.4")


def _wav_bytes(
    *,
    channels: int = 1,
    sample_rate: int = 16_000,
    frames: int = 1_600,
) -> bytes:
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as wav:
        wav.setnchannels(channels)
        wav.setsampwidth(2)
        wav.setframerate(sample_rate)
        wav.writeframes(b"\x00\x00" * frames * channels)
    return buffer.getvalue()


def _write_wav(path: Path, *, channels: int = 1, frames: int = 1_600) -> None:
    path.write_bytes(_wav_bytes(channels=channels, frames=frames))


def _wav_info(data: bytes) -> tuple[int, int, int]:
    with wave.open(io.BytesIO(data), "rb") as wav:
        return wav.getnchannels(), wav.getframerate(), wav.getnframes()


def _select_provider(provider: ProviderConfig) -> None:
    create_provider_config(provider)
    select_stt_provider(provider.id)


def _post_wav(client: TestClient, data: bytes | None = None) -> Any:
    return client.post(
        "/api/stt/transcribe",
        files={
            "file": (
                "audio.wav",
                data if data is not None else _wav_bytes(),
                "audio/wav",
            )
        },
    )


def _headers(request: urllib.request.Request) -> dict[str, str]:
    return {key.lower(): value for key, value in request.header_items()}


def test_stt_openai_request_shape_and_transcript(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _select_provider(
        ProviderConfig(
            id="openai-stt", name="OpenAI STT", kind="openai", api_key="oa-key"
        )
    )
    calls: list[urllib.request.Request] = []

    def fake_urlopen(request: urllib.request.Request, timeout: float) -> _FakeResponse:
        del timeout
        calls.append(request)
        return _FakeResponse({"text": "hello from openai"})

    monkeypatch.setattr(http_client, "urlopen", fake_urlopen)
    app = create_app(_settings())

    with TestClient(app) as client:
        response = _post_wav(client)

    assert response.status_code == 200
    assert response.json() == {"text": "hello from openai"}
    assert len(calls) == 1
    request = calls[0]
    headers = _headers(request)
    assert request.full_url == "https://api.openai.com/v1/audio/transcriptions"
    assert headers["authorization"] == "Bearer oa-key"
    assert headers["content-type"].startswith("multipart/form-data; boundary=")
    body = request.data
    assert isinstance(body, bytes)
    assert b'name="model"\r\n\r\ngpt-4o-transcribe' in body
    assert b'name="response_format"\r\n\r\njson' in body
    assert b'name="file"; filename="upload.wav"' in body
    assert b"Content-Type: audio/wav" in body


def test_stt_deepgram_request_shape_and_channel_join(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    wav_bytes = _wav_bytes(channels=2, sample_rate=8_000, frames=800)
    _select_provider(
        ProviderConfig(
            id="deepgram", name="Deepgram", kind="deepgram", api_key="dg-key"
        )
    )
    calls: list[urllib.request.Request] = []

    def fake_urlopen(request: urllib.request.Request, timeout: float) -> _FakeResponse:
        del timeout
        calls.append(request)
        return _FakeResponse(
            {
                "results": {
                    "channels": [
                        {"alternatives": [{"transcript": "first channel"}]},
                        {"alternatives": [{"transcript": "second channel"}]},
                    ]
                }
            }
        )

    monkeypatch.setattr(http_client, "urlopen", fake_urlopen)
    app = create_app(_settings())

    with TestClient(app) as client:
        response = _post_wav(client, wav_bytes)

    assert response.status_code == 200
    assert response.json() == {"text": "first channel\nsecond channel"}
    request = calls[0]
    headers = _headers(request)
    assert request.full_url == (
        "https://api.deepgram.com/v1/listen?model=nova-3&smart_format=true"
    )
    assert headers["authorization"] == "Token dg-key"
    assert headers["content-type"] == "audio/wav"
    assert isinstance(request.data, bytes)
    assert request.data != wav_bytes
    channels, sample_rate, frames = _wav_info(request.data)
    assert channels == 1
    assert sample_rate == 16_000
    assert frames == 1_600


def test_stt_elevenlabs_request_shape_and_transcript_collection(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _select_provider(
        ProviderConfig(
            id="elevenlabs",
            name="ElevenLabs",
            kind="elevenlabs",
            api_key="el-key",
        )
    )
    calls: list[urllib.request.Request] = []

    def fake_urlopen(request: urllib.request.Request, timeout: float) -> _FakeResponse:
        del timeout
        calls.append(request)
        return _FakeResponse({"transcripts": [{"text": "alpha"}, {"text": "beta"}]})

    monkeypatch.setattr(http_client, "urlopen", fake_urlopen)
    app = create_app(_settings())

    with TestClient(app) as client:
        response = _post_wav(client, _wav_bytes(channels=2, sample_rate=8_000))

    assert response.status_code == 200
    assert response.json() == {"text": "alpha\nbeta"}
    request = calls[0]
    headers = _headers(request)
    assert request.full_url == "https://api.elevenlabs.io/v1/speech-to-text"
    assert headers["xi-api-key"] == "el-key"
    assert headers["content-type"].startswith("multipart/form-data; boundary=")
    body = request.data
    assert isinstance(body, bytes)
    assert b'name="model_id"\r\n\r\nscribe_v2' in body
    assert b'name="file_format"\r\n\r\npcm_s16le_16' in body
    assert b'name="timestamps_granularity"\r\n\r\nnone' in body
    assert b'name="diarize"\r\n\r\nfalse' in body
    assert b'name="tag_audio_events"\r\n\r\nfalse' in body
    assert b"Content-Type: application/octet-stream" in body
    assert b"RIFF" not in body


def test_stt_missing_selected_provider_rejected() -> None:
    app = create_app(_settings())

    with TestClient(app) as client:
        response = _post_wav(client)

    assert response.status_code == 400
    assert "No speech-to-text provider configured" in response.json()["detail"]


def test_stt_missing_api_key_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DEEPGRAM_API_KEY", raising=False)
    _select_provider(ProviderConfig(id="deepgram", name="Deepgram", kind="deepgram"))
    app = create_app(_settings())

    with TestClient(app) as client:
        response = _post_wav(client)

    assert response.status_code == 400
    assert "Missing API key" in response.json()["detail"]


def test_stt_unsupported_selected_provider_rejected() -> None:
    provider = ProviderConfig(
        id="generic", name="Generic", kind="generic", api_key="key"
    )
    provider.validate()
    save_internal_config(
        InternalConfig(
            providers=[provider],
            web=WebConfig(stt_provider_id="generic"),
        )
    )
    app = create_app(_settings())

    with TestClient(app) as client:
        response = _post_wav(client)

    assert response.status_code == 400
    assert "does not support speech-to-text" in response.json()["detail"]


def test_stt_rejects_non_wav_upload(monkeypatch: pytest.MonkeyPatch) -> None:
    _select_provider(
        ProviderConfig(
            id="openai-stt", name="OpenAI STT", kind="openai", api_key="oa-key"
        )
    )

    def fail_urlopen(request: urllib.request.Request, timeout: float) -> _FakeResponse:
        raise AssertionError("Provider HTTP should not be called")

    monkeypatch.setattr(http_client, "urlopen", fail_urlopen)
    app = create_app(_settings())

    with TestClient(app) as client:
        response = client.post(
            "/api/stt/transcribe",
            files={"file": ("audio.txt", b"not a wav", "text/plain")},
        )

    assert response.status_code == 400
    assert "WAV" in response.json()["detail"]


def test_stt_retries_transient_provider_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _select_provider(
        ProviderConfig(
            id="openai-stt", name="OpenAI STT", kind="openai", api_key="oa-key"
        )
    )
    attempts = 0
    sleeps: list[float] = []

    def fake_urlopen(request: urllib.request.Request, timeout: float) -> _FakeResponse:
        nonlocal attempts
        del timeout
        attempts += 1
        if attempts == 1:
            raise urllib.error.HTTPError(
                request.full_url,
                503,
                "Service Unavailable",
                hdrs=Message(),
                fp=io.BytesIO(b"temporary"),
            )
        return _FakeResponse({"text": "after retry"})

    monkeypatch.setattr(http_client, "urlopen", fake_urlopen)
    monkeypatch.setattr(http_client, "sleep", sleeps.append)
    app = create_app(_settings())

    with TestClient(app) as client:
        response = _post_wav(client)

    assert response.status_code == 200
    assert response.json() == {"text": "after retry"}
    assert attempts == 2
    assert sleeps == [0.1]


def test_stt_empty_transcript_returns_blank(monkeypatch: pytest.MonkeyPatch) -> None:
    _select_provider(
        ProviderConfig(
            id="openai-stt", name="OpenAI STT", kind="openai", api_key="oa-key"
        )
    )

    def fake_urlopen(request: urllib.request.Request, timeout: float) -> _FakeResponse:
        del request, timeout
        return _FakeResponse({"text": "  "})

    monkeypatch.setattr(http_client, "urlopen", fake_urlopen)
    app = create_app(_settings())

    with TestClient(app) as client:
        response = _post_wav(client)

    assert response.status_code == 200
    assert response.json() == {"text": ""}


def test_stt_wav_conversion_preserves_duration(tmp_path: Path) -> None:
    source = tmp_path / "source.wav"
    output = tmp_path / "output.wav"
    _write_wav(source, frames=300)

    result = convert_wav_to_wav_s16le_16k_mono(source, output)

    assert result.output_frames == 300
    channels, sample_rate, frames = _wav_info(output.read_bytes())
    assert channels == 1
    assert sample_rate == 16_000
    assert frames == result.output_frames


def test_elevenlabs_conversion_and_extraction(tmp_path: Path) -> None:
    source = tmp_path / "source.wav"
    output = tmp_path / "output.pcm"
    _write_wav(source, channels=2, frames=300)

    result = convert_wav_to_pcm_s16le_16k_mono(source, output)

    assert result.output_frames == 300
    assert len(output.read_bytes()) == result.output_frames * 2
    assert extract_elevenlabs_text({"text": "single"}) == "single"
    assert (
        extract_elevenlabs_text({"transcripts": [{"text": "one"}, {"text": "two"}]})
        == "one\ntwo"
    )
    assert (
        extract_elevenlabs_text(
            {"transcripts": {"left": {"text": "a"}, "right": {"text": "b"}}}
        )
        == "a\nb"
    )
