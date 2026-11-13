from __future__ import annotations

import array
import hashlib
import io
import os
import stat
import sys
import tarfile
import wave
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from pbi_agent.config import (
    LOCAL_STT_PROVIDER_ID,
    Settings,
    load_internal_config,
    select_stt_provider,
)
from pbi_agent.local_assets import Asset
from pbi_agent.stt import local, resolve_selected_stt_provider
from pbi_agent.stt.base import (
    ResolvedSttProvider,
    SttConfigurationError,
    SttProviderError,
)
from pbi_agent.web.serve import create_app

RATE = 16_000
PROVIDER = ResolvedSttProvider(LOCAL_STT_PROVIDER_ID, "local", "")

# Prints sherpa-onnx-offline style output: progress noise plus one JSON line
# whose text is the audio duration, so tests can see what each call received.
FAKE_SHERPA = """#!{python}
import json, sys, wave
args = sys.argv[1:]
assert "--model-type=nemo_transducer" in args and "--provider=cpu" in args, args
with wave.open(args[-1], "rb") as wav:
    seconds = wav.getnframes() / wav.getframerate()
if seconds < 0.5:
    sys.exit(3)
sys.stderr.write("Creating recognizer ...\\n{{not json\\n")
if seconds < 1.5:
    sys.exit(0)
sys.stderr.write(json.dumps({{"lang": "", "text": " %.1fs" % seconds}}) + "\\n")
"""


class FakeResponse(io.BytesIO):
    status = 200

    def __enter__(self) -> FakeResponse:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()


def _asset(data: bytes, name: str) -> Asset:
    return Asset(
        f"https://example.invalid/{name}", hashlib.sha256(data).hexdigest(), len(data)
    )


def _archive(files: dict[str, bytes]) -> bytes:
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w:bz2") as bundle:
        for name, data in files.items():
            info = tarfile.TarInfo(name)
            info.size = len(data)
            info.mode = 0o755
            bundle.addfile(info, io.BytesIO(data))
    return buffer.getvalue()


def _fake_downloads(monkeypatch: pytest.MonkeyPatch) -> dict[str, bytes]:
    binary = "sherpa-onnx-offline.exe" if os.name == "nt" else "sherpa-onnx-offline"
    runtime = _archive({f"sherpa-test/bin/{binary}": b"#!"})
    model = _archive(
        {
            f"model-test/{name}": b"onnx"
            for name in (
                "encoder.int8.onnx",
                "decoder.int8.onnx",
                "joiner.int8.onnx",
                "tokens.txt",
            )
        }
    )
    monkeypatch.setattr(local, "MODEL", _asset(model, "model.tar.bz2"))
    monkeypatch.setattr(
        local, "runtime_asset", lambda: _asset(runtime, "runtime.tar.bz2")
    )
    return {"runtime.tar.bz2": runtime, "model.tar.bz2": model}


def _urlopen(files: dict[str, bytes]):
    def urlopen(request, timeout):
        del timeout
        return FakeResponse(files[request.full_url.rsplit("/", 1)[-1]])

    return urlopen


def _write_wav(path: Path, samples: array.array) -> Path:
    data = array.array("h", samples)
    if sys.byteorder == "big":
        data.byteswap()
    with wave.open(str(path), "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(RATE)
        wav.writeframes(data.tobytes())
    return path


def _tone(seconds: float) -> array.array:
    return array.array("h", [8000, -8000] * int(seconds * RATE / 2))


def _frames(path: Path) -> int:
    with wave.open(str(path), "rb") as wav:
        return wav.getnframes()


@pytest.fixture
def ready_engine() -> Path:
    """An installed local engine whose sherpa-onnx-offline is a small script."""
    if os.name == "nt":
        pytest.skip("fake sherpa-onnx-offline is a POSIX script")
    model = local.model_dir() / "model-test"
    model.mkdir(parents=True)
    for name in (
        "encoder.int8.onnx",
        "decoder.int8.onnx",
        "joiner.int8.onnx",
        "tokens.txt",
    ):
        (model / name).write_bytes(b"onnx")
    binary = local.runtime_dir() / "sherpa-test" / "bin" / "sherpa-onnx-offline"
    binary.parent.mkdir(parents=True)
    binary.write_text(FAKE_SHERPA.format(python=sys.executable))
    binary.chmod(binary.stat().st_mode | stat.S_IXUSR)
    return binary


def test_every_supported_platform_has_a_pinned_runtime() -> None:
    assert sorted(local._RUNTIMES) == [
        ("Darwin", "arm64"),
        ("Darwin", "x64"),
        ("Linux", "arm64"),
        ("Linux", "x64"),
        ("Windows", "arm64"),
        ("Windows", "x64"),
    ]
    for asset in local._RUNTIMES.values():
        assert asset.url.endswith(".tar.bz2")
        assert len(asset.sha256) == 64


def test_status_reports_unsupported_platform(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(local, "runtime_asset", lambda: None)

    assert local.status().state == "unsupported"
    local.ensure_assets()
    assert not local.assets_root().exists()


def test_ensure_assets_installs_runtime_and_model(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    files = _fake_downloads(monkeypatch)
    total = sum(len(data) for data in files.values())
    assert local.status() == local.LocalSttStatus("missing", 0, total, None)

    with patch("urllib.request.urlopen", _urlopen(files)):
        local.ensure_assets()

    assert local.status() == local.LocalSttStatus("ready", total, total, None)
    assert local.is_ready()
    assert sorted(p.name for p in local.assets_root().iterdir()) == [
        "parakeet-tdt-0.6b-v3-int8",
        f"sherpa-onnx-{local.SHERPA_ONNX_TAG}",
    ]


def test_failed_download_is_reported_and_can_be_retried(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    files = _fake_downloads(monkeypatch)
    corrupted = {**files, "model.tar.bz2": files["model.tar.bz2"][:-1] + b"!"}

    with patch("urllib.request.urlopen", _urlopen(corrupted)):
        local.ensure_assets()

    failed = local.status()
    assert failed.state == "failed"
    assert failed.error is not None and "checksum mismatch" in failed.error
    # The runtime was installed; only the model is still missing.
    assert failed.downloaded_bytes == len(files["runtime.tar.bz2"])

    with patch("urllib.request.urlopen", _urlopen(files)):
        local.ensure_assets()

    assert local.status().state == "ready"


def test_status_is_downloading_while_another_process_holds_the_lock(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _fake_downloads(monkeypatch)
    local.assets_root().mkdir(parents=True)
    (local.assets_root() / "download.lock").touch()

    with patch("urllib.request.urlopen", side_effect=AssertionError("no download")):
        local.ensure_assets()

    assert local.status().state == "downloading"


def test_split_wav_keeps_short_audio_as_is(tmp_path: Path) -> None:
    wav_path = _write_wav(tmp_path / "short.wav", _tone(30))

    assert local.split_wav(wav_path, tmp_path) == [wav_path]


def test_split_wav_cuts_long_audio_at_quiet_moments(tmp_path: Path) -> None:
    # 70 s of tone with pauses at 24 s and 50 s; no pause in the last stretch.
    samples = _tone(70)
    silence = array.array("h", [0] * (RATE // 2))
    for pause_at in (24, 50):
        samples[pause_at * RATE : pause_at * RATE + len(silence)] = silence
    wav_path = _write_wav(tmp_path / "long.wav", samples)

    pieces = local.split_wav(wav_path, tmp_path)

    lengths = [_frames(piece) / RATE for piece in pieces]
    assert lengths == pytest.approx([24.05, 26.0, 19.95], abs=0.06)
    assert sum(_frames(piece) for piece in pieces) == len(samples)


def test_transcribe_joins_pieces_in_order(ready_engine: Path, tmp_path: Path) -> None:
    samples = _tone(50)
    samples[24 * RATE : 24 * RATE + RATE // 2] = array.array("h", [0] * (RATE // 2))
    wav_path = _write_wav(tmp_path / "long.wav", samples)

    text = local.LocalSttBackend().transcribe(wav_path, PROVIDER)

    assert text == "24.1s 25.9s"


def test_transcribe_returns_blank_for_audio_without_speech(
    ready_engine: Path, tmp_path: Path
) -> None:
    wav_path = _write_wav(tmp_path / "quiet.wav", _tone(2))
    blank = ready_engine.read_text().replace('" %.1fs" % seconds', '""')
    ready_engine.write_text(blank)

    assert local.LocalSttBackend().transcribe(wav_path, PROVIDER) == ""


def test_transcribe_reports_engine_failures(ready_engine: Path, tmp_path: Path) -> None:
    crash = _write_wav(tmp_path / "crash.wav", _tone(0.2))
    silent = _write_wav(tmp_path / "silent.wav", _tone(1))

    with pytest.raises(SttProviderError, match="exit code 3"):
        local.LocalSttBackend().transcribe(crash, PROVIDER)
    with pytest.raises(SttProviderError, match="no transcript"):
        local.LocalSttBackend().transcribe(silent, PROVIDER)


def test_transcribe_before_install_starts_the_download(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    started: list[bool] = []
    monkeypatch.setattr(local, "start_download", lambda: started.append(True))
    wav_path = _write_wav(tmp_path / "short.wav", _tone(1))

    with pytest.raises(SttConfigurationError, match="Downloading it now"):
        local.LocalSttBackend().transcribe(wav_path, PROVIDER)

    assert started == [True]


def test_local_engine_can_be_selected_without_a_saved_provider() -> None:
    selected, _revision = select_stt_provider(LOCAL_STT_PROVIDER_ID)

    assert selected == LOCAL_STT_PROVIDER_ID
    assert load_internal_config().web.stt_provider_id == LOCAL_STT_PROVIDER_ID
    assert resolve_selected_stt_provider() == PROVIDER


def test_web_selection_starts_download_and_transcribes(
    ready_engine: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    started: list[bool] = []
    monkeypatch.setattr(local, "start_download", lambda: started.append(True))
    app = create_app(Settings(api_key="test-key", provider="openai", model="gpt-5.4"))
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(RATE)
        wav.writeframes(b"\x10\x00" * RATE * 2)

    with TestClient(app) as client:
        revision = client.get("/api/config/bootstrap").json()["config_revision"]
        selected = client.put(
            "/api/config/stt-provider",
            headers={"If-Match": revision},
            json={"provider_id": LOCAL_STT_PROVIDER_ID},
        )
        status = client.get("/api/stt/local")
        retry = client.post("/api/stt/local/download")
        transcript = client.post(
            "/api/stt/transcribe",
            files={"file": ("audio.wav", buffer.getvalue(), "audio/wav")},
        )

    assert selected.status_code == 200
    assert selected.json()["stt_provider_id"] == LOCAL_STT_PROVIDER_ID
    assert status.json()["state"] == "ready"
    assert status.json()["error"] is None
    assert retry.status_code == 200
    assert started == [True, True]
    assert transcript.status_code == 200
    assert transcript.json() == {"text": "2.0s"}
