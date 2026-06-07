from __future__ import annotations

import json
import subprocess
import urllib.request
from typing import Any

import pytest

from pbi_agent.agent.tool_runtime import ToolExecutionBatch
from pbi_agent.auth.models import ApiKeyAuth
import pbi_agent.providers.auth_strategies as auth_strategies
from pbi_agent.config import (
    DEFAULT_GOOGLE_GCP_MODEL,
    DEFAULT_GOOGLE_GCP_RESPONSES_URL,
    DEFAULT_GOOGLE_GCP_SUB_AGENT_MODEL,
    DEFAULT_MAX_TOKENS,
    Settings,
)
from pbi_agent.models.messages import (
    CompletedResponse,
    ImageAttachment,
    TokenUsage,
    ToolCall,
    UserTurnInput,
)
from pbi_agent.providers.auth_strategies import (
    GOOGLE_GCP_ACCESS_TOKEN_TIMEOUT_ENV,
    google_gcp_auth,
    google_gcp_bearer_headers,
    google_gcp_bearer_token,
    run_gcloud_print_access_token,
)
from pbi_agent.providers.endpoints import google_gcp_endpoint_url
from pbi_agent.providers.google_gcp_provider import (
    GOOGLE_GCP_SHAPE_ENV,
    GoogleGcpProvider,
    google_gcp_shape_for_model,
)
from pbi_agent.providers.protocols.gemini_generate_content import (
    GeminiGenerateContentProtocol,
)
from pbi_agent.tools.catalog import ToolCatalog, ToolCatalogEntry
from pbi_agent.tools.types import ToolOutput, ToolResult, ToolSpec


def _make_settings(**overrides: object) -> Settings:
    defaults: dict[str, Any] = {
        "api_key": "",
        "provider": "google_gcp",
        "responses_url": DEFAULT_GOOGLE_GCP_RESPONSES_URL,
        "model": DEFAULT_GOOGLE_GCP_MODEL,
        "sub_agent_model": DEFAULT_GOOGLE_GCP_SUB_AGENT_MODEL,
        "max_tokens": DEFAULT_MAX_TOKENS,
        "max_retries": 0,
    }
    defaults.update(overrides)
    return Settings(**defaults)


def _request_json_body(request: urllib.request.Request) -> dict[str, Any]:
    data = request.data
    assert isinstance(data, bytes)
    parsed = json.loads(data.decode("utf-8"))
    assert isinstance(parsed, dict)
    return parsed


def test_google_gcp_settings_validate_allows_adc_without_api_key() -> None:
    settings = _make_settings(api_key="")

    settings.validate()


def test_google_gcp_explicit_api_key_is_used_as_bearer_token() -> None:
    settings = _make_settings(api_key="ya29.explicit-token")

    assert (
        google_gcp_bearer_token(
            settings,
            access_token_resolver=lambda: "adc-token",
        )
        == "ya29.explicit-token"
    )
    assert google_gcp_bearer_headers(settings) == {
        "Authorization": "Bearer ya29.explicit-token"
    }
    assert google_gcp_auth(settings).headers == {
        "Authorization": "Bearer ya29.explicit-token"
    }


def test_google_gcp_explicit_vertex_api_key_uses_api_key_header() -> None:
    settings = _make_settings(api_key="AQ.test-api-key")

    auth = google_gcp_auth(settings)

    assert auth.kind == "api_key"
    assert auth.headers == {"x-goog-api-key": "AQ.test-api-key"}


def test_google_gcp_api_key_can_be_skipped_for_standard_vertex_auth() -> None:
    settings = _make_settings(api_key="AQ.test-api-key")

    auth = google_gcp_auth(
        settings,
        access_token_resolver=lambda: "adc-token",
        allow_api_key=False,
    )

    assert auth.kind == "adc_bearer"
    assert auth.headers == {"Authorization": "Bearer adc-token"}


def test_google_gcp_forced_api_key_rejected_for_standard_vertex_auth(
    monkeypatch,
) -> None:
    settings = _make_settings(api_key="AQ.test-api-key")
    monkeypatch.setenv(auth_strategies.GOOGLE_GCP_AUTH_ENV, "api_key")

    with pytest.raises(ValueError, match="Gemini express-mode"):
        google_gcp_auth(
            settings,
            access_token_resolver=lambda: "adc-token",
            allow_api_key=False,
        )


def test_google_gcp_api_key_env_error_mentions_standard_vertex_auth() -> None:
    settings = _make_settings(api_key="")

    with pytest.raises(ValueError, match="Gemini express-mode"):
        google_gcp_auth(
            settings,
            access_token_resolver=lambda: "",
            env={"GOOGLE_API_KEY": "AIza-test-api-key"},
            allow_api_key=False,
        )


def test_google_gcp_api_key_env_uses_api_key_header() -> None:
    settings = _make_settings(
        api_key="env-token",
        auth=ApiKeyAuth(api_key="env-token", api_key_env="GOOGLE_API_KEY"),
    )

    auth = google_gcp_auth(settings)

    assert auth.kind == "api_key"
    assert auth.headers == {"x-goog-api-key": "env-token"}


def test_google_gcp_access_token_falls_back_to_gcloud(monkeypatch) -> None:
    def fake_run(
        command: list[str],
        *,
        check: bool,
        capture_output: bool,
        text: bool,
        timeout: float,
    ) -> subprocess.CompletedProcess[str]:
        assert command == [
            "gcloud",
            "auth",
            "application-default",
            "print-access-token",
        ]
        assert check is True
        assert capture_output is True
        assert text is True
        assert timeout in {1.5, 30.0}
        return subprocess.CompletedProcess(command, 0, stdout="adc-token\n")

    monkeypatch.setattr(auth_strategies.subprocess, "run", fake_run)

    assert run_gcloud_print_access_token(timeout=1.5) == "adc-token"
    assert google_gcp_bearer_token(_make_settings()) == "adc-token"


def test_google_gcp_access_token_timeout_can_be_overridden(monkeypatch) -> None:
    observed_timeout: float | None = None

    def fake_run(
        command: list[str],
        *,
        check: bool,
        capture_output: bool,
        text: bool,
        timeout: float,
    ) -> subprocess.CompletedProcess[str]:
        del check, capture_output, text
        nonlocal observed_timeout
        observed_timeout = timeout
        return subprocess.CompletedProcess(command, 0, stdout="adc-token\n")

    monkeypatch.setenv(GOOGLE_GCP_ACCESS_TOKEN_TIMEOUT_ENV, "45")
    monkeypatch.setattr(auth_strategies.subprocess, "run", fake_run)

    assert run_gcloud_print_access_token() == "adc-token"
    assert observed_timeout == 45.0


def test_google_gcp_access_token_reports_gcloud_failure(monkeypatch) -> None:
    def fake_run(
        command: list[str],
        *,
        check: bool,
        capture_output: bool,
        text: bool,
        timeout: float,
    ) -> subprocess.CompletedProcess[str]:
        del check, capture_output, text, timeout
        raise subprocess.CalledProcessError(
            1,
            command,
            stderr="not logged in",
        )

    monkeypatch.setattr(auth_strategies.subprocess, "run", fake_run)

    with pytest.raises(ValueError, match="not logged in"):
        run_gcloud_print_access_token()


@pytest.mark.parametrize(
    ("model", "expected_shape"),
    [
        ("gemini-2.5-flash", "gemini_generate_content"),
        ("google/gemini-2.5-flash", "gemini_generate_content"),
        ("xai/grok-4.20-reasoning", "openai_responses"),
        ("grok-4.20", "openai_responses"),
        ("xai/grok-4.1-fast-reasoning", "openai_responses"),
        ("xai/grok-4.1-fast-non-reasoning", "openai_responses"),
        ("grok-4.1-fast-non-reasoning", "openai_responses"),
        ("claude-sonnet-4-6", "anthropic_messages"),
        ("anthropic/claude-sonnet-4-6", "anthropic_messages"),
        ("deepseek-ai/deepseek-v3.1-maas", "openai_chat_completions"),
    ],
)
def test_google_gcp_shape_routing(model: str, expected_shape: str) -> None:
    assert google_gcp_shape_for_model(model, env={}) == expected_shape


def test_google_gcp_shape_routing_env_override() -> None:
    env = {GOOGLE_GCP_SHAPE_ENV: "openai_responses"}

    assert google_gcp_shape_for_model("gemini-2.5-flash", env=env) == (
        "openai_responses"
    )


def test_google_gcp_shape_routing_rejects_invalid_override() -> None:
    env = {GOOGLE_GCP_SHAPE_ENV: "nope"}

    with pytest.raises(ValueError, match=GOOGLE_GCP_SHAPE_ENV):
        google_gcp_shape_for_model("gemini-2.5-flash", env=env)


def test_google_gcp_endpoint_derives_gemini_global_url() -> None:
    url = google_gcp_endpoint_url(
        _make_settings(model="gemini-2.5-flash"),
        "gemini_generate_content",
        env={"GOOGLE_CLOUD_PROJECT": "demo-project"},
    )

    assert url == (
        "https://aiplatform.googleapis.com/v1/projects/demo-project/locations/"
        "global/publishers/google/models/gemini-2.5-flash:generateContent"
    )


def test_google_gcp_endpoint_strips_google_prefix_for_gemini_alias() -> None:
    url = google_gcp_endpoint_url(
        _make_settings(model="google/gemini-2.5-flash"),
        "gemini_generate_content",
        env={"GOOGLE_CLOUD_PROJECT": "demo-project"},
    )

    assert url == (
        "https://aiplatform.googleapis.com/v1/projects/demo-project/locations/"
        "global/publishers/google/models/gemini-2.5-flash:generateContent"
    )


def test_google_gcp_endpoint_derives_regional_chat_completions_url() -> None:
    url = google_gcp_endpoint_url(
        _make_settings(model="deepseek-ai/deepseek-v3.1-maas"),
        "openai_chat_completions",
        env={
            "GOOGLE_CLOUD_PROJECT_ID": "demo-project",
            "GOOGLE_CLOUD_REGION": "us-central1",
        },
    )

    assert url == (
        "https://us-central1-aiplatform.googleapis.com/v1/projects/"
        "demo-project/locations/us-central1/endpoints/openapi/chat/completions"
    )


def test_google_gcp_endpoint_uses_settings_project_and_location() -> None:
    url = google_gcp_endpoint_url(
        _make_settings(
            model="xai/grok-4.20-reasoning",
            google_cloud_project="saved-project",
            google_cloud_location="us-east5",
        ),
        "openai_responses",
        env={},
    )

    assert url == (
        "https://us-east5-aiplatform.googleapis.com/v1/projects/"
        "saved-project/locations/us-east5/endpoints/openapi/responses"
    )


def test_google_gcp_endpoint_supports_openapi_base_url() -> None:
    settings = _make_settings(
        responses_url=(
            "https://aiplatform.googleapis.com/v1/projects/demo-project/"
            "locations/global/endpoints/openapi"
        )
    )

    assert google_gcp_endpoint_url(settings, "openai_responses") == (
        "https://aiplatform.googleapis.com/v1/projects/demo-project/locations/"
        "global/endpoints/openapi/responses"
    )


def test_google_gcp_endpoint_supports_root_base_url_with_env() -> None:
    settings = _make_settings(responses_url="https://aiplatform.googleapis.com")

    assert google_gcp_endpoint_url(
        settings,
        "anthropic_messages",
        model="claude-sonnet-4-6",
        env={"GOOGLE_CLOUD_PROJECT": "demo-project"},
    ) == (
        "https://aiplatform.googleapis.com/v1/projects/demo-project/locations/"
        "global/publishers/anthropic/models/claude-sonnet-4-6:rawPredict"
    )


def test_google_gcp_endpoint_supports_version_base_url_with_env() -> None:
    settings = _make_settings(responses_url="https://aiplatform.googleapis.com/v1")

    assert google_gcp_endpoint_url(
        settings,
        "gemini_generate_content",
        model="gemini-2.5-flash",
        env={"GOOGLE_CLOUD_PROJECT": "demo-project"},
    ) == (
        "https://aiplatform.googleapis.com/v1/projects/demo-project/locations/"
        "global/publishers/google/models/gemini-2.5-flash:generateContent"
    )


def test_google_gcp_endpoint_can_defer_project_for_root_base_url() -> None:
    settings = _make_settings(responses_url="https://aiplatform.googleapis.com")

    assert (
        google_gcp_endpoint_url(
            settings,
            "gemini_generate_content",
            env={},
            require_project=False,
        )
        == ""
    )


def test_google_gcp_endpoint_preserves_exact_url() -> None:
    exact_url = (
        "https://aiplatform.googleapis.com/v1/projects/demo-project/locations/"
        "global/endpoints/openapi/responses"
    )
    settings = _make_settings(responses_url=exact_url)

    assert google_gcp_endpoint_url(settings, "openai_responses") == exact_url


def test_google_gcp_provider_connect_resolves_endpoint_and_auth_headers(
    monkeypatch,
) -> None:
    monkeypatch.setenv("GOOGLE_CLOUD_PROJECT", "demo-project")
    provider = GoogleGcpProvider(
        _make_settings(api_key="", model="gemini-2.5-flash"),
        access_token_resolver=lambda: "adc-token",
    )

    provider.connect()

    assert provider.endpoint_url == (
        "https://aiplatform.googleapis.com/v1/projects/demo-project/locations/"
        "global/publishers/google/models/gemini-2.5-flash:generateContent"
    )
    assert provider.auth_headers["Authorization"] == "Bearer adc-token"


def test_google_gcp_provider_connect_uses_saved_project_and_adc_for_xai(
    monkeypatch,
) -> None:
    monkeypatch.delenv("GOOGLE_CLOUD_PROJECT", raising=False)
    monkeypatch.delenv("GOOGLE_CLOUD_PROJECT_ID", raising=False)
    provider = GoogleGcpProvider(
        _make_settings(
            api_key="AQ.test-api-key",
            model="xai/grok-4.1-fast-non-reasoning",
            google_cloud_project="saved-project",
            google_cloud_location="us-east5",
        ),
        access_token_resolver=lambda: "adc-token",
    )

    provider.connect()

    assert provider.endpoint_url == (
        "https://us-east5-aiplatform.googleapis.com/v1/projects/saved-project/"
        "locations/us-east5/endpoints/openapi/responses"
    )
    assert provider.auth_headers["Authorization"] == "Bearer adc-token"
    assert "x-goog-api-key" not in provider.auth_headers


def test_google_gcp_provider_connect_skips_api_key_env_for_xai(
    monkeypatch,
) -> None:
    monkeypatch.delenv("GOOGLE_CLOUD_PROJECT", raising=False)
    monkeypatch.delenv("GOOGLE_CLOUD_PROJECT_ID", raising=False)
    monkeypatch.setenv("GOOGLE_API_KEY", "AIza-test-api-key")
    provider = GoogleGcpProvider(
        _make_settings(
            api_key="",
            model="xai/grok-4.1-fast-non-reasoning",
            google_cloud_project="saved-project",
            google_cloud_location="global",
        ),
        access_token_resolver=lambda: "adc-token",
    )

    provider.connect()

    assert provider.endpoint_url == (
        "https://aiplatform.googleapis.com/v1/projects/saved-project/"
        "locations/global/endpoints/openapi/responses"
    )
    assert provider.auth_headers["Authorization"] == "Bearer adc-token"
    assert "x-goog-api-key" not in provider.auth_headers


def test_google_gcp_adc_bearer_is_reused_until_expiry(
    monkeypatch,
    display_spy,
    make_http_response,
) -> None:
    monkeypatch.setenv("GOOGLE_CLOUD_PROJECT", "demo-project")
    resolver_calls = 0
    authorizations: list[str | None] = []

    def resolve_token() -> str:
        nonlocal resolver_calls
        resolver_calls += 1
        return "adc-token"

    def fake_urlopen(request: urllib.request.Request, timeout: float):
        del timeout
        authorizations.append(request.get_header("Authorization"))
        return make_http_response(
            {
                "responseId": f"gemini_resp_{len(authorizations)}",
                "candidates": [
                    {"content": {"role": "model", "parts": [{"text": "ok"}]}}
                ],
            }
        )

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    provider = GoogleGcpProvider(
        _make_settings(api_key="", model="gemini-2.5-flash"),
        access_token_resolver=resolve_token,
        tool_catalog=ToolCatalog(),
    )

    for prompt in ("first", "second"):
        provider.request_turn(
            user_message=prompt,
            display=display_spy,
            session_usage=TokenUsage(),
            turn_usage=TokenUsage(),
        )

    assert resolver_calls == 1
    assert authorizations == ["Bearer adc-token", "Bearer adc-token"]


def test_google_gcp_adc_bearer_refreshes_after_expiry_error(
    monkeypatch,
    display_spy,
    make_http_error,
    make_http_response,
) -> None:
    monkeypatch.setenv("GOOGLE_CLOUD_PROJECT", "demo-project")
    tokens = iter(["old-token", "new-token"])
    authorizations: list[str | None] = []
    expiry_error = make_http_error(
        code=401,
        body=json.dumps(
            {
                "error": {
                    "status": "UNAUTHENTICATED",
                    "message": "OAuth 2 access token expired.",
                    "details": [{"reason": "ACCESS_TOKEN_EXPIRED"}],
                }
            }
        ),
    )

    def fake_urlopen(request: urllib.request.Request, timeout: float):
        del timeout
        authorizations.append(request.get_header("Authorization"))
        if len(authorizations) == 1:
            raise expiry_error
        return make_http_response(
            {
                "responseId": "gemini_resp_refreshed",
                "candidates": [
                    {"content": {"role": "model", "parts": [{"text": "ok"}]}}
                ],
            }
        )

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    provider = GoogleGcpProvider(
        _make_settings(api_key="", model="gemini-2.5-flash", max_retries=0),
        access_token_resolver=lambda: next(tokens),
        tool_catalog=ToolCatalog(),
    )

    result = provider.request_turn(
        user_message="hello",
        display=display_spy,
        session_usage=TokenUsage(),
        turn_usage=TokenUsage(),
    )

    assert result.response_id == "gemini_resp_refreshed"
    assert authorizations == ["Bearer old-token", "Bearer new-token"]


def test_google_gcp_gemini_request_uses_vertex_url_auth_and_body(
    monkeypatch,
    display_spy,
    make_http_response,
) -> None:
    monkeypatch.setenv("GOOGLE_CLOUD_PROJECT", "demo-project")
    seen: dict[str, Any] = {}

    def fake_urlopen(request: urllib.request.Request, timeout: float):
        seen["url"] = request.full_url
        seen["authorization"] = request.get_header("Authorization")
        seen["content_type"] = request.get_header("Content-type")
        seen["timeout"] = timeout
        seen["body"] = _request_json_body(request)
        return make_http_response(
            {
                "responseId": "gemini_resp_1",
                "modelVersion": "gemini-2.5-flash-001",
                "candidates": [
                    {"content": {"role": "model", "parts": [{"text": "ok"}]}}
                ],
            }
        )

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)

    provider = GoogleGcpProvider(
        _make_settings(api_key="explicit-token", model="gemini-2.5-flash"),
        system_prompt="be concise",
        tool_catalog=ToolCatalog(),
    )

    provider.request_turn(
        user_message="hello",
        display=display_spy,
        session_usage=TokenUsage(),
        turn_usage=TokenUsage(),
    )

    assert seen["url"] == (
        "https://aiplatform.googleapis.com/v1/projects/demo-project/locations/"
        "global/publishers/google/models/gemini-2.5-flash:generateContent"
    )
    assert seen["authorization"] == "Bearer explicit-token"
    assert seen["content_type"] == "application/json"
    assert seen["timeout"] == 3600.0
    assert seen["body"] == {
        "contents": [{"role": "user", "parts": [{"text": "hello"}]}],
        "generationConfig": {"maxOutputTokens": DEFAULT_MAX_TOKENS},
        "systemInstruction": {"parts": [{"text": "be concise"}]},
    }


def test_google_gcp_gemini_api_key_uses_express_url_and_header(
    monkeypatch,
    display_spy,
    make_http_response,
) -> None:
    monkeypatch.delenv("GOOGLE_CLOUD_PROJECT", raising=False)
    monkeypatch.delenv("GOOGLE_CLOUD_PROJECT_ID", raising=False)
    seen: dict[str, Any] = {}

    def fake_urlopen(request: urllib.request.Request, timeout: float):
        del timeout
        seen["url"] = request.full_url
        seen["authorization"] = request.get_header("Authorization")
        seen["api_key"] = request.get_header("X-goog-api-key")
        seen["body"] = _request_json_body(request)
        return make_http_response(
            {
                "responseId": "gemini_resp_api_key",
                "modelVersion": "gemini-2.5-flash-lite",
                "candidates": [
                    {"content": {"role": "model", "parts": [{"text": "ok"}]}}
                ],
            }
        )

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)

    provider = GoogleGcpProvider(
        _make_settings(
            api_key="AQ.test-api-key",
            model="gemini-2.5-flash-lite",
            google_cloud_project="saved-project",
        ),
        tool_catalog=ToolCatalog(),
    )

    provider.request_turn(
        user_message="hello",
        display=display_spy,
        session_usage=TokenUsage(),
        turn_usage=TokenUsage(),
    )

    assert seen["url"] == (
        "https://aiplatform.googleapis.com/v1beta1/publishers/google/models/"
        "gemini-2.5-flash-lite:generateContent"
    )
    assert seen["authorization"] is None
    assert seen["api_key"] == "AQ.test-api-key"
    assert seen["body"]["contents"] == [{"role": "user", "parts": [{"text": "hello"}]}]


def test_google_gcp_gemini_api_key_auth_error_falls_back_to_adc_vertex(
    monkeypatch,
    display_spy,
    make_http_error,
    make_http_response,
) -> None:
    monkeypatch.delenv("GOOGLE_CLOUD_PROJECT", raising=False)
    monkeypatch.delenv("GOOGLE_CLOUD_PROJECT_ID", raising=False)
    seen: list[dict[str, str | None]] = []
    auth_error = make_http_error(
        code=401,
        body=json.dumps(
            {
                "error": {
                    "code": 401,
                    "status": "UNAUTHENTICATED",
                    "message": (
                        "Request had invalid authentication credentials. Expected "
                        "OAuth 2 access token, login cookie or other valid "
                        "authentication credential."
                    ),
                    "details": [{"reason": "ACCESS_TOKEN_TYPE_UNSUPPORTED"}],
                }
            }
        ),
    )

    def fake_urlopen(request: urllib.request.Request, timeout: float):
        del timeout
        seen.append(
            {
                "url": request.full_url,
                "authorization": request.get_header("Authorization"),
                "api_key": request.get_header("X-goog-api-key"),
            }
        )
        if len(seen) == 1:
            raise auth_error
        return make_http_response(
            {
                "responseId": "gemini_resp_adc",
                "modelVersion": "gemini-3.5-flash",
                "candidates": [
                    {"content": {"role": "model", "parts": [{"text": "ok"}]}}
                ],
            }
        )

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    provider = GoogleGcpProvider(
        _make_settings(
            api_key="AQ.test-api-key",
            model="gemini-3.5-flash",
            google_cloud_project="saved-project",
        ),
        access_token_resolver=lambda: "adc-token",
        tool_catalog=ToolCatalog(),
    )

    result = provider.request_turn(
        user_message="hello",
        display=display_spy,
        session_usage=TokenUsage(),
        turn_usage=TokenUsage(),
    )

    assert result.response_id == "gemini_resp_adc"
    assert seen == [
        {
            "url": (
                "https://aiplatform.googleapis.com/v1beta1/publishers/google/"
                "models/gemini-3.5-flash:generateContent"
            ),
            "authorization": None,
            "api_key": "AQ.test-api-key",
        },
        {
            "url": (
                "https://aiplatform.googleapis.com/v1/projects/saved-project/"
                "locations/global/publishers/google/models/"
                "gemini-3.5-flash:generateContent"
            ),
            "authorization": "Bearer adc-token",
            "api_key": None,
        },
    ]


def test_google_gcp_runtime_settings_preserve_same_shape_history(
    monkeypatch,
    display_spy,
    make_http_response,
) -> None:
    monkeypatch.setenv("GOOGLE_CLOUD_PROJECT", "demo-project")
    requests: list[dict[str, Any]] = []

    def fake_urlopen(request: urllib.request.Request, timeout: float):
        del timeout
        requests.append(
            {
                "url": request.full_url,
                "body": _request_json_body(request),
            }
        )
        return make_http_response(
            {
                "responseId": f"gemini_resp_{len(requests)}",
                "modelVersion": "gemini-2.5-flash-001",
                "candidates": [
                    {"content": {"role": "model", "parts": [{"text": "ok"}]}}
                ],
            }
        )

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    provider = GoogleGcpProvider(
        _make_settings(api_key="explicit-token", model="gemini-2.5-flash"),
        tool_catalog=ToolCatalog(),
    )

    provider.request_turn(
        user_message="first",
        display=display_spy,
        session_usage=TokenUsage(),
        turn_usage=TokenUsage(),
    )
    provider.set_runtime_settings(
        _make_settings(
            api_key="explicit-token",
            model="gemini-2.5-pro",
            max_tokens=123,
        )
    )
    provider.request_turn(
        user_message="second",
        display=display_spy,
        session_usage=TokenUsage(),
        turn_usage=TokenUsage(),
    )

    assert requests[1]["url"] == (
        "https://aiplatform.googleapis.com/v1/projects/demo-project/locations/"
        "global/publishers/google/models/gemini-2.5-pro:generateContent"
    )
    assert requests[1]["body"]["contents"] == [
        {"role": "user", "parts": [{"text": "first"}]},
        {"role": "model", "parts": [{"text": "ok"}]},
        {"role": "user", "parts": [{"text": "second"}]},
    ]
    assert requests[1]["body"]["generationConfig"] == {"maxOutputTokens": 123}


def test_google_gcp_gemini_response_records_text_usage_and_display(
    monkeypatch,
    display_spy,
    make_http_response,
) -> None:
    monkeypatch.setenv("GOOGLE_CLOUD_PROJECT", "demo-project")

    def fake_urlopen(request: urllib.request.Request, timeout: float):
        del request, timeout
        return make_http_response(
            {
                "responseId": "gemini_resp_2",
                "modelVersion": "gemini-2.5-pro-001",
                "usageMetadata": {
                    "promptTokenCount": 11,
                    "candidatesTokenCount": 7,
                    "totalTokenCount": 21,
                    "thoughtsTokenCount": 3,
                    "cachedContentTokenCount": 2,
                },
                "candidates": [
                    {
                        "content": {
                            "role": "model",
                            "parts": [
                                {"text": "hidden reasoning", "thought": True},
                                {"text": "Hello"},
                                {"text": "world"},
                            ],
                        }
                    }
                ],
            }
        )

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    provider = GoogleGcpProvider(
        _make_settings(api_key="explicit-token", model="gemini-2.5-pro"),
        tool_catalog=ToolCatalog(),
    )
    session_usage = TokenUsage()
    turn_usage = TokenUsage()

    result = provider.request_turn(
        user_message="hello",
        display=display_spy,
        session_usage=session_usage,
        turn_usage=turn_usage,
    )

    assert result.response_id == "gemini_resp_2"
    assert result.text == "Hello\n\nworld"
    assert result.reasoning_content == "hidden reasoning"
    assert result.usage.input_tokens == 11
    assert result.usage.cached_input_tokens == 2
    assert result.usage.output_tokens == 7
    assert result.usage.reasoning_tokens == 3
    assert result.usage.provider_total_tokens == 21
    assert result.usage.context_tokens == 21
    assert result.usage.model == "gemini-2.5-pro-001"
    assert session_usage.snapshot().total_tokens == 21
    assert turn_usage.snapshot().total_tokens == 21
    assert display_spy.thinking_calls[0]["text"] == "hidden reasoning"
    assert display_spy.markdown_calls == ["Hello\n\nworld"]


def test_google_gcp_gemini_function_call_and_tool_result_shape() -> None:
    protocol = GeminiGenerateContentProtocol(
        _make_settings(model="gemini-2.5-flash"),
        system_prompt="",
        tool_catalog=ToolCatalog(),
    )

    result = protocol.parse_response(
        {
            "candidates": [
                {
                    "content": {
                        "role": "model",
                        "parts": [
                            {
                                "functionCall": {
                                    "name": "get_weather",
                                    "args": {"city": "Paris"},
                                }
                            }
                        ],
                    }
                }
            ]
        }
    )

    assert len(result.function_calls) == 1
    call = result.function_calls[0]
    assert call.call_id == "gemini_call_0_0"
    assert call.name == "get_weather"
    assert call.arguments == {"city": "Paris"}

    assert protocol.serialize_tool_result(
        ToolResult(
            call_id=call.call_id,
            output_json='{"temperature":"20C"}',
        ),
        call,
    ) == {
        "role": "user",
        "parts": [
            {
                "functionResponse": {
                    "name": "get_weather",
                    "response": {
                        "call_id": "gemini_call_0_0",
                        "output": {"temperature": "20C"},
                    },
                }
            }
        ],
    }


def test_google_gcp_gemini_execute_tool_calls_serializes_function_response(
    monkeypatch,
    display_spy,
) -> None:
    def handler(arguments, context):
        del arguments, context
        return ToolOutput(result={"temperature": "20C"})

    catalog = ToolCatalog(
        {
            "get_weather": ToolCatalogEntry(
                spec=ToolSpec(
                    name="get_weather",
                    description="Get weather.",
                    parameters_schema={
                        "type": "object",
                        "properties": {"city": {"type": "string"}},
                        "required": ["city"],
                    },
                ),
                handler=handler,
            )
        }
    )
    provider = GoogleGcpProvider(
        _make_settings(api_key="explicit-token", model="gemini-2.5-flash"),
        tool_catalog=catalog,
    )

    batch = ToolExecutionBatch(
        results=[
            ToolResult(
                call_id="gemini_call_0_0",
                output_json='{"temperature":"20C"}',
            )
        ],
        had_errors=False,
    )
    monkeypatch.setattr(
        "pbi_agent.providers.google_gcp_provider._execute_tool_calls",
        lambda calls, max_workers, context=None, on_result=None: (
            (
                [on_result(call, result) for call, result in zip(calls, batch.results)]
                if on_result is not None
                else None
            )
            and batch
        ),
    )

    tool_result_items, had_errors = provider.execute_tool_calls(
        CompletedResponse(
            response_id="gemini_resp",
            text="",
            function_calls=[
                ToolCall(
                    call_id="gemini_call_0_0",
                    name="get_weather",
                    arguments={"city": "Paris"},
                )
            ],
        ),
        max_workers=1,
        display=display_spy,
        session_usage=TokenUsage(),
        turn_usage=TokenUsage(),
    )

    assert had_errors is False
    assert tool_result_items == [
        {
            "role": "user",
            "parts": [
                {
                    "functionResponse": {
                        "name": "get_weather",
                        "response": {
                            "call_id": "gemini_call_0_0",
                            "output": {"temperature": "20C"},
                        },
                    }
                }
            ],
        }
    ]
    assert display_spy.function_counts == [1]
    assert display_spy.function_results == [
        {
            "name": "get_weather",
            "success": True,
            "call_id": "gemini_call_0_0",
            "arguments": {"city": "Paris"},
        }
    ]


def test_google_gcp_gemini_image_input_uses_inline_data(
    monkeypatch,
    display_spy,
    make_http_response,
) -> None:
    monkeypatch.setenv("GOOGLE_CLOUD_PROJECT", "demo-project")
    seen: dict[str, Any] = {}

    def fake_urlopen(request: urllib.request.Request, timeout: float):
        del timeout
        seen["body"] = _request_json_body(request)
        return make_http_response(
            {
                "responseId": "gemini_resp_image",
                "candidates": [
                    {"content": {"role": "model", "parts": [{"text": "a cat"}]}}
                ],
            }
        )

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)

    provider = GoogleGcpProvider(
        _make_settings(api_key="explicit-token", model="gemini-2.5-flash"),
        tool_catalog=ToolCatalog(),
    )

    provider.request_turn(
        user_input=UserTurnInput(
            text="describe",
            images=[
                ImageAttachment(
                    path="cat.png",
                    mime_type="image/png",
                    data_base64="aW1hZ2UtYnl0ZXM=",
                    byte_count=11,
                )
            ],
        ),
        display=display_spy,
        session_usage=TokenUsage(),
        turn_usage=TokenUsage(),
    )

    assert seen["body"]["contents"] == [
        {
            "role": "user",
            "parts": [
                {"text": "describe"},
                {
                    "inlineData": {
                        "mimeType": "image/png",
                        "data": "aW1hZ2UtYnl0ZXM=",
                    }
                },
            ],
        }
    ]


def test_google_gcp_openai_chat_request_uses_maas_url_auth_stream_and_body(
    monkeypatch,
    display_spy,
    make_http_response,
) -> None:
    monkeypatch.delenv(GOOGLE_GCP_SHAPE_ENV, raising=False)
    monkeypatch.setenv("GOOGLE_CLOUD_PROJECT", "demo-project")
    monkeypatch.setenv("GOOGLE_CLOUD_PROJECT_ID", "demo-project")
    monkeypatch.setenv("GOOGLE_CLOUD_LOCATION", "us-central1")
    monkeypatch.setenv("GOOGLE_CLOUD_REGION", "us-central1")
    seen: dict[str, Any] = {}

    def fake_urlopen(request: urllib.request.Request, timeout: float):
        seen["url"] = request.full_url
        seen["authorization"] = request.get_header("Authorization")
        seen["content_type"] = request.get_header("Content-type")
        seen["timeout"] = timeout
        seen["body"] = _request_json_body(request)
        return make_http_response(
            {
                "id": "chatcmpl-gcp-1",
                "model": "deepseek-ai/deepseek-v3.1-maas",
                "choices": [{"message": {"role": "assistant", "content": "ok"}}],
                "usage": {
                    "prompt_tokens": 5,
                    "completion_tokens": 2,
                    "total_tokens": 7,
                },
            }
        )

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    provider = GoogleGcpProvider(
        _make_settings(
            api_key="",
            model="deepseek-ai/deepseek-v3.1-maas",
            max_tokens=123,
        ),
        system_prompt="be concise",
        access_token_resolver=lambda: "adc-token",
        tool_catalog=ToolCatalog(),
    )

    assert provider.shape_name == "openai_chat_completions"
    provider.request_turn(
        user_message="hello",
        display=display_spy,
        session_usage=TokenUsage(),
        turn_usage=TokenUsage(),
    )

    assert seen["url"] == (
        "https://us-central1-aiplatform.googleapis.com/v1/projects/"
        "demo-project/locations/us-central1/endpoints/openapi/chat/completions"
    )
    assert seen["authorization"] == "Bearer adc-token"
    assert seen["content_type"] == "application/json"
    assert seen["timeout"] == 3600.0
    assert seen["body"] == {
        "model": "deepseek-ai/deepseek-v3.1-maas",
        "messages": [
            {"role": "system", "content": "be concise"},
            {"role": "user", "content": "hello"},
        ],
        "max_tokens": 123,
        "tools": [],
        "tool_choice": "auto",
        "stream": False,
    }


def test_google_gcp_openai_chat_response_records_text_usage_and_display(
    monkeypatch,
    display_spy,
    make_http_response,
) -> None:
    monkeypatch.delenv(GOOGLE_GCP_SHAPE_ENV, raising=False)
    monkeypatch.setenv("GOOGLE_CLOUD_PROJECT", "demo-project")

    def fake_urlopen(request: urllib.request.Request, timeout: float):
        del request, timeout
        return make_http_response(
            {
                "id": "chatcmpl-gcp-2",
                "model": "deepseek-ai/deepseek-v3.1-maas",
                "choices": [
                    {
                        "message": {
                            "role": "assistant",
                            "content": [
                                {"type": "text", "text": "Hello "},
                                {"type": "output_text", "text": "world"},
                            ],
                        }
                    }
                ],
                "usage": {
                    "prompt_tokens": 11,
                    "completion_tokens": 7,
                    "total_tokens": 18,
                    "completion_tokens_details": {"reasoning_tokens": 3},
                },
            }
        )

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    provider = GoogleGcpProvider(
        _make_settings(
            api_key="explicit-token",
            model="deepseek-ai/deepseek-v3.1-maas",
        ),
        tool_catalog=ToolCatalog(),
    )
    session_usage = TokenUsage()
    turn_usage = TokenUsage()

    result = provider.request_turn(
        user_message="hello",
        display=display_spy,
        session_usage=session_usage,
        turn_usage=turn_usage,
    )

    assert result.response_id == "chatcmpl-gcp-2"
    assert result.text == "Hello world"
    assert result.usage.input_tokens == 11
    assert result.usage.output_tokens == 7
    assert result.usage.reasoning_tokens == 3
    assert result.usage.context_tokens == 18
    assert result.usage.model == "deepseek-ai/deepseek-v3.1-maas"
    assert session_usage.snapshot().total_tokens == 18
    assert turn_usage.snapshot().total_tokens == 18
    assert display_spy.markdown_calls == ["Hello world"]


def test_google_gcp_openai_chat_tool_calls_execute_and_serialize_messages(
    monkeypatch,
    display_spy,
    make_http_response,
) -> None:
    monkeypatch.delenv(GOOGLE_GCP_SHAPE_ENV, raising=False)
    monkeypatch.setenv("GOOGLE_CLOUD_PROJECT", "demo-project")

    def fake_urlopen(request: urllib.request.Request, timeout: float):
        del request, timeout
        return make_http_response(
            {
                "id": "chatcmpl-gcp-tools",
                "model": "deepseek-ai/deepseek-v3.1-maas",
                "choices": [
                    {
                        "message": {
                            "role": "assistant",
                            "content": "",
                            "tool_calls": [
                                {
                                    "id": "call_weather",
                                    "type": "function",
                                    "function": {
                                        "name": "get_weather",
                                        "arguments": '{"city":"Paris"}',
                                    },
                                }
                            ],
                        }
                    }
                ],
            }
        )

    def handler(arguments, context):
        del context
        assert arguments == {"city": "Paris"}
        return ToolOutput(result={"temperature": "20C"})

    catalog = ToolCatalog(
        {
            "get_weather": ToolCatalogEntry(
                spec=ToolSpec(
                    name="get_weather",
                    description="Get weather.",
                    parameters_schema={
                        "type": "object",
                        "properties": {"city": {"type": "string"}},
                        "required": ["city"],
                    },
                ),
                handler=handler,
            )
        }
    )
    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    provider = GoogleGcpProvider(
        _make_settings(
            api_key="explicit-token",
            model="deepseek-ai/deepseek-v3.1-maas",
        ),
        tool_catalog=catalog,
    )

    response = provider.request_turn(
        user_message="weather?",
        display=display_spy,
        session_usage=TokenUsage(),
        turn_usage=TokenUsage(),
    )

    assert len(response.function_calls) == 1
    assert response.function_calls[0].call_id == "call_weather"
    assert response.function_calls[0].name == "get_weather"
    assert response.function_calls[0].arguments == {"city": "Paris"}

    tool_result_items, had_errors = provider.execute_tool_calls(
        response,
        max_workers=1,
        display=display_spy,
        session_usage=TokenUsage(),
        turn_usage=TokenUsage(),
    )

    assert had_errors is False
    assert len(tool_result_items) == 1
    tool_result = tool_result_items[0]
    assert tool_result["role"] == "tool"
    assert tool_result["tool_call_id"] == "call_weather"
    assert json.loads(str(tool_result["content"])) == {
        "ok": True,
        "result": {"temperature": "20C"},
    }
    assert display_spy.function_counts == [1]
    assert display_spy.function_results == [
        {
            "name": "get_weather",
            "success": True,
            "call_id": "call_weather",
            "arguments": {"city": "Paris"},
        }
    ]


def test_google_gcp_openai_responses_request_uses_vertex_url_auth_and_body(
    monkeypatch,
    display_spy,
    make_http_response,
) -> None:
    monkeypatch.delenv(GOOGLE_GCP_SHAPE_ENV, raising=False)
    monkeypatch.setenv("GOOGLE_CLOUD_PROJECT", "demo-project")
    seen: dict[str, Any] = {}

    def fake_urlopen(request: urllib.request.Request, timeout: float):
        seen["url"] = request.full_url
        seen["authorization"] = request.get_header("Authorization")
        seen["content_type"] = request.get_header("Content-type")
        seen["timeout"] = timeout
        seen["body"] = _request_json_body(request)
        return make_http_response(
            {
                "id": "resp-gcp-1",
                "model": "xai/grok-4.20-reasoning",
                "output": [
                    {
                        "type": "message",
                        "role": "assistant",
                        "content": [{"type": "output_text", "text": "ok"}],
                    }
                ],
            }
        )

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    provider = GoogleGcpProvider(
        _make_settings(
            api_key="",
            model="xai/grok-4.20-reasoning",
            max_tokens=123,
        ),
        system_prompt="be concise",
        access_token_resolver=lambda: "adc-token",
        tool_catalog=ToolCatalog(),
    )

    assert provider.shape_name == "openai_responses"
    provider.request_turn(
        user_message="hello",
        display=display_spy,
        session_usage=TokenUsage(),
        turn_usage=TokenUsage(),
    )

    assert seen["url"] == (
        "https://aiplatform.googleapis.com/v1/projects/demo-project/locations/"
        "global/endpoints/openapi/responses"
    )
    assert seen["authorization"] == "Bearer adc-token"
    assert seen["content_type"] == "application/json"
    assert seen["timeout"] == 3600.0
    assert seen["body"] == {
        "model": "xai/grok-4.20-reasoning",
        "input": "hello",
        "max_output_tokens": 123,
        "stream": False,
        "store": False,
        "instructions": "be concise",
    }
    assert "previous_response_id" not in seen["body"]


def test_google_gcp_openai_responses_supports_grok_41_fast_and_sanitizes_tools(
    monkeypatch,
    display_spy,
    make_http_response,
) -> None:
    monkeypatch.delenv(GOOGLE_GCP_SHAPE_ENV, raising=False)
    monkeypatch.setenv("GOOGLE_CLOUD_PROJECT", "demo-project")
    seen: dict[str, Any] = {}

    def fake_urlopen(request: urllib.request.Request, timeout: float):
        del timeout
        seen["url"] = request.full_url
        seen["body"] = _request_json_body(request)
        return make_http_response(
            {
                "id": "resp-gcp-grok-41-fast",
                "model": "xai/grok-4.1-fast-non-reasoning",
                "output": [
                    {
                        "type": "message",
                        "role": "assistant",
                        "content": [{"type": "output_text", "text": "ok"}],
                    }
                ],
            }
        )

    def handler(arguments, context):
        del arguments, context
        return ToolOutput(result={})

    catalog = ToolCatalog(
        {
            "lookup": ToolCatalogEntry(
                spec=ToolSpec(
                    name="lookup",
                    description="Lookup a target.",
                    parameters_schema={
                        "type": "object",
                        "properties": {
                            "target": {
                                "description": "Lookup target.",
                                "oneOf": [
                                    {"type": "string"},
                                    {
                                        "type": "array",
                                        "items": {"type": "string"},
                                    },
                                ],
                            }
                        },
                        "required": ["target"],
                        "additionalProperties": False,
                    },
                ),
                handler=handler,
            )
        }
    )
    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    provider = GoogleGcpProvider(
        _make_settings(
            api_key="",
            model="xai/grok-4.1-fast-non-reasoning",
            max_tokens=123,
        ),
        system_prompt="be concise",
        access_token_resolver=lambda: "adc-token",
        tool_catalog=catalog,
    )

    assert provider.shape_name == "openai_responses"
    provider.request_turn(
        user_message="hello",
        display=display_spy,
        session_usage=TokenUsage(),
        turn_usage=TokenUsage(),
    )

    assert seen["url"] == (
        "https://aiplatform.googleapis.com/v1/projects/demo-project/locations/"
        "global/endpoints/openapi/responses"
    )
    body = seen["body"]
    assert body["model"] == "xai/grok-4.1-fast-non-reasoning"
    assert body["input"] == "hello"
    assert body["max_output_tokens"] == 123
    assert body["stream"] is False
    assert body["tools"][0]["parameters"]["properties"]["target"] == {
        "description": (
            "Lookup target. Accepted value shapes: string, array of string."
        )
    }
    assert "oneOf" not in json.dumps(body)


def test_google_gcp_openai_responses_raises_model_error_payload(
    monkeypatch,
    display_spy,
    make_http_response,
) -> None:
    monkeypatch.delenv(GOOGLE_GCP_SHAPE_ENV, raising=False)
    monkeypatch.setenv("GOOGLE_CLOUD_PROJECT", "demo-project")

    def fake_urlopen(request: urllib.request.Request, timeout: float):
        del request, timeout
        return make_http_response(
            {
                "code": "Client specified an invalid argument",
                "error": "Invalid arguments passed to the model.",
                "id": "CMglaqCMIuWMvdIP77KO8A4",
                "model": "xai/grok-4.20-reasoning",
                "store": False,
            }
        )

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    provider = GoogleGcpProvider(
        _make_settings(
            api_key="explicit-token",
            model="xai/grok-4.20-reasoning",
            max_retries=0,
        ),
        tool_catalog=ToolCatalog(),
    )

    with pytest.raises(RuntimeError, match="Invalid arguments passed to the model"):
        provider.request_turn(
            user_message="hello",
            display=display_spy,
            session_usage=TokenUsage(),
            turn_usage=TokenUsage(),
        )


def test_google_gcp_openai_responses_second_turn_replays_client_history(
    monkeypatch,
    display_spy,
    make_http_response,
) -> None:
    monkeypatch.delenv(GOOGLE_GCP_SHAPE_ENV, raising=False)
    monkeypatch.setenv("GOOGLE_CLOUD_PROJECT", "demo-project")
    bodies: list[dict[str, Any]] = []

    responses = iter(
        [
            {
                "id": "resp-gcp-first",
                "model": "xai/grok-4.20-reasoning",
                "output": [
                    {
                        "id": "msg-first",
                        "type": "message",
                        "role": "assistant",
                        "status": "completed",
                        "content": [
                            {
                                "type": "output_text",
                                "text": "hi",
                                "logprobs": [],
                            }
                        ],
                    }
                ],
            },
            {
                "id": "resp-gcp-second",
                "model": "xai/grok-4.20-reasoning",
                "output": [
                    {
                        "type": "message",
                        "role": "assistant",
                        "content": [{"type": "output_text", "text": "again"}],
                    }
                ],
            },
        ]
    )

    def fake_urlopen(request: urllib.request.Request, timeout: float):
        del timeout
        bodies.append(_request_json_body(request))
        return make_http_response(next(responses))

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    provider = GoogleGcpProvider(
        _make_settings(
            api_key="explicit-token",
            model="xai/grok-4.20-reasoning",
        ),
        system_prompt="be concise",
        tool_catalog=ToolCatalog(),
    )

    provider.request_turn(
        user_message="hello",
        display=display_spy,
        session_usage=TokenUsage(),
        turn_usage=TokenUsage(),
    )
    provider.request_turn(
        user_message="continue",
        display=display_spy,
        session_usage=TokenUsage(),
        turn_usage=TokenUsage(),
    )

    assert bodies[0]["input"] == "hello"
    assert bodies[1]["input"] == [
        {"role": "user", "content": "hello"},
        {
            "type": "message",
            "role": "assistant",
            "content": [{"type": "output_text", "text": "hi"}],
        },
        {"role": "user", "content": "continue"},
    ]
    assert bodies[0]["store"] is False
    assert bodies[1]["store"] is False
    assert "previous_response_id" not in bodies[0]
    assert "previous_response_id" not in bodies[1]


def test_google_gcp_openai_responses_records_text_usage_reasoning_and_display(
    monkeypatch,
    display_spy,
    make_http_response,
) -> None:
    monkeypatch.delenv(GOOGLE_GCP_SHAPE_ENV, raising=False)
    monkeypatch.setenv("GOOGLE_CLOUD_PROJECT", "demo-project")

    def fake_urlopen(request: urllib.request.Request, timeout: float):
        del request, timeout
        return make_http_response(
            {
                "id": "resp-gcp-usage",
                "model": "xai/grok-4.20-reasoning",
                "reasoning": {"effort": "medium", "summary": "detailed"},
                "usage": {
                    "input_tokens": 10,
                    "input_tokens_details": {"cached_tokens": 4},
                    "output_tokens": 5,
                    "output_tokens_details": {"reasoning_tokens": 2},
                    "total_tokens": 15,
                },
                "output": [
                    {
                        "type": "reasoning",
                        "summary": [
                            {
                                "type": "summary_text",
                                "text": "Planned the answer",
                            }
                        ],
                        "content": [
                            {
                                "type": "reasoning_text",
                                "text": "Checked the prompt.",
                            }
                        ],
                        "encrypted_content": "encrypted-value",
                    },
                    {
                        "type": "message",
                        "role": "assistant",
                        "content": [
                            {"type": "output_text", "text": "Hello "},
                            {"type": "text", "text": "world"},
                        ],
                    },
                ],
            }
        )

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    provider = GoogleGcpProvider(
        _make_settings(
            api_key="explicit-token",
            model="xai/grok-4.20-reasoning",
        ),
        tool_catalog=ToolCatalog(),
    )
    session_usage = TokenUsage()
    turn_usage = TokenUsage()

    result = provider.request_turn(
        user_message="hello",
        display=display_spy,
        session_usage=session_usage,
        turn_usage=turn_usage,
    )

    assert result.response_id == "resp-gcp-usage"
    assert result.text == "Hello world"
    assert result.reasoning_summary == "Planned the answer"
    assert result.reasoning_content == "Checked the prompt."
    assert result.provider_data["encrypted_reasoning_content"] == ["encrypted-value"]
    assert result.usage.input_tokens == 10
    assert result.usage.cached_input_tokens == 4
    assert result.usage.output_tokens == 5
    assert result.usage.reasoning_tokens == 2
    assert result.usage.provider_total_tokens == 15
    assert result.usage.context_tokens == 15
    assert result.usage.model == "xai/grok-4.20-reasoning"
    assert session_usage.snapshot().total_tokens == 15
    assert turn_usage.snapshot().total_tokens == 15
    assert display_spy.thinking_calls == [
        {
            "text": "Checked the prompt.\n\nPlanned the answer",
            "title": "Planned the answer",
            "replace_existing": False,
            "widget_id": None,
        }
    ]
    assert display_spy.markdown_calls == ["Hello world"]


def test_google_gcp_openai_responses_function_calls_execute_and_serialize(
    monkeypatch,
    display_spy,
    make_http_response,
) -> None:
    monkeypatch.delenv(GOOGLE_GCP_SHAPE_ENV, raising=False)
    monkeypatch.setenv("GOOGLE_CLOUD_PROJECT", "demo-project")
    bodies: list[dict[str, Any]] = []
    responses = iter(
        [
            {
                "id": "resp-gcp-tool-call",
                "model": "xai/grok-4.20-reasoning",
                "output": [
                    {
                        "type": "function_call",
                        "call_id": "call_weather",
                        "name": "get_weather",
                        "arguments": '{"city":"Paris"}',
                        "status": "completed",
                    }
                ],
            },
            {
                "id": "resp-gcp-tool-answer",
                "model": "xai/grok-4.20-reasoning",
                "output": [
                    {
                        "type": "message",
                        "role": "assistant",
                        "content": [{"type": "output_text", "text": "20C"}],
                    }
                ],
            },
        ]
    )

    def fake_urlopen(request: urllib.request.Request, timeout: float):
        del timeout
        bodies.append(_request_json_body(request))
        return make_http_response(next(responses))

    def handler(arguments, context):
        del context
        assert arguments == {"city": "Paris"}
        return ToolOutput(result={"temperature": "20C"})

    catalog = ToolCatalog(
        {
            "get_weather": ToolCatalogEntry(
                spec=ToolSpec(
                    name="get_weather",
                    description="Get weather.",
                    parameters_schema={
                        "type": "object",
                        "properties": {"city": {"type": "string"}},
                        "required": ["city"],
                    },
                ),
                handler=handler,
            )
        }
    )
    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    provider = GoogleGcpProvider(
        _make_settings(
            api_key="explicit-token",
            model="xai/grok-4.20-reasoning",
        ),
        tool_catalog=catalog,
    )

    response = provider.request_turn(
        user_message="weather?",
        display=display_spy,
        session_usage=TokenUsage(),
        turn_usage=TokenUsage(),
    )

    assert len(response.function_calls) == 1
    assert response.function_calls[0].call_id == "call_weather"
    assert response.function_calls[0].name == "get_weather"
    assert response.function_calls[0].arguments == {"city": "Paris"}
    assert bodies[0]["tools"] == [
        {
            "type": "function",
            "name": "get_weather",
            "description": "Get weather.",
            "parameters": {
                "type": "object",
                "properties": {"city": {"type": "string"}},
                "required": ["city"],
            },
        }
    ]
    assert bodies[0]["parallel_tool_calls"] is True
    assert "previous_response_id" not in bodies[0]

    tool_result_items, had_errors = provider.execute_tool_calls(
        response,
        max_workers=1,
        display=display_spy,
        session_usage=TokenUsage(),
        turn_usage=TokenUsage(),
    )

    assert had_errors is False
    assert len(tool_result_items) == 1
    assert tool_result_items[0]["type"] == "function_call_output"
    assert tool_result_items[0]["call_id"] == "call_weather"
    assert json.loads(str(tool_result_items[0]["output"])) == {
        "ok": True,
        "result": {"temperature": "20C"},
    }

    provider.request_turn(
        tool_result_items=tool_result_items,
        display=display_spy,
        session_usage=TokenUsage(),
        turn_usage=TokenUsage(),
    )

    assert bodies[1]["input"] == [
        {"role": "user", "content": "weather?"},
        {
            "type": "function_call",
            "call_id": "call_weather",
            "name": "get_weather",
            "arguments": '{"city":"Paris"}',
        },
        tool_result_items[0],
    ]
    assert "previous_response_id" not in bodies[1]
    assert display_spy.function_counts == [1]
    assert display_spy.function_results == [
        {
            "name": "get_weather",
            "success": True,
            "call_id": "call_weather",
            "arguments": {"city": "Paris"},
        }
    ]


def test_google_gcp_openai_responses_rejects_image_inputs(
    display_spy,
) -> None:
    provider = GoogleGcpProvider(
        _make_settings(
            api_key="explicit-token",
            model="xai/grok-4.20-reasoning",
        ),
        tool_catalog=ToolCatalog(),
    )

    with pytest.raises(ValueError, match="image inputs are not enabled"):
        provider.request_turn(
            user_input=UserTurnInput(
                text="describe",
                images=[
                    ImageAttachment(
                        path="cat.png",
                        mime_type="image/png",
                        data_base64="aW1hZ2U=",
                    )
                ],
            ),
            display=display_spy,
            session_usage=TokenUsage(),
            turn_usage=TokenUsage(),
        )


def test_google_gcp_anthropic_request_uses_vertex_url_bearer_auth_and_body(
    monkeypatch,
    display_spy,
    make_http_response,
) -> None:
    monkeypatch.delenv(GOOGLE_GCP_SHAPE_ENV, raising=False)
    monkeypatch.setenv("GOOGLE_CLOUD_PROJECT", "demo-project")
    monkeypatch.setenv("GOOGLE_CLOUD_LOCATION", "us-east5")
    seen: dict[str, Any] = {}

    def fake_urlopen(request: urllib.request.Request, timeout: float):
        seen["url"] = request.full_url
        seen["headers"] = {key.lower(): value for key, value in request.header_items()}
        seen["timeout"] = timeout
        seen["body"] = _request_json_body(request)
        return make_http_response(
            {
                "id": "msg_vrtx_1",
                "model": "claude-sonnet-4-6",
                "content": [{"type": "text", "text": "ok"}],
                "usage": {"input_tokens": 5, "output_tokens": 2},
            }
        )

    def handler(arguments, context):
        del arguments, context
        return ToolOutput(result={"temperature": "20C"})

    catalog = ToolCatalog(
        {
            "get_weather": ToolCatalogEntry(
                spec=ToolSpec(
                    name="get_weather",
                    description="Get weather.",
                    parameters_schema={
                        "type": "object",
                        "properties": {"city": {"type": "string"}},
                        "required": ["city"],
                    },
                ),
                handler=handler,
            )
        }
    )
    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    provider = GoogleGcpProvider(
        _make_settings(
            api_key="",
            model="claude-sonnet-4-6",
            max_tokens=123,
        ),
        system_prompt="be concise",
        access_token_resolver=lambda: "adc-token",
        tool_catalog=catalog,
    )

    assert provider.shape_name == "anthropic_messages"
    provider.request_turn(
        user_message="hello",
        display=display_spy,
        session_usage=TokenUsage(),
        turn_usage=TokenUsage(),
    )

    assert seen["url"] == (
        "https://us-east5-aiplatform.googleapis.com/v1/projects/"
        "demo-project/locations/us-east5/publishers/anthropic/models/"
        "claude-sonnet-4-6:rawPredict"
    )
    headers = seen["headers"]
    assert headers["authorization"] == "Bearer adc-token"
    assert headers["content-type"] == "application/json"
    assert seen["timeout"] == 3600.0
    assert "x-api-key" not in headers
    assert "anthropic-version" not in headers
    assert seen["body"] == {
        "anthropic_version": "vertex-2023-10-16",
        "max_tokens": 123,
        "stream": False,
        "messages": [
            {
                "role": "user",
                "content": [{"type": "text", "text": "hello"}],
            }
        ],
        "tools": [
            {
                "name": "get_weather",
                "description": "Get weather.",
                "input_schema": {
                    "type": "object",
                    "properties": {"city": {"type": "string"}},
                    "required": ["city"],
                },
            }
        ],
        "system": "be concise",
    }
    assert "model" not in seen["body"]
    assert "cache_control" not in seen["body"]


def test_google_gcp_anthropic_endpoint_strips_anthropic_model_prefix(
    monkeypatch,
) -> None:
    monkeypatch.delenv(GOOGLE_GCP_SHAPE_ENV, raising=False)
    monkeypatch.setenv("GOOGLE_CLOUD_PROJECT", "demo-project")
    provider = GoogleGcpProvider(
        _make_settings(api_key="", model="anthropic/claude-sonnet-4-6"),
        access_token_resolver=lambda: "adc-token",
        tool_catalog=ToolCatalog(),
    )

    provider.connect()

    assert provider.endpoint_url == (
        "https://aiplatform.googleapis.com/v1/projects/demo-project/locations/"
        "global/publishers/anthropic/models/claude-sonnet-4-6:rawPredict"
    )
    assert "anthropic%2F" not in provider.endpoint_url


def test_google_gcp_anthropic_response_records_text_usage_thinking_and_tools(
    monkeypatch,
    display_spy,
    make_http_response,
) -> None:
    monkeypatch.delenv(GOOGLE_GCP_SHAPE_ENV, raising=False)
    monkeypatch.setenv("GOOGLE_CLOUD_PROJECT", "demo-project")

    def fake_urlopen(request: urllib.request.Request, timeout: float):
        del request, timeout
        return make_http_response(
            {
                "id": "msg_vrtx_usage",
                "model": "claude-sonnet-4-6",
                "content": [
                    {"type": "thinking", "thinking": "Checking the request."},
                    {"type": "redacted_thinking"},
                    {"type": "text", "text": "Need data."},
                    {
                        "type": "tool_use",
                        "id": "toolu_weather",
                        "name": "get_weather",
                        "input": {"city": "Paris"},
                    },
                    {"type": "text", "text": "Then done."},
                ],
                "usage": {
                    "input_tokens": 10,
                    "output_tokens": 5,
                    "cache_read_input_tokens": 2,
                    "cache_creation_input_tokens": 4,
                    "cache_creation": {"ephemeral_1h_input_tokens": 1},
                },
            }
        )

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    provider = GoogleGcpProvider(
        _make_settings(api_key="explicit-token", model="claude-sonnet-4-6"),
        tool_catalog=ToolCatalog(),
    )
    session_usage = TokenUsage()
    turn_usage = TokenUsage()

    result = provider.request_turn(
        user_message="weather?",
        display=display_spy,
        session_usage=session_usage,
        turn_usage=turn_usage,
    )

    assert result.response_id == "msg_vrtx_usage"
    assert result.text == "Need data.\n\nThen done."
    assert result.usage.input_tokens == 16
    assert result.usage.cached_input_tokens == 2
    assert result.usage.cache_write_tokens == 3
    assert result.usage.cache_write_1h_tokens == 1
    assert result.usage.output_tokens == 5
    assert result.usage.context_tokens == 21
    assert result.usage.model == "claude-sonnet-4-6"
    assert len(result.function_calls) == 1
    assert result.function_calls[0].call_id == "toolu_weather"
    assert result.function_calls[0].name == "get_weather"
    assert result.function_calls[0].arguments == {"city": "Paris"}
    assert result.provider_data["thinking_parts"] == ["Checking the request."]
    assert result.provider_data["has_redacted_thinking"] is True
    assert session_usage.snapshot().total_tokens == 21
    assert turn_usage.snapshot().total_tokens == 21
    assert display_spy.thinking_calls[0]["text"] == "Checking the request."
    assert display_spy.redacted_thinking_calls == 1
    assert display_spy.markdown_calls == ["Need data.", "Then done."]


def test_google_gcp_anthropic_tool_calls_execute_and_replay_tool_results(
    monkeypatch,
    display_spy,
    make_http_response,
) -> None:
    monkeypatch.delenv(GOOGLE_GCP_SHAPE_ENV, raising=False)
    monkeypatch.setenv("GOOGLE_CLOUD_PROJECT", "demo-project")
    bodies: list[dict[str, Any]] = []
    first_content = [
        {"type": "text", "text": "I'll check."},
        {
            "type": "tool_use",
            "id": "toolu_weather",
            "name": "get_weather",
            "input": {"city": "Paris"},
        },
    ]
    responses = iter(
        [
            {
                "id": "msg_vrtx_tool",
                "model": "claude-sonnet-4-6",
                "content": first_content,
                "usage": {"input_tokens": 8, "output_tokens": 4},
            },
            {
                "id": "msg_vrtx_answer",
                "model": "claude-sonnet-4-6",
                "content": [{"type": "text", "text": "20C"}],
                "usage": {"input_tokens": 12, "output_tokens": 2},
            },
        ]
    )

    def fake_urlopen(request: urllib.request.Request, timeout: float):
        del timeout
        bodies.append(_request_json_body(request))
        return make_http_response(next(responses))

    def handler(arguments, context):
        del context
        assert arguments == {"city": "Paris"}
        return ToolOutput(result={"temperature": "20C"})

    catalog = ToolCatalog(
        {
            "get_weather": ToolCatalogEntry(
                spec=ToolSpec(
                    name="get_weather",
                    description="Get weather.",
                    parameters_schema={
                        "type": "object",
                        "properties": {"city": {"type": "string"}},
                        "required": ["city"],
                    },
                ),
                handler=handler,
            )
        }
    )
    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    provider = GoogleGcpProvider(
        _make_settings(api_key="explicit-token", model="claude-sonnet-4-6"),
        tool_catalog=catalog,
    )

    response = provider.request_turn(
        user_message="weather?",
        display=display_spy,
        session_usage=TokenUsage(),
        turn_usage=TokenUsage(),
    )
    tool_result_items, had_errors = provider.execute_tool_calls(
        response,
        max_workers=1,
        display=display_spy,
        session_usage=TokenUsage(),
        turn_usage=TokenUsage(),
    )
    provider.request_turn(
        tool_result_items=tool_result_items,
        display=display_spy,
        session_usage=TokenUsage(),
        turn_usage=TokenUsage(),
    )

    assert had_errors is False
    assert len(tool_result_items) == 1
    tool_result = tool_result_items[0]
    assert tool_result["type"] == "tool_result"
    assert tool_result["tool_use_id"] == "toolu_weather"
    assert json.loads(str(tool_result["content"])) == {
        "ok": True,
        "result": {"temperature": "20C"},
    }
    assert bodies[0]["tools"] == [
        {
            "name": "get_weather",
            "description": "Get weather.",
            "input_schema": {
                "type": "object",
                "properties": {"city": {"type": "string"}},
                "required": ["city"],
            },
        }
    ]
    assert bodies[1]["messages"] == [
        {"role": "user", "content": [{"type": "text", "text": "weather?"}]},
        {"role": "assistant", "content": first_content},
        {"role": "user", "content": [tool_result]},
    ]
    assert display_spy.function_counts == [1]
    assert display_spy.function_results == [
        {
            "name": "get_weather",
            "success": True,
            "call_id": "toolu_weather",
            "arguments": {"city": "Paris"},
        }
    ]


def test_google_gcp_anthropic_image_input_uses_anthropic_image_blocks(
    monkeypatch,
    display_spy,
    make_http_response,
) -> None:
    monkeypatch.delenv(GOOGLE_GCP_SHAPE_ENV, raising=False)
    monkeypatch.setenv("GOOGLE_CLOUD_PROJECT", "demo-project")
    seen: dict[str, Any] = {}

    def fake_urlopen(request: urllib.request.Request, timeout: float):
        del timeout
        seen["body"] = _request_json_body(request)
        return make_http_response(
            {
                "id": "msg_vrtx_image",
                "content": [{"type": "text", "text": "a cat"}],
                "usage": {"input_tokens": 5, "output_tokens": 2},
            }
        )

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    provider = GoogleGcpProvider(
        _make_settings(api_key="explicit-token", model="claude-sonnet-4-6"),
        tool_catalog=ToolCatalog(),
    )

    provider.request_turn(
        user_input=UserTurnInput(
            text="describe",
            images=[
                ImageAttachment(
                    path="cat.png",
                    mime_type="image/png",
                    data_base64="aW1hZ2UtYnl0ZXM=",
                    byte_count=11,
                )
            ],
        ),
        display=display_spy,
        session_usage=TokenUsage(),
        turn_usage=TokenUsage(),
    )

    assert seen["body"]["messages"] == [
        {
            "role": "user",
            "content": [
                {
                    "type": "image",
                    "source": {
                        "type": "base64",
                        "media_type": "image/png",
                        "data": "aW1hZ2UtYnl0ZXM=",
                    },
                },
                {"type": "text", "text": "describe"},
            ],
        }
    ]
