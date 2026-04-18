from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Any

from pbi_agent.auth.models import (
    AUTH_FLOW_METHOD_DEVICE,
    AUTH_FLOW_STATUS_COMPLETED,
    AUTH_FLOW_STATUS_PENDING,
    AUTH_MODE_COPILOT_ACCOUNT,
    AUTH_SESSION_STATUS_CONNECTED,
    AUTH_SESSION_STATUS_MISSING,
    AuthFlowPollResult,
    DeviceAuthChallenge,
    ProviderAuthStatus,
    RequestAuthConfig,
    StoredAuthSession,
)
from pbi_agent.auth.providers.base import AuthProviderBackend
from pbi_agent.auth.store import build_auth_session

GITHUB_COPILOT_BACKEND_ID = "github_copilot"
GITHUB_COPILOT_CLIENT_ID = "Ov23li8tweQw6odWQebz"
GITHUB_COPILOT_DEVICE_CODE_URL = "https://github.com/login/device/code"
GITHUB_COPILOT_ACCESS_TOKEN_URL = "https://github.com/login/oauth/access_token"
GITHUB_COPILOT_VERIFICATION_URL = "https://github.com/login/device"
GITHUB_COPILOT_RESPONSES_URL = "https://api.githubcopilot.com/responses"
_AUTH_FLOW_TIMEOUT_SECS = 30.0


class GitHubCopilotAuthBackend(AuthProviderBackend):
    @property
    def backend_id(self) -> str:
        return GITHUB_COPILOT_BACKEND_ID

    def build_status(self, session: StoredAuthSession | None) -> ProviderAuthStatus:
        if session is None:
            return ProviderAuthStatus(
                auth_mode=AUTH_MODE_COPILOT_ACCOUNT,
                backend=self.backend_id,
                session_status=AUTH_SESSION_STATUS_MISSING,
                has_session=False,
                can_refresh=False,
            )
        return ProviderAuthStatus(
            auth_mode=AUTH_MODE_COPILOT_ACCOUNT,
            backend=self.backend_id,
            session_status=AUTH_SESSION_STATUS_CONNECTED,
            has_session=True,
            can_refresh=False,
            account_id=session.account_id,
            email=session.email,
            plan_type=session.plan_type,
            expires_at=session.expires_at,
        )

    def supported_auth_flow_methods(self) -> tuple[str, ...]:
        return (AUTH_FLOW_METHOD_DEVICE,)

    def import_session(
        self,
        *,
        provider_id: str,
        payload: dict[str, Any],
        previous: StoredAuthSession | None = None,
    ) -> StoredAuthSession:
        access_token = _require_non_empty_string(payload, "access_token")
        metadata = {
            "token_type": _optional_non_empty_string(payload, "token_type") or "bearer",
            "scope": _optional_non_empty_string(payload, "scope"),
            "github_login": _optional_non_empty_string(payload, "github_login"),
            "token_source": _optional_non_empty_string(payload, "token_source")
            or "manual_import",
        }
        if previous is not None:
            metadata = {**previous.metadata, **metadata}
        return build_auth_session(
            provider_id=provider_id,
            backend=self.backend_id,
            access_token=access_token,
            refresh_token=None,
            expires_at=None,
            account_id=_optional_non_empty_string(payload, "account_id")
            or _optional_non_empty_string(payload, "github_login"),
            email=_optional_non_empty_string(payload, "email"),
            plan_type=_optional_non_empty_string(payload, "plan_type")
            or "github_copilot",
            metadata=metadata,
            previous=previous,
        )

    def refresh_session(self, session: StoredAuthSession) -> StoredAuthSession:
        raise ValueError(
            "GitHub Copilot auth sessions do not support token refresh. "
            "Re-run device login to reconnect."
        )

    def build_request_auth(
        self,
        *,
        request_url: str,
        session: StoredAuthSession,
    ) -> RequestAuthConfig:
        return RequestAuthConfig(
            request_url=request_url,
            headers={"Authorization": f"Bearer {session.access_token}"},
        )

    def start_device_auth(self) -> DeviceAuthChallenge:
        payload = _post_json(
            GITHUB_COPILOT_DEVICE_CODE_URL,
            {
                "client_id": GITHUB_COPILOT_CLIENT_ID,
                "scope": "read:user",
            },
            timeout=_AUTH_FLOW_TIMEOUT_SECS,
            action="GitHub Copilot device authorization start",
        )
        return DeviceAuthChallenge(
            verification_url=_require_non_empty_string(payload, "verification_uri"),
            user_code=_require_non_empty_string(payload, "user_code"),
            device_auth_id=_require_non_empty_string(payload, "device_code"),
            interval_seconds=_interval_seconds(payload.get("interval")),
        )

    def poll_device_auth(
        self,
        *,
        provider_id: str,
        device_auth: DeviceAuthChallenge,
        previous: StoredAuthSession | None = None,
    ) -> AuthFlowPollResult:
        payload = _post_json(
            GITHUB_COPILOT_ACCESS_TOKEN_URL,
            {
                "client_id": GITHUB_COPILOT_CLIENT_ID,
                "device_code": device_auth.device_auth_id,
                "grant_type": "urn:ietf:params:oauth:grant-type:device_code",
            },
            timeout=_AUTH_FLOW_TIMEOUT_SECS,
            action="GitHub Copilot device authorization poll",
        )
        error = _optional_non_empty_string(payload, "error")
        if error in {"authorization_pending", "slow_down"}:
            interval_seconds = device_auth.interval_seconds
            if error == "slow_down":
                interval_seconds = _interval_seconds(payload.get("interval")) + 5
            return AuthFlowPollResult(
                status=AUTH_FLOW_STATUS_PENDING,
                retry_after_seconds=interval_seconds,
            )
        if error:
            message = _optional_non_empty_string(payload, "error_description") or error
            raise ValueError(f"GitHub Copilot device authorization failed: {message}")
        session = self.import_session(
            provider_id=provider_id,
            payload={
                "access_token": _require_non_empty_string(payload, "access_token"),
                "token_type": _optional_non_empty_string(payload, "token_type"),
                "scope": _optional_non_empty_string(payload, "scope"),
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


def _interval_seconds(value: object) -> int:
    if isinstance(value, int):
        return max(value, 1)
    if isinstance(value, str):
        try:
            return max(int(value), 1)
        except ValueError:
            return 5
    return 5


def _post_json(
    url: str,
    payload: dict[str, Any],
    *,
    timeout: float,
    action: str,
) -> dict[str, Any]:
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Accept": "application/json",
            "Content-Type": "application/json",
            "User-Agent": "pbi-agent",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            body = response.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace").strip()
        raise RuntimeError(f"{action} failed with HTTP {exc.code}: {body}") from exc

    parsed = json.loads(body or "{}")
    if not isinstance(parsed, dict):
        raise ValueError(f"{action} returned a non-object JSON payload.")
    return parsed
