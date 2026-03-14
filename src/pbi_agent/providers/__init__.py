"""Provider factory.

Use :func:`create_provider` to instantiate the correct LLM provider based on
the current :class:`~pbi_agent.config.Settings`.
"""

from __future__ import annotations

from pbi_agent.config import Settings
from pbi_agent.providers.base import Provider


def create_provider(
    settings: Settings,
    *,
    system_prompt: str | None = None,
    excluded_tools: set[str] | None = None,
) -> Provider:
    """Return a configured :class:`Provider` instance.

    The ``settings.provider`` field selects the backend:

    - ``"openai"`` (default) → OpenAI Responses HTTP provider
    - ``"xai"``              → xAI Responses HTTP provider
    - ``"google"``           → Google Gemini Interactions HTTP provider
    - ``"anthropic"``        → Anthropic Messages HTTP provider
    - ``"generic"``          → OpenAI-compatible Chat Completions HTTP provider
    """
    name = settings.provider.lower()

    if name == "openai":
        from pbi_agent.providers.openai_provider import OpenAIProvider

        return OpenAIProvider(
            settings,
            system_prompt=system_prompt,
            excluded_tools=excluded_tools,
        )

    if name == "xai":
        from pbi_agent.providers.xai_provider import XAIProvider

        return XAIProvider(
            settings,
            system_prompt=system_prompt,
            excluded_tools=excluded_tools,
        )

    if name == "google":
        from pbi_agent.providers.google_provider import GoogleProvider

        return GoogleProvider(
            settings,
            system_prompt=system_prompt,
            excluded_tools=excluded_tools,
        )

    if name == "anthropic":
        from pbi_agent.providers.anthropic_provider import AnthropicProvider

        return AnthropicProvider(
            settings,
            system_prompt=system_prompt,
            excluded_tools=excluded_tools,
        )

    if name == "generic":
        from pbi_agent.providers.generic_provider import GenericProvider

        return GenericProvider(
            settings,
            system_prompt=system_prompt,
            excluded_tools=excluded_tools,
        )

    raise ValueError(
        f"Unknown provider {name!r}. Supported: openai, xai, google, anthropic, generic."
    )


__all__ = ["Provider", "create_provider"]
