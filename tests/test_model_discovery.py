from __future__ import annotations

import io
import json
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from email.message import Message
from typing import Any

from pbi_agent.auth.models import OAuthSessionAuth
from pbi_agent.config import (
    DEFAULT_MAX_TOKENS,
    DEFAULT_XAI_MODEL,
    DEFAULT_XAI_RESPONSES_URL,
    Settings,
)
from pbi_agent.providers import model_discovery
from pbi_agent.providers.model_discovery import discover_provider_models


class _FakeHTTPResponse:
    def __init__(self, payload: dict[str, Any]) -> None:
        self._payload = payload

    def read(self) -> bytes:
        return json.dumps(self._payload).encode("utf-8")

    def __enter__(self) -> _FakeHTTPResponse:
        return self

    def __exit__(self, *_: object) -> None:
        return None


def _xai_settings(auth: OAuthSessionAuth) -> Settings:
    return Settings(
        api_key="",
        auth=auth,
        provider="xai",
        responses_url=DEFAULT_XAI_RESPONSES_URL,
        model=DEFAULT_XAI_MODEL,
        max_tokens=DEFAULT_MAX_TOKENS,
    )


def _xai_api_key_settings() -> Settings:
    return Settings(
        api_key="api-key",
        provider="xai",
        responses_url=DEFAULT_XAI_RESPONSES_URL,
        model=DEFAULT_XAI_MODEL,
        max_tokens=DEFAULT_MAX_TOKENS,
    )


def _xai_auth(access_token: str, *, expires_at: int | None = None) -> OAuthSessionAuth:
    return OAuthSessionAuth(
        provider_id="xai-main",
        backend="xai_account",
        access_token=access_token,
        refresh_token="refresh-token",
        expires_at=expires_at,
    )


def test_xai_model_discovery_uses_oauth_session_without_api_key(monkeypatch) -> None:
    captured: dict[str, str | None] = {}

    def fake_urlopen(
        request: urllib.request.Request,
        timeout: float,
    ) -> _FakeHTTPResponse:
        del timeout
        captured["url"] = request.full_url
        captured["authorization"] = request.get_header("Authorization")
        return _FakeHTTPResponse(
            {
                "models": [
                    {
                        "id": "grok-4-1-fast-reasoning",
                        "display_name": "Grok 4 Fast",
                        "input_modalities": ["text"],
                        "output_modalities": ["text"],
                    }
                ]
            }
        )

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)

    result = discover_provider_models(_xai_settings(_xai_auth("oauth-token")))

    assert result.error is None
    assert [model.id for model in result.models] == [
        "grok-4-1-fast-reasoning",
        "grok-composer-2.5-fast",
    ]
    assert captured["url"] == "https://api.x.ai/v1/language-models"
    assert captured["authorization"] == "Bearer oauth-token"


def test_xai_model_discovery_adds_subscription_curated_composer_model(
    monkeypatch,
) -> None:
    def fake_urlopen(
        request: urllib.request.Request,
        timeout: float,
    ) -> _FakeHTTPResponse:
        del request, timeout
        return _FakeHTTPResponse({"models": [{"id": "grok-build-0.1"}]})

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)

    result = discover_provider_models(_xai_settings(_xai_auth("oauth-token")))

    assert result.error is None
    assert "grok-build-0.1" in [model.id for model in result.models]
    assert "grok-composer-2.5-fast" in [model.id for model in result.models]


def test_xai_model_discovery_keeps_api_key_models_endpoint_only(monkeypatch) -> None:
    def fake_urlopen(
        request: urllib.request.Request,
        timeout: float,
    ) -> _FakeHTTPResponse:
        del request, timeout
        return _FakeHTTPResponse({"models": [{"id": "grok-build-0.1"}]})

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)

    result = discover_provider_models(_xai_api_key_settings())

    assert result.error is None
    assert [model.id for model in result.models] == ["grok-build-0.1"]


def test_xai_model_discovery_refreshes_oauth_session_after_unauthorized(
    monkeypatch,
) -> None:
    authorizations: list[str | None] = []
    refreshed_auth = _xai_auth("fresh-token")

    def fake_refresh_runtime_auth(
        *,
        provider_kind: str,
        auth: OAuthSessionAuth,
    ) -> OAuthSessionAuth:
        assert provider_kind == "xai"
        assert auth.access_token == "stale-token"
        return refreshed_auth

    def fake_urlopen(
        request: urllib.request.Request,
        timeout: float,
    ) -> _FakeHTTPResponse:
        del timeout
        authorizations.append(request.get_header("Authorization"))
        if len(authorizations) == 1:
            raise urllib.error.HTTPError(
                request.full_url,
                401,
                "Unauthorized",
                hdrs=Message(),
                fp=io.BytesIO(b'{"error":{"message":"expired"}}'),
            )
        return _FakeHTTPResponse({"models": [{"id": "grok-4"}]})

    monkeypatch.setattr(
        model_discovery, "refresh_runtime_auth", fake_refresh_runtime_auth
    )
    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)

    settings = _xai_settings(_xai_auth("stale-token"))
    result = discover_provider_models(settings)

    assert result.error is None
    assert [model.id for model in result.models] == [
        "grok-4",
        "grok-composer-2.5-fast",
    ]
    assert authorizations == ["Bearer stale-token", "Bearer fresh-token"]
    assert settings.auth is refreshed_auth


def test_xai_model_discovery_proactively_refreshes_expiring_oauth_session(
    monkeypatch,
) -> None:
    authorizations: list[str | None] = []
    refreshed_auth = _xai_auth("fresh-token")

    def fake_refresh_runtime_auth(
        *,
        provider_kind: str,
        auth: OAuthSessionAuth,
    ) -> OAuthSessionAuth:
        assert provider_kind == "xai"
        assert auth.access_token == "expiring-token"
        return refreshed_auth

    def fake_urlopen(
        request: urllib.request.Request,
        timeout: float,
    ) -> _FakeHTTPResponse:
        del timeout
        authorizations.append(request.get_header("Authorization"))
        return _FakeHTTPResponse({"models": [{"id": "grok-4"}]})

    monkeypatch.setattr(
        model_discovery, "refresh_runtime_auth", fake_refresh_runtime_auth
    )
    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)

    expires_at = int((datetime.now(timezone.utc) + timedelta(minutes=30)).timestamp())
    settings = _xai_settings(_xai_auth("expiring-token", expires_at=expires_at))
    result = discover_provider_models(settings)

    assert result.error is None
    assert authorizations == ["Bearer fresh-token"]
    assert settings.auth is refreshed_auth
