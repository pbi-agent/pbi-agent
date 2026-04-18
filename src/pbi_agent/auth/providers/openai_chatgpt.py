from __future__ import annotations

import base64
import hashlib
import json
import os
import secrets
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from typing import Any

from pbi_agent.auth.models import (
    AUTH_FLOW_METHOD_BROWSER,
    AUTH_FLOW_METHOD_DEVICE,
    AUTH_FLOW_STATUS_COMPLETED,
    AUTH_FLOW_STATUS_PENDING,
    AUTH_MODE_CHATGPT_ACCOUNT,
    AUTH_SESSION_STATUS_CONNECTED,
    AUTH_SESSION_STATUS_EXPIRED,
    AUTH_SESSION_STATUS_MISSING,
    AuthFlowPollResult,
    BrowserAuthChallenge,
    DeviceAuthChallenge,
    ProviderAuthStatus,
    RequestAuthConfig,
    StoredAuthSession,
)
from pbi_agent.auth.providers.base import AuthProviderBackend
from pbi_agent.auth.store import build_auth_session

OPENAI_CHATGPT_BACKEND_ID = "openai_chatgpt"
OPENAI_CHATGPT_RESPONSES_URL = "https://chatgpt.com/backend-api/codex/responses"
OPENAI_CHATGPT_REFRESH_URL = "https://auth.openai.com/oauth/token"
OPENAI_CHATGPT_CLIENT_ID = "app_EMoamEEZ73f0CkXaXp7hrann"
OPENAI_CHATGPT_AUTHORIZE_URL = "https://auth.openai.com/oauth/authorize"
OPENAI_CHATGPT_DEVICE_USER_CODE_URL = (
    "https://auth.openai.com/api/accounts/deviceauth/usercode"
)
OPENAI_CHATGPT_DEVICE_TOKEN_URL = (
    "https://auth.openai.com/api/accounts/deviceauth/token"
)
OPENAI_CHATGPT_DEVICE_VERIFICATION_URL = "https://auth.openai.com/codex/device"
OPENAI_CHATGPT_DEVICE_CALLBACK_URL = "https://auth.openai.com/deviceauth/callback"
OPENAI_CHATGPT_ORIGINATOR_ENV = "PBI_AGENT_OPENAI_ORIGINATOR"
OPENAI_CHATGPT_OAUTH_SCOPE_ENV = "PBI_AGENT_OPENAI_OAUTH_SCOPE"
OPENAI_CHATGPT_OAUTH_SCOPE = "openid profile email offline_access"
_TOKEN_REFRESH_TIMEOUT_SECS = 30.0
_AUTH_FLOW_TIMEOUT_SECS = 30.0
_PKCE_VERIFIER_LENGTH = 64
_PKCE_ALLOWED_CHARS = (
    "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-._~"
)


class OpenAIChatGPTAuthBackend(AuthProviderBackend):
    @property
    def backend_id(self) -> str:
        return OPENAI_CHATGPT_BACKEND_ID

    def build_status(self, session: StoredAuthSession | None) -> ProviderAuthStatus:
        if session is None:
            return ProviderAuthStatus(
                auth_mode=AUTH_MODE_CHATGPT_ACCOUNT,
                backend=self.backend_id,
                session_status=AUTH_SESSION_STATUS_MISSING,
                has_session=False,
                can_refresh=False,
            )
        return ProviderAuthStatus(
            auth_mode=AUTH_MODE_CHATGPT_ACCOUNT,
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
        return (AUTH_FLOW_METHOD_BROWSER, AUTH_FLOW_METHOD_DEVICE)

    def import_session(
        self,
        *,
        provider_id: str,
        payload: dict[str, Any],
        previous: StoredAuthSession | None = None,
    ) -> StoredAuthSession:
        access_token = _require_non_empty_string(payload, "access_token")
        refresh_token = _optional_non_empty_string(payload, "refresh_token")
        account_id = _optional_non_empty_string(payload, "account_id")
        email = _optional_non_empty_string(payload, "email")
        plan_type = _optional_non_empty_string(payload, "plan_type")
        id_token = _optional_non_empty_string(payload, "id_token")
        expires_at = _optional_int(payload, "expires_at")
        expires_in = _optional_int(payload, "expires_in")

        access_claims = _decode_jwt_claims(access_token)
        id_claims = _decode_jwt_claims(id_token) if id_token else {}
        merged_claims = dict(access_claims)
        merged_claims.update(id_claims)

        resolved_account_id = (
            account_id
            or _string_value(merged_claims.get("chatgpt_account_id"))
            or _claim_string(
                merged_claims,
                "https://api.openai.com/auth",
                "chatgpt_account_id",
            )
            or _organization_account_id(merged_claims)
        )
        if not resolved_account_id:
            raise ValueError(
                "ChatGPT account auth requires an account_id or a token with "
                "chatgpt_account_id claims."
            )
        resolved_email = (
            email
            or _claim_string(merged_claims, "https://api.openai.com/profile", "email")
            or _string_value(merged_claims.get("email"))
        )
        resolved_plan_type = (
            plan_type
            or _claim_string(
                merged_claims,
                "https://api.openai.com/auth",
                "chatgpt_plan_type",
            )
            or _string_value(merged_claims.get("chatgpt_plan_type"))
        )
        resolved_expires_at = (
            expires_at
            if expires_at is not None
            else _expires_at_from_duration(expires_in)
            if expires_in is not None
            else _int_value(merged_claims.get("exp"))
        )
        metadata = {
            "id_token": id_token,
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
            account_id=resolved_account_id,
            email=resolved_email,
            plan_type=resolved_plan_type,
            metadata=metadata,
            previous=previous,
        )

    def refresh_session(self, session: StoredAuthSession) -> StoredAuthSession:
        if not session.refresh_token:
            raise ValueError(
                "This ChatGPT auth session does not include a refresh token."
            )
        payload = _post_form_json(
            OPENAI_CHATGPT_REFRESH_URL,
            {
                "client_id": OPENAI_CHATGPT_CLIENT_ID,
                "grant_type": "refresh_token",
                "refresh_token": session.refresh_token,
            },
            timeout=_TOKEN_REFRESH_TIMEOUT_SECS,
            action="ChatGPT token refresh",
        )
        return self.import_session(
            provider_id=session.provider_id,
            payload={
                "access_token": payload.get("access_token") or session.access_token,
                "refresh_token": payload.get("refresh_token") or session.refresh_token,
                "account_id": session.account_id,
                "email": session.email,
                "plan_type": session.plan_type,
                "expires_in": payload.get("expires_in"),
                "id_token": payload.get("id_token"),
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
        headers = {"Authorization": f"Bearer {session.access_token}"}
        if session.account_id:
            headers["ChatGPT-Account-Id"] = session.account_id
        return RequestAuthConfig(request_url=request_url, headers=headers)

    def start_browser_auth(
        self,
        *,
        redirect_uri: str,
    ) -> BrowserAuthChallenge:
        code_verifier = _generate_pkce_code_verifier()
        state = _generate_state()
        query = urllib.parse.urlencode(
            {
                "response_type": "code",
                "client_id": OPENAI_CHATGPT_CLIENT_ID,
                "redirect_uri": redirect_uri,
                "scope": _oauth_scope(),
                "code_challenge": _pkce_code_challenge(code_verifier),
                "code_challenge_method": "S256",
                "id_token_add_organizations": "true",
                "codex_cli_simplified_flow": "true",
                "state": state,
                "originator": _oauth_originator(),
            }
        )
        return BrowserAuthChallenge(
            authorization_url=f"{OPENAI_CHATGPT_AUTHORIZE_URL}?{query}",
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
        return self.import_session(
            provider_id=provider_id,
            payload={
                **_exchange_authorization_code(
                    code=code,
                    redirect_uri=browser_auth.redirect_uri,
                    code_verifier=browser_auth.code_verifier,
                ),
                "token_source": "browser_oauth",
            },
            previous=previous,
        )

    def start_device_auth(self) -> DeviceAuthChallenge:
        payload = _post_json(
            OPENAI_CHATGPT_DEVICE_USER_CODE_URL,
            {"client_id": OPENAI_CHATGPT_CLIENT_ID},
            timeout=_AUTH_FLOW_TIMEOUT_SECS,
            action="ChatGPT device authorization start",
        )
        device_auth_id = _require_non_empty_string(payload, "device_auth_id")
        user_code = _optional_non_empty_string(payload, "user_code") or (
            _optional_non_empty_string(payload, "usercode")
        )
        if not user_code:
            raise ValueError("ChatGPT device authorization did not return a user code.")
        return DeviceAuthChallenge(
            verification_url=OPENAI_CHATGPT_DEVICE_VERIFICATION_URL,
            user_code=user_code,
            device_auth_id=device_auth_id,
            interval_seconds=_interval_seconds(payload.get("interval")),
        )

    def poll_device_auth(
        self,
        *,
        provider_id: str,
        device_auth: DeviceAuthChallenge,
        previous: StoredAuthSession | None = None,
    ) -> AuthFlowPollResult:
        status_code, payload = _post_json_with_status(
            OPENAI_CHATGPT_DEVICE_TOKEN_URL,
            {
                "device_auth_id": device_auth.device_auth_id,
                "user_code": device_auth.user_code,
            },
            timeout=_AUTH_FLOW_TIMEOUT_SECS,
            action="ChatGPT device authorization poll",
            allowed_statuses={403, 404},
        )
        if status_code in {403, 404}:
            return AuthFlowPollResult(
                status=AUTH_FLOW_STATUS_PENDING,
                retry_after_seconds=device_auth.interval_seconds,
            )

        authorization_code = _require_non_empty_string(payload, "authorization_code")
        code_verifier = _require_non_empty_string(payload, "code_verifier")
        session = self.import_session(
            provider_id=provider_id,
            payload={
                **_exchange_authorization_code(
                    code=authorization_code,
                    redirect_uri=OPENAI_CHATGPT_DEVICE_CALLBACK_URL,
                    code_verifier=code_verifier,
                ),
                "token_source": "device_oauth",
            },
            previous=previous,
        )
        return AuthFlowPollResult(
            status=AUTH_FLOW_STATUS_COMPLETED,
            session=session,
        )


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


def _claim_string(
    claims: dict[str, Any], nested_key: str, field_name: str
) -> str | None:
    nested = claims.get(nested_key)
    if not isinstance(nested, dict):
        return None
    return _string_value(nested.get(field_name))


def _string_value(value: object) -> str | None:
    return value if isinstance(value, str) and value.strip() else None


def _int_value(value: object) -> int | None:
    return value if isinstance(value, int) else None


def _organization_account_id(claims: dict[str, Any]) -> str | None:
    organizations = claims.get("organizations")
    if not isinstance(organizations, list):
        return None
    for organization in organizations:
        if not isinstance(organization, dict):
            continue
        account_id = _string_value(organization.get("id"))
        if account_id:
            return account_id
    return None


def _expires_at_from_duration(expires_in: int) -> int:
    current_timestamp = int(datetime.now(timezone.utc).timestamp())
    return current_timestamp + max(expires_in, 0)


def _oauth_originator() -> str:
    override = os.environ.get(OPENAI_CHATGPT_ORIGINATOR_ENV)
    if override:
        stripped = override.strip()
        if stripped:
            return stripped
    return "opencode"


def _oauth_scope() -> str:
    override = os.environ.get(OPENAI_CHATGPT_OAUTH_SCOPE_ENV)
    if override:
        stripped = override.strip()
        if stripped:
            return stripped
    return OPENAI_CHATGPT_OAUTH_SCOPE


def utc_now_timestamp() -> int:
    return int(datetime.now(timezone.utc).timestamp())


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


def _exchange_authorization_code(
    *,
    code: str,
    redirect_uri: str,
    code_verifier: str,
) -> dict[str, Any]:
    return _post_form_json(
        OPENAI_CHATGPT_REFRESH_URL,
        {
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": redirect_uri,
            "client_id": OPENAI_CHATGPT_CLIENT_ID,
            "code_verifier": code_verifier,
        },
        timeout=_AUTH_FLOW_TIMEOUT_SECS,
        action="ChatGPT OAuth code exchange",
    )


def _post_form_json(
    url: str,
    payload: dict[str, str],
    *,
    timeout: float,
    action: str,
) -> dict[str, Any]:
    request = urllib.request.Request(
        url,
        data=urllib.parse.urlencode(payload).encode("utf-8"),
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        method="POST",
    )
    return _json_payload_from_request(
        request,
        timeout=timeout,
        action=action,
    )[1]


def _post_json(
    url: str,
    payload: dict[str, Any],
    *,
    timeout: float,
    action: str,
) -> dict[str, Any]:
    return _post_json_with_status(
        url,
        payload,
        timeout=timeout,
        action=action,
    )[1]


def _post_json_with_status(
    url: str,
    payload: dict[str, Any],
    *,
    timeout: float,
    action: str,
    allowed_statuses: set[int] | None = None,
) -> tuple[int, dict[str, Any]]:
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "User-Agent": "pbi-agent",
        },
        method="POST",
    )
    return _json_payload_from_request(
        request,
        timeout=timeout,
        action=action,
        allowed_statuses=allowed_statuses,
    )


def _json_payload_from_request(
    request: urllib.request.Request,
    *,
    timeout: float,
    action: str,
    allowed_statuses: set[int] | None = None,
) -> tuple[int, dict[str, Any]]:
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            status_code = getattr(response, "status", 200)
            return status_code, _decode_json_payload(response.read(), action=action)
    except urllib.error.HTTPError as exc:
        body = exc.read()
        if allowed_statuses and exc.code in allowed_statuses:
            return exc.code, _decode_json_payload(body, action=action, allow_empty=True)
        message = body.decode("utf-8", errors="replace")
        raise RuntimeError(
            f"{action} failed with status {exc.code}: {message}"
        ) from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"{action} failed: {exc.reason}") from exc


def _decode_json_payload(
    raw_body: bytes,
    *,
    action: str,
    allow_empty: bool = False,
) -> dict[str, Any]:
    if not raw_body:
        if allow_empty:
            return {}
        raise RuntimeError(f"{action} returned an empty response.")
    try:
        payload = json.loads(raw_body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"{action} returned invalid JSON.") from exc
    if not isinstance(payload, dict):
        raise RuntimeError(f"{action} returned an unexpected JSON payload.")
    return payload


def _interval_seconds(value: object) -> int:
    if isinstance(value, int):
        return max(value, 1)
    if isinstance(value, str):
        stripped = value.strip()
        if not stripped:
            return 5
        try:
            return max(int(stripped), 1)
        except ValueError:
            return 5
    return 5
