"""Reusable provider authentication header strategies."""

from __future__ import annotations

import subprocess
from collections.abc import Callable, Mapping
from dataclasses import dataclass
import os
from typing import Literal, NoReturn, Protocol

from pbi_agent import __version__

_GCLOUD_ACCESS_TOKEN_TIMEOUT_SECS = 30.0
GOOGLE_GCP_ACCESS_TOKEN_TIMEOUT_ENV = "PBI_AGENT_GOOGLE_GCP_ACCESS_TOKEN_TIMEOUT"
GOOGLE_GCP_API_KEY_ENVS = (
    "GOOGLE_API_KEY",
    "GEMINI_API_KEY",
    "GOOGLE_CLOUD_API_KEY",
    "VERTEX_AI_API_KEY",
    "VERTEX_API_KEY",
)
GOOGLE_GCP_BEARER_TOKEN_ENVS = ("GOOGLE_CLOUD_ACCESS_TOKEN",)
GOOGLE_GCP_AUTH_ENV = "PBI_AGENT_GOOGLE_GCP_AUTH"
GOOGLE_GCP_API_KEY_HEADER = "x-goog-api-key"
GoogleGcpAuthKind = Literal["api_key", "bearer", "adc_bearer"]


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


@dataclass(frozen=True, slots=True)
class GoogleGcpAuth:
    """Resolved Google Cloud Vertex authentication headers."""

    headers: dict[str, str]
    kind: GoogleGcpAuthKind
    refreshable: bool = False


class ApiKeySettings(Protocol):
    """Settings subset needed by Google Cloud bearer authentication."""

    api_key: str


def run_gcloud_print_access_token(*, timeout: float | None = None) -> str:
    """Return an ADC access token from ``gcloud auth application-default``."""
    command = ["gcloud", "auth", "application-default", "print-access-token"]
    resolved_timeout = (
        _google_gcp_access_token_timeout() if timeout is None else timeout
    )
    try:
        completed = subprocess.run(
            command,
            check=True,
            capture_output=True,
            text=True,
            timeout=resolved_timeout,
        )
    except FileNotFoundError as exc:
        raise ValueError(
            "Missing Google Cloud bearer token. Set PBI_AGENT_API_KEY, "
            "GOOGLE_CLOUD_ACCESS_TOKEN, or install gcloud and configure "
            "Application Default Credentials."
        ) from exc
    except subprocess.TimeoutExpired as exc:
        raise ValueError(
            f"Timed out after {resolved_timeout:g}s while resolving Google Cloud "
            "access token with 'gcloud auth application-default print-access-token'. "
            "Run that command once to verify ADC, set GOOGLE_CLOUD_ACCESS_TOKEN, "
            f"or increase {GOOGLE_GCP_ACCESS_TOKEN_TIMEOUT_ENV}."
        ) from exc
    except subprocess.CalledProcessError as exc:
        stderr = (exc.stderr or "").strip()
        detail = f": {stderr}" if stderr else "."
        raise ValueError(
            "Failed to resolve Google Cloud access token with "
            f"'gcloud auth application-default print-access-token'{detail}"
        ) from exc

    token = completed.stdout.strip()
    if not token:
        raise ValueError(
            "'gcloud auth application-default print-access-token' returned an "
            "empty Google Cloud access token."
        )
    return token


def google_gcp_auth(
    settings: ApiKeySettings,
    *,
    access_token_resolver: Callable[[], str] | None = None,
    env: Mapping[str, str] | None = None,
    allow_api_key: bool = True,
) -> GoogleGcpAuth:
    """Return Google Cloud Vertex auth headers from API key, bearer, or ADC."""
    auth_override = _google_gcp_auth_override(env=env)
    if not allow_api_key and auth_override == "api_key":
        _raise_google_gcp_api_key_not_supported()

    explicit_token = settings.api_key.strip()
    if explicit_token:
        if _google_gcp_explicit_token_is_api_key(
            settings,
            explicit_token,
            env=env,
        ):
            if not allow_api_key:
                return _google_gcp_adc_bearer_auth(
                    access_token_resolver,
                    env=env,
                    skipped_api_key=True,
                )
            return GoogleGcpAuth(
                headers=ApiKeyHeaderAuth(
                    explicit_token,
                    GOOGLE_GCP_API_KEY_HEADER,
                ).headers(),
                kind="api_key",
            )
        return GoogleGcpAuth(
            headers=BearerTokenAuth(explicit_token).headers(),
            kind="bearer",
        )

    api_key = google_gcp_api_key_from_env(env=env)
    if allow_api_key and api_key:
        return GoogleGcpAuth(
            headers=ApiKeyHeaderAuth(api_key, GOOGLE_GCP_API_KEY_HEADER).headers(),
            kind="api_key",
        )

    return _google_gcp_adc_bearer_auth(
        access_token_resolver,
        env=env,
        skipped_api_key=bool(api_key),
    )


def _google_gcp_adc_bearer_auth(
    access_token_resolver: Callable[[], str] | None,
    *,
    env: Mapping[str, str] | None,
    skipped_api_key: bool = False,
) -> GoogleGcpAuth:
    if token := google_gcp_bearer_token_from_env(env=env):
        return GoogleGcpAuth(
            headers=BearerTokenAuth(token).headers(),
            kind="bearer",
        )

    try:
        token = _resolve_google_gcp_bearer_token(access_token_resolver)
    except ValueError as exc:
        if skipped_api_key:
            raise ValueError(
                _google_gcp_api_key_not_supported_message()
                + f" Failed to resolve OAuth2 credentials: {exc}"
            ) from exc
        raise

    return GoogleGcpAuth(
        headers=BearerTokenAuth(token).headers(),
        kind="adc_bearer",
        refreshable=True,
    )


def google_gcp_api_key_from_env(*, env: Mapping[str, str] | None = None) -> str:
    """Return a Google Cloud Vertex API key from supported environment names."""
    source = os.environ if env is None else env
    for env_name in GOOGLE_GCP_API_KEY_ENVS:
        if token := source.get(env_name, "").strip():
            return token
    return ""


def google_gcp_bearer_token_from_env(*, env: Mapping[str, str] | None = None) -> str:
    """Return a Google Cloud OAuth2 bearer token from supported environment names."""
    source = os.environ if env is None else env
    for env_name in GOOGLE_GCP_BEARER_TOKEN_ENVS:
        if token := source.get(env_name, "").strip():
            return token
    return ""


def google_gcp_bearer_token(
    settings: ApiKeySettings,
    *,
    access_token_resolver: Callable[[], str] | None = None,
    env: Mapping[str, str] | None = None,
) -> str:
    """Return a Google Cloud bearer token from explicit settings or ADC."""
    explicit_token = settings.api_key.strip()
    if explicit_token:
        return explicit_token
    if token := google_gcp_bearer_token_from_env(env=env):
        return token
    return _resolve_google_gcp_bearer_token(access_token_resolver)


def _resolve_google_gcp_bearer_token(
    access_token_resolver: Callable[[], str] | None,
) -> str:
    if access_token_resolver is None:
        return run_gcloud_print_access_token()
    token = access_token_resolver()
    if not isinstance(token, str) or not token.strip():
        raise ValueError("Google Cloud access token resolver returned no token.")
    return token.strip()


def _google_gcp_access_token_timeout(*, env: Mapping[str, str] | None = None) -> float:
    source = os.environ if env is None else env
    value = source.get(GOOGLE_GCP_ACCESS_TOKEN_TIMEOUT_ENV, "").strip()
    if not value:
        return _GCLOUD_ACCESS_TOKEN_TIMEOUT_SECS
    try:
        timeout = float(value)
    except ValueError as exc:
        raise ValueError(
            f"{GOOGLE_GCP_ACCESS_TOKEN_TIMEOUT_ENV} must be a positive number."
        ) from exc
    if timeout <= 0:
        raise ValueError(
            f"{GOOGLE_GCP_ACCESS_TOKEN_TIMEOUT_ENV} must be a positive number."
        )
    return timeout


def google_gcp_bearer_headers(
    settings: ApiKeySettings,
    *,
    access_token_resolver: Callable[[], str] | None = None,
    env: Mapping[str, str] | None = None,
) -> dict[str, str]:
    """Return Authorization headers for Google Cloud Vertex AI requests."""
    token = google_gcp_bearer_token(
        settings,
        access_token_resolver=access_token_resolver,
        env=env,
    )
    return BearerTokenAuth(token).headers()


def _google_gcp_api_key_not_supported_message() -> str:
    return (
        "Google GCP API-key auth is only supported for Gemini express-mode "
        "endpoints. OpenAI-compatible and Anthropic Vertex endpoints require "
        "an OAuth2 access token. Configure GOOGLE_CLOUD_ACCESS_TOKEN, set "
        "PBI_AGENT_GOOGLE_GCP_AUTH=bearer_token with an OAuth2 token, or "
        "configure Application Default Credentials."
    )


def _raise_google_gcp_api_key_not_supported() -> NoReturn:
    raise ValueError(_google_gcp_api_key_not_supported_message())


def _google_gcp_explicit_token_is_api_key(
    settings: ApiKeySettings,
    token: str,
    *,
    env: Mapping[str, str] | None,
) -> bool:
    override = _google_gcp_auth_override(env=env)
    if override is not None:
        return override == "api_key"
    api_key_env = _settings_api_key_env(settings)
    if api_key_env in GOOGLE_GCP_API_KEY_ENVS:
        return True
    if api_key_env in GOOGLE_GCP_BEARER_TOKEN_ENVS:
        return False
    return token.startswith(("AIza", "AQ."))


def _google_gcp_auth_override(
    *,
    env: Mapping[str, str] | None,
) -> Literal["api_key", "bearer"] | None:
    source = os.environ if env is None else env
    value = source.get(GOOGLE_GCP_AUTH_ENV, "").strip().lower().replace("-", "_")
    if not value:
        return None
    if value in {"api_key", "apikey", "key"}:
        return "api_key"
    if value in {"bearer", "bearer_token", "access_token", "oauth", "oauth2"}:
        return "bearer"
    raise ValueError(f"{GOOGLE_GCP_AUTH_ENV} must be one of: api_key, bearer_token.")


def _settings_api_key_env(settings: ApiKeySettings) -> str:
    auth = getattr(settings, "auth", None)
    api_key_env = getattr(auth, "api_key_env", None)
    return api_key_env.strip() if isinstance(api_key_env, str) else ""


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
