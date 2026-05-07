from __future__ import annotations

from typing import Any

from pbi_agent.config import list_command_configs
from pbi_agent.web.command_registry import (
    list_slash_commands,
    search_slash_command_tuples,
)
from pbi_agent.web.input_mentions import MentionSearchResult


class CatalogsMixin:
    def warm_file_mentions_cache(self) -> None:
        self._mention_index.warm_cache()

    def refresh_file_mentions_cache(self) -> None:
        self._mention_index.refresh_cache()
        self._mention_index.warm_cache()

    def search_file_mentions(
        self,
        query: str,
        *,
        limit: int = 20,
    ) -> list[MentionSearchResult]:
        return self._mention_index.search(query, limit=limit)

    def bootstrap(self) -> dict[str, Any]:
        default_runtime = self._resolve_runtime_optional(None)
        return {
            "workspace_root": str(self._workspace_root),
            "workspace_key": self._workspace_context.key,
            "workspace_display_path": self._workspace_context.display_path,
            "is_sandbox": self._workspace_context.is_sandbox,
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
            "sessions": self.list_sessions(),
            "tasks": self.list_tasks(),
            "live_sessions": [
                self._serialize_live_session(item)
                for item in self._live_sessions.values()
            ],
            "board_stages": self.list_board_stages(),
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
        for command in list_command_configs(self._workspace_root):
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
