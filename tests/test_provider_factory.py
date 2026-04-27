from __future__ import annotations

import pytest

from pbi_agent.config import Settings
from pbi_agent.auth.models import OAuthSessionAuth
from pbi_agent.auth.providers.github_copilot import GITHUB_COPILOT_RESPONSES_URL
from pbi_agent.providers import create_provider
from pbi_agent.providers.anthropic_provider import AnthropicProvider
from pbi_agent.providers.generic_provider import GenericProvider
from pbi_agent.providers.github_copilot_provider import GitHubCopilotProvider
from pbi_agent.providers.google_provider import GoogleProvider
from pbi_agent.providers.openai_provider import OpenAIProvider
from pbi_agent.providers.xai_provider import XAIProvider


@pytest.mark.parametrize(
    ("provider_name", "expected_type"),
    [
        ("openai", OpenAIProvider),
        ("chatgpt", OpenAIProvider),
        ("github_copilot", GitHubCopilotProvider),
        ("xai", XAIProvider),
        ("google", GoogleProvider),
        ("anthropic", AnthropicProvider),
        ("generic", GenericProvider),
    ],
)
def test_create_provider_returns_expected_backend(
    provider_name: str,
    expected_type: type,
) -> None:
    if provider_name == "github_copilot":
        settings = Settings(
            api_key="",
            provider=provider_name,
            responses_url=GITHUB_COPILOT_RESPONSES_URL,
            auth=OAuthSessionAuth(
                provider_id="copilot-main",
                backend="github_copilot",
                access_token="gho_test_token",
            ),
        )
    elif provider_name == "chatgpt":
        settings = Settings(
            api_key="",
            provider=provider_name,
            auth=OAuthSessionAuth(
                provider_id="chatgpt-main",
                backend="openai_chatgpt",
                access_token="access-token",
            ),
        )
    else:
        settings = Settings(api_key="test-key", provider=provider_name)

    provider = create_provider(settings)

    assert isinstance(provider, expected_type)


@pytest.mark.parametrize(
    ("url", "expected_type"),
    [
        (
            "https://mca-resource.openai.azure.com/openai/v1/responses",
            OpenAIProvider,
        ),
        ("https://mca-resource.openai.azure.com/openai/v1", GenericProvider),
        (
            "https://mca-resource.services.ai.azure.com/anthropic/v1/messages",
            AnthropicProvider,
        ),
    ],
)
def test_azure_routes_by_endpoint_url(url: str, expected_type: type) -> None:
    provider = create_provider(
        Settings(
            api_key="azure-key",
            provider="azure",
            responses_url=url,
        )
    )

    assert isinstance(provider, expected_type)
