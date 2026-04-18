from __future__ import annotations

import base64
import io
import json
import urllib.error
import urllib.parse
import urllib.request

from pbi_agent.auth.models import (
    AUTH_FLOW_STATUS_COMPLETED,
    AUTH_FLOW_STATUS_PENDING,
    DeviceAuthChallenge,
)
from pbi_agent.auth.providers.openai_chatgpt import (
    OPENAI_CHATGPT_BACKEND_ID,
    OPENAI_CHATGPT_DEVICE_TOKEN_URL,
    OPENAI_CHATGPT_REFRESH_URL,
    OpenAIChatGPTAuthBackend,
)
from pbi_agent.auth.store import build_auth_session


def _jwt(payload: dict[str, object]) -> str:
    def encode(part: dict[str, object]) -> str:
        raw = json.dumps(part, separators=(",", ":")).encode("utf-8")
        return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")

    return f"{encode({'alg': 'none', 'typ': 'JWT'})}.{encode(payload)}."


class _FakeHTTPResponse:
    def __init__(self, payload: dict[str, object], *, status: int = 200) -> None:
        self._payload = payload
        self.status = status

    def read(self) -> bytes:
        return json.dumps(self._payload).encode("utf-8")

    def __enter__(self) -> _FakeHTTPResponse:
        return self

    def __exit__(self, *_: object) -> None:
        return None


def test_start_browser_auth_builds_expected_authorize_url() -> None:
    backend = OpenAIChatGPTAuthBackend()

    browser_auth = backend.start_browser_auth(
        redirect_uri="http://localhost:1455/auth/callback"
    )

    parsed = urllib.parse.urlparse(browser_auth.authorization_url)
    params = urllib.parse.parse_qs(parsed.query)
    assert parsed.scheme == "https"
    assert parsed.netloc == "auth.openai.com"
    assert parsed.path == "/oauth/authorize"
    assert params["response_type"] == ["code"]
    assert params["client_id"] == ["app_EMoamEEZ73f0CkXaXp7hrann"]
    assert params["redirect_uri"] == ["http://localhost:1455/auth/callback"]
    assert params["id_token_add_organizations"] == ["true"]
    assert params["codex_cli_simplified_flow"] == ["true"]
    assert params["originator"] == ["opencode"]
    assert params["state"] == [browser_auth.state]
    assert params["code_challenge_method"] == ["S256"]
    assert params["scope"] == ["openid profile email offline_access"]
    assert browser_auth.code_verifier


def test_start_browser_auth_honors_originator_env_override(monkeypatch) -> None:
    monkeypatch.setenv("PBI_AGENT_OPENAI_ORIGINATOR", "codex_cli")
    backend = OpenAIChatGPTAuthBackend()

    browser_auth = backend.start_browser_auth(
        redirect_uri="http://localhost:1455/auth/callback"
    )

    parsed = urllib.parse.urlparse(browser_auth.authorization_url)
    params = urllib.parse.parse_qs(parsed.query)
    assert params["originator"] == ["codex_cli"]


def test_start_browser_auth_honors_scope_env_override(monkeypatch) -> None:
    monkeypatch.setenv(
        "PBI_AGENT_OPENAI_OAUTH_SCOPE",
        "openid profile email offline_access api.connectors.read api.connectors.invoke",
    )
    backend = OpenAIChatGPTAuthBackend()

    browser_auth = backend.start_browser_auth(
        redirect_uri="http://localhost:1455/auth/callback"
    )

    parsed = urllib.parse.urlparse(browser_auth.authorization_url)
    params = urllib.parse.parse_qs(parsed.query)
    assert params["scope"] == [
        "openid profile email offline_access api.connectors.read api.connectors.invoke"
    ]


def test_exchange_browser_code_posts_oauth_form(monkeypatch) -> None:
    backend = OpenAIChatGPTAuthBackend()
    browser_auth = backend.start_browser_auth(
        redirect_uri="http://localhost:1455/auth/callback"
    )
    captured: dict[str, object] = {}

    def fake_urlopen(
        request: urllib.request.Request,
        timeout: float,
    ) -> _FakeHTTPResponse:
        captured["url"] = request.full_url
        captured["timeout"] = timeout
        captured["body"] = request.data.decode("utf-8") if request.data else ""
        return _FakeHTTPResponse(
            {
                "access_token": _jwt(
                    {
                        "chatgpt_account_id": "acct_browser",
                        "email": "browser@example.com",
                    }
                ),
                "refresh_token": "refresh-browser",
                "expires_in": 3600,
                "id_token": _jwt({"chatgpt_account_id": "acct_browser"}),
            }
        )

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)

    session = backend.exchange_browser_code(
        provider_id="openai-chatgpt",
        browser_auth=browser_auth,
        code="auth-code-123",
    )

    body = urllib.parse.parse_qs(captured["body"])
    assert captured["url"] == OPENAI_CHATGPT_REFRESH_URL
    assert body["grant_type"] == ["authorization_code"]
    assert body["code"] == ["auth-code-123"]
    assert body["redirect_uri"] == [browser_auth.redirect_uri]
    assert body["code_verifier"] == [browser_auth.code_verifier]
    assert session.account_id == "acct_browser"
    assert session.email == "browser@example.com"
    assert session.refresh_token == "refresh-browser"


def test_start_device_auth_parses_user_code_response(monkeypatch) -> None:
    backend = OpenAIChatGPTAuthBackend()

    def fake_urlopen(
        request: urllib.request.Request,
        timeout: float,
    ) -> _FakeHTTPResponse:
        del request, timeout
        return _FakeHTTPResponse(
            {
                "device_auth_id": "device-auth-123",
                "user_code": "ABCD-EFGH",
                "interval": "7",
            }
        )

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)

    device_auth = backend.start_device_auth()

    assert device_auth.device_auth_id == "device-auth-123"
    assert device_auth.user_code == "ABCD-EFGH"
    assert device_auth.interval_seconds == 7
    assert device_auth.verification_url.endswith("/codex/device")


def test_poll_device_auth_returns_pending_for_403(monkeypatch) -> None:
    backend = OpenAIChatGPTAuthBackend()

    def fake_urlopen(
        request: urllib.request.Request,
        timeout: float,
    ) -> _FakeHTTPResponse:
        del timeout
        raise urllib.error.HTTPError(
            request.full_url,
            403,
            "Forbidden",
            hdrs=None,
            fp=io.BytesIO(b"{}"),
        )

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)

    result = backend.poll_device_auth(
        provider_id="openai-chatgpt",
        device_auth=DeviceAuthChallenge(
            verification_url="https://auth.openai.com/codex/device",
            user_code="ABCD-EFGH",
            device_auth_id="device-auth-123",
            interval_seconds=7,
        ),
    )

    assert result.status == AUTH_FLOW_STATUS_PENDING
    assert result.session is None


def test_poll_device_auth_exchanges_code_when_ready(monkeypatch) -> None:
    backend = OpenAIChatGPTAuthBackend()
    calls: list[tuple[str, str]] = []

    def fake_urlopen(
        request: urllib.request.Request,
        timeout: float,
    ) -> _FakeHTTPResponse:
        del timeout
        body = request.data.decode("utf-8") if request.data else ""
        calls.append((request.full_url, body))
        if request.full_url == OPENAI_CHATGPT_DEVICE_TOKEN_URL:
            return _FakeHTTPResponse(
                {
                    "authorization_code": "device-code-123",
                    "code_verifier": "device-verifier-123",
                }
            )
        return _FakeHTTPResponse(
            {
                "access_token": _jwt(
                    {
                        "chatgpt_account_id": "acct_device",
                        "email": "device@example.com",
                    }
                ),
                "refresh_token": "refresh-device",
                "expires_in": 3600,
            }
        )

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)

    result = backend.poll_device_auth(
        provider_id="openai-chatgpt",
        device_auth=DeviceAuthChallenge(
            verification_url="https://auth.openai.com/codex/device",
            user_code="ABCD-EFGH",
            device_auth_id="device-auth-123",
            interval_seconds=7,
        ),
    )

    assert result.status == AUTH_FLOW_STATUS_COMPLETED
    assert result.session is not None
    assert result.session.account_id == "acct_device"
    assert result.session.email == "device@example.com"
    assert calls[0][0] == OPENAI_CHATGPT_DEVICE_TOKEN_URL
    assert calls[1][0] == OPENAI_CHATGPT_REFRESH_URL


def test_import_session_uses_organization_id_as_account_fallback() -> None:
    backend = OpenAIChatGPTAuthBackend()

    session = backend.import_session(
        provider_id="openai-chatgpt",
        payload={
            "access_token": _jwt(
                {
                    "organizations": [
                        {"id": "org_123"},
                        {"id": "org_456"},
                    ],
                    "email": "user@example.com",
                }
            ),
            "refresh_token": "refresh-token",
        },
    )

    assert session.backend == OPENAI_CHATGPT_BACKEND_ID
    assert session.account_id == "org_123"
    assert session.email == "user@example.com"


def test_refresh_session_uses_expires_in_when_token_has_no_exp(monkeypatch) -> None:
    backend = OpenAIChatGPTAuthBackend()
    session = build_auth_session(
        provider_id="openai-chatgpt",
        backend=OPENAI_CHATGPT_BACKEND_ID,
        access_token="old-access-token",
        refresh_token="refresh-token",
        expires_at=100,
        account_id="acct_123",
    )

    def fake_urlopen(
        request: urllib.request.Request,
        timeout: float,
    ) -> _FakeHTTPResponse:
        del request, timeout
        return _FakeHTTPResponse(
            {
                "access_token": _jwt({"email": "user@example.com"}),
                "refresh_token": "next-refresh-token",
                "expires_in": 3600,
            }
        )

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)

    refreshed = backend.refresh_session(session)

    assert refreshed.access_token != session.access_token
    assert refreshed.refresh_token == "next-refresh-token"
    assert refreshed.account_id == "acct_123"
    assert refreshed.expires_at is not None
    assert refreshed.expires_at > 100
    assert refreshed.email == "user@example.com"
