from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from pbi_agent.auth.models import (
    AuthFlowPollResult,
    BrowserAuthChallenge,
    DeviceAuthChallenge,
    ProviderAuthStatus,
    RequestAuthConfig,
    StoredAuthSession,
)


class AuthProviderBackend(ABC):
    @property
    @abstractmethod
    def backend_id(self) -> str:
        """Stable backend ID stored with sessions."""

    @abstractmethod
    def build_status(self, session: StoredAuthSession | None) -> ProviderAuthStatus:
        """Return a normalized auth status view for this backend."""

    @abstractmethod
    def import_session(
        self,
        *,
        provider_id: str,
        payload: dict[str, Any],
        previous: StoredAuthSession | None = None,
    ) -> StoredAuthSession:
        """Build a stored session from a user-supplied payload."""

    @abstractmethod
    def refresh_session(self, session: StoredAuthSession) -> StoredAuthSession:
        """Refresh the current auth session."""

    @abstractmethod
    def build_request_auth(
        self,
        *,
        request_url: str,
        session: StoredAuthSession,
    ) -> RequestAuthConfig:
        """Return the request URL and auth headers for a provider call."""

    def supported_auth_flow_methods(self) -> tuple[str, ...]:
        """Return the built-in auth flow methods supported by this backend."""
        return ()

    def start_browser_auth(
        self,
        *,
        redirect_uri: str,
    ) -> BrowserAuthChallenge:
        raise NotImplementedError(
            f"Auth backend '{self.backend_id}' does not support browser login."
        )

    def exchange_browser_code(
        self,
        *,
        provider_id: str,
        browser_auth: BrowserAuthChallenge,
        code: str,
        previous: StoredAuthSession | None = None,
    ) -> StoredAuthSession:
        raise NotImplementedError(
            f"Auth backend '{self.backend_id}' does not support browser login."
        )

    def start_device_auth(self) -> DeviceAuthChallenge:
        raise NotImplementedError(
            f"Auth backend '{self.backend_id}' does not support device login."
        )

    def poll_device_auth(
        self,
        *,
        provider_id: str,
        device_auth: DeviceAuthChallenge,
        previous: StoredAuthSession | None = None,
    ) -> AuthFlowPollResult:
        raise NotImplementedError(
            f"Auth backend '{self.backend_id}' does not support device login."
        )
