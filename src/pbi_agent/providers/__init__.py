"""Provider factory.

Use :func:`create_provider` to instantiate the correct LLM provider based on
the current :class:`~pbi_agent.config.Settings`.
"""

from __future__ import annotations

from pbi_agent.config import Settings
from pbi_agent.providers.base import Provider


def create_provider(settings: Settings) -> Provider:
    """Return a configured :class:`Provider` instance.

    The ``settings.provider`` field selects the backend:

    - ``"openai"`` (default) → OpenAI Responses WebSocket provider
    - ``"anthropic"``        → Anthropic Messages HTTP provider
    - ``"generic"``          → OpenAI-compatible Chat Completions HTTP provider
    """
    name = settings.provider.lower()

    if name == "openai":
        from pbi_agent.providers.openai_provider import OpenAIProvider

        return OpenAIProvider(settings)

    if name == "anthropic":
        from pbi_agent.providers.anthropic_provider import AnthropicProvider

        return AnthropicProvider(settings)

    if name == "generic":
        from pbi_agent.providers.generic_provider import GenericProvider

        return GenericProvider(settings)

    raise ValueError(
        f"Unknown provider {name!r}. Supported: openai, anthropic, generic."
    )


__all__ = ["Provider", "create_provider"]
