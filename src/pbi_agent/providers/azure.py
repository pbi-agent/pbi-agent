from __future__ import annotations

from dataclasses import replace
from enum import Enum
from urllib.parse import urlparse

from pbi_agent.config import Settings


class AzureEndpointKind(str, Enum):
    OPENAI_RESPONSES = "openai_responses"
    OPENAI_CHAT_COMPLETIONS = "openai_chat_completions"
    ANTHROPIC_MESSAGES = "anthropic_messages"


def azure_endpoint_kind(url: str) -> AzureEndpointKind:
    path = urlparse(url.strip()).path.rstrip("/").lower()
    if path.endswith("/anthropic/v1/messages"):
        return AzureEndpointKind.ANTHROPIC_MESSAGES
    if path.endswith("/openai/v1/responses"):
        return AzureEndpointKind.OPENAI_RESPONSES
    return AzureEndpointKind.OPENAI_CHAT_COMPLETIONS


def azure_chat_completions_url(url: str) -> str:
    stripped = url.strip().rstrip("/")
    path = urlparse(stripped).path.rstrip("/").lower()
    if path.endswith("/chat/completions") or path.endswith("/models"):
        return stripped
    return f"{stripped}/chat/completions"


def settings_for_azure_endpoint(settings: Settings) -> Settings:
    if settings.provider != "azure":
        return settings
    endpoint_kind = azure_endpoint_kind(settings.responses_url)
    if endpoint_kind == AzureEndpointKind.OPENAI_CHAT_COMPLETIONS:
        return replace(
            settings,
            provider="azure",
            generic_api_url=azure_chat_completions_url(settings.responses_url),
        )
    return settings
