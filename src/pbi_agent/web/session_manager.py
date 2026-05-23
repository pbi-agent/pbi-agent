from __future__ import annotations

import argparse
import threading
import time
import uuid
from pathlib import Path
from typing import Any

from pbi_agent.config import ResolvedRuntime, Settings
from pbi_agent.session_store import (
    RecentWorkspaceRecord,
    SessionStore,
    WebManagerLeaseBusyError,
)
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
from pbi_agent.workspace_context import (
    WorkspaceContext,
    current_workspace_context,
    workspace_context_from_root,
)

_WEB_MANAGER_LEASE_STALE_SECS = 30.0
_WEB_MANAGER_LEASE_BUSY_RETRY_SECS = 2.0
_WEB_MANAGER_LEASE_BUSY_RETRY_DELAY_SECS = 0.1

__all__ = [
    "APP_EVENT_STREAM_ID",
    "WebManagerAlreadyRunningError",
    "WebManagerStartupError",
    "WebSessionManager",
    "WebWorkspaceCoordinator",
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
        workspace_context: WorkspaceContext | None = None,
    ) -> None:
        self._default_runtime = (
            settings
            if isinstance(settings, ResolvedRuntime)
            else ResolvedRuntime(settings=settings, provider_id=None, profile_id=None)
        )
        self._runtime_args = runtime_args
        self._workspace_context = workspace_context or current_workspace_context()
        self._workspace_root = self._workspace_context.execution_root
        self._mention_index = WorkspaceFileIndex(self._workspace_root)
        self._directory_key = self._workspace_context.directory_key
        self._app_stream = EventStream()
        self._live_sessions: dict[str, LiveSessionState] = {}
        self._provider_auth_flows: dict[str, PendingProviderAuthFlow] = {}
        self._task_workers: dict[str, threading.Thread] = {}
        self._running_task_ids: set[str] = set()
        self._shutdown_interrupted_task_ids: set[str] = set()
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
    def workspace_key(self) -> str:
        return self._workspace_context.key

    @property
    def workspace_display_path(self) -> str:
        return self._workspace_context.display_path

    @property
    def is_sandbox(self) -> bool:
        return self._workspace_context.is_sandbox

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
            self._shutdown_interrupted_task_ids.clear()
            self._lease_stop.clear()
            self._lease_thread = threading.Thread(
                target=self._renew_manager_lease_loop,
                daemon=True,
                name=f"pbi-agent-web-lease-{self._manager_owner_id[:8]}",
            )
            self._lease_thread.start()
            self._started = True


class WebWorkspaceCoordinator:
    _COORDINATOR_ATTRS = {
        "_settings",
        "_runtime_args",
        "_managers",
        "_active_directory_key",
        "_lock",
    }

    def __init__(
        self,
        settings: Settings | ResolvedRuntime,
        *,
        runtime_args: argparse.Namespace | None = None,
    ) -> None:
        self._settings = settings
        self._runtime_args = runtime_args
        initial_context = current_workspace_context()
        initial_manager = WebSessionManager(
            settings,
            runtime_args=runtime_args,
            workspace_context=initial_context,
        )
        self._managers: dict[str, WebSessionManager] = {
            initial_context.directory_key: initial_manager,
        }
        self._active_directory_key = initial_context.directory_key
        self._lock = threading.Lock()

    @property
    def active_manager(self) -> WebSessionManager:
        with self._lock:
            return self._managers[self._active_directory_key]

    @property
    def workspace_root(self) -> Path:
        return self.active_manager.workspace_root

    @property
    def workspace_key(self) -> str:
        return self.active_manager.workspace_key

    @property
    def workspace_display_path(self) -> str:
        return self.active_manager.workspace_display_path

    @property
    def is_sandbox(self) -> bool:
        return self.active_manager.is_sandbox

    @property
    def settings(self) -> Settings:
        return self.active_manager.settings

    def __getattr__(self, name: str) -> Any:
        return getattr(self.active_manager, name)

    def __setattr__(self, name: str, value: Any) -> None:
        if (
            name in self._COORDINATOR_ATTRS
            or "_managers" not in self.__dict__
            or hasattr(type(self), name)
        ):
            object.__setattr__(self, name, value)
            return
        active_manager = self.active_manager
        if hasattr(active_manager, name):
            setattr(active_manager, name, value)
            return
        object.__setattr__(self, name, value)

    def start(self) -> None:
        manager = self.active_manager
        manager.start()
        self._record_recent_workspace(manager)

    def shutdown(self) -> None:
        with self._lock:
            managers = list(self._managers.values())
        for manager in managers:
            manager.shutdown()

    def warm_file_mentions_cache(self) -> None:
        self.active_manager.warm_file_mentions_cache()

    def list_recent_workspaces(self, *, limit: int = 20) -> list[dict[str, Any]]:
        with SessionStore() as store:
            records = store.list_recent_workspaces(limit=limit)
        active_key = self.active_manager._directory_key
        return [
            self._serialize_recent_workspace(
                record, is_current=record.directory_key == active_key
            )
            for record in records
        ]

    def switch_to_recent_workspace(self, directory_key: str) -> dict[str, Any]:
        with SessionStore() as store:
            record = store.get_recent_workspace(directory_key)
        if record is None:
            raise KeyError(directory_key)
        root = Path(record.root_path).expanduser()
        if not root.exists() or not root.is_dir():
            raise ValueError("Recent workspace folder is no longer available.")
        context = WorkspaceContext(
            execution_root=root.resolve(),
            key=record.directory_key,
            directory_key=record.directory_key,
            display_path=record.display_path,
            is_sandbox=record.is_sandbox,
        )
        return self._switch_to_context(context)

    def switch_to_folder(self, folder: Path) -> dict[str, Any]:
        root = folder.expanduser().resolve()
        if not root.exists() or not root.is_dir():
            raise ValueError("Selected workspace folder is not available.")
        return self._switch_to_context(workspace_context_from_root(root))

    def choose_folder_and_switch(self) -> dict[str, Any]:
        try:
            import tkinter as tk
            from tkinter import filedialog
        except Exception as exc:
            return {
                "status": "unavailable",
                "message": f"Native folder picker is unavailable: {exc}",
                "bootstrap": None,
            }

        try:
            root = tk.Tk()
            root.withdraw()
            root.attributes("-topmost", True)
            selected = filedialog.askdirectory(title="Choose pbi-agent workspace")
            root.destroy()
        except Exception as exc:
            return {
                "status": "error",
                "message": f"Native folder picker failed: {exc}",
                "bootstrap": None,
            }
        if not selected:
            return {
                "status": "canceled",
                "message": "Folder selection was canceled.",
                "bootstrap": None,
            }
        bootstrap = self.switch_to_folder(Path(selected))
        return {"status": "switched", "message": None, "bootstrap": bootstrap}

    def _switch_to_context(self, context: WorkspaceContext) -> dict[str, Any]:
        with self._lock:
            previous_manager = self._managers[self._active_directory_key]
            existing = self._managers.get(context.directory_key)
            if existing is not None:
                self._active_directory_key = context.directory_key
                manager = existing
            else:
                manager = WebSessionManager(
                    self._settings,
                    runtime_args=self._runtime_args,
                    workspace_context=context,
                )
                manager.start()
                self._managers[context.directory_key] = manager
                self._active_directory_key = context.directory_key
        self._record_recent_workspace(manager)
        bootstrap = manager.bootstrap()
        if previous_manager is not manager:
            previous_manager._app_stream.publish(
                "workspace_switched",
                {"workspace_key": manager.workspace_key},
            )
        manager._app_stream.publish(
            "workspace_switched",
            {"workspace_key": manager.workspace_key},
        )
        return bootstrap

    def _record_recent_workspace(self, manager: WebSessionManager) -> None:
        with SessionStore() as store:
            store.record_recent_workspace(
                directory_key=manager._directory_key,
                root_path=str(manager.workspace_root),
                display_path=manager.workspace_display_path,
                is_sandbox=manager.is_sandbox,
            )

    @staticmethod
    def _serialize_recent_workspace(
        record: RecentWorkspaceRecord,
        *,
        is_current: bool,
    ) -> dict[str, Any]:
        return {
            "directory_key": record.directory_key,
            "root_path": record.root_path,
            "display_path": record.display_path,
            "is_sandbox": record.is_sandbox,
            "last_opened_at": record.last_opened_at,
            "is_current": is_current,
        }
