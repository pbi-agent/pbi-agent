from __future__ import annotations

import argparse
import os
import urllib.parse
from dataclasses import dataclass

from dotenv import load_dotenv

DEFAULT_WS_URL = "wss://api.openai.com/v1/responses"
DEFAULT_RESPONSES_URL = "https://api.openai.com/v1/responses"
DEFAULT_MODEL = "gpt-5.4-2026-03-05"
DEFAULT_ANTHROPIC_MODEL = "claude-opus-4-6"
DEFAULT_ANTHROPIC_MAX_TOKENS = 16384


class ConfigError(ValueError):
    """Raised when required runtime configuration is invalid."""


@dataclass(slots=True)
class Settings:
    api_key: str
    ws_url: str = DEFAULT_WS_URL
    responses_url: str = DEFAULT_RESPONSES_URL
    model: str = DEFAULT_MODEL
    verbose: bool = False
    max_tool_workers: int = 4
    ws_max_retries: int = 2
    reasoning_effort: str = "xhigh"
    compact_threshold: int = 200000
    # Provider selection
    provider: str = "openai"
    # Anthropic-specific
    anthropic_model: str = DEFAULT_ANTHROPIC_MODEL
    anthropic_max_tokens: int = DEFAULT_ANTHROPIC_MAX_TOKENS

    def validate(self) -> None:
        if self.provider not in {"openai", "anthropic"}:
            raise ConfigError("--provider must be one of: openai, anthropic.")
        if self.provider == "openai" and not self.api_key:
            raise ConfigError(
                "Missing OpenAI API key. Set OPENAI_API_KEY in environment or pass "
                "--openai-api-key."
            )
        if self.provider == "anthropic" and not self.api_key:
            raise ConfigError(
                "Missing Anthropic API key. Set ANTHROPIC_API_KEY in environment or "
                "pass --anthropic-api-key."
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
            raise ConfigError("--max-tokens must be >= 1.")

    def redacted(self) -> dict[str, str | int | bool]:
        return {
            "provider": self.provider,
            "api_key": redact_secret(self.api_key),
            "ws_url": self.ws_url,
            "responses_url": self.responses_url,
            "model": self.model,
            "verbose": self.verbose,
            "max_tool_workers": self.max_tool_workers,
            "ws_max_retries": self.ws_max_retries,
            "reasoning_effort": self.reasoning_effort,
            "compact_threshold": self.compact_threshold,
            "anthropic_model": self.anthropic_model,
            "anthropic_max_tokens": self.anthropic_max_tokens,
        }


def redact_secret(value: str) -> str:
    if not value:
        return ""
    if len(value) <= 8:
        return "***"
    return f"{value[:4]}...{value[-4:]}"


def _default_responses_url(ws_url: str) -> str:
    parsed = urllib.parse.urlsplit(ws_url)
    scheme = {"ws": "http", "wss": "https"}.get(
        parsed.scheme,
        parsed.scheme or "https",
    )
    return urllib.parse.urlunsplit(
        (scheme, parsed.netloc, parsed.path, parsed.query, "")
    )


def resolve_settings(args: argparse.Namespace) -> Settings:
    load_dotenv()

    # Provider selection
    provider = (
        getattr(args, "provider", None) or os.getenv("PBI_AGENT_PROVIDER") or "openai"
    )

    openai_api_key = getattr(args, "openai_api_key", None) or os.getenv(
        "OPENAI_API_KEY", ""
    )
    anthropic_api_key = getattr(args, "anthropic_api_key", None) or os.getenv(
        "ANTHROPIC_API_KEY", ""
    )
    api_key = openai_api_key if provider == "openai" else anthropic_api_key
    ws_url = args.ws_url or os.getenv("PBI_AGENT_WS_URL") or DEFAULT_WS_URL
    responses_url_override = getattr(args, "responses_url", None) or os.getenv(
        "PBI_AGENT_RESPONSES_URL"
    )
    responses_url = responses_url_override or _default_responses_url(ws_url)
    model_override = args.model or os.getenv("PBI_AGENT_MODEL")
    model = model_override or DEFAULT_MODEL
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
        ws_url=ws_url,
        responses_url=responses_url,
        model=model,
        verbose=bool(args.verbose),
        max_tool_workers=max_tool_workers,
        ws_max_retries=ws_max_retries,
        reasoning_effort=reasoning_effort,
        compact_threshold=compact_threshold,
        provider=provider,
        anthropic_model=anthropic_model,
        anthropic_max_tokens=anthropic_max_tokens,
    )
