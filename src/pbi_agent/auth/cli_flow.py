from __future__ import annotations

import queue
import time
from dataclasses import dataclass
from typing import Callable

from pbi_agent.auth.browser_callback import (
    BrowserAuthCallbackOutcome,
    BrowserAuthCallbackParams,
    create_browser_auth_callback_listener,
)
from pbi_agent.auth.models import (
    BrowserAuthChallenge,
    DeviceAuthChallenge,
    StoredAuthSession,
)
from pbi_agent.auth.service import (
    complete_provider_browser_auth,
    poll_provider_device_auth,
    start_provider_browser_auth,
    start_provider_device_auth,
)

_BROWSER_AUTH_TIMEOUT_SECS = 5 * 60
_DEVICE_AUTH_TIMEOUT_SECS = 15 * 60


@dataclass(slots=True)
class BrowserAuthFlowResult:
    session: StoredAuthSession
    browser_auth: BrowserAuthChallenge
    opened_browser: bool


@dataclass(slots=True)
class DeviceAuthFlowResult:
    session: StoredAuthSession
    device_auth: DeviceAuthChallenge


def run_provider_browser_auth_flow(
    *,
    provider_kind: str,
    provider_id: str,
    auth_mode: str,
    open_browser: Callable[[str], bool],
    on_ready: Callable[[BrowserAuthChallenge], None] | None = None,
) -> BrowserAuthFlowResult:
    browser_auth: BrowserAuthChallenge | None = None
    result_queue: queue.Queue[StoredAuthSession | Exception] = queue.Queue()

    def callback_handler(
        params: BrowserAuthCallbackParams,
    ) -> BrowserAuthCallbackOutcome:
        if browser_auth is None:
            error = RuntimeError("Browser authorization was not initialized correctly.")
            result_queue.put(error)
            return BrowserAuthCallbackOutcome(completed=False, error_message=str(error))
        if params.error:
            error = RuntimeError(params.error_description or params.error)
            result_queue.put(error)
            return BrowserAuthCallbackOutcome(completed=False, error_message=str(error))
        if params.state != browser_auth.state:
            error = RuntimeError("Invalid authorization state in callback.")
            result_queue.put(error)
            return BrowserAuthCallbackOutcome(completed=False, error_message=str(error))
        if not params.code:
            error = RuntimeError("Missing authorization code in callback.")
            result_queue.put(error)
            return BrowserAuthCallbackOutcome(completed=False, error_message=str(error))
        try:
            session = complete_provider_browser_auth(
                provider_kind=provider_kind,
                provider_id=provider_id,
                auth_mode=auth_mode,
                browser_auth=browser_auth,
                code=params.code,
            )
        except Exception as exc:  # pragma: no cover - exercised via tests
            result_queue.put(exc)
            return BrowserAuthCallbackOutcome(completed=False, error_message=str(exc))
        result_queue.put(session)
        return BrowserAuthCallbackOutcome(completed=True)

    listener = create_browser_auth_callback_listener(
        callback_handler=callback_handler,
    )
    try:
        browser_auth = start_provider_browser_auth(
            provider_kind=provider_kind,
            provider_id=provider_id,
            auth_mode=auth_mode,
            redirect_uri=listener.callback_url,
        )
        if on_ready is not None:
            on_ready(browser_auth)
        listener.start()
        opened_browser = bool(open_browser(browser_auth.authorization_url))
        try:
            result = result_queue.get(timeout=_BROWSER_AUTH_TIMEOUT_SECS)
        except queue.Empty as exc:
            raise RuntimeError(
                "Timed out waiting for the browser authorization callback."
            ) from exc
        if isinstance(result, Exception):
            raise result
        return BrowserAuthFlowResult(
            session=result,
            browser_auth=browser_auth,
            opened_browser=opened_browser,
        )
    finally:
        listener.shutdown()


def run_provider_device_auth_flow(
    *,
    provider_kind: str,
    provider_id: str,
    auth_mode: str,
    timeout_seconds: int = _DEVICE_AUTH_TIMEOUT_SECS,
    on_start: Callable[[DeviceAuthChallenge], None] | None = None,
) -> DeviceAuthFlowResult:
    device_auth = start_provider_device_auth(
        provider_kind=provider_kind,
        provider_id=provider_id,
        auth_mode=auth_mode,
    )
    if on_start is not None:
        on_start(device_auth)
    deadline = time.monotonic() + timeout_seconds
    while True:
        result = poll_provider_device_auth(
            provider_kind=provider_kind,
            provider_id=provider_id,
            auth_mode=auth_mode,
            device_auth=device_auth,
        )
        if result.session is not None:
            return DeviceAuthFlowResult(session=result.session, device_auth=device_auth)
        if time.monotonic() >= deadline:
            raise RuntimeError("Timed out waiting for device authorization.")
        sleep_for = result.retry_after_seconds or device_auth.interval_seconds
        time.sleep(max(sleep_for, 1))
