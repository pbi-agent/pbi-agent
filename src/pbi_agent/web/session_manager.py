from __future__ import annotations

import argparse
import threading
import time
import uuid
from pathlib import Path

from pbi_agent.config import ResolvedRuntime, Settings
from pbi_agent.session_store import SessionStore, WebManagerLeaseBusyError
from pbi_agent.web.input_mentions import WorkspaceFileIndex
from pbi_agent.web.session.catalogs import CatalogsMixin
from pbi_agent.web.session.configuration import ConfigurationMixin
from pbi_agent.web.session.events import EventsMixin
from pbi_agent.web.session.live_sessions import LiveSessionsMixin
from pbi_agent.web.session.provider_auth import ProviderAuthMixin
from pbi_agent.web.session.saved_sessions import SavedSessionsMixin
from pbi_agent.web.session.state import (
    APP_EVENT_STREAM_ID,
    EventStream,
    LiveSessionState,
    PendingProviderAuthFlow,
)
from pbi_agent.web.session.tasks import TasksMixin
from pbi_agent.web.session.workers import WorkersMixin

_WEB_MANAGER_LEASE_STALE_SECS = 30.0
_WEB_MANAGER_LEASE_BUSY_RETRY_SECS = 2.0
_WEB_MANAGER_LEASE_BUSY_RETRY_DELAY_SECS = 0.1

__all__ = [
    "APP_EVENT_STREAM_ID",
    "WebManagerAlreadyRunningError",
    "WebManagerStartupError",
    "WebSessionManager",
]


class WebManagerStartupError(RuntimeError):
    """User-facing startup failure for the web manager."""


class WebManagerAlreadyRunningError(WebManagerStartupError):
    """Raised when another web server already owns the workspace lease."""


class WebSessionManager(
    CatalogsMixin,
    SavedSessionsMixin,
    LiveSessionsMixin,
    EventsMixin,
    TasksMixin,
    WorkersMixin,
    ConfigurationMixin,
    ProviderAuthMixin,
):
    def __init__(
        self,
        settings: Settings | ResolvedRuntime,
        *,
        runtime_args: argparse.Namespace | None = None,
    ) -> None:
        self._default_runtime = (
            settings
            if isinstance(settings, ResolvedRuntime)
            else ResolvedRuntime(settings=settings, provider_id=None, profile_id=None)
        )
        self._runtime_args = runtime_args
        self._workspace_root = Path.cwd().resolve()
        self._mention_index = WorkspaceFileIndex(self._workspace_root)
        self._directory_key = str(self._workspace_root).lower()
        self._app_stream = EventStream()
        self._live_sessions: dict[str, LiveSessionState] = {}
        self._provider_auth_flows: dict[str, PendingProviderAuthFlow] = {}
        self._task_workers: dict[str, threading.Thread] = {}
        self._running_task_ids: set[str] = set()
        self._manager_owner_id = uuid.uuid4().hex
        self._lease_stop = threading.Event()
        self._lease_thread: threading.Thread | None = None
        self._started = False
        self._shutdown_requested = False
        self._lock = threading.Lock()

    @property
    def workspace_root(self) -> Path:
        return self._workspace_root

    @property
    def settings(self) -> Settings:
        runtime = self._resolve_runtime_optional(None)
        if runtime is not None:
            return runtime.settings
        return self._default_runtime.settings

    def start(self) -> None:
        with self._lock:
            if self._started:
                return
        deadline = time.monotonic() + _WEB_MANAGER_LEASE_BUSY_RETRY_SECS
        while True:
            try:
                with SessionStore() as store:
                    acquired = store.acquire_web_manager_lease(
                        self._directory_key,
                        owner_id=self._manager_owner_id,
                        stale_after_seconds=_WEB_MANAGER_LEASE_STALE_SECS,
                    )
                    if not acquired:
                        raise WebManagerAlreadyRunningError(
                            "Another web app instance is already managing this workspace."
                        )
                    store.normalize_kanban_running_tasks(directory=self._directory_key)
                    store.mark_web_runs_stale(self._directory_key)
                break
            except WebManagerLeaseBusyError as exc:
                if time.monotonic() >= deadline:
                    raise WebManagerStartupError(
                        "Session database is busy. Try starting the web app again."
                    ) from exc
                time.sleep(_WEB_MANAGER_LEASE_BUSY_RETRY_DELAY_SECS)
        with self._lock:
            if self._started:
                return
            self._shutdown_requested = False
            self._lease_stop.clear()
            self._lease_thread = threading.Thread(
                target=self._renew_manager_lease_loop,
                daemon=True,
                name=f"pbi-agent-web-lease-{self._manager_owner_id[:8]}",
            )
            self._lease_thread.start()
            self._started = True
