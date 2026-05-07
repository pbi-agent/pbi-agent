from __future__ import annotations

from pathlib import Path
from typing import Any, Protocol, cast

from pbi_agent.config import ResolvedRuntime, list_command_configs
from pbi_agent.web.command_registry import (
    list_slash_commands,
    search_slash_command_tuples,
)
from pbi_agent.web.input_mentions import MentionSearchResult, WorkspaceFileIndex
from pbi_agent.web.session.state import LiveSessionState
from pbi_agent.workspace_context import WorkspaceContext


class _CatalogsManager(Protocol):
    _live_sessions: dict[str, LiveSessionState]
    _mention_index: WorkspaceFileIndex
    _workspace_context: WorkspaceContext
    _workspace_root: Path

    def _resolve_runtime_optional(
        self,
        profile_id: str | None,
    ) -> ResolvedRuntime | None: ...

    def _serialize_live_session(
        self,
        live_session: LiveSessionState,
    ) -> dict[str, Any]: ...

    def list_board_stages(self) -> list[dict[str, Any]]: ...

    def list_sessions(self) -> list[dict[str, Any]]: ...

    def list_tasks(self) -> list[dict[str, Any]]: ...


class CatalogsMixin:
    def _catalogs_manager(self) -> _CatalogsManager:
        return cast(_CatalogsManager, self)

    def warm_file_mentions_cache(self) -> None:
        self._catalogs_manager()._mention_index.warm_cache()

    def refresh_file_mentions_cache(self) -> None:
        manager = self._catalogs_manager()
        manager._mention_index.refresh_cache()
        manager._mention_index.warm_cache()

    def search_file_mentions(
        self,
        query: str,
        *,
        limit: int = 20,
    ) -> list[MentionSearchResult]:
        return self._catalogs_manager()._mention_index.search(query, limit=limit)

    def bootstrap(self) -> dict[str, Any]:
        manager = self._catalogs_manager()
        default_runtime = manager._resolve_runtime_optional(None)
        return {
            "workspace_root": str(manager._workspace_root),
            "workspace_key": manager._workspace_context.key,
            "workspace_display_path": manager._workspace_context.display_path,
            "is_sandbox": manager._workspace_context.is_sandbox,
            "provider": (
                default_runtime.settings.provider
                if default_runtime is not None
                else None
            ),
            "provider_id": default_runtime.provider_id if default_runtime else None,
            "profile_id": default_runtime.profile_id if default_runtime else None,
            "model": default_runtime.settings.model if default_runtime else None,
            "reasoning_effort": (
                default_runtime.settings.reasoning_effort
                if default_runtime is not None
                else None
            ),
            "supports_image_inputs": default_runtime is not None,
            "sessions": manager.list_sessions(),
            "tasks": manager.list_tasks(),
            "live_sessions": [
                manager._serialize_live_session(item)
                for item in manager._live_sessions.values()
            ],
            "board_stages": manager.list_board_stages(),
        }

    def search_slash_commands(
        self,
        query: str,
        *,
        limit: int = 10,
    ) -> list[dict[str, str]]:
        command_tuples = [
            (
                command.name,
                command.description,
                command.hidden_keywords,
                command.kind,
            )
            for command in list_slash_commands()
        ]
        for command in list_command_configs(self._catalogs_manager()._workspace_root):
            command_tuples.append(
                (
                    command.slash_alias,
                    command.description or f"Activate {command.name}",
                    f"{command.name} command prompt preset",
                    "command",
                )
            )
        return [
            {"name": name, "description": description, "kind": kind}
            for name, description, _keywords, kind in search_slash_command_tuples(
                query,
                command_tuples,
                limit=limit,
            )
        ]
