from __future__ import annotations

import json
import urllib.request
from unittest.mock import Mock

import pytest

from pbi_agent.agent.system_prompt import get_system_prompt
from pbi_agent.agent.tool_runtime import ToolExecutionBatch
from pbi_agent.cli import build_parser
from pbi_agent.config import (
    ConfigError,
    DEFAULT_GOOGLE_INTERACTIONS_URL,
    DEFAULT_GOOGLE_MODEL,
    DEFAULT_MAX_TOKENS,
    Settings,
    resolve_settings,
)
from pbi_agent.models.messages import (
    CompletedResponse,
    ImageAttachment,
    TokenUsage,
    ToolCall,
    UserTurnInput,
    WebSearchSource,
)
from pbi_agent.providers.google_provider import GoogleProvider
from pbi_agent.tools.types import ToolResult


class _FakeHTTPResponse:
    def __init__(self, payload: dict[str, object]) -> None:
        self._payload = payload

    def read(self) -> bytes:
        return json.dumps(self._payload).encode("utf-8")

    def __enter__(self) -> _FakeHTTPResponse:
        return self

    def __exit__(self, *_: object) -> None:
        return None


def _make_settings(**overrides: object) -> Settings:
    defaults: dict[str, object] = {
        "api_key": "test-key",
        "provider": "google",
        "responses_url": DEFAULT_GOOGLE_INTERACTIONS_URL,
        "model": DEFAULT_GOOGLE_MODEL,
        "max_tokens": DEFAULT_MAX_TOKENS,
        "reasoning_effort": "xhigh",
        "max_retries": 0,
    }
    defaults.update(overrides)
    return Settings(**defaults)


def test_resolve_settings_uses_google_defaults(monkeypatch) -> None:
    for name in (
        "PBI_AGENT_PROVIDER",
        "PBI_AGENT_API_KEY",
        "PBI_AGENT_RESPONSES_URL",
        "PBI_AGENT_MODEL",
    ):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("GEMINI_API_KEY", "gemini-test-key")

    parser = build_parser()
    args = parser.parse_args(["--provider", "google", "web"])
    settings = resolve_settings(args)

    assert settings.provider == "google"
    assert settings.api_key == "gemini-test-key"
    assert settings.responses_url == DEFAULT_GOOGLE_INTERACTIONS_URL
    assert settings.model == DEFAULT_GOOGLE_MODEL
    assert settings.reasoning_effort == "high"
    settings.validate()


def test_google_settings_validate_mentions_google_specific_api_key_sources() -> None:
    settings = _make_settings(api_key="")

    with pytest.raises(ConfigError) as excinfo:
        settings.validate()

    assert "GEMINI_API_KEY" in str(excinfo.value)
    assert "--google-api-key" in str(excinfo.value)


def test_google_provider_connect_mentions_google_specific_api_key_sources() -> None:
    provider = GoogleProvider(_make_settings(api_key=""))

    with pytest.raises(ValueError) as excinfo:
        provider.connect()

    assert "GEMINI_API_KEY" in str(excinfo.value)
    assert "--google-api-key" in str(excinfo.value)


def test_google_build_request_body_uses_interactions_shape() -> None:
    provider = GoogleProvider(_make_settings())

    body = provider._build_request_body(
        input_value="hello",
        instructions="be concise",
    )

    assert body["model"] == DEFAULT_GOOGLE_MODEL
    assert body["input"] == "hello"
    assert body["stream"] is False
    assert body["store"] is True
    assert body["system_instruction"] == "be concise"
    assert body["generation_config"] == {
        "thinking_level": "high",
        "thinking_summaries": "auto",
        "max_output_tokens": DEFAULT_MAX_TOKENS,
    }
    assert "previous_interaction_id" not in body


def test_google_provider_exposes_shell_required_schema() -> None:
    provider = GoogleProvider(_make_settings())

    shell_tool = next(tool for tool in provider._tools if tool["name"] == "shell")

    assert shell_tool["parameters"]["required"] == ["command"]


def test_google_parse_response_extracts_function_calls_thoughts_and_usage() -> None:
    provider = GoogleProvider(_make_settings())

    result = provider._parse_response(
        {
            "id": "int_123",
            "model": DEFAULT_GOOGLE_MODEL,
            "status": "requires_action",
            "usage": {
                "total_input_tokens": 376,
                "total_cached_tokens": 12,
                "total_output_tokens": 33,
                "total_thought_tokens": 207,
                "total_tool_use_tokens": 50,
                "total_tokens": 666,
            },
            "outputs": [
                {
                    "type": "thought",
                    "signature": "sig_123",
                    "summary": [
                        {
                            "type": "text",
                            "text": "Examined the request before deciding to call a tool.",
                        }
                    ],
                },
                {
                    "type": "function_call",
                    "id": "call_88263992",
                    "name": "get_temperature",
                    "arguments": {"location": "San Francisco"},
                },
            ],
        }
    )

    assert result.response_id == "int_123"
    assert result.text == ""
    assert (
        result.reasoning_content
        == "Examined the request before deciding to call a tool."
    )
    assert result.provider_data["status"] == "requires_action"
    assert result.provider_data["thought_signatures"] == ["sig_123"]
    assert result.function_calls[0].call_id == "call_88263992"
    assert result.function_calls[0].name == "get_temperature"
    assert result.function_calls[0].arguments == {"location": "San Francisco"}
    assert result.usage.input_tokens == 376
    assert result.usage.cached_input_tokens == 12
    assert result.usage.output_tokens == 33
    assert result.usage.reasoning_tokens == 207
    assert result.usage.tool_use_tokens == 50
    assert result.usage.provider_total_tokens == 666
    assert result.usage.total_tokens == 666
    assert result.usage.model == DEFAULT_GOOGLE_MODEL


def test_google_request_turn_reuses_previous_interaction_id(monkeypatch) -> None:
    requests: list[dict[str, object]] = []
    responses = iter(
        [
            {
                "id": "int_1",
                "model": DEFAULT_GOOGLE_MODEL,
                "status": "requires_action",
                "usage": {
                    "total_input_tokens": 10,
                    "total_cached_tokens": 0,
                    "total_output_tokens": 3,
                    "total_thought_tokens": 2,
                },
                "outputs": [
                    {
                        "type": "function_call",
                        "id": "call_1",
                        "name": "get_temperature",
                        "arguments": {"location": "San Francisco"},
                    }
                ],
            },
            {
                "id": "int_2",
                "model": DEFAULT_GOOGLE_MODEL,
                "status": "completed",
                "usage": {
                    "total_input_tokens": 12,
                    "total_cached_tokens": 0,
                    "total_output_tokens": 4,
                    "total_thought_tokens": 1,
                },
                "outputs": [
                    {
                        "type": "text",
                        "text": "The current temperature is 59F.",
                    }
                ],
            },
        ]
    )

    def fake_urlopen(
        request: urllib.request.Request,
        timeout: float,
    ) -> _FakeHTTPResponse:
        del timeout
        payload = request.data.decode("utf-8") if request.data else "{}"
        requests.append(json.loads(payload))
        return _FakeHTTPResponse(next(responses))

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)

    provider = GoogleProvider(_make_settings())
    display = _DisplayStub()
    session_usage = TokenUsage(model=DEFAULT_GOOGLE_MODEL)

    first_turn_usage = TokenUsage(model=DEFAULT_GOOGLE_MODEL)
    first = provider.request_turn(
        user_message="What is the temperature in San Francisco?",
        display=display,
        session_usage=session_usage,
        turn_usage=first_turn_usage,
    )
    assert provider.get_conversation_checkpoint() is None

    second_turn_usage = TokenUsage(model=DEFAULT_GOOGLE_MODEL)
    second = provider.request_turn(
        tool_result_items=[
            {
                "type": "function_result",
                "name": "get_temperature",
                "call_id": "call_1",
                "result": '{"temperature":59}',
            }
        ],
        display=display,
        session_usage=session_usage,
        turn_usage=second_turn_usage,
    )
    assert provider.get_conversation_checkpoint() == "int_2"

    assert first.response_id == "int_1"
    assert second.response_id == "int_2"
    assert requests[0]["input"] == "What is the temperature in San Francisco?"
    assert requests[0]["system_instruction"] == get_system_prompt()
    assert requests[0]["generation_config"] == {
        "thinking_level": "high",
        "thinking_summaries": "auto",
        "max_output_tokens": 16384,
    }
    assert "previous_interaction_id" not in requests[0]
    assert requests[1]["previous_interaction_id"] == "int_1"
    assert requests[1]["system_instruction"] == get_system_prompt()
    assert requests[1]["input"] == [
        {
            "type": "function_result",
            "name": "get_temperature",
            "call_id": "call_1",
            "result": '{"temperature":59}',
        }
    ]


def test_google_execute_tool_calls_returns_function_results(
    monkeypatch,
    display_spy,
) -> None:
    provider = GoogleProvider(_make_settings())
    response = CompletedResponse(
        response_id="int_1",
        text="",
        function_calls=[
            ToolCall(call_id="call_1", name="shell", arguments={"command": "pwd"}),
            ToolCall(
                call_id="call_2", name="read_file", arguments={"path": "README.md"}
            ),
        ],
    )
    batch = ToolExecutionBatch(
        results=[
            ToolResult(
                call_id="call_1",
                output_json='{"ok": true, "result": "/workspace"}',
            ),
            ToolResult(
                call_id="call_2",
                output_json=(
                    '{"ok": false, "error": {"type": "tool_execution_failed", '
                    '"message": "boom"}}'
                ),
                is_error=True,
            ),
        ],
        had_errors=True,
    )

    monkeypatch.setattr(
        "pbi_agent.providers.google_provider._execute_tool_calls",
        lambda calls, max_workers, context=None, tool_catalog=None: batch,
    )

    tool_result_items, had_errors = provider.execute_tool_calls(
        response,
        max_workers=2,
        display=display_spy,
        session_usage=TokenUsage(model=DEFAULT_GOOGLE_MODEL),
        turn_usage=TokenUsage(model=DEFAULT_GOOGLE_MODEL),
    )

    assert had_errors is True
    assert tool_result_items == [
        {
            "type": "function_result",
            "name": "shell",
            "call_id": "call_1",
            "result": '{"ok": true, "result": "/workspace"}',
        },
        {
            "type": "function_result",
            "name": "read_file",
            "call_id": "call_2",
            "result": (
                '{"ok": false, "error": {"type": "tool_execution_failed", '
                '"message": "boom"}}'
            ),
            "is_error": True,
        },
    ]
    assert display_spy.function_counts == [2]
    assert display_spy.function_results == [
        {
            "name": "shell",
            "success": True,
            "call_id": "call_1",
            "arguments": {"command": "pwd"},
        },
        {
            "name": "read_file",
            "success": False,
            "call_id": "call_2",
            "arguments": {"path": "README.md"},
        },
    ]
    assert display_spy.tool_group_end_count == 1


def test_google_request_turn_retries_after_rate_limit_and_renders_thinking(
    monkeypatch,
    display_spy,
    make_http_error,
    make_http_response,
) -> None:
    requests: list[dict[str, object]] = []
    waits: list[float] = []
    response_payload = {
        "id": "int_retry",
        "model": DEFAULT_GOOGLE_MODEL,
        "status": "completed",
        "usage": {
            "total_input_tokens": 6,
            "total_cached_tokens": 1,
            "total_output_tokens": 4,
            "total_thought_tokens": 2,
            "total_tool_use_tokens": 3,
            "total_tokens": 15,
        },
        "outputs": [
            {
                "type": "thought",
                "signature": "sig_retry",
                "summary": [{"type": "text", "text": "Checked the request first."}],
            },
            {
                "type": "text",
                "text": "Recovered.",
            },
        ],
    }

    def fake_urlopen(
        request: urllib.request.Request,
        timeout: float,
    ) -> _FakeHTTPResponse:
        del timeout
        payload = request.data.decode("utf-8") if request.data else "{}"
        requests.append(json.loads(payload))
        if len(requests) == 1:
            raise make_http_error(
                url=DEFAULT_GOOGLE_INTERACTIONS_URL,
                code=429,
                body='{"error":{"message":"slow down"}}',
                headers={"Retry-After": "0.25"},
            )
        return make_http_response(response_payload)

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    monkeypatch.setattr(
        "pbi_agent.providers.google_provider.time.sleep",
        lambda seconds: waits.append(seconds),
    )

    provider = GoogleProvider(_make_settings(max_retries=1))
    response = provider.request_turn(
        user_message="hello",
        display=display_spy,
        session_usage=TokenUsage(model=DEFAULT_GOOGLE_MODEL),
        turn_usage=TokenUsage(model=DEFAULT_GOOGLE_MODEL),
    )

    assert response.text == "Recovered."
    assert len(requests) == 2
    assert waits == [1.25]
    assert display_spy.wait_messages == ["analyzing your request..."]
    assert display_spy.retry_notices == [(1, 1)]
    assert display_spy.rate_limit_notices == [(1.25, 1, 1)]
    assert display_spy.thinking_calls == [
        {
            "text": "Checked the request first.",
            "title": None,
            "replace_existing": False,
            "widget_id": None,
        }
    ]
    assert display_spy.markdown_calls == ["Recovered."]
    assert display_spy.session_usage_snapshots[-1].input_tokens == 6
    assert display_spy.session_usage_snapshots[-1].cached_input_tokens == 1
    assert display_spy.session_usage_snapshots[-1].output_tokens == 4
    assert display_spy.session_usage_snapshots[-1].tool_use_tokens == 3
    assert display_spy.session_usage_snapshots[-1].total_tokens == 15


def test_google_request_turn_retries_when_api_is_overloaded(
    monkeypatch,
    display_spy,
    make_http_error,
    make_http_response,
) -> None:
    waits: list[float] = []
    requests: list[dict[str, object]] = []
    response_payload = {
        "id": "int_retry",
        "model": DEFAULT_GOOGLE_MODEL,
        "status": "completed",
        "usage": {
            "total_input_tokens": 6,
            "total_cached_tokens": 0,
            "total_output_tokens": 4,
        },
        "outputs": [{"type": "text", "text": "Recovered."}],
    }

    def fake_urlopen(
        request: urllib.request.Request,
        timeout: float,
    ) -> _FakeHTTPResponse:
        del timeout
        payload = request.data.decode("utf-8") if request.data else "{}"
        requests.append(json.loads(payload))
        if len(requests) == 1:
            raise make_http_error(
                url=DEFAULT_GOOGLE_INTERACTIONS_URL,
                code=503,
                body=(
                    '{"error":{"status":"UNAVAILABLE","message":"The service is '
                    'temporarily running out of capacity."}}'
                ),
            )
        return make_http_response(response_payload)

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    monkeypatch.setattr(
        "pbi_agent.providers.google_provider.time.sleep",
        lambda seconds: waits.append(seconds),
    )

    provider = GoogleProvider(_make_settings(max_retries=1))
    response = provider.request_turn(
        user_message="hello",
        display=display_spy,
        session_usage=TokenUsage(model=DEFAULT_GOOGLE_MODEL),
        turn_usage=TokenUsage(model=DEFAULT_GOOGLE_MODEL),
    )

    assert response.text == "Recovered."
    assert len(requests) == 2
    assert waits == [3.0]
    assert display_spy.overload_notices == [(3.0, 1, 1)]
    assert display_spy.rate_limit_notices == []
    assert display_spy.retry_notices == [(1, 1)]


def test_google_request_turn_preserves_gemini_error_type_and_request_id(
    monkeypatch,
    display_spy,
    make_http_error,
) -> None:
    def fake_urlopen(
        request: urllib.request.Request,
        timeout: float,
    ) -> _FakeHTTPResponse:
        del request, timeout
        raise make_http_error(
            url=DEFAULT_GOOGLE_INTERACTIONS_URL,
            code=400,
            body=(
                '{"error":{"status":"FAILED_PRECONDITION","message":"Gemini API '
                "free tier is not available in your country. Please enable billing "
                'on your project in Google AI Studio."}}'
            ),
            headers={"x-request-id": "req_gemini_precondition"},
        )

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)

    provider = GoogleProvider(_make_settings(max_retries=0))

    with pytest.raises(RuntimeError) as exc_info:
        provider.request_turn(
            user_message="hello",
            display=display_spy,
            session_usage=TokenUsage(model=DEFAULT_GOOGLE_MODEL),
            turn_usage=TokenUsage(model=DEFAULT_GOOGLE_MODEL),
        )

    assert str(exc_info.value) == (
        'Google Interactions API error 400: {"error": {"message": "Gemini API '
        "free tier is not available in your country. Please enable billing on "
        'your project in Google AI Studio.", "type": "failed_precondition"}, '
        '"request_id": "req_gemini_precondition", "status": 400, "type": "error"}'
    )


def test_google_request_turn_raises_for_failed_response_payload(
    monkeypatch,
    display_spy,
    make_http_response,
) -> None:
    def fake_urlopen(
        request: urllib.request.Request,
        timeout: float,
    ) -> _FakeHTTPResponse:
        del request, timeout
        return make_http_response(
            {
                "status": "failed",
                "error": {
                    "code": "internal",
                    "message": "Upstream processing failed.",
                },
            }
        )

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)

    provider = GoogleProvider(_make_settings())

    try:
        provider.request_turn(
            user_message="hello",
            display=display_spy,
            session_usage=TokenUsage(model=DEFAULT_GOOGLE_MODEL),
            turn_usage=TokenUsage(model=DEFAULT_GOOGLE_MODEL),
        )
    except RuntimeError as exc:
        assert str(exc) == (
            "Google interaction failed (internal): Upstream processing failed."
        )
    else:
        raise AssertionError("Expected RuntimeError for failed Google interaction")


class _DisplayStub:
    def __init__(self) -> None:
        self.events: list[tuple[str, object]] = []

    def begin_sub_agent(
        self,
        *,
        task_instruction: str,
        reasoning_effort: str | None = None,
        name: str = "sub_agent",
    ) -> _DisplayStub:
        del task_instruction, reasoning_effort, name
        return self

    def finish_sub_agent(self, *, status: str) -> None:
        del status

    def wait_start(self, message: str = "") -> None:
        self.last_wait_message = message

    def wait_stop(self) -> None:
        pass

    def retry_notice(self, attempt: int, max_retries: int) -> None:
        self.retry = (attempt, max_retries)

    def rate_limit_notice(
        self,
        *,
        wait_seconds: float,
        attempt: int,
        max_retries: int,
    ) -> None:
        self.rate_limit = (wait_seconds, attempt, max_retries)

    def overload_notice(
        self,
        *,
        wait_seconds: float,
        attempt: int,
        max_retries: int,
    ) -> None:
        self.overload = (wait_seconds, attempt, max_retries)

    def session_usage(self, usage: TokenUsage) -> None:
        self.session_usage_snapshot = usage.snapshot()

    def render_thinking(
        self,
        text: str | None = None,
        *,
        title: str | None = None,
        replace_existing: bool = False,
        widget_id: str | None = None,
    ) -> str | None:
        self.thinking = {
            "text": text,
            "title": title,
            "replace_existing": replace_existing,
            "widget_id": widget_id,
        }
        return widget_id

    def render_markdown(self, text: str) -> None:
        self.markdown = text
        self.events.append(("markdown", text))

    def function_start(self, count: int) -> None:
        self.function_count = count
        self.events.append(("function_start", count))

    def function_result(
        self,
        *,
        name: str,
        success: bool,
        call_id: str,
        arguments: object,
    ) -> None:
        self.last_function_result = {
            "name": name,
            "success": success,
            "call_id": call_id,
            "arguments": arguments,
        }
        self.events.append(("function_result", self.last_function_result))

    def tool_group_end(self) -> None:
        self.tool_group_closed = True
        self.events.append(("tool_group_end", None))

    def web_search_sources(self, sources: list[WebSearchSource]) -> None:
        self.last_web_search_sources = list(sources)
        self.events.append(("web_search_sources", list(sources)))


def test_google_request_turn_serializes_user_input_images(monkeypatch) -> None:
    requests: list[dict[str, object]] = []

    def fake_urlopen(
        request: urllib.request.Request,
        timeout: float,
    ) -> _FakeHTTPResponse:
        del timeout
        payload = request.data.decode("utf-8") if request.data else "{}"
        requests.append(json.loads(payload))
        return _FakeHTTPResponse(
            {
                "id": "int_1",
                "model": DEFAULT_GOOGLE_MODEL,
                "status": "completed",
                "usage": {
                    "total_input_tokens": 10,
                    "total_cached_tokens": 0,
                    "total_output_tokens": 3,
                    "total_thought_tokens": 0,
                },
                "outputs": [{"type": "text", "text": "done"}],
            }
        )

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)

    provider = GoogleProvider(_make_settings())
    provider.request_turn(
        user_input=UserTurnInput(
            text="Describe this image.",
            images=[
                ImageAttachment(
                    path="chart.png",
                    mime_type="image/png",
                    data_base64="QUJDRA==",
                )
            ],
        ),
        display=_DisplayStub(),
        session_usage=TokenUsage(model=DEFAULT_GOOGLE_MODEL),
        turn_usage=TokenUsage(model=DEFAULT_GOOGLE_MODEL),
    )

    assert requests[0]["input"] == [
        {"type": "text", "text": "Describe this image."},
        {
            "type": "image",
            "mime_type": "image/png",
            "data": "QUJDRA==",
        },
    ]


def test_google_execute_tool_calls_serializes_image_attachments(
    monkeypatch,
    display_spy,
) -> None:
    provider = GoogleProvider(_make_settings())
    response = CompletedResponse(
        response_id="int_1",
        text="",
        function_calls=[
            ToolCall(
                call_id="call_1", name="read_image", arguments={"path": "chart.png"}
            )
        ],
    )
    batch = ToolExecutionBatch(
        results=[
            ToolResult(
                call_id="call_1",
                output_json='{"ok": true, "result": {"path": "chart.png"}}',
                attachments=[
                    ImageAttachment(
                        path="chart.png",
                        mime_type="image/png",
                        data_base64="QUJDRA==",
                    )
                ],
            )
        ],
        had_errors=False,
    )

    monkeypatch.setattr(
        "pbi_agent.providers.google_provider._execute_tool_calls",
        lambda calls, max_workers, context=None, tool_catalog=None: batch,
    )

    tool_result_items, had_errors = provider.execute_tool_calls(
        response,
        max_workers=1,
        display=display_spy,
        session_usage=TokenUsage(model=DEFAULT_GOOGLE_MODEL),
        turn_usage=TokenUsage(model=DEFAULT_GOOGLE_MODEL),
    )

    assert had_errors is False
    assert tool_result_items == [
        {
            "type": "function_result",
            "name": "read_image",
            "call_id": "call_1",
            "result": [
                {
                    "type": "text",
                    "text": '{"ok": true, "result": {"path": "chart.png"}}',
                },
                {
                    "type": "image",
                    "mime_type": "image/png",
                    "data": "QUJDRA==",
                },
            ],
        }
    ]


def test_google_web_search_tool_included_when_enabled() -> None:
    provider = GoogleProvider(_make_settings(web_search=True))
    assert {"type": "google_search"} in provider._tools


def test_google_web_search_tool_excluded_when_disabled() -> None:
    provider = GoogleProvider(_make_settings(web_search=False))
    assert {"type": "google_search"} not in provider._tools


def test_google_parse_response_extracts_grounding_sources() -> None:
    provider = GoogleProvider(_make_settings())

    result = provider._parse_response(
        {
            "id": "int_ws",
            "model": DEFAULT_GOOGLE_MODEL,
            "status": "completed",
            "usage": {
                "total_input_tokens": 50,
                "total_cached_tokens": 0,
                "total_output_tokens": 20,
                "total_thought_tokens": 0,
            },
            "outputs": [
                {"type": "text", "text": "Here is the answer."},
            ],
            "groundingMetadata": {
                "groundingChunks": [
                    {
                        "web": {
                            "uri": "https://example.com/page",
                            "title": "Example Page",
                        }
                    },
                    {
                        "web": {
                            "uri": "https://example.com/another",
                            "title": "Another Page",
                        }
                    },
                ]
            },
        }
    )

    assert result.text == "Here is the answer."
    assert len(result.web_search_sources) == 2
    assert result.web_search_sources[0].title == "Example Page"
    assert result.web_search_sources[0].url == "https://example.com/page"
    assert result.web_search_sources[1].title == "Another Page"
    assert result.web_search_sources[1].url == "https://example.com/another"
    assert result.provider_data["web_search_queries"] == []


def test_google_parse_response_extracts_queries_from_grounding_metadata() -> None:
    provider = GoogleProvider(_make_settings())

    result = provider._parse_response(
        {
            "id": "int_ws_queries",
            "model": DEFAULT_GOOGLE_MODEL,
            "status": "completed",
            "usage": {
                "total_input_tokens": 50,
                "total_cached_tokens": 0,
                "total_output_tokens": 20,
                "total_thought_tokens": 0,
            },
            "outputs": [{"type": "text", "text": "Here is the answer."}],
            "groundingMetadata": {
                "webSearchQueries": ["bitcoin live price", "BTC USD"],
                "groundingChunks": [
                    {
                        "web": {
                            "uri": "https://example.com/page",
                            "title": "Example Page",
                        }
                    }
                ],
            },
        }
    )

    assert result.provider_data["web_search_queries"] == [
        "bitcoin live price",
        "BTC USD",
    ]
    assert result.provider_data["display_items"][0]["type"] == "google_search_result"
    assert result.provider_data["display_items"][0]["queries"] == [
        "bitcoin live price",
        "BTC USD",
    ]
    assert result.provider_data["display_items"][1] == {
        "type": "text",
        "text": "Here is the answer.",
    }


def test_google_grounding_sources_preserve_duplicate_urls() -> None:
    provider = GoogleProvider(_make_settings())

    result = provider._parse_response(
        {
            "id": "int_dedup",
            "model": DEFAULT_GOOGLE_MODEL,
            "status": "completed",
            "usage": {
                "total_input_tokens": 10,
                "total_cached_tokens": 0,
                "total_output_tokens": 5,
            },
            "outputs": [{"type": "text", "text": "Answer."}],
            "groundingMetadata": {
                "groundingChunks": [
                    {"web": {"uri": "https://example.com/same", "title": "Page A"}},
                    {
                        "web": {
                            "uri": "https://example.com/same",
                            "title": "Page A again",
                        }
                    },
                ]
            },
        }
    )

    assert len(result.web_search_sources) == 2
    assert result.web_search_sources[0].url == "https://example.com/same"
    assert result.web_search_sources[1].url == "https://example.com/same"


def test_google_parse_response_no_grounding_metadata() -> None:
    provider = GoogleProvider(_make_settings())

    result = provider._parse_response(
        {
            "id": "int_no_ground",
            "model": DEFAULT_GOOGLE_MODEL,
            "status": "completed",
            "usage": {
                "total_input_tokens": 10,
                "total_cached_tokens": 0,
                "total_output_tokens": 5,
            },
            "outputs": [{"type": "text", "text": "No grounding."}],
        }
    )

    assert result.web_search_sources == []


def test_google_parse_response_extracts_google_search_result_output() -> None:
    provider = GoogleProvider(_make_settings())

    result = provider._parse_response(
        {
            "id": "int_search_output",
            "model": DEFAULT_GOOGLE_MODEL,
            "status": "completed",
            "usage": {
                "total_input_tokens": 12,
                "total_cached_tokens": 0,
                "total_output_tokens": 7,
            },
            "outputs": [
                {
                    "type": "google_search_result",
                    "call_id": "search_1",
                    "result": [
                        {
                            "url": "https://example.com/price",
                            "title": "BTC price",
                        }
                    ],
                },
                {"type": "text", "text": "Bitcoin is around $70k."},
            ],
            "groundingMetadata": {
                "webSearchQueries": ["bitcoin live price"],
            },
        }
    )

    assert len(result.web_search_sources) == 1
    assert result.web_search_sources[0].url == "https://example.com/price"
    assert result.provider_data["display_items"][0] == {
        "type": "google_search_result",
        "queries": ["bitcoin live price"],
        "sources": [
            WebSearchSource(title="BTC price", url="https://example.com/price")
        ],
    }
    assert result.provider_data["display_items"][1] == {
        "type": "text",
        "text": "Bitcoin is around $70k.",
    }


def test_google_parse_response_uses_google_search_call_queries_and_text_citations() -> (
    None
):
    provider = GoogleProvider(_make_settings())

    result = provider._parse_response(
        {
            "id": "int_google_search_call",
            "model": DEFAULT_GOOGLE_MODEL,
            "status": "completed",
            "usage": {
                "total_input_tokens": 12,
                "total_cached_tokens": 0,
                "total_output_tokens": 7,
            },
            "outputs": [
                {
                    "type": "google_search_call",
                    "id": "search_1",
                    "arguments": {"queries": ["current bitcoin price"]},
                },
                {
                    "type": "google_search_result",
                    "call_id": "search_1",
                    "result": [{"search_suggestions": "<div>chip</div>"}],
                },
                {
                    "type": "text",
                    "text": "Bitcoin is around $70k.",
                    "annotations": [
                        {
                            "type": "url_citation",
                            "url": "https://example.com/coindesk",
                            "title": "coindesk.com",
                        },
                        {
                            "type": "url_citation",
                            "url": "https://example.com/kraken",
                            "title": "kraken.com",
                        },
                    ],
                },
            ],
        }
    )

    assert result.provider_data["display_items"][0] == {
        "type": "google_search_result",
        "queries": ["current bitcoin price"],
        "sources": [
            WebSearchSource(
                title="coindesk.com",
                url="https://example.com/coindesk",
            ),
            WebSearchSource(
                title="kraken.com",
                url="https://example.com/kraken",
            ),
        ],
    }
    assert result.web_search_sources == [
        WebSearchSource(
            title="coindesk.com",
            url="https://example.com/coindesk",
        ),
        WebSearchSource(
            title="kraken.com",
            url="https://example.com/kraken",
        ),
    ]


def test_google_request_turn_renders_google_search_block_before_text(
    monkeypatch,
) -> None:
    def fake_urlopen(
        request: urllib.request.Request,
        timeout: float,
    ) -> _FakeHTTPResponse:
        del request, timeout
        return _FakeHTTPResponse(
            {
                "id": "int_1",
                "model": DEFAULT_GOOGLE_MODEL,
                "status": "completed",
                "usage": {
                    "total_input_tokens": 10,
                    "total_cached_tokens": 0,
                    "total_output_tokens": 3,
                    "total_thought_tokens": 0,
                },
                "outputs": [
                    {
                        "type": "google_search_call",
                        "id": "search_1",
                        "arguments": {"queries": ["bitcoin live price"]},
                    },
                    {
                        "type": "google_search_result",
                        "call_id": "search_1",
                        "result": [{"search_suggestions": "<div>chip</div>"}],
                    },
                    {
                        "type": "text",
                        "text": "Bitcoin is around $70k.",
                        "annotations": [
                            {
                                "type": "url_citation",
                                "url": "https://example.com/price",
                                "title": "BTC price",
                            }
                        ],
                    },
                ],
            }
        )

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)

    provider = GoogleProvider(_make_settings())
    display = _DisplayStub()

    provider.request_turn(
        user_message="check bitcoin price",
        display=display,
        session_usage=TokenUsage(model=DEFAULT_GOOGLE_MODEL),
        turn_usage=TokenUsage(model=DEFAULT_GOOGLE_MODEL),
    )

    assert display.events[0] == ("function_start", 1)
    assert display.events[1][0] == "function_result"
    assert display.events[1][1]["name"] == "web_search"
    assert display.events[1][1]["arguments"] == {
        "queries": ["bitcoin live price"],
        "sources": [
            {
                "title": "BTC price",
                "url": "https://example.com/price",
                "snippet": "",
            }
        ],
    }
    assert display.events[2] == ("tool_group_end", None)
    assert display.events[3] == ("markdown", "Bitcoin is around $70k.")


def test_google_request_turn_records_observability(monkeypatch) -> None:
    tracer = Mock()

    def fake_urlopen(
        request: urllib.request.Request,
        timeout: float,
    ) -> _FakeHTTPResponse:
        del request, timeout
        return _FakeHTTPResponse(
            {
                "id": "resp_trace",
                "model": DEFAULT_GOOGLE_MODEL,
                "usage": {
                    "total_input_tokens": 7,
                    "total_output_tokens": 3,
                    "total_tokens": 10,
                },
                "outputs": [{"type": "text", "text": "Traced."}],
            }
        )

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)

    provider = GoogleProvider(_make_settings())
    provider.request_turn(
        user_message="hello",
        display=_DisplayStub(),
        session_usage=TokenUsage(model=DEFAULT_GOOGLE_MODEL),
        turn_usage=TokenUsage(model=DEFAULT_GOOGLE_MODEL),
        tracer=tracer,
    )

    tracer.log_model_call.assert_called_once()
    assert (
        tracer.log_model_call.call_args.kwargs["url"] == DEFAULT_GOOGLE_INTERACTIONS_URL
    )
