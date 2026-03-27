from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from pbi_agent.config import Settings
from pbi_agent.models.messages import CompletedResponse, TokenUsage, UserTurnInput
from pbi_agent.session_store import MessageRecord
from pbi_agent.ui.display_protocol import DisplayProtocol


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
    def reset_conversation(self) -> None:
        """Clear any provider-side conversation state for a fresh chat."""

    @abstractmethod
    def request_turn(
        self,
        *,
        user_message: str | None = None,
        user_input: UserTurnInput | None = None,
        tool_result_items: list[dict[str, Any]] | None = None,
        instructions: str | None = None,
        display: DisplayProtocol,
        session_usage: TokenUsage,
        turn_usage: TokenUsage,
    ) -> CompletedResponse:
        """Send a turn and return the model response.

        Exactly one of *user_message* / *user_input* or *tool_result_items* should be
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
        display: DisplayProtocol,
        session_usage: TokenUsage,
        turn_usage: TokenUsage,
        sub_agent_depth: int = 0,
    ) -> tuple[list[dict[str, Any]], bool]:
        """Execute every tool call present in *response*.

        Returns ``(tool_result_items, had_errors)`` where
        *tool_result_items* are in the provider's native format, ready
        to be passed back via :meth:`request_turn`.
        """

    @property
    @abstractmethod
    def settings(self) -> Settings:
        """Return the provider runtime settings."""

    # -- session resume -------------------------------------------------------

    def set_previous_response_id(self, response_id: str | None) -> None:
        """Set conversation continuation ID for session resume. No-op by default."""

    def restore_messages(self, messages: list[MessageRecord]) -> None:
        """Restore persisted conversation messages for client-side history providers."""

    def set_system_prompt(self, system_prompt: str) -> None:
        """Replace the provider-level system prompt for future turns. No-op by default."""

    def refresh_tools(self) -> None:
        """Rebuild provider tool definitions when dynamic schemas change."""

    # -- context manager convenience ----------------------------------------

    def __enter__(self) -> Provider:
        self.connect()
        return self

    def __exit__(self, *_: object) -> None:
        self.close()
