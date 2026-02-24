from __future__ import annotations

import argparse
import os
from dataclasses import dataclass

from dotenv import load_dotenv

DEFAULT_WS_URL = "wss://api.openai.com/v1/responses"
DEFAULT_MODEL = "gpt-5.2-2025-12-11"


class ConfigError(ValueError):
    """Raised when required runtime configuration is invalid."""


@dataclass(slots=True)
class Settings:
    api_key: str
    ws_url: str = DEFAULT_WS_URL
    model: str = DEFAULT_MODEL
    verbose: bool = False
    max_tool_workers: int = 4

    def validate(self) -> None:
        if not self.api_key:
            raise ConfigError(
                "Missing API key. Set OPENAI_API_KEY in environment or pass --api-key."
            )
        if self.max_tool_workers < 1:
            raise ConfigError("--max-tool-workers must be >= 1.")

    def redacted(self) -> dict[str, str | int | bool]:
        return {
            "api_key": redact_secret(self.api_key),
            "ws_url": self.ws_url,
            "model": self.model,
            "verbose": self.verbose,
            "max_tool_workers": self.max_tool_workers,
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

    return Settings(
        api_key=api_key,
        ws_url=ws_url,
        model=model,
        verbose=bool(args.verbose),
        max_tool_workers=max_tool_workers,
    )
