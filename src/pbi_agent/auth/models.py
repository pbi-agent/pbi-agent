from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

AUTH_MODE_API_KEY = "api_key"
AUTH_MODE_CHATGPT_ACCOUNT = "chatgpt_account"
SUPPORTED_OPENAI_AUTH_MODES = (AUTH_MODE_API_KEY, AUTH_MODE_CHATGPT_ACCOUNT)

RUNTIME_AUTH_KIND_API_KEY = "api_key"
RUNTIME_AUTH_KIND_OAUTH_SESSION = "oauth_session"

AUTH_FLOW_METHOD_BROWSER = "browser"
AUTH_FLOW_METHOD_DEVICE = "device"

AUTH_FLOW_STATUS_PENDING = "pending"
AUTH_FLOW_STATUS_COMPLETED = "completed"
AUTH_FLOW_STATUS_FAILED = "failed"

AUTH_SESSION_STATUS_MISSING = "missing"
AUTH_SESSION_STATUS_CONNECTED = "connected"
AUTH_SESSION_STATUS_EXPIRED = "expired"


@dataclass(slots=True)
class ApiKeyAuth:
    kind: str = RUNTIME_AUTH_KIND_API_KEY
    api_key: str = ""
    api_key_env: str | None = None


@dataclass(slots=True)
class OAuthSessionAuth:
    kind: str = RUNTIME_AUTH_KIND_OAUTH_SESSION
    provider_id: str = ""
    backend: str = ""
    access_token: str = ""
    refresh_token: str | None = None
    expires_at: int | None = None
    account_id: str | None = None
    email: str | None = None
    plan_type: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def is_expired(self, *, now: datetime | None = None) -> bool:
        if self.expires_at is None:
            return False
        current = now or datetime.now(timezone.utc)
        return self.expires_at <= int(current.timestamp())


ResolvedProviderAuth = ApiKeyAuth | OAuthSessionAuth


@dataclass(slots=True)
class StoredAuthSession:
    provider_id: str
    backend: str
    access_token: str
    refresh_token: str | None = None
    expires_at: int | None = None
    account_id: str | None = None
    email: str | None = None
    plan_type: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: str = ""
    updated_at: str = ""

    def to_runtime_auth(self) -> OAuthSessionAuth:
        return OAuthSessionAuth(
            provider_id=self.provider_id,
            backend=self.backend,
            access_token=self.access_token,
            refresh_token=self.refresh_token,
            expires_at=self.expires_at,
            account_id=self.account_id,
            email=self.email,
            plan_type=self.plan_type,
            metadata=dict(self.metadata),
        )

    def is_expired(self, *, now: datetime | None = None) -> bool:
        return self.to_runtime_auth().is_expired(now=now)


@dataclass(slots=True)
class ProviderAuthStatus:
    auth_mode: str
    backend: str | None
    session_status: str
    has_session: bool
    can_refresh: bool
    account_id: str | None = None
    email: str | None = None
    plan_type: str | None = None
    expires_at: int | None = None


@dataclass(slots=True)
class RequestAuthConfig:
    request_url: str
    headers: dict[str, str]


@dataclass(slots=True)
class BrowserAuthChallenge:
    authorization_url: str
    redirect_uri: str
    state: str
    code_verifier: str


@dataclass(slots=True)
class DeviceAuthChallenge:
    verification_url: str
    user_code: str
    device_auth_id: str
    interval_seconds: int


@dataclass(slots=True)
class AuthFlowPollResult:
    status: str
    session: StoredAuthSession | None = None
    retry_after_seconds: int | None = None


AuthSessionStatus = (
    AUTH_SESSION_STATUS_MISSING,
    AUTH_SESSION_STATUS_CONNECTED,
    AUTH_SESSION_STATUS_EXPIRED,
)

SupportedAuthFlowMethods = (
    AUTH_FLOW_METHOD_BROWSER,
    AUTH_FLOW_METHOD_DEVICE,
)

AuthFlowStatuses = (
    AUTH_FLOW_STATUS_PENDING,
    AUTH_FLOW_STATUS_COMPLETED,
    AUTH_FLOW_STATUS_FAILED,
)
