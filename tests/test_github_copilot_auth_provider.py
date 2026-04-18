from __future__ import annotations

import json
import urllib.request

import pytest

from pbi_agent.auth.models import (
    AUTH_FLOW_STATUS_COMPLETED,
    AUTH_FLOW_STATUS_PENDING,
    DeviceAuthChallenge,
)
from pbi_agent.auth.providers.github_copilot import (
    GITHUB_COPILOT_BACKEND_ID,
    GITHUB_COPILOT_CLIENT_ID,
    GITHUB_COPILOT_DEVICE_CODE_URL,
    GITHUB_COPILOT_RESPONSES_URL,
    GitHubCopilotAuthBackend,
)


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


def test_start_device_auth_posts_expected_payload(monkeypatch) -> None:
    backend = GitHubCopilotAuthBackend()
    captured: dict[str, object] = {}

    def fake_urlopen(
        request: urllib.request.Request,
        timeout: float,
    ) -> _FakeHTTPResponse:
        captured["url"] = request.full_url
        captured["timeout"] = timeout
        captured["body"] = json.loads(request.data.decode("utf-8"))
        return _FakeHTTPResponse(
            {
                "device_code": "device-code-123",
                "user_code": "8F43-6FCF",
                "verification_uri": "https://github.com/login/device",
                "interval": 5,
            }
        )

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)

    device_auth = backend.start_device_auth()

    assert captured["url"] == GITHUB_COPILOT_DEVICE_CODE_URL
    assert captured["body"] == {
        "client_id": GITHUB_COPILOT_CLIENT_ID,
        "scope": "read:user",
    }
    assert device_auth.device_auth_id == "device-code-123"
    assert device_auth.user_code == "8F43-6FCF"
    assert device_auth.verification_url == "https://github.com/login/device"
    assert device_auth.interval_seconds == 5


def test_poll_device_auth_returns_pending_for_authorization_pending(
    monkeypatch,
) -> None:
    backend = GitHubCopilotAuthBackend()

    def fake_urlopen(
        request: urllib.request.Request,
        timeout: float,
    ) -> _FakeHTTPResponse:
        del request, timeout
        return _FakeHTTPResponse({"error": "authorization_pending"})

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)

    result = backend.poll_device_auth(
        provider_id="copilot-main",
        device_auth=DeviceAuthChallenge(
            verification_url="https://github.com/login/device",
            user_code="8F43-6FCF",
            device_auth_id="device-code-123",
            interval_seconds=5,
        ),
    )

    assert result.status == AUTH_FLOW_STATUS_PENDING
    assert result.retry_after_seconds == 5
    assert result.session is None


def test_poll_device_auth_completes_session(monkeypatch) -> None:
    backend = GitHubCopilotAuthBackend()
    captured_bodies: list[dict[str, object]] = []

    def fake_urlopen(
        request: urllib.request.Request,
        timeout: float,
    ) -> _FakeHTTPResponse:
        del timeout
        captured_bodies.append(json.loads(request.data.decode("utf-8")))
        return _FakeHTTPResponse(
            {
                "access_token": "gho_test_token",
                "token_type": "bearer",
                "scope": "read:user",
            }
        )

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)

    result = backend.poll_device_auth(
        provider_id="copilot-main",
        device_auth=DeviceAuthChallenge(
            verification_url="https://github.com/login/device",
            user_code="8F43-6FCF",
            device_auth_id="device-code-123",
            interval_seconds=5,
        ),
    )

    assert captured_bodies == [
        {
            "client_id": GITHUB_COPILOT_CLIENT_ID,
            "device_code": "device-code-123",
            "grant_type": "urn:ietf:params:oauth:grant-type:device_code",
        }
    ]
    assert result.status == AUTH_FLOW_STATUS_COMPLETED
    assert result.session is not None
    assert result.session.backend == GITHUB_COPILOT_BACKEND_ID
    assert result.session.access_token == "gho_test_token"
    assert result.session.plan_type == "github_copilot"


def test_build_request_auth_keeps_runtime_request_url() -> None:
    backend = GitHubCopilotAuthBackend()

    request_auth = backend.build_request_auth(
        request_url=GITHUB_COPILOT_RESPONSES_URL,
        session=type("Session", (), {"access_token": "gho_test_token"})(),
    )

    assert request_auth.request_url == GITHUB_COPILOT_RESPONSES_URL
    assert request_auth.headers == {"Authorization": "Bearer gho_test_token"}


def test_refresh_session_is_not_supported() -> None:
    backend = GitHubCopilotAuthBackend()

    with pytest.raises(ValueError, match="do not support token refresh"):
        backend.refresh_session(
            type("Session", (), {"provider_id": "copilot-main"})(),
        )
