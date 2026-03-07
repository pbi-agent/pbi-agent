from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from pbi_agent.ui import Display
from pbi_agent.models.messages import CompletedResponse, TokenUsage


class Provider(ABC):
    """Abstract base for LLM providers.

    Each provider encapsulates:
    - Transport
    - Conversation history management
    - Tool definitions (provider-specific format)
    - Tool execution and result formatting
    """

    @abstractmethod
    def connect(self) -> None:
        """Establish the connection / session."""

    @abstractmethod
    def close(self) -> None:
        """Tear down the connection / session."""

    @abstractmethod
    def request_turn(
        self,
        *,
        user_message: str | None = None,
        tool_result_items: list[dict[str, Any]] | None = None,
        instructions: str | None = None,
        display: Display,
        session_usage: TokenUsage,
        turn_usage: TokenUsage,
    ) -> CompletedResponse:
        """Send a turn and return the model response.

        Exactly one of *user_message* or *tool_result_items* should be
        provided.  The provider manages history internally (server-side
        ``previous_response_id`` for OpenAI/xAI, client-side ``messages``
        list for Anthropic and generic chat-completions providers).
        """

    @abstractmethod
    def execute_tool_calls(
        self,
        response: CompletedResponse,
        *,
        max_workers: int,
        display: Display,
    ) -> tuple[list[dict[str, Any]], bool]:
        """Execute every tool call present in *response*.

        Returns ``(tool_result_items, had_errors)`` where
        *tool_result_items* are in the provider's native format, ready
        to be passed back via :meth:`request_turn`.
        """

    # -- context manager convenience ----------------------------------------

    def __enter__(self) -> Provider:
        self.connect()
        return self

    def __exit__(self, *_: object) -> None:
        self.close()
