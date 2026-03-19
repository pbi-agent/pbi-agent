from __future__ import annotations

import json
from pathlib import Path

import pytest

import pbi_agent.config as config_module
from pbi_agent.cli import build_parser
from pbi_agent.config import (
    ConfigError,
    DEFAULT_RESPONSES_URL,
    Settings,
    resolve_settings,
    save_internal_config,
)


def test_resolve_settings_uses_saved_provider_when_none_specified(
    monkeypatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(config_module, "load_dotenv", lambda: None)
    internal_config = tmp_path / "internal-config.json"
    monkeypatch.setenv("PBI_AGENT_INTERNAL_CONFIG_PATH", str(internal_config))
    for name in (
        "PBI_AGENT_PROVIDER",
        "PBI_AGENT_API_KEY",
        "OPENAI_API_KEY",
        "XAI_API_KEY",
    ):
        monkeypatch.delenv(name, raising=False)

    save_internal_config(
        Settings(
            api_key="xai-saved-key",
            provider="xai",
            responses_url="https://api.x.ai/v1/responses",
            model="grok-4-1-fast-reasoning",
            reasoning_effort="high",
            max_tool_workers=6,
            max_retries=5,
            compact_threshold=123456,
        )
    )

    parser = build_parser()
    args = parser.parse_args(["console"])

    settings = resolve_settings(args)

    assert settings.provider == "xai"
    assert settings.api_key == "xai-saved-key"
    assert settings.max_tool_workers == 6
    assert settings.max_retries == 5
    assert settings.compact_threshold == 123456


def test_resolve_settings_uses_saved_generic_api_url(
    monkeypatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(config_module, "load_dotenv", lambda: None)
    internal_config = tmp_path / "internal-config.json"
    monkeypatch.setenv("PBI_AGENT_INTERNAL_CONFIG_PATH", str(internal_config))
    for name in (
        "PBI_AGENT_PROVIDER",
        "PBI_AGENT_API_KEY",
        "GENERIC_API_KEY",
        "PBI_AGENT_GENERIC_API_URL",
    ):
        monkeypatch.delenv(name, raising=False)

    save_internal_config(
        Settings(
            api_key="generic-saved-key",
            provider="generic",
            responses_url=DEFAULT_RESPONSES_URL,
            generic_api_url="https://example.test/v1/chat/completions",
            model="openrouter/custom-model",
            reasoning_effort="high",
        )
    )

    parser = build_parser()
    args = parser.parse_args(["console"])

    settings = resolve_settings(args)

    assert settings.provider == "generic"
    assert settings.generic_api_url == "https://example.test/v1/chat/completions"


def test_resolve_settings_uses_saved_anthropic_model(
    monkeypatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(config_module, "load_dotenv", lambda: None)
    internal_config = tmp_path / "internal-config.json"
    monkeypatch.setenv("PBI_AGENT_INTERNAL_CONFIG_PATH", str(internal_config))
    for name in (
        "PBI_AGENT_PROVIDER",
        "PBI_AGENT_API_KEY",
        "ANTHROPIC_API_KEY",
        "PBI_AGENT_MODEL",
    ):
        monkeypatch.delenv(name, raising=False)

    save_internal_config(
        Settings(
            api_key="anthropic-saved-key",
            provider="anthropic",
            responses_url=DEFAULT_RESPONSES_URL,
            model="claude-sonnet-4-5",
            reasoning_effort="high",
        )
    )

    parser = build_parser()
    args = parser.parse_args(["console"])

    settings = resolve_settings(args)

    assert settings.provider == "anthropic"
    assert settings.model == "claude-sonnet-4-5"


def test_resolve_settings_uses_saved_sub_agent_model(
    monkeypatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(config_module, "load_dotenv", lambda: None)
    internal_config = tmp_path / "internal-config.json"
    monkeypatch.setenv("PBI_AGENT_INTERNAL_CONFIG_PATH", str(internal_config))
    for name in (
        "PBI_AGENT_PROVIDER",
        "PBI_AGENT_API_KEY",
        "OPENAI_API_KEY",
        "PBI_AGENT_MODEL",
        "PBI_AGENT_SUB_AGENT_MODEL",
    ):
        monkeypatch.delenv(name, raising=False)

    save_internal_config(
        Settings(
            api_key="openai-saved-key",
            provider="openai",
            responses_url=DEFAULT_RESPONSES_URL,
            model="gpt-5.4-2026-03-05",
            sub_agent_model="gpt-5.4-mini",
            reasoning_effort="xhigh",
        )
    )

    parser = build_parser()
    args = parser.parse_args(["console"])

    settings = resolve_settings(args)

    assert settings.provider == "openai"
    assert settings.model == "gpt-5.4-2026-03-05"
    assert settings.sub_agent_model == "gpt-5.4-mini"


def test_resolve_settings_prefers_cli_sub_agent_model_over_env_and_config(
    monkeypatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(config_module, "load_dotenv", lambda: None)
    internal_config = tmp_path / "internal-config.json"
    monkeypatch.setenv("PBI_AGENT_INTERNAL_CONFIG_PATH", str(internal_config))
    monkeypatch.setenv("PBI_AGENT_PROVIDER", "openai")
    monkeypatch.setenv("OPENAI_API_KEY", "openai-test-key")
    monkeypatch.setenv("PBI_AGENT_SUB_AGENT_MODEL", "gpt-5.4-env")

    save_internal_config(
        Settings(
            api_key="openai-saved-key",
            provider="openai",
            responses_url=DEFAULT_RESPONSES_URL,
            model="gpt-5.4-2026-03-05",
            sub_agent_model="gpt-5.4-saved",
            reasoning_effort="xhigh",
        )
    )

    parser = build_parser()
    args = parser.parse_args(["--sub-agent-model", "gpt-5.4-cli", "console"])

    settings = resolve_settings(args)

    assert settings.sub_agent_model == "gpt-5.4-cli"


def test_resolve_settings_rejects_invalid_service_tier_from_env(monkeypatch) -> None:
    monkeypatch.setattr(config_module, "load_dotenv", lambda: None)
    monkeypatch.setenv("PBI_AGENT_PROVIDER", "openai")
    monkeypatch.setenv("OPENAI_API_KEY", "openai-test-key")
    monkeypatch.setenv("PBI_AGENT_SERVICE_TIER", "bogus")

    parser = build_parser()
    args = parser.parse_args(["console"])
    settings = resolve_settings(args)

    with pytest.raises(ConfigError, match="--service-tier must be one of"):
        settings.validate()


def test_resolve_settings_rejects_invalid_service_tier_from_saved_config(
    monkeypatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(config_module, "load_dotenv", lambda: None)
    internal_config = tmp_path / "internal-config.json"
    monkeypatch.setenv("PBI_AGENT_INTERNAL_CONFIG_PATH", str(internal_config))
    for name in (
        "PBI_AGENT_PROVIDER",
        "PBI_AGENT_API_KEY",
        "OPENAI_API_KEY",
        "PBI_AGENT_SERVICE_TIER",
    ):
        monkeypatch.delenv(name, raising=False)

    internal_config.write_text(
        json.dumps(
            {
                "last_used_provider": "openai",
                "providers": {
                    "openai": {
                        "api_key": "openai-saved-key",
                        "service_tier": "bogus",
                    }
                },
            }
        ),
        encoding="utf-8",
    )

    parser = build_parser()
    args = parser.parse_args(["console"])
    settings = resolve_settings(args)

    with pytest.raises(ConfigError, match="--service-tier must be one of"):
        settings.validate()


def test_save_internal_config_persists_by_provider_and_last_used(
    monkeypatch, tmp_path: Path
) -> None:
    internal_config = tmp_path / "internal-config.json"
    monkeypatch.setenv("PBI_AGENT_INTERNAL_CONFIG_PATH", str(internal_config))

    save_internal_config(
        Settings(
            api_key="openai-key",
            provider="openai",
            responses_url=DEFAULT_RESPONSES_URL,
            model="gpt-5.4-2026-03-05",
            sub_agent_model="gpt-5.4-mini",
            reasoning_effort="xhigh",
        )
    )
    save_internal_config(
        Settings(
            api_key="xai-key",
            provider="xai",
            responses_url="https://api.x.ai/v1/responses",
            model="grok-4-1-fast-reasoning",
            reasoning_effort="high",
        )
    )

    content = internal_config.read_text(encoding="utf-8")

    assert '"last_used_provider": "xai"' in content
    assert '"openai": {' in content
    assert '"sub_agent_model": "gpt-5.4-mini"' in content
    assert '"xai": {' in content
