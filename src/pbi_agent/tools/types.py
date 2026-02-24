from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol


@dataclass(slots=True)
class ToolSpec:
    name: str
    description: str
    parameters_schema: dict[str, Any]
    is_destructive: bool = False


@dataclass(slots=True)
class ToolContext:
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class ToolResult:
    call_id: str
    output_json: str
    is_error: bool = False


class ToolHandler(Protocol):
    def __call__(self, arguments: dict[str, Any], context: ToolContext) -> dict[str, Any] | str:
        ...
