from __future__ import annotations

import argparse
import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

DEFAULT_RESPONSES_URL = "https://api.openai.com/v1/responses"
DEFAULT_XAI_RESPONSES_URL = "https://api.x.ai/v1/responses"
DEFAULT_GOOGLE_INTERACTIONS_URL = (
    "https://generativelanguage.googleapis.com/v1beta/interactions"
)
DEFAULT_GENERIC_API_URL = "https://openrouter.ai/api/v1/chat/completions"
DEFAULT_MODEL = "gpt-5.4-2026-03-05"
DEFAULT_XAI_MODEL = "grok-4-1-fast-reasoning"
DEFAULT_GOOGLE_MODEL = "gemini-3.1-flash-lite-preview"
DEFAULT_ANTHROPIC_MODEL = "claude-opus-4-6"
DEFAULT_MAX_TOKENS = 16384
PROVIDER_API_KEY_ENVS = {
    "openai": "OPENAI_API_KEY",
    "xai": "XAI_API_KEY",
    "google": "GEMINI_API_KEY",
    "anthropic": "ANTHROPIC_API_KEY",
    "generic": "GENERIC_API_KEY",
}
INTERNAL_CONFIG_PATH_ENV = "PBI_AGENT_INTERNAL_CONFIG_PATH"
DEFAULT_INTERNAL_CONFIG_PATH = Path.home() / ".pbi-agent" / "config.json"


class ConfigError(ValueError):
    """Raised when required runtime configuration is invalid."""


def missing_api_key_message(provider: str) -> str:
    if provider == "google":
        return (
            "Missing API key for provider 'google'. Set GEMINI_API_KEY (or "
            "PBI_AGENT_API_KEY) in environment, or pass --google-api-key "
            "(or --api-key)."
        )
    return (
        f"Missing API key for provider '{provider}'. Set PBI_AGENT_API_KEY in "
        "environment or pass --api-key."
    )


@dataclass(slots=True)
class Settings:
    api_key: str
    responses_url: str = DEFAULT_RESPONSES_URL
    model: str = DEFAULT_MODEL
    max_tokens: int = DEFAULT_MAX_TOKENS
    verbose: bool = False
    max_tool_workers: int = 4
    max_retries: int = 3
    reasoning_effort: str = "xhigh"
    compact_threshold: int = 200000
    # Provider selection
    provider: str = "openai"
    generic_api_url: str = DEFAULT_GENERIC_API_URL

    def validate(self) -> None:
        if self.provider not in {"openai", "xai", "google", "anthropic", "generic"}:
            raise ConfigError(
                "--provider must be one of: openai, xai, google, anthropic, generic."
            )
        if not self.api_key:
            raise ConfigError(missing_api_key_message(self.provider))
        if self.max_tool_workers < 1:
            raise ConfigError("--max-tool-workers must be >= 1.")
        if self.max_retries < 0:
            raise ConfigError("--max-retries must be >= 0.")
        if self.reasoning_effort not in {"low", "medium", "high", "xhigh"}:
            raise ConfigError(
                "--reasoning-effort must be one of: low, medium, high, xhigh."
            )
        if self.compact_threshold < 1:
            raise ConfigError("--compact-threshold must be >= 1.")
        if self.max_tokens < 1:
            raise ConfigError("--max-tokens must be >= 1.")

    def redacted(self) -> dict[str, str | int | bool]:
        return {
            "provider": self.provider,
            "api_key": redact_secret(self.api_key),
            "responses_url": self.responses_url,
            "model": self.model,
            "max_tokens": self.max_tokens,
            "verbose": self.verbose,
            "max_tool_workers": self.max_tool_workers,
            "max_retries": self.max_retries,
            "reasoning_effort": self.reasoning_effort,
            "compact_threshold": self.compact_threshold,
            "generic_api_url": self.generic_api_url,
        }


def redact_secret(value: str) -> str:
    if not value:
        return ""
    if len(value) <= 8:
        return "***"
    return f"{value[:4]}...{value[-4:]}"


def _default_responses_url(provider: str) -> str:
    if provider == "xai":
        return DEFAULT_XAI_RESPONSES_URL
    if provider == "google":
        return DEFAULT_GOOGLE_INTERACTIONS_URL
    return DEFAULT_RESPONSES_URL


def _default_model(provider: str) -> str:
    if provider == "generic":
        return ""
    if provider == "xai":
        return DEFAULT_XAI_MODEL
    if provider == "google":
        return DEFAULT_GOOGLE_MODEL
    if provider == "anthropic":
        return DEFAULT_ANTHROPIC_MODEL
    return DEFAULT_MODEL


def resolve_settings(args: argparse.Namespace) -> Settings:
    load_dotenv()

    internal_config = _read_internal_config()
    providers_config = _provider_configs(internal_config)

    provider_from_cli = getattr(args, "provider", None)
    provider_from_env = os.getenv("PBI_AGENT_PROVIDER")
    provider = (
        provider_from_cli
        or provider_from_env
        or _last_used_provider(internal_config)
        or "openai"
    )
    provider_config = providers_config.get(provider, {})

    api_key = (
        getattr(args, "api_key", None)
        or os.getenv("PBI_AGENT_API_KEY", "")
        or os.getenv(PROVIDER_API_KEY_ENVS.get(provider, ""), "")
        or str(provider_config.get("api_key", ""))
    )
    responses_url_override = getattr(args, "responses_url", None) or os.getenv(
        "PBI_AGENT_RESPONSES_URL"
    )
    generic_api_url = (
        getattr(args, "generic_api_url", None)
        or os.getenv("PBI_AGENT_GENERIC_API_URL")
        or _config_string(provider_config, "generic_api_url")
    )
    responses_url = (
        responses_url_override
        or _config_string(provider_config, "responses_url")
        or _default_responses_url(provider)
    )
    model_override = args.model or os.getenv("PBI_AGENT_MODEL")
    if not model_override:
        model_override = _config_string(provider_config, "model")
    model = model_override or _default_model(provider)
    max_tool_workers = args.max_tool_workers
    if max_tool_workers is None:
        max_tool_workers = int(
            os.getenv(
                "PBI_AGENT_MAX_TOOL_WORKERS",
                str(_config_int(provider_config, "max_tool_workers", 4)),
            )
        )
    max_retries = args.max_retries
    if max_retries is None:
        max_retries = int(
            os.getenv(
                "PBI_AGENT_MAX_RETRIES",
                str(_config_int(provider_config, "max_retries", 3)),
            )
        )
    default_effort = "xhigh" if provider == "openai" else "high"
    reasoning_effort = (
        args.reasoning_effort
        or os.getenv("PBI_AGENT_REASONING_EFFORT")
        or _config_string(provider_config, "reasoning_effort")
        or default_effort
    )
    compact_threshold = args.compact_threshold
    if compact_threshold is None:
        compact_threshold = int(
            os.getenv(
                "PBI_AGENT_COMPACT_THRESHOLD",
                str(_config_int(provider_config, "compact_threshold", 150000)),
            )
        )

    max_tokens_raw = getattr(args, "max_tokens", None)

    if max_tokens_raw is None:
        max_tokens = int(
            os.getenv(
                "PBI_AGENT_MAX_TOKENS",
                str(_config_int(provider_config, "max_tokens", DEFAULT_MAX_TOKENS)),
            )
        )
    else:
        max_tokens = int(max_tokens_raw)

    return Settings(
        api_key=api_key,
        responses_url=responses_url,
        generic_api_url=generic_api_url or DEFAULT_GENERIC_API_URL,
        model=model,
        max_tokens=max_tokens,
        verbose=bool(args.verbose),
        max_tool_workers=max_tool_workers,
        max_retries=max_retries,
        reasoning_effort=reasoning_effort,
        compact_threshold=compact_threshold,
        provider=provider,
    )


def save_internal_config(settings: Settings) -> None:
    path = _internal_config_path()
    data = _read_internal_config()
    providers = _provider_configs(data)
    providers[settings.provider] = {
        "api_key": settings.api_key,
        "responses_url": settings.responses_url,
        "generic_api_url": settings.generic_api_url,
        "model": settings.model,
        "max_tokens": settings.max_tokens,
        "reasoning_effort": settings.reasoning_effort,
        "max_tool_workers": settings.max_tool_workers,
        "max_retries": settings.max_retries,
        "compact_threshold": settings.compact_threshold,
    }
    data["providers"] = providers
    data["last_used_provider"] = settings.provider
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=True), encoding="utf-8")


def _internal_config_path() -> Path:
    configured_path = os.getenv(INTERNAL_CONFIG_PATH_ENV)
    if configured_path:
        return Path(configured_path).expanduser().resolve()
    return DEFAULT_INTERNAL_CONFIG_PATH


def _read_internal_config() -> dict[str, Any]:
    path = _internal_config_path()
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    if not isinstance(payload, dict):
        return {}
    return payload


def _provider_configs(config: dict[str, Any]) -> dict[str, dict[str, Any]]:
    providers = config.get("providers")
    if not isinstance(providers, dict):
        return {}
    return {
        name: payload
        for name, payload in providers.items()
        if isinstance(name, str) and isinstance(payload, dict)
    }


def _last_used_provider(config: dict[str, Any]) -> str | None:
    last_used = config.get("last_used_provider")
    if isinstance(last_used, str):
        return last_used
    return None


def _config_string(provider_config: dict[str, Any], key: str) -> str | None:
    value = provider_config.get(key)
    if isinstance(value, str):
        return value
    return None


def _config_int(provider_config: dict[str, Any], key: str, fallback: int) -> int:
    value = provider_config.get(key)
    if isinstance(value, int):
        return value
    return fallback
