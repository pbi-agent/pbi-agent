from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
import uuid
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from typing import Any

from pbi_agent import __version__
from pbi_agent.stt.base import (
    DEFAULT_STT_HTTP_TIMEOUT_SECONDS,
    DEFAULT_STT_MAX_RETRIES,
    SttProviderError,
)

TRANSIENT_HTTP_STATUSES = frozenset({429, 500, 502, 503, 504})
MAX_ERROR_BODY_CHARS = 1000

urlopen = urllib.request.urlopen
sleep = time.sleep


@dataclass(frozen=True, slots=True)
class MultipartFile:
    field_name: str
    filename: str
    content_type: str
    content: bytes


def request_with_retry(
    request_factory: Callable[[], urllib.request.Request],
    *,
    provider_name: str,
    max_retries: int = DEFAULT_STT_MAX_RETRIES,
    timeout: float = DEFAULT_STT_HTTP_TIMEOUT_SECONDS,
    initial_delay_seconds: float = 0.1,
) -> bytes:
    """Execute a urllib request with deterministic retry for transient failures."""

    last_error: BaseException | None = None
    attempts = max_retries + 1
    for attempt in range(attempts):
        try:
            request = request_factory()
            with urlopen(request, timeout=timeout) as response:
                body = response.read()
                status = int(
                    getattr(response, "status", getattr(response, "code", 200))
                )
            if 200 <= status < 300:
                return body
            if status in TRANSIENT_HTTP_STATUSES and attempt < max_retries:
                _sleep_before_retry(attempt, initial_delay_seconds)
                continue
            raise SttProviderError(_http_error_message(provider_name, status, body))
        except urllib.error.HTTPError as exc:
            body = _read_http_error_body(exc)
            last_error = exc
            if exc.code in TRANSIENT_HTTP_STATUSES and attempt < max_retries:
                _sleep_before_retry(attempt, initial_delay_seconds)
                continue
            raise SttProviderError(
                _http_error_message(provider_name, exc.code, body)
            ) from exc
        except urllib.error.URLError as exc:
            last_error = exc
            if attempt < max_retries:
                _sleep_before_retry(attempt, initial_delay_seconds)
                continue
            raise SttProviderError(
                f"{provider_name} request failed after {attempts} attempts: {exc}"
            ) from exc
        except (TimeoutError, OSError) as exc:
            last_error = exc
            if attempt < max_retries:
                _sleep_before_retry(attempt, initial_delay_seconds)
                continue
            raise SttProviderError(
                f"{provider_name} request failed after {attempts} attempts: {exc}"
            ) from exc

    raise SttProviderError(
        f"{provider_name} request failed after {attempts} attempts: {last_error}"
    )


def json_response(body: bytes, *, provider_name: str) -> dict[str, Any]:
    try:
        payload = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        preview = body.decode("utf-8", errors="replace")[:MAX_ERROR_BODY_CHARS]
        raise SttProviderError(
            f"{provider_name} returned a non-JSON response: {preview}"
        ) from exc
    if not isinstance(payload, dict):
        raise SttProviderError(f"{provider_name} returned an invalid JSON response.")
    return payload


def encode_multipart_form_data(
    *,
    fields: Mapping[str, str],
    files: Iterable[MultipartFile],
) -> tuple[bytes, str]:
    boundary = "----pbi-agent-" + uuid.uuid4().hex
    parts: list[bytes] = []
    for name, value in fields.items():
        parts.append(
            (
                f"--{boundary}\r\n"
                f'Content-Disposition: form-data; name="{_escape_header(name)}"\r\n'
                "\r\n"
                f"{value}\r\n"
            ).encode("utf-8")
        )
    for file_item in files:
        parts.append(
            (
                f"--{boundary}\r\n"
                "Content-Disposition: form-data; "
                f'name="{_escape_header(file_item.field_name)}"; '
                f'filename="{_escape_header(file_item.filename)}"\r\n'
                f"Content-Type: {file_item.content_type}\r\n"
                "\r\n"
            ).encode("utf-8")
        )
        parts.append(file_item.content)
        parts.append(b"\r\n")
    parts.append(f"--{boundary}--\r\n".encode("utf-8"))
    return b"".join(parts), f"multipart/form-data; boundary={boundary}"


def request_headers(extra: Mapping[str, str]) -> dict[str, str]:
    headers = {
        "Accept": "application/json",
        "User-Agent": f"pbi-agent/{__version__}",
    }
    headers.update(extra)
    return headers


def _sleep_before_retry(attempt: int, initial_delay_seconds: float) -> None:
    sleep(initial_delay_seconds * (2**attempt))


def _read_http_error_body(exc: urllib.error.HTTPError) -> bytes:
    try:
        return exc.read()
    except Exception:
        return b""


def _http_error_message(provider_name: str, status_code: int, body: bytes) -> str:
    text = body.decode("utf-8", errors="replace").strip()
    if len(text) > MAX_ERROR_BODY_CHARS:
        text = text[:MAX_ERROR_BODY_CHARS] + "…"
    suffix = f": {text}" if text else ""
    return f"{provider_name} API error HTTP {status_code}{suffix}"


def _escape_header(value: str) -> str:
    return (
        value.replace("\\", "\\\\")
        .replace('"', '\\"')
        .replace("\r", "")
        .replace("\n", "")
    )
