from __future__ import annotations

import array
import math
import sys
import wave
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path

from pbi_agent.stt.base import SttInputError

TARGET_PCM_SAMPLE_RATE = 16_000


class AudioConversionError(SttInputError):
    """Raised when a WAV file cannot be converted for an STT provider."""


@dataclass(frozen=True, slots=True)
class PcmConversionResult:
    input_duration_seconds: float
    output_duration_seconds: float
    output_frames: int


def validate_wav_bytes(data: bytes) -> None:
    if not data:
        raise SttInputError("Uploaded WAV file is empty.")
    if len(data) < 12 or data[0:4] not in {b"RIFF", b"RF64"} or data[8:12] != b"WAVE":
        raise SttInputError("Upload must be a WAV file.")
    try:
        with wave.open(BytesIO(data), "rb") as wav:
            if wav.getnframes() < 1:
                raise SttInputError("Uploaded WAV file is empty.")
    except SttInputError:
        raise
    except wave.Error as exc:
        raise SttInputError(f"Upload must be a valid WAV file: {exc}") from exc


def convert_wav_to_pcm_s16le_16k_mono(
    input_wav: Path,
    output_pcm: Path,
    *,
    method: str = "nearest",
    target_rate: int = TARGET_PCM_SAMPLE_RATE,
) -> PcmConversionResult:
    """Convert an uncompressed PCM WAV to raw 16 kHz mono signed 16-bit PCM."""

    result, output = _convert_wav_to_s16le_16k_mono_samples(
        input_wav,
        method=method,
        target_rate=target_rate,
    )
    output_pcm.parent.mkdir(parents=True, exist_ok=True)
    output_pcm.write_bytes(_array_to_little_endian_bytes(output))
    return result


def convert_wav_to_wav_s16le_16k_mono(
    input_wav: Path,
    output_wav: Path,
    *,
    method: str = "nearest",
    target_rate: int = TARGET_PCM_SAMPLE_RATE,
) -> PcmConversionResult:
    """Convert an uncompressed PCM WAV to a 16 kHz mono WAV."""

    result, output = _convert_wav_to_s16le_16k_mono_samples(
        input_wav,
        method=method,
        target_rate=target_rate,
    )
    output_wav.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(output_wav), "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(target_rate)
        wav.writeframes(_array_to_little_endian_bytes(output))
    return result


def _convert_wav_to_s16le_16k_mono_samples(
    input_wav: Path,
    *,
    method: str,
    target_rate: int,
) -> tuple[PcmConversionResult, array.array]:
    """Convert an uncompressed PCM WAV to mono signed 16-bit samples."""

    if method not in {"nearest", "linear"}:
        raise AudioConversionError(
            "PCM conversion method must be 'nearest' or 'linear'."
        )
    if target_rate != TARGET_PCM_SAMPLE_RATE:
        raise AudioConversionError("PCM conversion target rate must be 16 kHz.")

    try:
        with wave.open(str(input_wav), "rb") as wav:
            channels = wav.getnchannels()
            sample_width = wav.getsampwidth()
            input_rate = wav.getframerate()
            frame_count = wav.getnframes()
            comptype = wav.getcomptype()
            raw = wav.readframes(frame_count)
    except wave.Error as exc:
        raise AudioConversionError(f"Could not read WAV file: {exc}") from exc

    if comptype != "NONE":
        raise AudioConversionError("Only uncompressed PCM WAV input is supported.")
    if channels < 1:
        raise AudioConversionError("WAV file has no audio channels.")
    if frame_count < 1:
        raise AudioConversionError("Uploaded WAV file is empty.")
    if input_rate < 1:
        raise AudioConversionError("WAV file has an invalid sample rate.")
    if sample_width not in {1, 2, 3, 4}:
        raise AudioConversionError(
            f"Unsupported PCM sample width: {sample_width} bytes."
        )

    input_duration = frame_count / float(input_rate)
    out_frames = max(1, int(frame_count * target_rate / input_rate))
    output_duration = out_frames / float(target_rate)
    step = input_rate / float(target_rate)
    output = array.array("h", [0]) * out_frames

    if sample_width == 2:
        _convert_i16_frames(
            raw=raw,
            channels=channels,
            frame_count=frame_count,
            out_frames=out_frames,
            step=step,
            method=method,
            output=output,
        )
    else:
        _convert_generic_pcm_frames(
            raw=raw,
            channels=channels,
            sample_width=sample_width,
            frame_count=frame_count,
            out_frames=out_frames,
            step=step,
            method=method,
            output=output,
        )

    return (
        PcmConversionResult(
            input_duration_seconds=input_duration,
            output_duration_seconds=output_duration,
            output_frames=out_frames,
        ),
        output,
    )


def _convert_i16_frames(
    *,
    raw: bytes,
    channels: int,
    frame_count: int,
    out_frames: int,
    step: float,
    method: str,
    output: array.array,
) -> None:
    samples = _array_from_little_endian_i16(raw)
    expected_samples = frame_count * channels
    if len(samples) < expected_samples:
        raise AudioConversionError("WAV data is shorter than expected.")

    if method == "nearest":
        if channels == 1:
            for index in range(out_frames):
                output[index] = samples[int(index * step)]
            return
        if channels == 2:
            for index in range(out_frames):
                base = int(index * step) * 2
                output[index] = (samples[base] + samples[base + 1]) // 2
            return
        for index in range(out_frames):
            base = int(index * step) * channels
            total = 0
            for channel in range(channels):
                total += samples[base + channel]
            output[index] = total // channels
        return

    last_frame = frame_count - 1
    if channels == 1:
        for index in range(out_frames):
            pos = index * step
            left = int(pos)
            right = min(left + 1, last_frame)
            frac = pos - left
            output[index] = clamp_i16(
                samples[left] + (samples[right] - samples[left]) * frac
            )
        return
    if channels == 2:
        for index in range(out_frames):
            pos = index * step
            left = int(pos)
            right = min(left + 1, last_frame)
            frac = pos - left
            left_base = left * 2
            right_base = right * 2
            a = (samples[left_base] + samples[left_base + 1]) / 2.0
            b = (samples[right_base] + samples[right_base + 1]) / 2.0
            output[index] = clamp_i16(a + (b - a) * frac)
        return

    for index in range(out_frames):
        pos = index * step
        left = int(pos)
        right = min(left + 1, last_frame)
        frac = pos - left
        left_base = left * channels
        right_base = right * channels
        a_total = 0
        b_total = 0
        for channel in range(channels):
            a_total += samples[left_base + channel]
            b_total += samples[right_base + channel]
        a = a_total / float(channels)
        b = b_total / float(channels)
        output[index] = clamp_i16(a + (b - a) * frac)


def _convert_generic_pcm_frames(
    *,
    raw: bytes,
    channels: int,
    sample_width: int,
    frame_count: int,
    out_frames: int,
    step: float,
    method: str,
    output: array.array,
) -> None:
    bytes_per_frame = sample_width * channels
    last_frame = frame_count - 1

    def frame_to_mono_i16(frame_index: int) -> int:
        base = frame_index * bytes_per_frame
        total = 0
        for channel in range(channels):
            pos = base + channel * sample_width
            total += _read_pcm_sample_as_i16(raw, pos, sample_width)
        return total // channels

    if method == "nearest":
        for index in range(out_frames):
            output[index] = frame_to_mono_i16(int(index * step))
        return

    for index in range(out_frames):
        pos = index * step
        left = int(pos)
        right = min(left + 1, last_frame)
        frac = pos - left
        a = frame_to_mono_i16(left)
        b = frame_to_mono_i16(right)
        output[index] = clamp_i16(a + (b - a) * frac)


def _read_pcm_sample_as_i16(raw: bytes, byte_pos: int, sample_width: int) -> int:
    if sample_width == 1:
        return (raw[byte_pos] - 128) << 8
    if sample_width == 2:
        return int.from_bytes(raw[byte_pos : byte_pos + 2], "little", signed=True)
    if sample_width == 3:
        sample = raw[byte_pos : byte_pos + 3]
        sign = b"\xff" if sample[2] & 0x80 else b"\x00"
        value = int.from_bytes(sample + sign, "little", signed=True)
        return clamp_i16(value >> 8)
    if sample_width == 4:
        value = int.from_bytes(raw[byte_pos : byte_pos + 4], "little", signed=True)
        return clamp_i16(value >> 16)
    raise AudioConversionError(f"Unsupported PCM sample width: {sample_width} bytes.")


def _array_from_little_endian_i16(raw: bytes) -> array.array:
    samples = array.array("h")
    samples.frombytes(raw)
    if sys.byteorder != "little":
        samples.byteswap()
    return samples


def _array_to_little_endian_bytes(samples: array.array) -> bytes:
    if sys.byteorder == "little":
        return samples.tobytes()
    copy = array.array("h", samples)
    copy.byteswap()
    return copy.tobytes()


def clamp_i16(value: float | int) -> int:
    if value > 32767:
        return 32767
    if value < -32768:
        return -32768
    if isinstance(value, float) and not math.isfinite(value):
        return 0
    return int(round(value))
