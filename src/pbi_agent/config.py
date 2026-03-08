from __future__ import annotations

import argparse
import os
from dataclasses import dataclass

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
DEFAULT_ANTHROPIC_MAX_TOKENS = 16384
PROVIDER_API_KEY_ENVS = {
    "openai": "OPENAI_API_KEY",
    "xai": "XAI_API_KEY",
    "google": "GEMINI_API_KEY",
    "anthropic": "ANTHROPIC_API_KEY",
    "generic": "GENERIC_API_KEY",
}


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
    verbose: bool = False
    max_tool_workers: int = 4
    max_retries: int = 2
    reasoning_effort: str = "xhigh"
    compact_threshold: int = 200000
    # Provider selection
    provider: str = "openai"
    generic_api_url: str = DEFAULT_GENERIC_API_URL
    # Anthropic-specific
    anthropic_model: str = DEFAULT_ANTHROPIC_MODEL
    anthropic_max_tokens: int = DEFAULT_ANTHROPIC_MAX_TOKENS

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
        if self.anthropic_max_tokens < 1:
            raise ConfigError("--max-tokens must be >= 1.")

    def redacted(self) -> dict[str, str | int | bool]:
        return {
            "provider": self.provider,
            "api_key": redact_secret(self.api_key),
            "responses_url": self.responses_url,
            "model": self.model,
            "verbose": self.verbose,
            "max_tool_workers": self.max_tool_workers,
            "max_retries": self.max_retries,
            "reasoning_effort": self.reasoning_effort,
            "compact_threshold": self.compact_threshold,
            "anthropic_model": self.anthropic_model,
            "anthropic_max_tokens": self.anthropic_max_tokens,
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
    return DEFAULT_MODEL


def resolve_settings(args: argparse.Namespace) -> Settings:
    load_dotenv()

    # Provider selection
    provider = (
        getattr(args, "provider", None) or os.getenv("PBI_AGENT_PROVIDER") or "openai"
    )

    api_key = (
        getattr(args, "api_key", None)
        or os.getenv("PBI_AGENT_API_KEY", "")
        or os.getenv(PROVIDER_API_KEY_ENVS.get(provider, ""), "")
    )
    responses_url_override = getattr(args, "responses_url", None) or os.getenv(
        "PBI_AGENT_RESPONSES_URL"
    )
    generic_api_url = getattr(args, "generic_api_url", None) or os.getenv(
        "PBI_AGENT_GENERIC_API_URL"
    )
    responses_url = responses_url_override or _default_responses_url(provider)
    model_override = args.model or os.getenv("PBI_AGENT_MODEL")
    model = model_override or _default_model(provider)
    max_tool_workers = args.max_tool_workers
    if max_tool_workers is None:
        max_tool_workers = int(os.getenv("PBI_AGENT_MAX_TOOL_WORKERS", "4"))
    max_retries = args.max_retries
    if max_retries is None:
        max_retries = int(os.getenv("PBI_AGENT_MAX_RETRIES", "2"))
    default_effort = "high" if provider in {"anthropic", "xai"} else "high"
    reasoning_effort = (
        args.reasoning_effort
        or os.getenv("PBI_AGENT_REASONING_EFFORT")
        or default_effort
    )
    compact_threshold = args.compact_threshold
    if compact_threshold is None:
        compact_threshold = int(os.getenv("PBI_AGENT_COMPACT_THRESHOLD", "150000"))

    # Anthropic settings
    anthropic_model = model_override or DEFAULT_ANTHROPIC_MODEL
    max_tokens_raw = getattr(args, "max_tokens", None)

    if max_tokens_raw is None:
        anthropic_max_tokens = int(
            os.getenv("PBI_AGENT_MAX_TOKENS", str(DEFAULT_ANTHROPIC_MAX_TOKENS))
        )
    else:
        anthropic_max_tokens = int(max_tokens_raw)

    return Settings(
        api_key=api_key,
        responses_url=responses_url,
        generic_api_url=generic_api_url or DEFAULT_GENERIC_API_URL,
        model=model,
        verbose=bool(args.verbose),
        max_tool_workers=max_tool_workers,
        max_retries=max_retries,
        reasoning_effort=reasoning_effort,
        compact_threshold=compact_threshold,
        provider=provider,
        anthropic_model=anthropic_model,
        anthropic_max_tokens=anthropic_max_tokens,
    )
