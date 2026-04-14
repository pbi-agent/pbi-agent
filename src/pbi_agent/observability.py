from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import logging
from pathlib import Path
import threading
import time
from typing import TYPE_CHECKING, Any

from pbi_agent.session_store import SessionStore

if TYPE_CHECKING:
    from pbi_agent.models.messages import TokenUsage

_log = logging.getLogger(__name__)

_REDACTED = "***REDACTED***"
_SECRET_KEYS = {
    "api_key",
    "apikey",
    "authorization",
    "token",
    "secret",
    "password",
    "x-api-key",
}


def _coerce_json_value(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    if isinstance(value, dict):
        redacted: dict[str, Any] = {}
        for key, inner in value.items():
            key_str = str(key)
            if key_str.strip().lower() in _SECRET_KEYS:
                redacted[key_str] = _REDACTED
                continue
            redacted[key_str] = _coerce_json_value(inner)
        return redacted
    if isinstance(value, (list, tuple, set)):
        return [_coerce_json_value(item) for item in value]
    return repr(value)


def redacted_json(value: Any) -> Any:
    return _coerce_json_value(value)


def _redacted_metadata(metadata: dict[str, Any] | None) -> dict[str, Any]:
    sanitized = redacted_json(metadata or {})
    if isinstance(sanitized, dict):
        return sanitized
    return {}


@dataclass(slots=True)
class RunTracer:
    store: SessionStore | None
    run_session_id: str | None
    session_id: str | None
    parent_run_session_id: str | None
    agent_name: str | None
    agent_type: str | None
    provider: str | None
    provider_id: str | None
    profile_id: str | None
    model: str | None
    _started_at_monotonic: float
    _lock: threading.Lock
    _run_metadata: dict[str, Any]
    _next_step_index: int = 0
    _total_tool_calls: int = 0
    _total_api_calls: int = 0
    _error_count: int = 0
    _finished: bool = False

    @classmethod
    def start(
        cls,
        *,
        store: SessionStore | None,
        session_id: str | None,
        parent_run_session_id: str | None = None,
        agent_name: str | None,
        agent_type: str | None,
        provider: str | None,
        provider_id: str | None,
        profile_id: str | None,
        model: str | None,
        metadata: dict[str, Any] | None = None,
    ) -> RunTracer:
        lock = threading.Lock()
        started_at_monotonic = time.perf_counter()
        run_session_id: str | None = None
        run_metadata = _redacted_metadata(metadata)
        if store is not None:
            try:
                run_session_id = store.create_run_session(
                    session_id=session_id,
                    parent_run_session_id=parent_run_session_id,
                    agent_name=agent_name,
                    agent_type=agent_type,
                    provider=provider,
                    provider_id=provider_id,
                    profile_id=profile_id,
                    model=model,
                    metadata=run_metadata,
                )
            except Exception:
                _log.warning("Failed to create run session", exc_info=True)
        tracer = cls(
            store=store,
            run_session_id=run_session_id,
            session_id=session_id,
            parent_run_session_id=parent_run_session_id,
            agent_name=agent_name,
            agent_type=agent_type,
            provider=provider,
            provider_id=provider_id,
            profile_id=profile_id,
            model=model,
            _started_at_monotonic=started_at_monotonic,
            _lock=lock,
            _run_metadata=run_metadata,
        )
        tracer.log_event(
            "run_start",
            provider=provider,
            model=model,
            metadata=metadata or {},
        )
        return tracer

    def child(
        self,
        *,
        agent_name: str | None,
        agent_type: str | None,
        provider: str | None,
        provider_id: str | None,
        profile_id: str | None,
        model: str | None,
        metadata: dict[str, Any] | None = None,
    ) -> RunTracer:
        return RunTracer.start(
            store=self.store,
            session_id=self.session_id,
            parent_run_session_id=self.run_session_id,
            agent_name=agent_name,
            agent_type=agent_type,
            provider=provider,
            provider_id=provider_id,
            profile_id=profile_id,
            model=model,
            metadata=metadata,
        )

    def log_event(
        self,
        event_type: str,
        *,
        duration_ms: int | None = None,
        provider: str | None = None,
        model: str | None = None,
        url: str | None = None,
        request_config: Any = None,
        request_payload: Any = None,
        response_payload: Any = None,
        tool_name: str | None = None,
        tool_call_id: str | None = None,
        tool_input: Any = None,
        tool_output: Any = None,
        tool_duration_ms: int | None = None,
        prompt_tokens: int | None = None,
        completion_tokens: int | None = None,
        total_tokens: int | None = None,
        status_code: int | None = None,
        success: bool | None = None,
        error_message: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        if self.store is None or self.run_session_id is None:
            return
        with self._lock:
            step_index = self._next_step_index
            self._next_step_index += 1
        try:
            self.store.add_observability_event(
                run_session_id=self.run_session_id,
                session_id=self.session_id,
                step_index=step_index,
                event_type=event_type,
                duration_ms=duration_ms,
                provider=provider or self.provider,
                model=model or self.model,
                url=url,
                request_config=redacted_json(request_config),
                request_payload=redacted_json(request_payload),
                response_payload=redacted_json(response_payload),
                tool_name=tool_name,
                tool_call_id=tool_call_id,
                tool_input=redacted_json(tool_input),
                tool_output=redacted_json(tool_output),
                tool_duration_ms=tool_duration_ms,
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                total_tokens=total_tokens,
                status_code=status_code,
                success=success,
                error_message=error_message,
                metadata=redacted_json(metadata or {}),
            )
        except Exception:
            _log.warning("Failed to persist observability event", exc_info=True)

    def log_model_call(
        self,
        *,
        provider: str | None,
        model: str | None,
        url: str,
        request_config: Any,
        request_payload: Any,
        response_payload: Any,
        duration_ms: int,
        prompt_tokens: int | None = None,
        completion_tokens: int | None = None,
        total_tokens: int | None = None,
        status_code: int | None = None,
        success: bool,
        error_message: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        with self._lock:
            self._total_api_calls += 1
            if not success:
                self._error_count += 1
        self.log_event(
            "model_call",
            duration_ms=duration_ms,
            provider=provider,
            model=model,
            url=url,
            request_config=request_config,
            request_payload=request_payload,
            response_payload=response_payload,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=total_tokens,
            status_code=status_code,
            success=success,
            error_message=error_message,
            metadata=metadata,
        )

    def log_tool_call(
        self,
        *,
        tool_name: str,
        tool_call_id: str,
        tool_input: Any,
        tool_output: Any,
        duration_ms: int,
        success: bool,
        error_message: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        with self._lock:
            self._total_tool_calls += 1
            if not success:
                self._error_count += 1
        self.log_event(
            "tool_call",
            duration_ms=duration_ms,
            tool_name=tool_name,
            tool_call_id=tool_call_id,
            tool_input=tool_input,
            tool_output=tool_output,
            tool_duration_ms=duration_ms,
            success=success,
            error_message=error_message,
            metadata=metadata,
        )

    def log_error(
        self,
        error_message: str,
        *,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        with self._lock:
            self._error_count += 1
        self.log_event(
            "error",
            success=False,
            error_message=error_message,
            metadata=metadata,
        )

    def finish(
        self,
        *,
        status: str,
        usage: TokenUsage | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        if self.store is None or self.run_session_id is None:
            return
        finish_metadata = _redacted_metadata(metadata)
        with self._lock:
            if self._finished:
                return
            self._finished = True
            total_tool_calls = self._total_tool_calls
            total_api_calls = self._total_api_calls
            error_count = self._error_count
            run_metadata = {**self._run_metadata, **finish_metadata}
            self._run_metadata = run_metadata
        duration_ms = max(
            0,
            int((time.perf_counter() - self._started_at_monotonic) * 1000),
        )
        snap = usage.snapshot() if usage is not None else None
        self.log_event(
            "run_end",
            duration_ms=duration_ms,
            provider=self.provider,
            model=self.model,
            prompt_tokens=snap.input_tokens if snap is not None else None,
            completion_tokens=snap.output_tokens if snap is not None else None,
            total_tokens=snap.total_tokens if snap is not None else None,
            success=status == "completed",
            error_message=finish_metadata.get("error_message"),
            metadata={"status": status, **finish_metadata},
        )
        try:
            self.store.update_run_session(
                self.run_session_id,
                status=status,
                ended_at=datetime.now(timezone.utc).isoformat(),
                total_duration_ms=duration_ms,
                input_tokens=snap.input_tokens if snap is not None else None,
                cached_input_tokens=(
                    snap.cached_input_tokens if snap is not None else None
                ),
                cache_write_tokens=snap.cache_write_tokens
                if snap is not None
                else None,
                cache_write_1h_tokens=(
                    snap.cache_write_1h_tokens if snap is not None else None
                ),
                output_tokens=snap.output_tokens if snap is not None else None,
                reasoning_tokens=snap.reasoning_tokens if snap is not None else None,
                tool_use_tokens=snap.tool_use_tokens if snap is not None else None,
                provider_total_tokens=(
                    snap.provider_total_tokens if snap is not None else None
                ),
                estimated_cost_usd=snap.estimated_cost_usd
                if snap is not None
                else None,
                total_tool_calls=total_tool_calls,
                total_api_calls=total_api_calls,
                error_count=error_count,
                metadata=run_metadata,
            )
        except Exception:
            _log.warning("Failed to finalize run session", exc_info=True)
