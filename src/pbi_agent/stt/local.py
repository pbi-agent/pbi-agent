"""On-device speech-to-text: NVIDIA Parakeet TDT 0.6B v3 on sherpa-onnx.

The 8-bit ONNX model and the official prebuilt sherpa-onnx build for this
platform are downloaded into ``~/.pbi-agent/stt-model`` once the user picks the
local engine. Each transcription is one short-lived ``sherpa-onnx-offline``
process per audio piece: memory grows with clip length (measured: 1.1 GB for
10 s, 2.4 GB for 2 min, out of memory at 5 min on an 8 GB host), so longer
recordings are cut at quiet points and decoded one piece at a time.
"""

from __future__ import annotations

import array
import json
import logging
import os
import platform
import subprocess
import sys
import threading
import time
import wave
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from pbi_agent.local_assets import (
    LOCK_STALE_SECS,
    Asset,
    claim,
    download,
    extract,
    machine,
    part_path,
)
from pbi_agent.stt.base import (
    ResolvedSttProvider,
    SttConfigurationError,
    SttProviderError,
)
from pbi_agent.stt.registry import register_stt_backend

_log = logging.getLogger(__name__)

ROOT_ENV = "PBI_AGENT_STT_MODEL_DIR"

MODEL_NAME = "sherpa-onnx-nemo-parakeet-tdt-0.6b-v3-int8"
# The upstream asset name is not versioned; the checksum is the pin.
MODEL = Asset(
    url=(
        "https://github.com/k2-fsa/sherpa-onnx/releases/download/asr-models/"
        f"{MODEL_NAME}.tar.bz2"
    ),
    sha256="1495e91b59d7fc53ddca91f3431758ec99f8fa253fdb0e1e851be0f72b14b0f9",
    size=487_211_443,
)
_MODEL_FILES = ("encoder.int8.onnx", "decoder.int8.onnx", "joiner.int8.onnx")
_TOKENS_FILE = "tokens.txt"

SHERPA_ONNX_TAG = "v2.0.1"
_RELEASE_URL = (
    "https://github.com/k2-fsa/sherpa-onnx/releases/download/"
    f"{SHERPA_ONNX_TAG}/sherpa-onnx-{SHERPA_ONNX_TAG}-"
)
# (platform.system(), machine) -> official sherpa-onnx CPU build. The Windows
# "MT" builds link the C runtime statically, so no VC++ redistributable.
_RUNTIMES: dict[tuple[str, str], Asset] = {
    ("Linux", "x64"): Asset(
        _RELEASE_URL + "linux-x64-shared.tar.bz2",
        "2e823376987c3b6960d50726b6560155e2ad92da0b8b3886325773225ec6bdec",
        28_003_506,
    ),
    ("Linux", "arm64"): Asset(
        _RELEASE_URL + "linux-aarch64-shared-cpu.tar.bz2",
        "a8fc9fb3940d1aa3f83136767742b05068f00253f560d53c4f5aeb75ab4cb350",
        27_889_232,
    ),
    ("Darwin", "arm64"): Asset(
        _RELEASE_URL + "osx-arm64-shared.tar.bz2",
        "5e874d3c9b3d6b8c71f7c09e3a9fb9ae846c3009129d302b398d1f7aedb69f84",
        20_348_241,
    ),
    ("Darwin", "x64"): Asset(
        _RELEASE_URL + "osx-x64-shared.tar.bz2",
        "100315fbb174de2d7fec92b67d28c4128499daf3a6f47b4da6350252680d178f",
        22_897_549,
    ),
    ("Windows", "x64"): Asset(
        _RELEASE_URL + "win-x64-shared-MT-Release.tar.bz2",
        "dc703575a68594435f53dec93df775ff4913af851a196c0537163f21d8d2364e",
        26_664_192,
    ),
    ("Windows", "arm64"): Asset(
        _RELEASE_URL + "win-arm64-shared-MT-Release.tar.bz2",
        "d6faf59919314d4728a2701e715ea748a8a5d846fde1f1d58a38ecd91c848011",
        25_598_348,
    ),
}

_SAMPLE_RATE = 16_000
# Pieces are cut at the quietest 100 ms between 20 s and 30 s.
_MAX_PIECE_SECS = 30
_MIN_PIECE_SECS = 20
_QUIET_WINDOW_SECS = 0.1
# More threads than this made decoding slower on a 22-thread host.
_MAX_THREADS = 4
_TRANSCRIBE_TIMEOUT_SECS = 180

LocalSttState = Literal["unsupported", "missing", "downloading", "ready", "failed"]


@dataclass(frozen=True, slots=True)
class LocalSttStatus:
    state: LocalSttState
    downloaded_bytes: int
    total_bytes: int
    error: str | None


_ensure_lock = threading.Lock()
_transcribe_lock = threading.Lock()
_last_error: str | None = None


def assets_root() -> Path:
    override = os.environ.get(ROOT_ENV)
    if override:
        return Path(override)
    return Path.home() / ".pbi-agent" / "stt-model"


def runtime_dir() -> Path:
    return assets_root() / f"sherpa-onnx-{SHERPA_ONNX_TAG}"


def model_dir() -> Path:
    return assets_root() / "parakeet-tdt-0.6b-v3-int8"


def runtime_asset() -> Asset | None:
    return _RUNTIMES.get((platform.system(), machine() or ""))


def binary_path() -> Path | None:
    name = "sherpa-onnx-offline.exe" if os.name == "nt" else "sherpa-onnx-offline"
    directory = runtime_dir()
    if not directory.is_dir():
        return None
    return next(iter(sorted(directory.rglob(name))), None)


def model_files_dir() -> Path | None:
    """The directory holding the model files, or None until it is installed."""
    directory = model_dir()
    if not directory.is_dir():
        return None
    encoder = next(iter(sorted(directory.rglob(_MODEL_FILES[0]))), None)
    if encoder is None:
        return None
    names = (*_MODEL_FILES, _TOKENS_FILE)
    if not all((encoder.parent / name).is_file() for name in names):
        return None
    return encoder.parent


def is_ready() -> bool:
    """True when audio can be transcribed right now. Directories only appear
    under their final names after their archive's checksum was verified."""
    return binary_path() is not None and model_files_dir() is not None


def status() -> LocalSttStatus:
    runtime = runtime_asset()
    if runtime is None:
        return LocalSttStatus("unsupported", 0, 0, None)
    total = runtime.size + MODEL.size
    if is_ready():
        return LocalSttStatus("ready", total, total, None)
    root = assets_root()
    downloaded = _progress(runtime, root, binary_path() is not None) + _progress(
        MODEL, root, model_files_dir() is not None
    )
    if _ensure_lock.locked() or _lock_is_fresh(root / "download.lock"):
        return LocalSttStatus("downloading", downloaded, total, None)
    if _last_error is not None:
        return LocalSttStatus("failed", downloaded, total, _last_error)
    return LocalSttStatus("missing", downloaded, total, None)


def _progress(asset: Asset, root: Path, installed: bool) -> int:
    if installed:
        return asset.size
    archive = root / asset.url.rsplit("/", 1)[-1]
    for candidate in (archive, part_path(archive)):
        try:
            return min(candidate.stat().st_size, asset.size)
        except OSError:
            continue
    return 0


def _lock_is_fresh(lock_file: Path) -> bool:
    try:
        return time.time() - lock_file.stat().st_mtime < LOCK_STALE_SECS
    except OSError:
        return False


def start_download() -> None:
    """Fetch whatever is missing on a background thread."""
    if is_ready() or runtime_asset() is None or _ensure_lock.locked():
        return
    threading.Thread(
        target=ensure_assets, daemon=True, name="pbi-agent-stt-assets"
    ).start()


def ensure_assets() -> None:
    """Download whatever is missing. Blocking; run it off the event loop."""
    global _last_error
    runtime = runtime_asset()
    if runtime is None or is_ready():
        return
    if not _ensure_lock.acquire(blocking=False):
        return
    try:
        _last_error = None
        root = assets_root()
        root.mkdir(parents=True, exist_ok=True)
        lock_file = root / "download.lock"
        if not claim(lock_file):
            return  # another pbi-agent process is downloading
        try:
            if binary_path() is None:
                _install(runtime, runtime_dir(), lock_file)
            if model_files_dir() is None:
                _install(MODEL, model_dir(), lock_file)
        finally:
            lock_file.unlink(missing_ok=True)
        _log.info("Local speech-to-text is ready.")
    except Exception as exc:
        _last_error = str(exc) or type(exc).__name__
        _log.warning("Local speech-to-text unavailable: %s", exc)
    finally:
        _ensure_lock.release()


def _install(asset: Asset, destination: Path, lock_file: Path) -> None:
    archive = assets_root() / asset.url.rsplit("/", 1)[-1]
    download(asset, archive, lock_file)
    lock_file.touch()
    extract(archive, destination)
    archive.unlink(missing_ok=True)


def split_wav(wav_path: Path, directory: Path) -> list[Path]:
    """Cut a 16 kHz mono 16-bit WAV into pieces of at most 30 s, each cut
    placed in the quietest moment of the last 10 s. Short audio is returned
    as is."""
    with wave.open(str(wav_path), "rb") as source:
        rate = source.getframerate()
        frame_count = source.getnframes()
        max_frames = _MAX_PIECE_SECS * rate
        if frame_count <= max_frames:
            return [wav_path]
        samples = array.array("h")
        samples.frombytes(source.readframes(frame_count))
    if sys.byteorder == "big":
        samples.byteswap()

    window = max(int(_QUIET_WINDOW_SECS * rate), 1)
    pieces: list[Path] = []
    start = 0
    while start < len(samples):
        end = len(samples)
        if end - start > max_frames:
            end = _quietest_cut(
                samples, start + _MIN_PIECE_SECS * rate, start + max_frames, window
            )
        piece = samples[start:end]
        if sys.byteorder == "big":
            piece.byteswap()
        path = directory / f"piece-{len(pieces):03d}.wav"
        with wave.open(str(path), "wb") as target:
            target.setnchannels(1)
            target.setsampwidth(2)
            target.setframerate(rate)
            target.writeframes(piece.tobytes())
        pieces.append(path)
        start = end
    return pieces


def _quietest_cut(samples: array.array, low: int, high: int, window: int) -> int:
    best_start, best_energy = low, None
    for window_start in range(low, high - window + 1, window):
        energy = sum(map(abs, samples[window_start : window_start + window]))
        if best_energy is None or energy < best_energy:
            best_start, best_energy = window_start, energy
    return best_start + window // 2


def _transcribe_piece(binary: Path, model: Path, wav_path: Path) -> str:
    threads = min(max((os.cpu_count() or 2) // 2, 1), _MAX_THREADS)
    command = [
        str(binary),
        f"--encoder={model / _MODEL_FILES[0]}",
        f"--decoder={model / _MODEL_FILES[1]}",
        f"--joiner={model / _MODEL_FILES[2]}",
        f"--tokens={model / _TOKENS_FILE}",
        "--model-type=nemo_transducer",
        "--provider=cpu",
        f"--num-threads={threads}",
        str(wav_path),
    ]
    try:
        completed = subprocess.run(
            command,
            check=False,
            capture_output=True,
            stdin=subprocess.DEVNULL,
            timeout=_TRANSCRIBE_TIMEOUT_SECS,
            encoding="utf-8",
            errors="replace",
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except subprocess.TimeoutExpired as exc:
        raise SttProviderError("Local speech-to-text timed out.") from exc
    except OSError as exc:
        raise SttProviderError(f"Local speech-to-text could not start: {exc}") from exc
    if completed.returncode != 0:
        _log.debug("sherpa-onnx-offline output: %s", completed.stderr[-2000:])
        raise SttProviderError(
            f"Local speech-to-text failed (exit code {completed.returncode}). "
            "Long recordings can run out of memory."
        )
    # The result is one JSON object on its own line among progress messages.
    for line in (completed.stderr + "\n" + completed.stdout).splitlines():
        if not line.startswith("{"):
            continue
        try:
            payload = json.loads(line)
        except ValueError:
            continue
        if isinstance(payload, dict) and isinstance(payload.get("text"), str):
            return payload["text"].strip()
    raise SttProviderError("Local speech-to-text returned no transcript.")


class LocalSttBackend:
    kind = "local"

    def transcribe(self, wav_path: Path, provider: ResolvedSttProvider) -> str:
        del provider
        binary, model = binary_path(), model_files_dir()
        if binary is None or model is None:
            raise SttConfigurationError(_not_ready_message())
        pieces = split_wav(wav_path, wav_path.parent)
        with _transcribe_lock:
            texts = [_transcribe_piece(binary, model, piece) for piece in pieces]
        return " ".join(text for text in texts if text)


def _not_ready_message() -> str:
    current = status()
    if current.state == "unsupported":
        return "On-device speech-to-text is not available for this platform."
    if current.state == "downloading":
        percent = 100 * current.downloaded_bytes // max(current.total_bytes, 1)
        return (
            "The on-device speech model is still downloading "
            f"({percent}%). Try again shortly."
        )
    start_download()
    if current.state == "failed":
        return (
            f"The on-device speech model download failed ({current.error}). "
            "Retrying now."
        )
    return "The on-device speech model is not installed yet. Downloading it now."


register_stt_backend(LocalSttBackend())
