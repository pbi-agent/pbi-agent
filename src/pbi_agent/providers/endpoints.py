"""Reusable provider endpoint resolution helpers."""

from __future__ import annotations

from pbi_agent.config import Settings
from pbi_agent.providers.azure import (
    AzureEndpointKind,
    azure_chat_completions_url,
    azure_endpoint_kind,
)


def chat_completions_url(settings: Settings) -> str:
    """Return an OpenAI-compatible Chat Completions endpoint."""
    if settings.provider == "azure":
        return azure_chat_completions_url(settings.responses_url)
    return settings.generic_api_url


def anthropic_messages_url(settings: Settings, *, default_url: str) -> str:
    """Return an Anthropic Messages endpoint."""
    if (
        settings.provider == "azure"
        and azure_endpoint_kind(settings.responses_url)
        == AzureEndpointKind.ANTHROPIC_MESSAGES
    ):
        return settings.responses_url
    return default_url


def responses_url(settings: Settings) -> str:
    """Return the configured Responses-style endpoint."""
    return settings.responses_url
