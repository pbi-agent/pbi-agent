from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from pbi_agent.tools import registry
from pbi_agent.tools.types import ToolHandler, ToolSpec

_log = logging.getLogger(__name__)


@dataclass(slots=True, frozen=True)
class ToolCatalogEntry:
    spec: ToolSpec
    handler: ToolHandler


class ToolCatalog:
    def __init__(self, entries: dict[str, ToolCatalogEntry] | None = None) -> None:
        self._entries = dict(entries or {})

    def __len__(self) -> int:
        return len(self._entries)

    def __bool__(self) -> bool:
        return bool(self._entries)

    @classmethod
    def from_builtin_registry(cls) -> "ToolCatalog":
        entries: dict[str, ToolCatalogEntry] = {}
        for spec in registry.get_tool_specs():
            handler = registry.get_tool_handler(spec.name)
            if handler is None:
                continue
            entries[spec.name] = ToolCatalogEntry(spec=spec, handler=handler)
        return cls(entries)

    def merged(self, extra_entries: list[ToolCatalogEntry]) -> "ToolCatalog":
        merged = dict(self._entries)
        for entry in extra_entries:
            if entry.spec.name in self._entries:
                _log.warning(
                    "Skipping MCP tool %r: shadows a built-in tool with the same name",
                    entry.spec.name,
                )
                continue
            merged[entry.spec.name] = entry
        return ToolCatalog(merged)

    def get_specs(self, *, excluded_names: set[str] | None = None) -> list[ToolSpec]:
        excluded = excluded_names or set()
        return [
            entry.spec for name, entry in self._entries.items() if name not in excluded
        ]

    def get_handler(self, name: str) -> ToolHandler | None:
        entry = self._entries.get(name)
        if entry is None:
            return None
        return entry.handler

    def get_spec(self, name: str) -> ToolSpec | None:
        entry = self._entries.get(name)
        if entry is None:
            return None
        return entry.spec

    def get_openai_tool_definitions(
        self,
        *,
        excluded_names: set[str] | None = None,
    ) -> list[dict[str, Any]]:
        tools: list[dict[str, Any]] = []
        for spec in self.get_specs(excluded_names=excluded_names):
            tools.append(
                {
                    "type": "function",
                    "name": spec.name,
                    "description": spec.description,
                    "parameters": spec.parameters_schema,
                }
            )
        return tools

    def get_anthropic_tool_definitions(
        self,
        *,
        excluded_names: set[str] | None = None,
    ) -> list[dict[str, Any]]:
        tools: list[dict[str, Any]] = []
        for spec in self.get_specs(excluded_names=excluded_names):
            tools.append(
                {
                    "name": spec.name,
                    "description": spec.description,
                    "input_schema": spec.parameters_schema,
                }
            )
        return tools

    def get_openai_chat_tool_definitions(
        self,
        *,
        excluded_names: set[str] | None = None,
    ) -> list[dict[str, Any]]:
        tools: list[dict[str, Any]] = []
        for spec in self.get_specs(excluded_names=excluded_names):
            tools.append(
                {
                    "type": "function",
                    "function": {
                        "name": spec.name,
                        "description": spec.description,
                        "parameters": spec.parameters_schema,
                    },
                }
            )
        return tools
