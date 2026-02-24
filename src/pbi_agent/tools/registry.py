from __future__ import annotations

from typing import Any

from pbi_agent.tools.types import ToolHandler, ToolSpec

_REGISTRY: dict[str, tuple[ToolSpec, ToolHandler]] = {}


def get_tool_specs() -> list[ToolSpec]:
    return [item[0] for item in _REGISTRY.values()]


def get_tool_handler(name: str) -> ToolHandler | None:
    entry = _REGISTRY.get(name)
    if entry is None:
        return None
    return entry[1]


def get_tool_spec(name: str) -> ToolSpec | None:
    entry = _REGISTRY.get(name)
    if entry is None:
        return None
    return entry[0]


def get_openai_tool_definitions() -> list[dict[str, Any]]:
    tools: list[dict[str, Any]] = [{"type": "apply_patch"}, {"type": "shell"}]
    for spec in get_tool_specs():
        tools.append(
            {
                "type": "function",
                "name": spec.name,
                "description": spec.description,
                "parameters": spec.parameters_schema,
            }
        )
    return tools
