from __future__ import annotations

import base64
import io
import json
import socket
import urllib.error
import urllib.parse
import urllib.request

import pytest

from pbi_agent.auth.browser_callback import (
    BrowserAuthCallbackOutcome,
    BrowserAuthCallbackParams,
    create_browser_auth_callback_listener,
)
from pbi_agent.auth.models import (
    AUTH_MODE_API_KEY,
    AUTH_MODE_XAI_ACCOUNT,
    BrowserAuthChallenge,
)
from pbi_agent.auth.providers.xai import (
    XAI_BACKEND_ID,
    XAI_CLIENT_ID,
    XAI_DISCOVERY_URL,
    XAI_OAUTH_SCOPE,
    XAIAuthBackend,
)
from pbi_agent.auth.service import (
    provider_auth_modes,
    provider_browser_callback_options,
)
from pbi_agent.auth.store import build_auth_session
from pbi_agent.config import ProviderConfig


def _jwt(payload: dict[str, object]) -> str:
    def encode(part: dict[str, object]) -> str:
        raw = json.dumps(part, separators=(",", ":")).encode("utf-8")
        return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")

    return f"{encode({'alg': 'none', 'typ': 'JWT'})}.{encode(payload)}."


class _FakeHTTPResponse:
    def __init__(self, payload: dict[str, object]) -> None:
        self._payload = payload
        self.status = 200

    def read(self) -> bytes:
        return json.dumps(self._payload).encode("utf-8")

    def __enter__(self) -> _FakeHTTPResponse:
        return self

    def __exit__(self, *_: object) -> None:
        return None


def test_xai_auth_modes_and_callback_options() -> None:
    assert provider_auth_modes("xai") == (AUTH_MODE_API_KEY, AUTH_MODE_XAI_ACCOUNT)

    provider = ProviderConfig(
        id="x",
        name="X",
        kind="xai",
        auth_mode=AUTH_MODE_XAI_ACCOUNT,
        api_key="secret",
        api_key_env="XAI_API_KEY",
    )
    provider.validate()
    assert provider.api_key == ""
    assert provider.api_key_env is None

    options = provider_browser_callback_options("xai", AUTH_MODE_XAI_ACCOUNT)
    assert options.host == "127.0.0.1"
    assert options.preferred_port == 56121
    assert options.path == "/callback"
    assert options.callback_host == "127.0.0.1"
    assert options.allow_port_fallback is False


def test_xai_callback_listener_requires_exact_port() -> None:
    options = provider_browser_callback_options("xai", AUTH_MODE_XAI_ACCOUNT)

    blocker = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        try:
            blocker.bind((options.host, options.preferred_port))
        except OSError as exc:
            pytest.skip(f"Port {options.preferred_port} is already unavailable: {exc}")
        blocker.listen(1)

        def callback_handler(
            params: BrowserAuthCallbackParams,
        ) -> BrowserAuthCallbackOutcome:
            del params
            return BrowserAuthCallbackOutcome(completed=True)

        with pytest.raises(OSError, match="127.0.0.1:56121/callback"):
            create_browser_auth_callback_listener(
                callback_handler=callback_handler,
                options=options,
            )
    finally:
        blocker.close()


def test_callback_listener_shutdown_before_start_skips_server_shutdown() -> None:
    options = provider_browser_callback_options("xai", AUTH_MODE_XAI_ACCOUNT)

    def callback_handler(
        params: BrowserAuthCallbackParams,
    ) -> BrowserAuthCallbackOutcome:
        del params
        return BrowserAuthCallbackOutcome(completed=True)

    try:
        listener = create_browser_auth_callback_listener(
            callback_handler=callback_handler,
            options=options,
        )
    except OSError as exc:
        pytest.skip(f"Port {options.preferred_port} is unavailable: {exc}")

    def fail_if_called() -> None:
        raise AssertionError("shutdown() must not be called before serve_forever()")

    listener._server.shutdown = fail_if_called  # pyright: ignore[reportPrivateUsage]

    listener.shutdown()


def test_start_browser_auth_uses_discovery_and_xai_params(monkeypatch) -> None:
    backend = XAIAuthBackend()

    def fake_urlopen(
        request: urllib.request.Request,
        timeout: float,
    ) -> _FakeHTTPResponse:
        del timeout
        assert request.full_url == XAI_DISCOVERY_URL
        return _FakeHTTPResponse(
            {
                "authorization_endpoint": "https://auth.x.ai/authorize",
                "token_endpoint": "https://auth.x.ai/oauth/token",
            }
        )

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)

    browser_auth = backend.start_browser_auth(
        redirect_uri="http://127.0.0.1:56121/callback"
    )

    parsed = urllib.parse.urlparse(browser_auth.authorization_url)
    params = urllib.parse.parse_qs(parsed.query)
    assert parsed.scheme == "https"
    assert parsed.netloc == "auth.x.ai"
    assert parsed.path == "/authorize"
    assert params["response_type"] == ["code"]
    assert params["client_id"] == [XAI_CLIENT_ID]
    assert params["redirect_uri"] == ["http://127.0.0.1:56121/callback"]
    assert params["scope"] == [XAI_OAUTH_SCOPE]
    assert params["code_challenge_method"] == ["S256"]
    assert params["state"] == [browser_auth.state]
    assert params["nonce"][0]
    assert params["plan"] == ["generic"]
    assert params["referrer"] == ["pbi-agent"]
    assert browser_auth.code_verifier


def test_exchange_browser_code_posts_pkce_echo_and_imports_session(monkeypatch) -> None:
    backend = XAIAuthBackend()
    browser_auth = BrowserAuthChallenge(
        authorization_url="https://auth.x.ai/authorize",
        redirect_uri="http://127.0.0.1:56121/callback",
        state="state",
        code_verifier="verifier-123",
    )
    captured: dict[str, object] = {}
    responses = iter(
        [
            {
                "authorization_endpoint": "https://auth.x.ai/authorize",
                "token_endpoint": "https://auth.x.ai/oauth/token",
            },
            {
                "access_token": _jwt(
                    {"sub": "acct-x", "email": "x@example.com", "exp": 4_000_000_000}
                ),
                "refresh_token": "refresh-x",
                "expires_in": 3600,
            },
        ]
    )

    def fake_urlopen(
        request: urllib.request.Request,
        timeout: float,
    ) -> _FakeHTTPResponse:
        del timeout
        if request.full_url.endswith("/oauth/token"):
            captured["body"] = request.data.decode("utf-8") if request.data else ""
        return _FakeHTTPResponse(next(responses))

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)

    session = backend.exchange_browser_code(
        provider_id="xai-main",
        browser_auth=browser_auth,
        code="code-123",
    )

    body = urllib.parse.parse_qs(str(captured["body"]))
    assert body["grant_type"] == ["authorization_code"]
    assert body["code"] == ["code-123"]
    assert body["redirect_uri"] == [browser_auth.redirect_uri]
    assert body["client_id"] == [XAI_CLIENT_ID]
    assert body["code_verifier"] == ["verifier-123"]
    assert body["code_challenge"]
    assert body["code_challenge_method"] == ["S256"]
    assert session.backend == XAI_BACKEND_ID
    assert session.account_id == "acct-x"
    assert session.email == "x@example.com"
    assert session.refresh_token == "refresh-x"
    assert session.metadata["token_endpoint"] == "https://auth.x.ai/oauth/token"


def test_import_session_uses_access_token_expiry_before_id_token_claims() -> None:
    backend = XAIAuthBackend()

    session = backend.import_session(
        provider_id="xai-main",
        payload={
            "access_token": _jwt({"sub": "access-sub", "exp": 1_700_000_100}),
            "id_token": _jwt(
                {
                    "sub": "identity-sub",
                    "email": "x@example.com",
                    "exp": 1_800_000_000,
                }
            ),
            "refresh_token": "refresh-x",
        },
    )

    assert session.expires_at == 1_700_000_100
    assert session.account_id == "identity-sub"
    assert session.email == "x@example.com"


def test_refresh_posts_refresh_form_and_preserves_refresh_token(monkeypatch) -> None:
    backend = XAIAuthBackend()
    session = build_auth_session(
        provider_id="xai-main",
        backend=XAI_BACKEND_ID,
        access_token="old-token",
        refresh_token="refresh-old",
        account_id="acct-x",
        email="x@example.com",
        metadata={"token_endpoint": "https://auth.x.ai/oauth/token"},
    )
    captured: dict[str, object] = {}

    def fake_urlopen(
        request: urllib.request.Request,
        timeout: float,
    ) -> _FakeHTTPResponse:
        del timeout
        captured["url"] = request.full_url
        captured["body"] = request.data.decode("utf-8") if request.data else ""
        return _FakeHTTPResponse(
            {"access_token": _jwt({"sub": "acct-x"}), "expires_in": 7200}
        )

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)

    refreshed = backend.refresh_session(session)

    body = urllib.parse.parse_qs(str(captured["body"]))
    assert captured["url"] == "https://auth.x.ai/oauth/token"
    assert body["grant_type"] == ["refresh_token"]
    assert body["client_id"] == [XAI_CLIENT_ID]
    assert body["refresh_token"] == ["refresh-old"]
    assert refreshed.refresh_token == "refresh-old"


def test_refresh_honors_explicit_expires_at_before_token_claim(monkeypatch) -> None:
    backend = XAIAuthBackend()
    session = build_auth_session(
        provider_id="xai-main",
        backend=XAI_BACKEND_ID,
        access_token="old-token",
        refresh_token="refresh-old",
        account_id="acct-x",
        email="x@example.com",
        metadata={"token_endpoint": "https://auth.x.ai/oauth/token"},
    )

    def fake_urlopen(
        request: urllib.request.Request,
        timeout: float,
    ) -> _FakeHTTPResponse:
        del request, timeout
        return _FakeHTTPResponse(
            {
                "access_token": _jwt({"sub": "acct-x", "exp": 4_000_000_000}),
                "expires_at": 1_900_000_000,
                "expires_in": 7200,
            }
        )

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)

    refreshed = backend.refresh_session(session)

    assert refreshed.expires_at == 1_900_000_000


def test_refresh_403_mentions_subscription_entitlement(monkeypatch) -> None:
    backend = XAIAuthBackend()
    session = build_auth_session(
        provider_id="xai-main",
        backend=XAI_BACKEND_ID,
        access_token="old-token",
        refresh_token="refresh-old",
        metadata={"token_endpoint": "https://auth.x.ai/oauth/token"},
    )

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

    with pytest.raises(RuntimeError, match="subscription entitlement denied"):
        backend.refresh_session(session)


def test_rejects_non_xai_oauth_and_inference_urls(monkeypatch) -> None:
    backend = XAIAuthBackend()

    def fake_urlopen(
        request: urllib.request.Request,
        timeout: float,
    ) -> _FakeHTTPResponse:
        del request, timeout
        return _FakeHTTPResponse(
            {
                "authorization_endpoint": "https://evil.example/authorize",
                "token_endpoint": "https://auth.x.ai/oauth/token",
            }
        )

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)

    with pytest.raises(RuntimeError, match="HTTPS x.ai URL"):
        backend.start_browser_auth(redirect_uri="http://127.0.0.1:56121/callback")

    session = build_auth_session(
        provider_id="xai-main",
        backend=XAI_BACKEND_ID,
        access_token="access",
    )
    with pytest.raises(RuntimeError, match="HTTPS x.ai URL"):
        backend.build_request_auth(
            request_url="https://example.com/v1/responses",
            session=session,
        )
