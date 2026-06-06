"""Reusable provider authentication header strategies."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from pbi_agent import __version__


class AuthStrategy(Protocol):
    """Build authentication headers for a model request."""

    def headers(self) -> dict[str, str]:
        """Return headers that authenticate a request."""
        ...


@dataclass(frozen=True, slots=True)
class BearerTokenAuth:
    """Bearer token authentication."""

    token: str

    def headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.token}"}


@dataclass(frozen=True, slots=True)
class ApiKeyHeaderAuth:
    """API-key authentication using a configurable header name."""

    api_key: str
    header_name: str

    def headers(self) -> dict[str, str]:
        return {self.header_name: self.api_key}


def json_model_headers() -> dict[str, str]:
    """Common JSON model request headers."""
    return {
        "Accept": "application/json",
        "Content-Type": "application/json",
        "User-Agent": f"pbi-agent/{__version__}",
    }


def anthropic_headers(*, api_key: str, anthropic_version: str) -> dict[str, str]:
    """Headers for Anthropic Messages-compatible requests."""
    return {
        "Content-Type": "application/json",
        "x-api-key": api_key,
        "anthropic-version": anthropic_version,
    }
