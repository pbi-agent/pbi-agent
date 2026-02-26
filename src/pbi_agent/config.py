from __future__ import annotations

import argparse
import os
from dataclasses import dataclass

from dotenv import load_dotenv

DEFAULT_WS_URL = "wss://api.openai.com/v1/responses"
DEFAULT_MODEL = "gpt-5.3-codex"


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

    def validate(self) -> None:
        if not self.api_key:
            raise ConfigError(
                "Missing API key. Set OPENAI_API_KEY in environment or pass --api-key."
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

    def redacted(self) -> dict[str, str | int | bool]:
        return {
            "api_key": redact_secret(self.api_key),
            "ws_url": self.ws_url,
            "model": self.model,
            "verbose": self.verbose,
            "max_tool_workers": self.max_tool_workers,
            "ws_max_retries": self.ws_max_retries,
            "reasoning_effort": self.reasoning_effort,
            "compact_threshold": self.compact_threshold,
        }


def redact_secret(value: str) -> str:
    if not value:
        return ""
    if len(value) <= 8:
        return "***"
    return f"{value[:4]}...{value[-4:]}"


def resolve_settings(args: argparse.Namespace) -> Settings:
    load_dotenv()
    api_key = args.api_key or os.getenv("OPENAI_API_KEY", "")
    ws_url = args.ws_url or os.getenv("PBI_AGENT_WS_URL") or DEFAULT_WS_URL
    model = args.model or os.getenv("PBI_AGENT_MODEL") or DEFAULT_MODEL
    max_tool_workers = args.max_tool_workers
    if max_tool_workers is None:
        max_tool_workers = int(os.getenv("PBI_AGENT_MAX_TOOL_WORKERS", "4"))
    ws_max_retries = args.ws_max_retries
    if ws_max_retries is None:
        ws_max_retries = int(os.getenv("PBI_AGENT_WS_MAX_RETRIES", "2"))
    reasoning_effort = (
        args.reasoning_effort or os.getenv("PBI_AGENT_REASONING_EFFORT") or "xhigh"
    )
    compact_threshold = args.compact_threshold
    if compact_threshold is None:
        compact_threshold = int(os.getenv("PBI_AGENT_COMPACT_THRESHOLD", "150000"))

    return Settings(
        api_key=api_key,
        ws_url=ws_url,
        model=model,
        verbose=bool(args.verbose),
        max_tool_workers=max_tool_workers,
        ws_max_retries=ws_max_retries,
        reasoning_effort=reasoning_effort,
        compact_threshold=compact_threshold,
    )
