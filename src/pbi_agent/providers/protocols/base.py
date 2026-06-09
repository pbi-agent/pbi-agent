"""Shared protocol adapter types."""

from __future__ import annotations

from typing import Protocol

from pbi_agent.models.messages import CompletedResponse
from pbi_agent.tools.types import ToolResult


class ResponseProtocol(Protocol):
    """Protocol adapter that parses model responses and serializes tool results."""

    def parse_response(self, response_json: dict[str, object]) -> CompletedResponse:
        """Parse a provider payload."""
        ...

    def serialize_tool_result(self, result: ToolResult) -> dict[str, object]:
        """Serialize a tool result for a follow-up request."""
        ...
