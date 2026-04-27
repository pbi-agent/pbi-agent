from __future__ import annotations

from typing import Any

from pbi_agent.auth.models import (
    AUTH_MODE_API_KEY,
    AUTH_MODE_CHATGPT_ACCOUNT,
    AUTH_MODE_COPILOT_ACCOUNT,
    AUTH_FLOW_METHOD_BROWSER,
    AUTH_FLOW_METHOD_DEVICE,
    AuthFlowPollResult,
    ApiKeyAuth,
    BrowserAuthChallenge,
    DeviceAuthChallenge,
    OAuthSessionAuth,
    ProviderAuthStatus,
    RequestAuthConfig,
    StoredAuthSession,
)
from pbi_agent.auth.providers.base import AuthProviderBackend
from pbi_agent.auth.providers.github_copilot import (
    GITHUB_COPILOT_BACKEND_ID,
    GitHubCopilotAuthBackend,
)
from pbi_agent.auth.providers.openai_chatgpt import (
    OPENAI_CHATGPT_BACKEND_ID,
    OpenAIChatGPTAuthBackend,
)
from pbi_agent.auth.store import (
    delete_auth_session,
    load_auth_session,
    save_auth_session,
)


def provider_auth_backend_id(provider_kind: str, auth_mode: str) -> str | None:
    if provider_kind == "chatgpt" and auth_mode == AUTH_MODE_CHATGPT_ACCOUNT:
        return OPENAI_CHATGPT_BACKEND_ID
    if provider_kind == "github_copilot" and auth_mode == AUTH_MODE_COPILOT_ACCOUNT:
        return GITHUB_COPILOT_BACKEND_ID
    return None


def provider_auth_modes(provider_kind: str) -> tuple[str, ...]:
    if provider_kind == "openai":
        return (AUTH_MODE_API_KEY,)
    if provider_kind == "chatgpt":
        return (AUTH_MODE_CHATGPT_ACCOUNT,)
    if provider_kind == "github_copilot":
        return (AUTH_MODE_COPILOT_ACCOUNT,)
    return (AUTH_MODE_API_KEY,)


def provider_auth_mode_label(auth_mode: str) -> str:
    if auth_mode == AUTH_MODE_CHATGPT_ACCOUNT:
        return "ChatGPT account"
    if auth_mode == AUTH_MODE_COPILOT_ACCOUNT:
        return "GitHub Copilot account"
    return "API key"


def provider_auth_account_label(auth_mode: str) -> str | None:
    if auth_mode == AUTH_MODE_CHATGPT_ACCOUNT:
        return "ChatGPT subscription account"
    if auth_mode == AUTH_MODE_COPILOT_ACCOUNT:
        return "GitHub Copilot subscription account"
    return None


def provider_auth_flow_methods(provider_kind: str, auth_mode: str) -> tuple[str, ...]:
    if auth_mode == AUTH_MODE_API_KEY:
        return ()
    backend = _get_backend_for_provider(provider_kind, auth_mode)
    return backend.supported_auth_flow_methods()


def get_provider_auth_status(
    *,
    provider_kind: str,
    provider_id: str,
    auth_mode: str,
) -> ProviderAuthStatus:
    if auth_mode == AUTH_MODE_API_KEY:
        return ProviderAuthStatus(
            auth_mode=AUTH_MODE_API_KEY,
            backend=None,
            session_status="missing",
            has_session=False,
            can_refresh=False,
        )
    backend = _get_backend_for_provider(provider_kind, auth_mode)
    return backend.build_status(load_auth_session(provider_id))


def import_provider_auth_session(
    *,
    provider_kind: str,
    provider_id: str,
    auth_mode: str,
    payload: dict[str, Any],
) -> StoredAuthSession:
    backend = _get_backend_for_provider(provider_kind, auth_mode)
    previous = load_auth_session(provider_id)
    session = backend.import_session(
        provider_id=provider_id,
        payload=payload,
        previous=previous,
    )
    save_auth_session(session)
    return session


def refresh_provider_auth_session(
    *,
    provider_kind: str,
    provider_id: str,
    auth_mode: str,
) -> StoredAuthSession:
    backend = _get_backend_for_provider(provider_kind, auth_mode)
    session = load_auth_session(provider_id)
    if session is None:
        raise ValueError(f"No auth session is stored for provider '{provider_id}'.")
    refreshed = backend.refresh_session(session)
    save_auth_session(refreshed)
    return refreshed


def delete_provider_auth_session(provider_id: str) -> bool:
    return delete_auth_session(provider_id)


def start_provider_browser_auth(
    *,
    provider_kind: str,
    provider_id: str,
    auth_mode: str,
    redirect_uri: str,
) -> BrowserAuthChallenge:
    backend = _require_flow_backend(
        provider_kind=provider_kind,
        auth_mode=auth_mode,
        method=AUTH_FLOW_METHOD_BROWSER,
    )
    del provider_id
    return backend.start_browser_auth(redirect_uri=redirect_uri)


def complete_provider_browser_auth(
    *,
    provider_kind: str,
    provider_id: str,
    auth_mode: str,
    browser_auth: BrowserAuthChallenge,
    code: str,
) -> StoredAuthSession:
    backend = _require_flow_backend(
        provider_kind=provider_kind,
        auth_mode=auth_mode,
        method=AUTH_FLOW_METHOD_BROWSER,
    )
    previous = load_auth_session(provider_id)
    session = backend.exchange_browser_code(
        provider_id=provider_id,
        browser_auth=browser_auth,
        code=code,
        previous=previous,
    )
    save_auth_session(session)
    return session


def start_provider_device_auth(
    *,
    provider_kind: str,
    provider_id: str,
    auth_mode: str,
) -> DeviceAuthChallenge:
    backend = _require_flow_backend(
        provider_kind=provider_kind,
        auth_mode=auth_mode,
        method=AUTH_FLOW_METHOD_DEVICE,
    )
    del provider_id
    return backend.start_device_auth()


def poll_provider_device_auth(
    *,
    provider_kind: str,
    provider_id: str,
    auth_mode: str,
    device_auth: DeviceAuthChallenge,
) -> AuthFlowPollResult:
    backend = _require_flow_backend(
        provider_kind=provider_kind,
        auth_mode=auth_mode,
        method=AUTH_FLOW_METHOD_DEVICE,
    )
    previous = load_auth_session(provider_id)
    result = backend.poll_device_auth(
        provider_id=provider_id,
        device_auth=device_auth,
        previous=previous,
    )
    if result.session is not None:
        save_auth_session(result.session)
    return result


def resolve_runtime_auth(
    *,
    provider_kind: str,
    provider_id: str | None,
    auth_mode: str,
    api_key: str,
    api_key_env: str | None,
) -> ApiKeyAuth | OAuthSessionAuth | None:
    if auth_mode == AUTH_MODE_API_KEY:
        if not api_key:
            return None
        return ApiKeyAuth(api_key=api_key, api_key_env=api_key_env)
    if provider_id is None:
        return None
    session = load_auth_session(provider_id)
    if session is None:
        return None
    return session.to_runtime_auth()


def build_runtime_request_auth(
    *,
    provider_kind: str,
    request_url: str,
    auth: ApiKeyAuth | OAuthSessionAuth | None,
) -> RequestAuthConfig:
    if isinstance(auth, ApiKeyAuth):
        header_name = "api-key" if provider_kind == "azure" else "Authorization"
        header_value = (
            auth.api_key if header_name == "api-key" else f"Bearer {auth.api_key}"
        )
        return RequestAuthConfig(
            request_url=request_url,
            headers={header_name: header_value},
        )
    if isinstance(auth, OAuthSessionAuth):
        backend = _get_backend(auth.backend)
        return backend.build_request_auth(
            request_url=request_url,
            session=StoredAuthSession(
                provider_id=auth.provider_id,
                backend=auth.backend,
                access_token=auth.access_token,
                refresh_token=auth.refresh_token,
                expires_at=auth.expires_at,
                account_id=auth.account_id,
                email=auth.email,
                plan_type=auth.plan_type,
                metadata=dict(auth.metadata),
                created_at="",
                updated_at="",
            ),
        )
    raise ValueError(f"Unsupported runtime auth for provider '{provider_kind}'.")


def refresh_runtime_auth(
    *,
    provider_kind: str,
    auth: OAuthSessionAuth,
) -> OAuthSessionAuth:
    del provider_kind
    backend = _get_backend(auth.backend)
    refreshed = backend.refresh_session(
        StoredAuthSession(
            provider_id=auth.provider_id,
            backend=auth.backend,
            access_token=auth.access_token,
            refresh_token=auth.refresh_token,
            expires_at=auth.expires_at,
            account_id=auth.account_id,
            email=auth.email,
            plan_type=auth.plan_type,
            metadata=dict(auth.metadata),
            created_at="",
            updated_at="",
        )
    )
    save_auth_session(refreshed)
    return refreshed.to_runtime_auth()


def _get_backend_for_provider(
    provider_kind: str, auth_mode: str
) -> AuthProviderBackend:
    backend_id = provider_auth_backend_id(provider_kind, auth_mode)
    if backend_id is None:
        raise ValueError(
            f"Provider '{provider_kind}' does not support auth mode '{auth_mode}'."
        )
    return _get_backend(backend_id)


def _get_backend(backend_id: str) -> AuthProviderBackend:
    if backend_id == OPENAI_CHATGPT_BACKEND_ID:
        return OpenAIChatGPTAuthBackend()
    if backend_id == GITHUB_COPILOT_BACKEND_ID:
        return GitHubCopilotAuthBackend()
    raise ValueError(f"Unknown auth backend '{backend_id}'.")


def _require_flow_backend(
    *,
    provider_kind: str,
    auth_mode: str,
    method: str,
) -> AuthProviderBackend:
    backend = _get_backend_for_provider(provider_kind, auth_mode)
    if method not in backend.supported_auth_flow_methods():
        raise ValueError(
            f"Provider '{provider_kind}' does not support built-in '{method}' auth."
        )
    return backend
