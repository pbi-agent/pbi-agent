"""Provider factory.

Use :func:`create_provider` to instantiate the correct LLM provider based on
the current :class:`~pbi_agent.config.Settings`.
"""

from __future__ import annotations

from pbi_agent.config import Settings
from pbi_agent.providers.capabilities import image_excluded_tools
from pbi_agent.providers.base import Provider
from pbi_agent.tools.catalog import ToolCatalog


def create_provider(
    settings: Settings,
    *,
    system_prompt: str | None = None,
    excluded_tools: set[str] | None = None,
    tool_catalog: ToolCatalog | None = None,
) -> Provider:
    """Return a configured :class:`Provider` instance.

    The ``settings.provider`` field selects the backend:

    - ``"openai"`` (default) → OpenAI Responses HTTP provider
    - ``"azure"``     → Azure Responses HTTP provider
    - ``"chatgpt"``          → ChatGPT account-backed Responses HTTP provider
    - ``"github_copilot"``   → GitHub Copilot Responses HTTP provider
    - ``"xai"``              → xAI Responses HTTP provider
    - ``"google"``           → Google Gemini Interactions HTTP provider
    - ``"anthropic"``        → Anthropic Messages HTTP provider
    - ``"generic"``          → OpenAI-compatible Chat Completions HTTP provider
    """
    name = settings.provider.lower()
    effective_excluded_tools = set(excluded_tools or set())
    effective_excluded_tools.update(image_excluded_tools(name))

    if name == "azure":
        from pbi_agent.providers.anthropic_provider import AnthropicProvider
        from pbi_agent.providers.azure import (
            AzureEndpointKind,
            azure_endpoint_kind,
            settings_for_azure_endpoint,
        )
        from pbi_agent.providers.generic_provider import GenericProvider
        from pbi_agent.providers.openai_provider import OpenAIProvider

        azure_settings = settings_for_azure_endpoint(settings)
        endpoint_kind = azure_endpoint_kind(settings.responses_url)
        if endpoint_kind == AzureEndpointKind.ANTHROPIC_MESSAGES:
            return AnthropicProvider(
                azure_settings,
                system_prompt=system_prompt,
                excluded_tools=effective_excluded_tools,
                tool_catalog=tool_catalog,
            )
        if endpoint_kind == AzureEndpointKind.OPENAI_CHAT_COMPLETIONS:
            return GenericProvider(
                azure_settings,
                system_prompt=system_prompt,
                excluded_tools=effective_excluded_tools,
                tool_catalog=tool_catalog,
            )
        return OpenAIProvider(
            azure_settings,
            system_prompt=system_prompt,
            excluded_tools=effective_excluded_tools,
            tool_catalog=tool_catalog,
        )

    if name in {"openai", "chatgpt"}:
        from pbi_agent.providers.openai_provider import OpenAIProvider

        return OpenAIProvider(
            settings,
            system_prompt=system_prompt,
            excluded_tools=effective_excluded_tools,
            tool_catalog=tool_catalog,
        )

    if name == "github_copilot":
        from pbi_agent.providers.github_copilot_provider import GitHubCopilotProvider

        return GitHubCopilotProvider(
            settings,
            system_prompt=system_prompt,
            excluded_tools=effective_excluded_tools,
            tool_catalog=tool_catalog,
        )

    if name == "xai":
        from pbi_agent.providers.xai_provider import XAIProvider

        return XAIProvider(
            settings,
            system_prompt=system_prompt,
            excluded_tools=effective_excluded_tools,
            tool_catalog=tool_catalog,
        )

    if name == "google":
        from pbi_agent.providers.google_provider import GoogleProvider

        return GoogleProvider(
            settings,
            system_prompt=system_prompt,
            excluded_tools=effective_excluded_tools,
            tool_catalog=tool_catalog,
        )

    if name == "anthropic":
        from pbi_agent.providers.anthropic_provider import AnthropicProvider

        return AnthropicProvider(
            settings,
            system_prompt=system_prompt,
            excluded_tools=effective_excluded_tools,
            tool_catalog=tool_catalog,
        )

    if name == "generic":
        from pbi_agent.providers.generic_provider import GenericProvider

        return GenericProvider(
            settings,
            system_prompt=system_prompt,
            excluded_tools=effective_excluded_tools,
            tool_catalog=tool_catalog,
        )

    raise ValueError(
        "Unknown provider "
        f"{name!r}. Supported: openai, azure, chatgpt, github_copilot, xai, google, anthropic, generic."
    )


__all__ = ["Provider", "create_provider"]
