"""Small reusable runtime helpers for provider wrappers."""

from __future__ import annotations

from pbi_agent.display.protocol import DisplayProtocol
from pbi_agent.models.messages import CompletedResponse, TokenUsage


def record_response_usage(
    response: CompletedResponse,
    *,
    display: DisplayProtocol,
    session_usage: TokenUsage,
    turn_usage: TokenUsage,
) -> None:
    """Accumulate response usage and publish the session usage snapshot."""
    session_usage.add(response.usage)
    turn_usage.add(response.usage)
    display.session_usage(session_usage)
