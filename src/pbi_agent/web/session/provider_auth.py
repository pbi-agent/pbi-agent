from __future__ import annotations

import threading
from typing import TYPE_CHECKING, Any

from pbi_agent.auth.browser_callback import (
    BrowserAuthCallbackListener,
    BrowserAuthCallbackOutcome,
    BrowserAuthCallbackParams,
    create_browser_auth_callback_listener,
)
from pbi_agent.auth.models import (
    AUTH_FLOW_METHOD_BROWSER,
    AUTH_FLOW_METHOD_DEVICE,
    AUTH_FLOW_STATUS_COMPLETED,
    AUTH_FLOW_STATUS_FAILED,
    AUTH_FLOW_STATUS_PENDING,
    StoredAuthSession,
)
from pbi_agent.auth.service import (
    complete_provider_browser_auth,
    delete_provider_auth_session,
    get_provider_auth_status,
    import_provider_auth_session,
    poll_provider_device_auth,
    refresh_provider_auth_session,
    start_provider_browser_auth,
    start_provider_device_auth,
)
from pbi_agent.auth.usage_limits import get_provider_usage_limits
from pbi_agent.config import (
    ConfigError,
    InternalConfig,
    ProviderConfig,
    load_internal_config,
)
from pbi_agent.web.session.state import PendingProviderAuthFlow, _now_iso

_PROVIDER_AUTH_BROWSER_FLOW_TIMEOUT_SECS = 5 * 60


class ProviderAuthMixin:
    _lock: Any
    _provider_auth_flows: dict[str, PendingProviderAuthFlow]

    if TYPE_CHECKING:

        def _require_provider(
            self, config: InternalConfig, provider_id: str
        ) -> ProviderConfig: ...

        def _provider_view(self, provider: ProviderConfig) -> dict[str, Any]: ...

        def _auth_status_view(self, status: Any) -> dict[str, Any]: ...

        def _auth_session_view(
            self, session: StoredAuthSession | None
        ) -> dict[str, Any] | None: ...

    def get_provider_auth_status(self, provider_id: str) -> dict[str, Any]:
        config = load_internal_config()
        provider = self._require_provider(config, provider_id)
        status = get_provider_auth_status(
            provider_kind=provider.kind,
            provider_id=provider.id,
            auth_mode=provider.auth_mode,
        )
        return {
            "provider": self._provider_view(provider),
            "auth_status": self._auth_status_view(status),
        }

    def import_provider_auth(
        self,
        provider_id: str,
        *,
        access_token: str,
        refresh_token: str | None,
        account_id: str | None,
        email: str | None,
        plan_type: str | None,
        expires_at: int | None,
        id_token: str | None,
    ) -> dict[str, Any]:
        config = load_internal_config()
        provider = self._require_provider(config, provider_id)
        session = import_provider_auth_session(
            provider_kind=provider.kind,
            provider_id=provider.id,
            auth_mode=provider.auth_mode,
            payload={
                "access_token": access_token,
                "refresh_token": refresh_token,
                "account_id": account_id,
                "email": email,
                "plan_type": plan_type,
                "expires_at": expires_at,
                "id_token": id_token,
            },
        )
        status = get_provider_auth_status(
            provider_kind=provider.kind,
            provider_id=provider.id,
            auth_mode=provider.auth_mode,
        )
        return {
            "provider": self._provider_view(provider),
            "auth_status": self._auth_status_view(status),
            "session": self._auth_session_view(session),
        }

    def refresh_provider_auth(self, provider_id: str) -> dict[str, Any]:
        config = load_internal_config()
        provider = self._require_provider(config, provider_id)
        session = refresh_provider_auth_session(
            provider_kind=provider.kind,
            provider_id=provider.id,
            auth_mode=provider.auth_mode,
        )
        status = get_provider_auth_status(
            provider_kind=provider.kind,
            provider_id=provider.id,
            auth_mode=provider.auth_mode,
        )
        return {
            "provider": self._provider_view(provider),
            "auth_status": self._auth_status_view(status),
            "session": self._auth_session_view(session),
        }

    def logout_provider_auth(self, provider_id: str) -> dict[str, Any]:
        config = load_internal_config()
        provider = self._require_provider(config, provider_id)
        removed = delete_provider_auth_session(provider.id)
        status = get_provider_auth_status(
            provider_kind=provider.kind,
            provider_id=provider.id,
            auth_mode=provider.auth_mode,
        )
        return {
            "provider": self._provider_view(provider),
            "auth_status": self._auth_status_view(status),
            "removed": removed,
        }

    def get_provider_usage_limits(self, provider_id: str) -> dict[str, Any]:
        config = load_internal_config()
        provider = self._require_provider(config, provider_id)
        usage = get_provider_usage_limits(provider)
        return usage.to_dict()

    def start_provider_auth_flow(
        self,
        provider_id: str,
        *,
        flow_id: str,
        method: str,
    ) -> dict[str, Any]:
        config = load_internal_config()
        provider = self._require_provider(config, provider_id)
        status = get_provider_auth_status(
            provider_kind=provider.kind,
            provider_id=provider.id,
            auth_mode=provider.auth_mode,
        )
        created_at = _now_iso()
        if method == AUTH_FLOW_METHOD_BROWSER:
            listener: BrowserAuthCallbackListener | None = None
            timeout_timer: threading.Timer | None = None
            try:
                listener = create_browser_auth_callback_listener(
                    callback_handler=lambda params: (
                        self._handle_provider_auth_browser_callback(
                            provider_id=provider.id,
                            flow_id=flow_id,
                            params=params,
                        )
                    )
                )
                browser_auth = start_provider_browser_auth(
                    provider_kind=provider.kind,
                    provider_id=provider.id,
                    auth_mode=provider.auth_mode,
                    redirect_uri=listener.callback_url,
                )
                flow = PendingProviderAuthFlow(
                    flow_id=flow_id,
                    provider_id=provider.id,
                    backend=status.backend or "",
                    method=method,
                    status=AUTH_FLOW_STATUS_PENDING,
                    created_at=created_at,
                    updated_at=created_at,
                    browser_auth=browser_auth,
                    browser_callback_listener=listener,
                    browser_timeout_timer=None,
                    authorization_url=browser_auth.authorization_url,
                    callback_url=browser_auth.redirect_uri,
                )
                timeout_timer = threading.Timer(
                    _PROVIDER_AUTH_BROWSER_FLOW_TIMEOUT_SECS,
                    self._expire_provider_auth_flow,
                    kwargs={
                        "provider_id": provider.id,
                        "flow_id": flow_id,
                        "message": "Authorization timed out.",
                    },
                )
                flow.browser_timeout_timer = timeout_timer
                with self._lock:
                    self._provider_auth_flows[flow.flow_id] = flow
                timeout_timer.start()
                listener.start()
            except Exception:
                if timeout_timer is not None:
                    timeout_timer.cancel()
                if listener is not None:
                    listener.shutdown()
                with self._lock:
                    existing = self._provider_auth_flows.get(flow_id)
                    if existing is not None and existing.provider_id == provider.id:
                        self._provider_auth_flows.pop(flow_id, None)
                raise
        elif method == AUTH_FLOW_METHOD_DEVICE:
            device_auth = start_provider_device_auth(
                provider_kind=provider.kind,
                provider_id=provider.id,
                auth_mode=provider.auth_mode,
            )
            flow = PendingProviderAuthFlow(
                flow_id=flow_id,
                provider_id=provider.id,
                backend=status.backend or "",
                method=method,
                status=AUTH_FLOW_STATUS_PENDING,
                created_at=created_at,
                updated_at=created_at,
                device_auth=device_auth,
                verification_url=device_auth.verification_url,
                user_code=device_auth.user_code,
                interval_seconds=device_auth.interval_seconds,
            )
        else:
            raise ValueError(f"Unknown auth flow method '{method}'.")

        if method != AUTH_FLOW_METHOD_BROWSER:
            with self._lock:
                self._provider_auth_flows[flow.flow_id] = flow
        return {
            "provider": self._provider_view(provider),
            "auth_status": self._auth_status_view(status),
            "flow": self._provider_auth_flow_view(flow),
        }

    def get_provider_auth_flow(self, provider_id: str, flow_id: str) -> dict[str, Any]:
        config = load_internal_config()
        provider = self._require_provider(config, provider_id)
        flow = self._require_provider_auth_flow(provider.id, flow_id)
        status = get_provider_auth_status(
            provider_kind=provider.kind,
            provider_id=provider.id,
            auth_mode=provider.auth_mode,
        )
        return {
            "provider": self._provider_view(provider),
            "auth_status": self._auth_status_view(status),
            "flow": self._provider_auth_flow_view(flow),
            "session": self._auth_session_view(flow.session),
        }

    def poll_provider_auth_flow(self, provider_id: str, flow_id: str) -> dict[str, Any]:
        config = load_internal_config()
        provider = self._require_provider(config, provider_id)
        flow = self._require_provider_auth_flow(provider.id, flow_id)
        if flow.method != AUTH_FLOW_METHOD_DEVICE:
            raise ValueError("Only device auth flows can be polled.")
        if flow.device_auth is None:
            raise ValueError("Device auth flow is missing its device challenge.")
        if flow.status == AUTH_FLOW_STATUS_PENDING:
            try:
                result = poll_provider_device_auth(
                    provider_kind=provider.kind,
                    provider_id=provider.id,
                    auth_mode=provider.auth_mode,
                    device_auth=flow.device_auth,
                )
            except Exception as exc:
                self._mark_provider_auth_flow_failed(flow, str(exc))
            else:
                flow.updated_at = _now_iso()
                if result.session is not None:
                    flow.status = AUTH_FLOW_STATUS_COMPLETED
                    flow.session = result.session
                elif result.retry_after_seconds is not None:
                    flow.interval_seconds = result.retry_after_seconds
        status = get_provider_auth_status(
            provider_kind=provider.kind,
            provider_id=provider.id,
            auth_mode=provider.auth_mode,
        )
        return {
            "provider": self._provider_view(provider),
            "auth_status": self._auth_status_view(status),
            "flow": self._provider_auth_flow_view(flow),
            "session": self._auth_session_view(flow.session),
        }

    def complete_provider_browser_auth_flow(
        self,
        provider_id: str,
        flow_id: str,
        *,
        code: str | None,
        state: str | None,
        error: str | None,
        error_description: str | None,
    ) -> dict[str, Any]:
        config = load_internal_config()
        provider = self._require_provider(config, provider_id)
        flow = self._require_provider_auth_flow(provider.id, flow_id)
        if flow.method != AUTH_FLOW_METHOD_BROWSER:
            raise ValueError("Only browser auth flows can accept callbacks.")
        if flow.browser_auth is None:
            raise ValueError("Browser auth flow is missing its authorization state.")
        if flow.status == AUTH_FLOW_STATUS_PENDING:
            if error:
                self._mark_provider_auth_flow_failed(flow, error_description or error)
            elif not code:
                self._mark_provider_auth_flow_failed(
                    flow, "Missing authorization code in callback."
                )
            elif state != flow.browser_auth.state:
                self._mark_provider_auth_flow_failed(
                    flow, "Invalid authorization state in callback."
                )
            else:
                try:
                    session = complete_provider_browser_auth(
                        provider_kind=provider.kind,
                        provider_id=provider.id,
                        auth_mode=provider.auth_mode,
                        browser_auth=flow.browser_auth,
                        code=code,
                    )
                except Exception as exc:
                    self._mark_provider_auth_flow_failed(flow, str(exc))
                else:
                    flow.status = AUTH_FLOW_STATUS_COMPLETED
                    flow.updated_at = _now_iso()
                    flow.session = session
        status = get_provider_auth_status(
            provider_kind=provider.kind,
            provider_id=provider.id,
            auth_mode=provider.auth_mode,
        )
        return {
            "provider": self._provider_view(provider),
            "auth_status": self._auth_status_view(status),
            "flow": self._provider_auth_flow_view(flow),
            "session": self._auth_session_view(flow.session),
        }

    def _provider_auth_flow_view(self, flow: PendingProviderAuthFlow) -> dict[str, Any]:
        return {
            "flow_id": flow.flow_id,
            "provider_id": flow.provider_id,
            "backend": flow.backend,
            "method": flow.method,
            "status": flow.status,
            "authorization_url": flow.authorization_url,
            "callback_url": flow.callback_url,
            "verification_url": flow.verification_url,
            "user_code": flow.user_code,
            "interval_seconds": flow.interval_seconds,
            "error_message": flow.error_message,
            "created_at": flow.created_at,
            "updated_at": flow.updated_at,
        }

    def _require_provider_auth_flow(
        self, provider_id: str, flow_id: str
    ) -> PendingProviderAuthFlow:
        with self._lock:
            flow = self._provider_auth_flows.get(flow_id)
        if flow is None or flow.provider_id != provider_id:
            raise ConfigError(f"Unknown auth flow ID '{flow_id}'.")
        return flow

    def _mark_provider_auth_flow_failed(
        self, flow: PendingProviderAuthFlow, message: str
    ) -> None:
        flow.status = AUTH_FLOW_STATUS_FAILED
        flow.error_message = message
        flow.updated_at = _now_iso()

    def _handle_provider_auth_browser_callback(
        self,
        *,
        provider_id: str,
        flow_id: str,
        params: BrowserAuthCallbackParams,
    ) -> BrowserAuthCallbackOutcome:
        payload = self.complete_provider_browser_auth_flow(
            provider_id,
            flow_id,
            code=params.code,
            state=params.state,
            error=params.error,
            error_description=params.error_description,
        )
        flow = self._require_provider_auth_flow(provider_id, flow_id)
        self._cancel_provider_auth_flow_browser_timeout(flow)
        self._shutdown_provider_auth_flow_browser_listener(flow)
        if payload["flow"]["status"] == AUTH_FLOW_STATUS_COMPLETED:
            return BrowserAuthCallbackOutcome(completed=True)
        return BrowserAuthCallbackOutcome(
            completed=False,
            error_message=payload["flow"].get("error_message")
            or "Authorization failed.",
        )

    def _expire_provider_auth_flow(
        self,
        *,
        provider_id: str,
        flow_id: str,
        message: str,
    ) -> None:
        try:
            flow = self._require_provider_auth_flow(provider_id, flow_id)
        except ConfigError:
            return
        if flow.method != AUTH_FLOW_METHOD_BROWSER:
            return
        if flow.status != AUTH_FLOW_STATUS_PENDING:
            self._cancel_provider_auth_flow_browser_timeout(flow)
            return
        self._mark_provider_auth_flow_failed(flow, message)
        self._cancel_provider_auth_flow_browser_timeout(flow)
        self._shutdown_provider_auth_flow_browser_listener(flow)

    def _cancel_provider_auth_flow_browser_timeout(
        self, flow: PendingProviderAuthFlow
    ) -> None:
        timer = flow.browser_timeout_timer
        if timer is None:
            return
        flow.browser_timeout_timer = None
        timer.cancel()

    def _shutdown_provider_auth_flow_browser_listener(
        self, flow: PendingProviderAuthFlow
    ) -> None:
        listener = flow.browser_callback_listener
        if listener is None:
            return
        flow.browser_callback_listener = None
        listener.shutdown()
