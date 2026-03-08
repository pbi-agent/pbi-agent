from __future__ import annotations

import pytest

from pbi_agent.config import Settings
from pbi_agent.providers import create_provider
from pbi_agent.providers.anthropic_provider import AnthropicProvider
from pbi_agent.providers.generic_provider import GenericProvider
from pbi_agent.providers.google_provider import GoogleProvider
from pbi_agent.providers.openai_provider import OpenAIProvider
from pbi_agent.providers.xai_provider import XAIProvider


@pytest.mark.parametrize(
    ("provider_name", "expected_type"),
    [
        ("openai", OpenAIProvider),
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
    settings = Settings(api_key="test-key", provider=provider_name)

    provider = create_provider(settings)

    assert isinstance(provider, expected_type)
