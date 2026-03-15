from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol, TYPE_CHECKING

if TYPE_CHECKING:
    from pbi_agent.config import Settings
    from pbi_agent.models.messages import TokenUsage
    from pbi_agent.ui.display_protocol import DisplayProtocol


@dataclass(slots=True)
class ToolSpec:
    name: str
    description: str
    parameters_schema: dict[str, Any]
    is_destructive: bool = False


@dataclass(slots=True)
class ToolContext:
    """Runtime context passed to every tool handler.

    Typed fields are provided for the sub-agent runtime values that were
    previously accessed via the untyped ``metadata`` dict.
    """

    settings: Settings | None = None
    display: DisplayProtocol | None = None
    session_usage: TokenUsage | None = None
    turn_usage: TokenUsage | None = None
    sub_agent_depth: int = 0


@dataclass(slots=True)
class ToolResult:
    call_id: str
    output_json: str
    is_error: bool = False


class ToolHandler(Protocol):
    def __call__(
        self, arguments: dict[str, Any], context: ToolContext
    ) -> dict[str, Any] | str: ...
