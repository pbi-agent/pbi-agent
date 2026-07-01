"""Shared JSON HTTP transport for provider backends.

The transport owns request execution, retry notices, rate-limit/overload
handling, and observability. Protocol/provider modules still own request body
shape, auth headers, endpoint selection, response parsing, and rendering.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
import http.client
import json
import time
from typing import Any, TYPE_CHECKING
import urllib.error
import urllib.request

from pbi_agent.config import Settings
from pbi_agent.display.protocol import DisplayProtocol
from pbi_agent.models.messages import CompletedResponse
from pbi_agent.providers import retry as provider_retry
from pbi_agent.providers.wait_messages import waiting_message_for_input

if TYPE_CHECKING:
    from pbi_agent.models.messages import TokenUsage
    from pbi_agent.observability import RunTracer


HttpErrorNormalizer = Callable[[urllib.error.HTTPError, str], dict[str, Any]]
ErrorFormatter = Callable[[str, dict[str, Any]], str]
ResponseParser = Callable[[dict[str, Any]], CompletedResponse]
SemanticValidator = Callable[[dict[str, Any]], None]


@dataclass(frozen=True, slots=True)
class SemanticResponseError(RuntimeError):
    """A provider returned HTTP 200 with a failed semantic response state."""

    message: str
    payload: dict[str, Any]
    retryable: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        RuntimeError.__init__(self, self.message)


@dataclass(frozen=True, slots=True)
class JsonErrorPolicy:
    """Provider-specific error labels and normalization hooks."""

    api_error_label: str
    rate_limit_exhausted_label: str
    overload_exhausted_label: str
    request_failed_label: str
    normalize_http_error: HttpErrorNormalizer
    format_error: ErrorFormatter
    retryable_http_final_uses_error_message: bool = True


@dataclass(frozen=True, slots=True)
class JsonRequestSpec:
    """A provider JSON POST request."""

    provider: str
    model: str
    url: str
    headers: dict[str, str]
    body: dict[str, Any]
    request_config: dict[str, Any]
    wait_input: str | list[dict[str, Any]]
    timeout: float
    error_policy: JsonErrorPolicy
    trace_request_payload: dict[str, Any] | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    sleep: Callable[[float], None] = time.sleep


class JsonModelTransport:
    """Execute JSON model requests with shared retry and tracing behavior."""

    def post(
        self,
        spec: JsonRequestSpec,
        *,
        settings: Settings,
        display: DisplayProtocol,
        tracer: "RunTracer | None",
        parse_response: ResponseParser,
        semantic_validator: SemanticValidator | None = None,
    ) -> CompletedResponse:
        display.wait_start(waiting_message_for_input(spec.wait_input))

        request_data = json.dumps(spec.body).encode("utf-8")
        max_retries = settings.max_retries
        rate_limit_max_retries = provider_retry.rate_limit_max_retries(max_retries)
        retry_notice_max_retries = max_retries
        last_error: Exception | None = None
        last_error_message: str | None = None

        for attempt in range(rate_limit_max_retries + 1):
            if attempt > 0:
                display.retry_notice(attempt, retry_notice_max_retries)

            req_start = time.perf_counter()
            try:
                req = urllib.request.Request(
                    spec.url,
                    data=request_data,
                    headers=spec.headers,
                    method="POST",
                )
                with urllib.request.urlopen(req, timeout=spec.timeout) as resp:
                    response_json = json.loads(resp.read().decode("utf-8"))

                if semantic_validator is not None:
                    try:
                        semantic_validator(response_json)
                    except SemanticResponseError as exc:
                        last_error = exc
                        last_error_message = str(exc)
                        self._trace_call(
                            spec=spec,
                            tracer=tracer,
                            response_payload=exc.payload,
                            duration_ms=provider_retry.duration_ms(req_start),
                            status_code=200,
                            success=False,
                            error_message=str(exc),
                            metadata={
                                "attempt": attempt + 1,
                                "semantic_error": True,
                                **exc.metadata,
                            },
                        )
                        if exc.retryable and attempt < max_retries:
                            retry_notice_max_retries = max_retries
                            self._trace_retry(
                                spec=spec,
                                tracer=tracer,
                                status_code=200,
                                error_message=str(exc),
                                attempt=attempt + 1,
                                max_retries=max_retries,
                                metadata={
                                    "semantic_error": True,
                                    "retryable": True,
                                    **exc.metadata,
                                },
                            )
                            continue
                        display.wait_stop()
                        raise RuntimeError(str(exc)) from exc

                result = parse_response(response_json)
                self._trace_call(
                    spec=spec,
                    tracer=tracer,
                    response_payload=response_json,
                    duration_ms=provider_retry.duration_ms(req_start),
                    usage=result.usage,
                    status_code=200,
                    success=True,
                    metadata={"attempt": attempt + 1, **spec.metadata},
                )
                display.wait_stop()
                return result
            except urllib.error.HTTPError as exc:
                error_body = provider_retry.read_error_body(exc)
                error_payload = spec.error_policy.normalize_http_error(exc, error_body)
                api_error = spec.error_policy.format_error(
                    f"{spec.error_policy.api_error_label} {exc.code}",
                    error_payload,
                )
                self._trace_call(
                    spec=spec,
                    tracer=tracer,
                    response_payload=error_payload or {"body": error_body},
                    duration_ms=provider_retry.duration_ms(req_start),
                    status_code=exc.code,
                    success=False,
                    error_message=api_error,
                    metadata={"attempt": attempt + 1, **spec.metadata},
                )

                if exc.code == 429:
                    if not provider_retry.should_retry_rate_limit(error_payload):
                        display.wait_stop()
                        raise RuntimeError(api_error) from exc
                    if attempt >= rate_limit_max_retries:
                        display.wait_stop()
                        raise RuntimeError(
                            spec.error_policy.format_error(
                                f"{spec.error_policy.rate_limit_exhausted_label} "
                                f"after {rate_limit_max_retries + 1} attempts",
                                error_payload,
                            )
                        ) from exc
                    wait = provider_retry.retry_after_seconds(exc, attempt)
                    retry_notice_max_retries = rate_limit_max_retries
                    display.rate_limit_notice(
                        wait_seconds=wait,
                        attempt=attempt + 1,
                        max_retries=rate_limit_max_retries,
                    )
                    self._trace_retry(
                        spec=spec,
                        tracer=tracer,
                        status_code=exc.code,
                        error_message=api_error,
                        attempt=attempt + 1,
                        max_retries=rate_limit_max_retries,
                        metadata={"retryable": True},
                    )
                    spec.sleep(wait)
                    continue

                if provider_retry.is_overload_http_status(exc.code):
                    if attempt >= max_retries:
                        display.wait_stop()
                        raise RuntimeError(
                            spec.error_policy.format_error(
                                f"{spec.error_policy.overload_exhausted_label} "
                                f"after {max_retries + 1} attempts",
                                error_payload,
                            )
                        ) from exc
                    wait = provider_retry.retry_after_seconds(exc, attempt)
                    retry_notice_max_retries = max_retries
                    display.overload_notice(
                        wait_seconds=wait,
                        attempt=attempt + 1,
                        max_retries=max_retries,
                    )
                    self._trace_retry(
                        spec=spec,
                        tracer=tracer,
                        status_code=exc.code,
                        error_message=api_error,
                        attempt=attempt + 1,
                        max_retries=max_retries,
                        metadata={"retryable": True, "overloaded": True},
                    )
                    spec.sleep(wait)
                    continue

                if provider_retry.is_retryable_http_status(exc.code):
                    last_error = exc
                    if spec.error_policy.retryable_http_final_uses_error_message:
                        last_error_message = spec.error_policy.format_error(
                            f"{spec.error_policy.request_failed_label} "
                            f"after {max_retries + 1} attempts",
                            error_payload,
                        )
                    if attempt >= max_retries:
                        break
                    retry_notice_max_retries = max_retries
                    self._trace_retry(
                        spec=spec,
                        tracer=tracer,
                        status_code=exc.code,
                        error_message=api_error,
                        attempt=attempt + 1,
                        max_retries=max_retries,
                        metadata={"retryable": True},
                    )
                    continue

                display.wait_stop()
                raise RuntimeError(api_error) from exc
            except (
                http.client.IncompleteRead,
                TimeoutError,
                ConnectionError,
                urllib.error.URLError,
            ) as exc:
                last_error = exc
                last_error_message = None
                self._trace_call(
                    spec=spec,
                    tracer=tracer,
                    response_payload={"error": str(exc)},
                    duration_ms=provider_retry.duration_ms(req_start),
                    success=False,
                    error_message=str(exc),
                    metadata={"attempt": attempt + 1, **spec.metadata},
                )
                if attempt >= max_retries:
                    break
                retry_notice_max_retries = max_retries
                self._trace_retry(
                    spec=spec,
                    tracer=tracer,
                    status_code=None,
                    error_message=str(exc),
                    attempt=attempt + 1,
                    max_retries=max_retries,
                    metadata={"retryable": True},
                )
                continue

        display.wait_stop()
        if last_error is not None:
            raise RuntimeError(
                last_error_message
                or f"{spec.error_policy.request_failed_label} "
                f"after {max_retries + 1} attempts: {last_error}"
            ) from last_error
        raise RuntimeError(f"{spec.error_policy.request_failed_label} after retries.")

    def _trace_call(
        self,
        *,
        spec: JsonRequestSpec,
        tracer: "RunTracer | None",
        response_payload: dict[str, Any],
        duration_ms: int,
        success: bool,
        usage: "TokenUsage | None" = None,
        prompt_tokens: int | None = None,
        completion_tokens: int | None = None,
        total_tokens: int | None = None,
        status_code: int | None = None,
        error_message: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        provider_retry.trace_provider_call(
            tracer=tracer,
            provider=spec.provider,
            model=spec.model,
            url=spec.url,
            request_config=spec.request_config,
            request_payload=spec.trace_request_payload or spec.body,
            response_payload=response_payload,
            duration_ms=duration_ms,
            usage=usage,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=total_tokens,
            status_code=status_code,
            success=success,
            error_message=error_message,
            metadata=metadata,
        )

    def _trace_retry(
        self,
        *,
        spec: JsonRequestSpec,
        tracer: "RunTracer | None",
        status_code: int | None,
        error_message: str,
        attempt: int,
        max_retries: int,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        provider_retry.trace_provider_retry(
            tracer=tracer,
            provider=spec.provider,
            model=spec.model,
            url=spec.url,
            request_config=spec.request_config,
            request_payload=spec.trace_request_payload or spec.body,
            status_code=status_code,
            error_message=error_message,
            attempt=attempt,
            max_retries=max_retries,
            metadata=metadata,
        )


def parse_json_error_body(
    _exc: urllib.error.HTTPError,
    error_body: str,
) -> dict[str, Any]:
    """Normalize an HTTP error body as JSON when possible."""
    return provider_retry.parse_error_payload(error_body) or {"body": error_body}


def json_error_message(prefix: str, error_payload: dict[str, Any]) -> str:
    """Format a structured JSON provider error."""
    return provider_retry.format_error_message(prefix, error_payload)


def body_error_message(prefix: str, error_payload: dict[str, Any]) -> str:
    """Format a plain-body provider error."""
    body = error_payload.get("body")
    if isinstance(body, str):
        return f"{prefix}: {body}"
    return provider_retry.format_error_message(prefix, error_payload)
