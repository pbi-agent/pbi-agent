from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol, TYPE_CHECKING

from pbi_agent.models.messages import ImageAttachment
from pbi_agent.session_store import MessageRecord

if TYPE_CHECKING:
    from pbi_agent.config import Settings
    from pbi_agent.models.messages import TokenUsage
    from pbi_agent.observability import RunTracer
    from pbi_agent.tools.catalog import ToolCatalog
    from pbi_agent.display.protocol import DisplayProtocol


@dataclass(slots=True)
class ToolSpec:
    name: str
    description: str
    parameters_schema: dict[str, Any]
    is_destructive: bool = False


@dataclass(slots=True, frozen=True)
class ParentContextSnapshot:
    provider: str
    continuation_id: str | None = None
    messages: tuple[MessageRecord, ...] = ()
    current_user_turn: str | None = None


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
    tool_catalog: ToolCatalog | None = None
    parent_context: ParentContextSnapshot | None = None
    tracer: RunTracer | None = None
    display_metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class ToolResult:
    call_id: str
    output_json: str
    is_error: bool = False
    attachments: list[ImageAttachment] = field(default_factory=list)
    display_metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class ToolOutput:
    result: dict[str, Any] | str
    attachments: list[ImageAttachment] = field(default_factory=list)
    display_metadata: dict[str, Any] = field(default_factory=dict)


class ToolHandler(Protocol):
    def __call__(
        self, arguments: dict[str, Any], context: ToolContext
    ) -> dict[str, Any] | str | ToolOutput: ...
