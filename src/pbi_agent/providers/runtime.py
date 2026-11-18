"""Small reusable runtime helpers for provider wrappers."""

from __future__ import annotations

from pbi_agent.display.protocol import DisplayProtocol
from pbi_agent.models.messages import CompletedResponse, TokenUsage
from pbi_agent.providers.transport import SemanticResponseError


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


def record_failed_response_usage(
    exc: BaseException,
    *,
    display: DisplayProtocol,
    session_usage: TokenUsage,
    turn_usage: TokenUsage,
) -> None:
    """Accumulate usage the provider reported on a rejected HTTP 200 response.

    Semantic failures (for example a content-filtered completion) are raised
    before the response is parsed, but the tokens were still consumed.
    """
    error: BaseException | None = exc
    while error is not None and not isinstance(error, SemanticResponseError):
        error = error.__cause__
    if error is None or error.usage is None:
        return
    session_usage.add(error.usage)
    turn_usage.add(error.usage)
    display.session_usage(session_usage)
