"""Shared retry policy for model provider HTTP transports."""

from __future__ import annotations

import json
import time
import urllib.error
from typing import Any

MODEL_RATE_LIMIT_MAX_RETRIES = 10
RETRYABLE_HTTP_STATUS_CODES = frozenset({500, 502, 503, 504})
OVERLOAD_HTTP_STATUS_CODES = frozenset({503, 529})
RETRYABLE_SEMANTIC_ERROR_CODES = frozenset(
    {
        "api_error",
        "deadline_exceeded",
        "internal",
        "overloaded_error",
        "server_error",
        "server_is_overloaded",
        "service_unavailable",
        "unavailable",
    }
)
RETRYABLE_SEMANTIC_STATUSES = frozenset({"incomplete"})


def rate_limit_max_retries(configured_max_retries: int) -> int:
    return max(configured_max_retries, MODEL_RATE_LIMIT_MAX_RETRIES)


def retry_after_seconds(exc: Any, attempt: int) -> float:
    try:
        headers = getattr(exc, "headers", None)
        retry_after = headers.get("Retry-After") if headers else None
        if retry_after:
            return max(0.1, min(float(retry_after), 60.0))
    except (TypeError, ValueError):
        pass
    return min(2.0 * (2**attempt), 30.0)


def should_retry_rate_limit(error_payload: dict[str, Any]) -> bool:
    error = error_payload.get("error")
    if not isinstance(error, dict):
        return True
    error_type = error.get("type")
    if (
        isinstance(error_type, str)
        and error_type.strip().lower() == "insufficient_quota"
    ):
        return False
    return True


def is_retryable_http_status(status_code: int) -> bool:
    return status_code == 429 or status_code in RETRYABLE_HTTP_STATUS_CODES


def is_overload_http_status(status_code: int) -> bool:
    return status_code in OVERLOAD_HTTP_STATUS_CODES


def is_retryable_semantic_error_code(code: str | None) -> bool:
    if not code:
        return False
    return code.strip().lower() in RETRYABLE_SEMANTIC_ERROR_CODES


def is_retryable_semantic_status(status: str | None) -> bool:
    if not status:
        return False
    return status.strip().lower() in RETRYABLE_SEMANTIC_STATUSES


def read_error_body(exc: urllib.error.HTTPError) -> str:
    try:
        return exc.read().decode("utf-8", errors="replace")
    except Exception:
        return ""


def parse_error_payload(error_body: str) -> dict[str, Any] | None:
    stripped = error_body.strip()
    if not stripped.startswith("{"):
        return None
    try:
        payload = json.loads(stripped)
    except json.JSONDecodeError:
        return None
    return payload if isinstance(payload, dict) else None


def request_id_from_headers(
    exc: urllib.error.HTTPError,
    *,
    header_names: tuple[str, ...] = ("x-request-id", "request-id"),
) -> str | None:
    if not exc.headers:
        return None
    for header in header_names:
        request_id = exc.headers.get(header)
        if isinstance(request_id, str) and request_id.strip():
            return request_id.strip()
    return None


def format_error_message(prefix: str, error_payload: dict[str, Any]) -> str:
    return f"{prefix}: {json.dumps(error_payload, sort_keys=True)}"


def duration_ms(started_at: float) -> int:
    return max(0, int((time.perf_counter() - started_at) * 1000))


def trace_provider_call(
    *,
    tracer,
    provider: str,
    model: str,
    url: str,
    request_config: dict[str, Any],
    request_payload: dict[str, Any],
    response_payload: dict[str, Any],
    duration_ms: int,
    prompt_tokens: int | None = None,
    completion_tokens: int | None = None,
    total_tokens: int | None = None,
    status_code: int | None = None,
    success: bool,
    error_message: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> None:
    if tracer is None:
        return
    tracer.log_model_call(
        provider=provider,
        model=model,
        url=url,
        request_config=request_config,
        request_payload=request_payload,
        response_payload=response_payload,
        duration_ms=duration_ms,
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        total_tokens=total_tokens,
        status_code=status_code,
        success=success,
        error_message=error_message,
        metadata=metadata,
    )


def trace_provider_request_start(
    *,
    tracer,
    provider: str,
    model: str,
    url: str,
    request_config: dict[str, Any],
    request_payload: dict[str, Any],
    metadata: dict[str, Any] | None = None,
) -> None:
    if tracer is None:
        return
    tracer.log_event(
        "model_call_start",
        provider=provider,
        model=model,
        url=url,
        request_config=request_config,
        request_payload=request_payload,
        success=None,
        metadata=metadata,
    )


def trace_provider_retry(
    *,
    tracer,
    provider: str,
    model: str,
    url: str,
    request_config: dict[str, Any],
    request_payload: dict[str, Any],
    status_code: int | None,
    error_message: str,
    attempt: int,
    max_retries: int,
    metadata: dict[str, Any] | None = None,
) -> None:
    if tracer is None:
        return
    event_metadata = {
        "attempt": attempt,
        "max_retries": max_retries,
        **(metadata or {}),
    }
    tracer.log_event(
        "model_call_retry",
        provider=provider,
        model=model,
        url=url,
        request_config=request_config,
        request_payload=request_payload,
        status_code=status_code,
        success=False,
        error_message=error_message,
        metadata=event_metadata,
    )
