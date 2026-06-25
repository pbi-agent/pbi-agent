from __future__ import annotations

import base64
import hashlib
import json
import secrets
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from typing import Any

from pbi_agent.auth.browser_callback import BrowserAuthCallbackOptions
from pbi_agent.auth.models import (
    AUTH_FLOW_METHOD_BROWSER,
    AUTH_MODE_XAI_ACCOUNT,
    AUTH_SESSION_STATUS_CONNECTED,
    AUTH_SESSION_STATUS_EXPIRED,
    AUTH_SESSION_STATUS_MISSING,
    BrowserAuthChallenge,
    ProviderAuthStatus,
    RequestAuthConfig,
    StoredAuthSession,
)
from pbi_agent.auth.providers.base import AuthProviderBackend
from pbi_agent.auth.store import build_auth_session

XAI_BACKEND_ID = "xai_account"
XAI_DISCOVERY_URL = "https://auth.x.ai/.well-known/openid-configuration"
XAI_CLIENT_ID = "b1a00492-073a-47ea-816f-4c329264a828"
XAI_OAUTH_SCOPE = "openid profile email offline_access grok-cli:access api:access"
XAI_CALLBACK_PORT = 56121
XAI_CALLBACK_PATH = "/callback"
_AUTH_TIMEOUT_SECS = 30.0
_PKCE_VERIFIER_LENGTH = 64
_PKCE_ALLOWED_CHARS = (
    "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-._~"
)


class XAIAuthBackend(AuthProviderBackend):
    @property
    def backend_id(self) -> str:
        return XAI_BACKEND_ID

    def build_status(self, session: StoredAuthSession | None) -> ProviderAuthStatus:
        if session is None:
            return ProviderAuthStatus(
                auth_mode=AUTH_MODE_XAI_ACCOUNT,
                backend=self.backend_id,
                session_status=AUTH_SESSION_STATUS_MISSING,
                has_session=False,
                can_refresh=False,
            )
        return ProviderAuthStatus(
            auth_mode=AUTH_MODE_XAI_ACCOUNT,
            backend=self.backend_id,
            session_status=(
                AUTH_SESSION_STATUS_EXPIRED
                if session.is_expired()
                else AUTH_SESSION_STATUS_CONNECTED
            ),
            has_session=True,
            can_refresh=bool(session.refresh_token),
            account_id=session.account_id,
            email=session.email,
            plan_type=session.plan_type,
            expires_at=session.expires_at,
        )

    def supported_auth_flow_methods(self) -> tuple[str, ...]:
        return (AUTH_FLOW_METHOD_BROWSER,)

    def browser_callback_options(self) -> BrowserAuthCallbackOptions:
        return BrowserAuthCallbackOptions(
            host="127.0.0.1",
            preferred_port=XAI_CALLBACK_PORT,
            path=XAI_CALLBACK_PATH,
            callback_host="127.0.0.1",
            allow_port_fallback=False,
        )

    def import_session(
        self,
        *,
        provider_id: str,
        payload: dict[str, Any],
        previous: StoredAuthSession | None = None,
    ) -> StoredAuthSession:
        access_token = _require_non_empty_string(payload, "access_token")
        refresh_token = _optional_non_empty_string(payload, "refresh_token")
        id_token = _optional_non_empty_string(payload, "id_token")
        access_claims = _decode_jwt_claims(access_token)
        id_claims = _decode_jwt_claims(id_token)
        identity_claims = {**access_claims, **id_claims}

        expires_at = _optional_int(payload, "expires_at")
        expires_in = _optional_int(payload, "expires_in")
        if expires_at is not None:
            resolved_expires_at = expires_at
        elif expires_in is not None:
            resolved_expires_at = _expires_at_from_duration(expires_in)
        else:
            resolved_expires_at = _int_value(access_claims.get("exp"))
        metadata = {
            "id_token": id_token,
            "token_endpoint": _optional_non_empty_string(
                payload,
                "token_endpoint",
            ),
            "token_source": _optional_non_empty_string(payload, "token_source")
            or "manual_import",
        }
        if previous is not None:
            metadata = {**previous.metadata, **metadata}
        return build_auth_session(
            provider_id=provider_id,
            backend=self.backend_id,
            access_token=access_token,
            refresh_token=refresh_token
            or (previous.refresh_token if previous else None),
            expires_at=resolved_expires_at,
            account_id=_optional_non_empty_string(payload, "account_id")
            or _string_value(identity_claims.get("sub")),
            email=_optional_non_empty_string(payload, "email")
            or _string_value(identity_claims.get("email")),
            plan_type=_optional_non_empty_string(payload, "plan_type"),
            metadata=metadata,
            previous=previous,
        )

    def refresh_session(self, session: StoredAuthSession) -> StoredAuthSession:
        if not session.refresh_token:
            raise ValueError("This X auth session does not include a refresh token.")
        token_endpoint = _session_token_endpoint(session)
        payload = _post_form_json(
            token_endpoint,
            {
                "grant_type": "refresh_token",
                "client_id": XAI_CLIENT_ID,
                "refresh_token": session.refresh_token,
            },
            action="X token refresh",
        )
        return self.import_session(
            provider_id=session.provider_id,
            payload={
                "access_token": payload.get("access_token") or session.access_token,
                "refresh_token": payload.get("refresh_token") or session.refresh_token,
                "expires_at": payload.get("expires_at"),
                "expires_in": payload.get("expires_in"),
                "id_token": payload.get("id_token"),
                "account_id": session.account_id,
                "email": session.email,
                "plan_type": session.plan_type,
                "token_endpoint": token_endpoint,
                "token_source": "refresh",
            },
            previous=session,
        )

    def build_request_auth(
        self,
        *,
        request_url: str,
        session: StoredAuthSession,
    ) -> RequestAuthConfig:
        _validate_xai_url(request_url, label="xAI inference URL")
        return RequestAuthConfig(
            request_url=request_url,
            headers={"Authorization": f"Bearer {session.access_token}"},
        )

    def start_browser_auth(
        self,
        *,
        redirect_uri: str,
    ) -> BrowserAuthChallenge:
        discovery = _fetch_discovery()
        authorize_url = _require_valid_endpoint(discovery, "authorization_endpoint")
        code_verifier = _generate_pkce_code_verifier()
        code_challenge = _pkce_code_challenge(code_verifier)
        state = _generate_state()
        query = urllib.parse.urlencode(
            {
                "response_type": "code",
                "client_id": XAI_CLIENT_ID,
                "redirect_uri": redirect_uri,
                "scope": XAI_OAUTH_SCOPE,
                "code_challenge": code_challenge,
                "code_challenge_method": "S256",
                "state": state,
                "nonce": _generate_state(),
                "plan": "generic",
                "referrer": "pbi-agent",
            }
        )
        return BrowserAuthChallenge(
            authorization_url=f"{authorize_url}?{query}",
            redirect_uri=redirect_uri,
            state=state,
            code_verifier=code_verifier,
        )

    def exchange_browser_code(
        self,
        *,
        provider_id: str,
        browser_auth: BrowserAuthChallenge,
        code: str,
        previous: StoredAuthSession | None = None,
    ) -> StoredAuthSession:
        discovery = _fetch_discovery()
        token_endpoint = _require_valid_endpoint(discovery, "token_endpoint")
        code_challenge = _pkce_code_challenge(browser_auth.code_verifier)
        payload = _post_form_json(
            token_endpoint,
            {
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": browser_auth.redirect_uri,
                "client_id": XAI_CLIENT_ID,
                "code_verifier": browser_auth.code_verifier,
                "code_challenge": code_challenge,
                "code_challenge_method": "S256",
            },
            action="X OAuth code exchange",
        )
        if not _optional_non_empty_string(payload, "refresh_token"):
            raise RuntimeError("X OAuth code exchange did not return a refresh token.")
        return self.import_session(
            provider_id=provider_id,
            payload={
                **payload,
                "token_endpoint": token_endpoint,
                "token_source": "browser_oauth",
            },
            previous=previous,
        )


def _fetch_discovery() -> dict[str, Any]:
    _validate_xai_url(XAI_DISCOVERY_URL, label="xAI discovery URL")
    request = urllib.request.Request(
        XAI_DISCOVERY_URL,
        headers={"User-Agent": "pbi-agent"},
        method="GET",
    )
    try:
        with urllib.request.urlopen(request, timeout=_AUTH_TIMEOUT_SECS) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except urllib.error.URLError as exc:
        raise RuntimeError(f"X OAuth discovery failed: {exc.reason}") from exc
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise RuntimeError("X OAuth discovery returned invalid JSON.") from exc
    if not isinstance(payload, dict):
        raise RuntimeError("X OAuth discovery returned an unexpected JSON payload.")
    _require_valid_endpoint(payload, "authorization_endpoint")
    _require_valid_endpoint(payload, "token_endpoint")
    return payload


def _session_token_endpoint(session: StoredAuthSession) -> str:
    value = session.metadata.get("token_endpoint")
    if isinstance(value, str) and value.strip():
        return _validate_xai_url(value.strip(), label="xAI token endpoint")
    discovery = _fetch_discovery()
    return _require_valid_endpoint(discovery, "token_endpoint")


def _require_valid_endpoint(discovery: dict[str, Any], key: str) -> str:
    value = discovery.get(key)
    if not isinstance(value, str) or not value.strip():
        raise RuntimeError(f"X OAuth discovery missing '{key}'.")
    return _validate_xai_url(value.strip(), label=f"X OAuth {key}")


def _validate_xai_url(url: str, *, label: str) -> str:
    parsed = urllib.parse.urlparse(url)
    host = (parsed.hostname or "").lower()
    if parsed.scheme != "https" or not (host == "x.ai" or host.endswith(".x.ai")):
        raise RuntimeError(f"{label} must be an HTTPS x.ai URL.")
    return url


def _post_form_json(
    url: str,
    payload: dict[str, str],
    *,
    action: str,
) -> dict[str, Any]:
    _validate_xai_url(url, label=f"{action} URL")
    request = urllib.request.Request(
        url,
        data=urllib.parse.urlencode(payload).encode("utf-8"),
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=_AUTH_TIMEOUT_SECS) as response:
            raw_body = response.read()
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        if exc.code == 403:
            raise RuntimeError(
                f"{action} failed with status 403: X subscription entitlement denied."
            ) from exc
        raise RuntimeError(f"{action} failed with status {exc.code}: {body}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"{action} failed: {exc.reason}") from exc
    if not raw_body:
        raise RuntimeError(f"{action} returned an empty response.")
    try:
        decoded = json.loads(raw_body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"{action} returned invalid JSON.") from exc
    if not isinstance(decoded, dict):
        raise RuntimeError(f"{action} returned an unexpected JSON payload.")
    if not _optional_non_empty_string(decoded, "access_token"):
        raise RuntimeError(f"{action} did not return an access token.")
    return decoded


def _require_non_empty_string(payload: dict[str, Any], key: str) -> str:
    value = _optional_non_empty_string(payload, key)
    if value is None:
        raise ValueError(f"Missing required auth field '{key}'.")
    return value


def _optional_non_empty_string(payload: dict[str, Any], key: str) -> str | None:
    value = payload.get(key)
    if not isinstance(value, str):
        return None
    stripped = value.strip()
    return stripped or None


def _optional_int(payload: dict[str, Any], key: str) -> int | None:
    value = payload.get(key)
    return value if isinstance(value, int) else None


def _int_value(value: object) -> int | None:
    return value if isinstance(value, int) else None


def _string_value(value: object) -> str | None:
    return value if isinstance(value, str) and value.strip() else None


def _expires_at_from_duration(expires_in: int) -> int:
    current_timestamp = int(datetime.now(timezone.utc).timestamp())
    return current_timestamp + max(expires_in, 0)


def _decode_jwt_claims(token: str | None) -> dict[str, Any]:
    if not token:
        return {}
    parts = token.split(".")
    if len(parts) != 3:
        return {}
    payload = parts[1]
    padding = "=" * (-len(payload) % 4)
    try:
        decoded = base64.urlsafe_b64decode(payload + padding)
        claims = json.loads(decoded.decode("utf-8"))
    except (ValueError, json.JSONDecodeError):
        return {}
    return claims if isinstance(claims, dict) else {}


def _generate_pkce_code_verifier() -> str:
    return "".join(
        secrets.choice(_PKCE_ALLOWED_CHARS) for _ in range(_PKCE_VERIFIER_LENGTH)
    )


def _pkce_code_challenge(code_verifier: str) -> str:
    digest = hashlib.sha256(code_verifier.encode("utf-8")).digest()
    return _base64url_encode(digest)


def _generate_state() -> str:
    return _base64url_encode(secrets.token_bytes(32))


def _base64url_encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode("ascii").rstrip("=")
