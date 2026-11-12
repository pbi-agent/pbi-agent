"""Headless web session channel.

Runs an agent turn through the exact same live-session pipeline the web UI
uses (``LiveSessionState`` + ``WebDisplay`` + persisted ``web_event`` records
+ ``web_session`` run projection), without a FastAPI server or web manager
lease. Non-web entry points such as ``pbi-agent run`` use it so every saved
session has the same persisted structure and opens identically in the web UI.
"""

from __future__ import annotations

import threading
import uuid
from collections.abc import Callable
from typing import Any, TypeVar, cast

from pbi_agent.config import ResolvedRuntime
from pbi_agent.display.protocol import DisplayProtocol
from pbi_agent.web.display import WebDisplay
from pbi_agent.web.session.events import EventsMixin
from pbi_agent.web.session.live_sessions import LiveSessionsMixin
from pbi_agent.web.session.serializers import _runtime_summary
from pbi_agent.web.session.state import (
    EventStream,
    LiveSessionSnapshot,
    LiveSessionState,
    _now_iso,
)
from pbi_agent.web.session.workers import WorkersMixin
from pbi_agent.workspace_context import current_workspace_context

_T = TypeVar("_T")


class HeadlessSessionChannel(LiveSessionsMixin, EventsMixin, WorkersMixin):
    """Single live session persisted through the shared web event pipeline."""

    def __init__(
        self,
        runtime: ResolvedRuntime,
        *,
        source: str = "cli",
        session_id: str | None = None,
        include_tool_history: bool = False,
        renderer: DisplayProtocol | None = None,
    ) -> None:
        self._renderer = renderer
        self._workspace_context = current_workspace_context()
        self._workspace_root = self._workspace_context.execution_root
        self._directory_key = self._workspace_context.directory_key
        self._app_stream = EventStream()
        self._live_sessions: dict[str, LiveSessionState] = {}
        self._lock = threading.Lock()
        self._run_source = source
        live_session_id = uuid.uuid4().hex
        display = WebDisplay(
            publish_event=lambda event_type, payload: self._publish_live_event(
                live_session_id, event_type, payload
            ),
            verbose=runtime.settings.verbose,
            model=runtime.settings.model,
            reasoning_effort=runtime.settings.reasoning_effort,
            bind_session=lambda bound: self._bind_live_session(live_session_id, bound),
        )
        self.live_session = LiveSessionState(
            live_session_id=live_session_id,
            event_stream=EventStream(),
            snapshot=LiveSessionSnapshot(
                session_id=session_id,
                runtime=_runtime_summary(runtime),
            ),
            display=display,
            worker=None,
            runtime=runtime,
            bound_session_id=session_id,
            created_at=_now_iso(),
            include_tool_history=include_tool_history,
        )
        self._live_sessions[live_session_id] = self.live_session

    @property
    def display(self) -> WebDisplay:
        return self.live_session.display

    def _maybe_submit_deferred_follow_up(self, live_session_id: str) -> None:
        del live_session_id  # headless runs have no follow-up queue

    def run(self, turn: Callable[[DisplayProtocol], _T]) -> _T:
        """Run ``turn`` with a display that persists web timeline events."""
        live_session = self.live_session
        live_session_id = live_session.live_session_id
        self._create_live_run_projection(live_session)
        self._publish_live_session_runtime(live_session)
        live_session.status = "running"
        self._publish_live_event(
            live_session_id,
            "session_state",
            {
                "state": "running",
                "live_session_id": live_session_id,
                "session_id": live_session.bound_session_id,
                "resume_session_id": live_session.bound_session_id,
            },
        )
        try:
            outcome = turn(TeeDisplayFactory.wrap(self.display, self._renderer))
            session_id = getattr(outcome, "session_id", None)
            if isinstance(session_id, str) and session_id:
                self._bind_live_session(live_session_id, session_id)
            if getattr(outcome, "tool_errors", False):
                live_session.exit_code = 4
            return outcome
        except KeyboardInterrupt:
            live_session.exit_code = 130
            live_session.terminal_status = "interrupted"
            raise
        except Exception as exc:
            from pbi_agent.agent.error_formatting import format_user_facing_error

            live_session.exit_code = 1
            live_session.fatal_error = format_user_facing_error(exc)
            self._publish_live_event(
                live_session_id,
                "message_added",
                {
                    "item_id": f"fatal-{uuid.uuid4().hex}",
                    "role": "error",
                    "content": live_session.fatal_error,
                    "markdown": False,
                },
            )
            raise
        finally:
            with self._lock:
                self._finalize_live_session_locked(live_session)


class TeeDisplay:
    """Forward display calls to the persisted web display and a renderer.

    The primary (web) display owns return values so identifiers stay those
    of the shared web pipeline; the secondary only renders (e.g. console).
    """

    def __init__(self, primary: Any, secondary: Any) -> None:
        self._primary = primary
        self._secondary = secondary

    @property
    def verbose(self) -> bool:
        return bool(getattr(self._secondary, "verbose", False))

    def begin_sub_agent(self, **kwargs: Any) -> TeeDisplay:
        return TeeDisplay(
            self._primary.begin_sub_agent(**kwargs),
            self._secondary.begin_sub_agent(**kwargs),
        )

    def __getattr__(self, name: str) -> Any:
        primary_attr = getattr(self._primary, name)
        if not callable(primary_attr):
            return primary_attr
        secondary_attr = getattr(self._secondary, name, None)

        def forward(*args: Any, **kwargs: Any) -> Any:
            result = primary_attr(*args, **kwargs)
            if callable(secondary_attr):
                secondary_attr(*args, **kwargs)
            return result

        return forward


class TeeDisplayFactory:
    @staticmethod
    def wrap(
        primary: DisplayProtocol, secondary: DisplayProtocol | None
    ) -> DisplayProtocol:
        if secondary is None:
            return primary
        return cast(DisplayProtocol, TeeDisplay(primary, secondary))


__all__ = ["HeadlessSessionChannel", "TeeDisplay"]
