from __future__ import annotations

import asyncio
import threading
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from pbi_agent.auth.browser_callback import BrowserAuthCallbackListener
from pbi_agent.auth.models import (
    BrowserAuthChallenge,
    DeviceAuthChallenge,
    StoredAuthSession,
)
from pbi_agent.config import ResolvedRuntime
from pbi_agent.web.display import WebDisplay

APP_EVENT_STREAM_ID = "app"
_MAX_EVENT_HISTORY = 1000
_MAX_SUBSCRIBER_QUEUE_SIZE = 1000


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class EventStream:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._events: list[dict[str, Any]] = []
        self._subscribers: dict[
            str, tuple[asyncio.AbstractEventLoop, asyncio.Queue]
        ] = {}
        self._sequence = 0

    def publish(self, event_type: str, payload: dict[str, Any]) -> dict[str, Any]:
        with self._lock:
            self._sequence += 1
            event = {
                "seq": self._sequence,
                "type": event_type,
                "payload": payload,
                "created_at": _now_iso(),
            }
            self._events.append(event)
            if len(self._events) > _MAX_EVENT_HISTORY:
                self._events = self._events[-_MAX_EVENT_HISTORY:]
            subscribers = list(self._subscribers.values())
        for loop, queue in subscribers:
            loop.call_soon_threadsafe(_put_subscriber_event, queue, event)
        return event

    def load(self, events: list[dict[str, Any]]) -> None:
        with self._lock:
            for event in events:
                seq = event.get("seq")
                if not isinstance(seq, int) or seq <= 0:
                    continue
                self._sequence = max(self._sequence, seq)
                self._events.append(dict(event))
            if len(self._events) > _MAX_EVENT_HISTORY:
                self._events = self._events[-_MAX_EVENT_HISTORY:]

    def snapshot(self) -> list[dict[str, Any]]:
        with self._lock:
            return list(self._events)

    def bounds(self) -> tuple[int | None, int]:
        with self._lock:
            if not self._events:
                return None, self._sequence
            oldest_seq = self._events[0].get("seq")
            oldest = oldest_seq if isinstance(oldest_seq, int) else None
            return oldest, self._sequence

    def subscribe(self) -> tuple[str, asyncio.Queue]:
        subscriber_id = uuid.uuid4().hex
        queue: asyncio.Queue = asyncio.Queue(maxsize=_MAX_SUBSCRIBER_QUEUE_SIZE)
        with self._lock:
            self._subscribers[subscriber_id] = (asyncio.get_running_loop(), queue)
        return subscriber_id, queue

    def unsubscribe(self, subscriber_id: str) -> None:
        with self._lock:
            self._subscribers.pop(subscriber_id, None)

    def subscriber_count(self) -> int:
        with self._lock:
            return len(self._subscribers)


def _put_subscriber_event(queue: asyncio.Queue, event: dict[str, Any]) -> None:
    try:
        queue.put_nowait(event)
    except asyncio.QueueFull:
        while True:
            try:
                queue.get_nowait()
            except asyncio.QueueEmpty:
                break
        try:
            queue.put_nowait(_subscriber_overflow_event(event))
        except asyncio.QueueFull:
            pass


def _subscriber_overflow_event(event: dict[str, Any]) -> dict[str, Any]:
    seq = event.get("seq")
    latest_seq = seq if isinstance(seq, int) else 0
    return {
        "seq": latest_seq,
        "type": "server.replay_incomplete",
        "payload": {
            "reason": "subscriber_queue_overflow",
            "requested_since": 0,
            "resolved_since": 0,
            "oldest_available_seq": None,
            "latest_seq": latest_seq,
            "snapshot_required": True,
        },
        "created_at": _now_iso(),
    }


@dataclass(slots=True)
class LiveSessionState:
    live_session_id: str
    event_stream: EventStream
    snapshot: LiveSessionSnapshot
    display: WebDisplay
    worker: threading.Thread | None
    runtime: ResolvedRuntime
    bound_session_id: str | None
    created_at: str
    kind: str = "session"
    task_id: str | None = None
    project_dir: str = "."
    status: str = "starting"
    exit_code: int | None = None
    fatal_error: str | None = None
    terminal_status: str | None = None
    ended_at: str | None = None


@dataclass(slots=True)
class LiveSessionSnapshot:
    session_id: str | None = None
    runtime: dict[str, Any] | None = None
    input_enabled: bool = False
    wait_message: str | None = None
    processing: dict[str, Any] | None = None
    session_usage: dict[str, Any] | None = None
    turn_usage: dict[str, Any] | None = None
    session_ended: bool = False
    fatal_error: str | None = None
    pending_user_questions: dict[str, Any] | None = None
    items: list[dict[str, Any]] = None  # type: ignore[assignment]
    sub_agents: dict[str, dict[str, str]] = None  # type: ignore[assignment]
    last_event_seq: int = 0

    def __post_init__(self) -> None:
        if self.items is None:
            self.items = []
        if self.sub_agents is None:
            self.sub_agents = {}


@dataclass(slots=True)
class PendingProviderAuthFlow:
    flow_id: str
    provider_id: str
    backend: str
    method: str
    status: str
    created_at: str
    updated_at: str
    browser_auth: BrowserAuthChallenge | None = None
    browser_callback_listener: BrowserAuthCallbackListener | None = None
    browser_timeout_timer: threading.Timer | None = None
    device_auth: DeviceAuthChallenge | None = None
    authorization_url: str | None = None
    callback_url: str | None = None
    verification_url: str | None = None
    user_code: str | None = None
    interval_seconds: int | None = None
    error_message: str | None = None
    session: StoredAuthSession | None = None
