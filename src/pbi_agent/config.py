from __future__ import annotations

import argparse
import os
from dataclasses import dataclass

from dotenv import load_dotenv

DEFAULT_WS_URL = "wss://api.openai.com/v1/responses"
DEFAULT_MODEL = "gpt-5.3-codex"
DEFAULT_ANTHROPIC_MODEL = "claude-opus-4-6"
DEFAULT_ANTHROPIC_MAX_TOKENS = 16384


class ConfigError(ValueError):
    """Raised when required runtime configuration is invalid."""


@dataclass(slots=True)
class Settings:
    api_key: str
    ws_url: str = DEFAULT_WS_URL
    model: str = DEFAULT_MODEL
    verbose: bool = False
    max_tool_workers: int = 4
    ws_max_retries: int = 2
    reasoning_effort: str = "xhigh"
    compact_threshold: int = 200000
    # Provider selection
    provider: str = "openai"
    # Anthropic-specific
    anthropic_api_key: str = ""
    anthropic_model: str = DEFAULT_ANTHROPIC_MODEL
    anthropic_max_tokens: int = DEFAULT_ANTHROPIC_MAX_TOKENS

    def validate(self) -> None:
        if self.provider not in {"openai", "anthropic"}:
            raise ConfigError("--provider must be one of: openai, anthropic.")
        if self.provider == "openai" and not self.api_key:
            raise ConfigError(
                "Missing API key. Set OPENAI_API_KEY in environment or pass --api-key."
            )
        if self.provider == "anthropic" and not self.anthropic_api_key:
            raise ConfigError(
                "Missing Anthropic API key. Set ANTHROPIC_API_KEY in environment "
                "or pass --anthropic-api-key."
            )
        if self.max_tool_workers < 1:
            raise ConfigError("--max-tool-workers must be >= 1.")
        if self.ws_max_retries < 0:
            raise ConfigError("--ws-max-retries must be >= 0.")
        if self.reasoning_effort not in {"low", "medium", "high", "xhigh"}:
            raise ConfigError(
                "--reasoning-effort must be one of: low, medium, high, xhigh."
            )
        if self.compact_threshold < 1:
            raise ConfigError("--compact-threshold must be >= 1.")
        if self.anthropic_max_tokens < 1:
            raise ConfigError("--anthropic-max-tokens must be >= 1.")

    def redacted(self) -> dict[str, str | int | bool]:
        return {
            "provider": self.provider,
            "api_key": redact_secret(self.api_key),
            "ws_url": self.ws_url,
            "model": self.model,
            "verbose": self.verbose,
            "max_tool_workers": self.max_tool_workers,
            "ws_max_retries": self.ws_max_retries,
            "reasoning_effort": self.reasoning_effort,
            "compact_threshold": self.compact_threshold,
            "anthropic_api_key": redact_secret(self.anthropic_api_key),
            "anthropic_model": self.anthropic_model,
            "anthropic_max_tokens": self.anthropic_max_tokens,
        }


def redact_secret(value: str) -> str:
    if not value:
        return ""
    if len(value) <= 8:
        return "***"
    return f"{value[:4]}...{value[-4:]}"


def resolve_settings(args: argparse.Namespace) -> Settings:
    load_dotenv()

    # Provider selection
    provider = (
        getattr(args, "provider", None) or os.getenv("PBI_AGENT_PROVIDER") or "openai"
    )

    api_key = args.api_key or os.getenv("OPENAI_API_KEY", "")
    ws_url = args.ws_url or os.getenv("PBI_AGENT_WS_URL") or DEFAULT_WS_URL
    model = args.model or os.getenv("PBI_AGENT_MODEL") or DEFAULT_MODEL
    max_tool_workers = args.max_tool_workers
    if max_tool_workers is None:
        max_tool_workers = int(os.getenv("PBI_AGENT_MAX_TOOL_WORKERS", "4"))
    ws_max_retries = args.ws_max_retries
    if ws_max_retries is None:
        ws_max_retries = int(os.getenv("PBI_AGENT_WS_MAX_RETRIES", "2"))
    default_effort = "high" if provider == "anthropic" else "xhigh"
    reasoning_effort = (
        args.reasoning_effort
        or os.getenv("PBI_AGENT_REASONING_EFFORT")
        or default_effort
    )
    compact_threshold = args.compact_threshold
    if compact_threshold is None:
        compact_threshold = int(os.getenv("PBI_AGENT_COMPACT_THRESHOLD", "150000"))

    # Anthropic settings
    anthropic_api_key = getattr(args, "anthropic_api_key", None) or os.getenv(
        "ANTHROPIC_API_KEY", ""
    )
    anthropic_model = (
        getattr(args, "anthropic_model", None)
        or os.getenv("PBI_AGENT_ANTHROPIC_MODEL")
        or DEFAULT_ANTHROPIC_MODEL
    )
    anthropic_max_tokens_raw = getattr(args, "anthropic_max_tokens", None)
    if anthropic_max_tokens_raw is None:
        anthropic_max_tokens = int(
            os.getenv(
                "PBI_AGENT_ANTHROPIC_MAX_TOKENS", str(DEFAULT_ANTHROPIC_MAX_TOKENS)
            )
        )
    else:
        anthropic_max_tokens = int(anthropic_max_tokens_raw)

    return Settings(
        api_key=api_key,
        ws_url=ws_url,
        model=model,
        verbose=bool(args.verbose),
        max_tool_workers=max_tool_workers,
        ws_max_retries=ws_max_retries,
        reasoning_effort=reasoning_effort,
        compact_threshold=compact_threshold,
        provider=provider,
        anthropic_api_key=anthropic_api_key,
        anthropic_model=anthropic_model,
        anthropic_max_tokens=anthropic_max_tokens,
    )
