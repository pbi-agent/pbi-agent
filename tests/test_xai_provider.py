from __future__ import annotations

import json
import urllib.request

import pytest

from pbi_agent.agent.system_prompt import get_system_prompt
from pbi_agent.agent.tool_runtime import ToolExecutionBatch
from pbi_agent.cli import build_parser
from pbi_agent.config import (
    DEFAULT_MAX_TOKENS,
    DEFAULT_XAI_MODEL,
    DEFAULT_XAI_RESPONSES_URL,
    Settings,
    resolve_settings,
)
from pbi_agent.models.messages import (
    CompletedResponse,
    TokenUsage,
    ToolCall,
    WebSearchSource,
)
from pbi_agent.providers.xai_provider import XAIProvider
from pbi_agent.tools.types import ToolResult


class _DisplayStub:
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

    def function_start(self, count: int) -> None:
        self.function_count = count

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

    def tool_group_end(self) -> None:
        self.tool_group_closed = True

    def web_search_sources(self, sources: list[WebSearchSource]) -> None:
        self.last_web_search_sources = list(sources)


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
        "provider": "xai",
        "responses_url": DEFAULT_XAI_RESPONSES_URL,
        "model": DEFAULT_XAI_MODEL,
        "max_tokens": DEFAULT_MAX_TOKENS,
        "reasoning_effort": "high",
        "max_retries": 0,
    }
    defaults.update(overrides)
    return Settings(**defaults)


def test_resolve_settings_uses_xai_defaults(monkeypatch) -> None:
    for name in (
        "PBI_AGENT_PROVIDER",
        "PBI_AGENT_API_KEY",
        "PBI_AGENT_RESPONSES_URL",
        "PBI_AGENT_MODEL",
    ):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("XAI_API_KEY", "xai-test-key")

    parser = build_parser()
    args = parser.parse_args(["--provider", "xai", "console"])
    settings = resolve_settings(args)

    assert settings.provider == "xai"
    assert settings.api_key == "xai-test-key"
    assert settings.responses_url == DEFAULT_XAI_RESPONSES_URL
    assert settings.model == DEFAULT_XAI_MODEL
    assert settings.reasoning_effort == "high"
    settings.validate()


def test_xai_build_request_body_omits_unsupported_reasoning_effort() -> None:
    provider = XAIProvider(_make_settings(model="grok-4-1-fast-reasoning"))

    body = provider._build_request_body(
        input_items=[{"role": "user", "content": "hello"}],
        instructions="be concise",
    )

    assert body["max_output_tokens"] == DEFAULT_MAX_TOKENS
    assert body["stream"] is False
    assert body["parallel_tool_calls"] is True
    assert body["include"] == [
        "web_search_call.action.sources",
        "reasoning.encrypted_content",
    ]
    assert body["input"] == [
        {"role": "system", "content": "be concise"},
        {"role": "user", "content": "hello"},
    ]
    assert "instructions" not in body
    assert "reasoning" not in body


def test_xai_build_request_body_maps_grok_3_mini_reasoning_effort() -> None:
    provider = XAIProvider(
        _make_settings(model="grok-3-mini", reasoning_effort="medium")
    )

    body = provider._build_request_body(
        input_items=[{"role": "user", "content": "hello"}],
        instructions="be concise",
    )

    assert body["max_output_tokens"] == DEFAULT_MAX_TOKENS
    assert body["reasoning"] == {"effort": "high"}
    assert body["input"][0] == {"role": "system", "content": "be concise"}
    assert body["include"] == ["web_search_call.action.sources"]


def test_xai_parse_response_extracts_function_calls_and_encrypted_reasoning() -> None:
    provider = XAIProvider(_make_settings())

    result = provider._parse_response(
        {
            "id": "resp_123",
            "model": "grok-4-1-fast-reasoning",
            "usage": {
                "input_tokens": 376,
                "input_tokens_details": {"cached_tokens": 282},
                "output_tokens": 233,
                "output_tokens_details": {"reasoning_tokens": 207},
            },
            "reasoning": {"effort": "medium", "summary": "detailed"},
            "output": [
                {
                    "id": "rs_123",
                    "type": "reasoning",
                    "status": "completed",
                    "summary": [
                        {"type": "summary_text", "text": "Planned a tool call"}
                    ],
                    "content": [
                        {
                            "type": "reasoning_text",
                            "text": "Examined the request before deciding to call a tool.",
                        }
                    ],
                    "encrypted_content": "encrypted-value",
                },
                {
                    "arguments": '{"location":"San Francisco"}',
                    "call_id": "call_88263992",
                    "name": "get_temperature",
                    "type": "function_call",
                    "status": "completed",
                },
            ],
        }
    )

    assert result.response_id == "resp_123"
    assert result.text == ""
    assert result.reasoning_summary == "Planned a tool call"
    assert (
        result.reasoning_content
        == "Examined the request before deciding to call a tool."
    )
    assert result.provider_data["encrypted_reasoning_content"] == ["encrypted-value"]
    assert result.provider_data["reasoning"] == {
        "effort": "medium",
        "summary": "detailed",
    }
    assert result.function_calls[0].call_id == "call_88263992"
    assert result.function_calls[0].name == "get_temperature"
    assert result.function_calls[0].arguments == {"location": "San Francisco"}
    assert result.usage.input_tokens == 376
    assert result.usage.cached_input_tokens == 282
    assert result.usage.output_tokens == 233
    assert result.usage.reasoning_tokens == 207
    assert result.usage.model == "grok-4-1-fast-reasoning"


def test_xai_request_turn_reuses_previous_response_id(monkeypatch) -> None:
    requests: list[dict[str, object]] = []
    responses = iter(
        [
            {
                "id": "resp_1",
                "model": "grok-4-1-fast-reasoning",
                "usage": {
                    "input_tokens": 10,
                    "input_tokens_details": {"cached_tokens": 0},
                    "output_tokens": 3,
                    "output_tokens_details": {"reasoning_tokens": 2},
                },
                "output": [
                    {
                        "arguments": '{"location":"San Francisco"}',
                        "call_id": "call_1",
                        "name": "get_temperature",
                        "type": "function_call",
                    }
                ],
            },
            {
                "id": "resp_2",
                "model": "grok-4-1-fast-reasoning",
                "previous_response_id": "resp_1",
                "usage": {
                    "input_tokens": 12,
                    "input_tokens_details": {"cached_tokens": 0},
                    "output_tokens": 4,
                    "output_tokens_details": {"reasoning_tokens": 1},
                },
                "output": [
                    {
                        "type": "message",
                        "role": "assistant",
                        "content": [
                            {
                                "type": "output_text",
                                "text": "The current temperature is 59F.",
                            }
                        ],
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

    provider = XAIProvider(_make_settings())
    display = _DisplayStub()
    session_usage = TokenUsage(model="grok-4-1-fast-reasoning")

    first_turn_usage = TokenUsage(model="grok-4-1-fast-reasoning")
    first = provider.request_turn(
        user_message="What is the temperature in San Francisco?",
        display=display,
        session_usage=session_usage,
        turn_usage=first_turn_usage,
    )

    second_turn_usage = TokenUsage(model="grok-4-1-fast-reasoning")
    second = provider.request_turn(
        tool_result_items=[
            {
                "type": "function_call_output",
                "call_id": "call_1",
                "output": '{"temperature":59}',
            }
        ],
        display=display,
        session_usage=session_usage,
        turn_usage=second_turn_usage,
    )

    assert first.response_id == "resp_1"
    assert second.response_id == "resp_2"
    assert requests[0]["input"] == [
        {"role": "system", "content": get_system_prompt()},
        {"role": "user", "content": "What is the temperature in San Francisco?"},
    ]
    assert "instructions" not in requests[0]
    assert "previous_response_id" not in requests[0]
    assert requests[1]["previous_response_id"] == "resp_1"
    assert "instructions" not in requests[1]
    assert requests[1]["input"] == [
        {
            "type": "function_call_output",
            "call_id": "call_1",
            "output": '{"temperature":59}',
        }
    ]


def test_xai_execute_tool_calls_returns_function_call_outputs(
    monkeypatch,
    display_spy,
) -> None:
    provider = XAIProvider(_make_settings())
    response = CompletedResponse(
        response_id="resp_1",
        text="",
        function_calls=[
            ToolCall(call_id="call_1", name="shell", arguments={"command": "pwd"}),
            ToolCall(call_id="call_2", name="init_report", arguments={"dest": "."}),
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
        "pbi_agent.providers.xai_provider._execute_tool_calls",
        lambda calls, max_workers, context=None: batch,
    )

    tool_result_items, had_errors = provider.execute_tool_calls(
        response,
        max_workers=2,
        display=display_spy,
        session_usage=TokenUsage(model=DEFAULT_XAI_MODEL),
        turn_usage=TokenUsage(model=DEFAULT_XAI_MODEL),
    )

    assert had_errors is True
    assert tool_result_items == [
        {
            "type": "function_call_output",
            "call_id": "call_1",
            "output": '{"ok": true, "result": "/workspace"}',
        },
        {
            "type": "function_call_output",
            "call_id": "call_2",
            "output": (
                '{"ok": false, "error": {"type": "tool_execution_failed", '
                '"message": "boom"}}'
            ),
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
            "name": "init_report",
            "success": False,
            "call_id": "call_2",
            "arguments": {"dest": "."},
        },
    ]
    assert display_spy.tool_group_end_count == 1


def test_xai_request_turn_retries_after_rate_limit_and_renders_reasoning(
    monkeypatch,
    display_spy,
    make_http_error,
    make_http_response,
) -> None:
    requests: list[dict[str, object]] = []
    waits: list[float] = []
    response_payload = {
        "id": "resp_retry",
        "model": DEFAULT_XAI_MODEL,
        "usage": {
            "input_tokens": 6,
            "input_tokens_details": {"cached_tokens": 1},
            "output_tokens": 4,
            "output_tokens_details": {"reasoning_tokens": 2},
        },
        "reasoning": {"effort": "high", "summary": "detailed"},
        "output": [
            {
                "type": "reasoning",
                "summary": [
                    {"type": "summary_text", "text": "Planned a response"},
                ],
                "content": [
                    {
                        "type": "reasoning_text",
                        "text": "Checked the request before answering.",
                    }
                ],
                "encrypted_content": "encrypted-value",
            },
            {
                "type": "message",
                "role": "assistant",
                "content": [{"type": "output_text", "text": "Recovered."}],
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
                url=DEFAULT_XAI_RESPONSES_URL,
                code=429,
                body='{"error":"slow down"}',
                headers={"Retry-After": "0.25"},
            )
        return make_http_response(response_payload)

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    monkeypatch.setattr(
        "pbi_agent.providers.xai_provider.time.sleep",
        lambda seconds: waits.append(seconds),
    )

    provider = XAIProvider(_make_settings(max_retries=1))
    response = provider.request_turn(
        user_message="hello",
        display=display_spy,
        session_usage=TokenUsage(model=DEFAULT_XAI_MODEL),
        turn_usage=TokenUsage(model=DEFAULT_XAI_MODEL),
    )

    assert response.text == "Recovered."
    assert len(requests) == 2
    assert waits == [1.25]
    assert display_spy.wait_messages == ["analyzing your request..."]
    assert display_spy.retry_notices == [(1, 1)]
    assert display_spy.rate_limit_notices == [(1.25, 1, 1)]
    assert display_spy.thinking_calls == [
        {
            "text": "Checked the request before answering.",
            "title": "Planned a response",
            "replace_existing": False,
            "widget_id": None,
        }
    ]
    assert display_spy.markdown_calls == ["Recovered."]
    assert display_spy.session_usage_snapshots[-1].input_tokens == 6
    assert display_spy.session_usage_snapshots[-1].cached_input_tokens == 1
    assert display_spy.session_usage_snapshots[-1].output_tokens == 4


def test_xai_request_turn_preserves_error_type_and_request_id(
    monkeypatch,
    display_spy,
    make_http_error,
) -> None:
    def fake_urlopen(
        request: urllib.request.Request,
        timeout: float,
    ):
        del request, timeout
        raise make_http_error(
            url=DEFAULT_XAI_RESPONSES_URL,
            code=404,
            body=(
                '{"error":{"type":"not_found_error","message":"The requested '
                'model or endpoint could not be found."},"request_id":"req_404"}'
            ),
        )

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)

    provider = XAIProvider(_make_settings(max_retries=0))

    with pytest.raises(RuntimeError) as exc_info:
        provider.request_turn(
            user_message="hello",
            display=display_spy,
            session_usage=TokenUsage(),
            turn_usage=TokenUsage(),
        )

    assert str(exc_info.value) == (
        'xAI Responses API error 404: {"error": {"message": "The requested '
        'model or endpoint could not be found.", "type": "not_found_error"}, '
        '"request_id": "req_404", "status": 404, "type": "error"}'
    )


def test_xai_request_turn_uses_request_id_header_for_non_json_errors(
    monkeypatch,
    display_spy,
    make_http_error,
) -> None:
    def fake_urlopen(
        request: urllib.request.Request,
        timeout: float,
    ):
        del request, timeout
        raise make_http_error(
            url=DEFAULT_XAI_RESPONSES_URL,
            code=415,
            body="<html>Unsupported Media Type</html>",
            headers={"x-request-id": "req_415"},
        )

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)

    provider = XAIProvider(_make_settings(max_retries=0))

    with pytest.raises(RuntimeError) as exc_info:
        provider.request_turn(
            user_message="hello",
            display=display_spy,
            session_usage=TokenUsage(),
            turn_usage=TokenUsage(),
        )

    assert str(exc_info.value) == (
        'xAI Responses API error 415: {"error": {"message": "Request body is '
        'missing or Content-Type is not application/json.", "type": '
        '"invalid_request_error"}, "request_id": "req_415", "status": 415, '
        '"type": "error"}'
    )


def test_xai_request_turn_renders_web_search_as_tool_result(
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
                "id": "resp_ws_display",
                "model": DEFAULT_XAI_MODEL,
                "usage": {
                    "input_tokens": 5,
                    "input_tokens_details": {"cached_tokens": 0},
                    "output_tokens": 7,
                    "output_tokens_details": {"reasoning_tokens": 0},
                },
                "output": [
                    {
                        "type": "web_search_call",
                        "id": "ws_1",
                        "status": "completed",
                        "action": {
                            "type": "search",
                            "queries": ["bitcoin price"],
                            "sources": [
                                {
                                    "type": "url",
                                    "url": "https://example.com/btc",
                                    "title": "BTC",
                                }
                            ],
                        },
                    },
                    {
                        "type": "message",
                        "role": "assistant",
                        "content": [
                            {"type": "output_text", "text": "Done."},
                        ],
                    },
                ],
            }
        )

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)

    provider = XAIProvider(_make_settings())
    response = provider.request_turn(
        user_message="bitcoin price?",
        display=display_spy,
        session_usage=TokenUsage(model=DEFAULT_XAI_MODEL),
        turn_usage=TokenUsage(model=DEFAULT_XAI_MODEL),
    )

    assert response.text == "Done."
    assert display_spy.markdown_calls == ["Done."]
    assert display_spy.function_counts == [1]
    assert display_spy.function_results == [
        {
            "name": "web_search",
            "success": True,
            "call_id": "",
            "arguments": {
                "queries": ["bitcoin price"],
                "sources": [
                    {
                        "title": "BTC",
                        "url": "https://example.com/btc",
                        "snippet": "",
                    }
                ]
            },
        }
    ]
    assert display_spy.tool_group_end_count == 1
    assert display_spy.web_search_sources_calls == []


def test_xai_request_turn_renders_web_search_block_without_sources(
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
                "id": "resp_ws_no_sources",
                "model": DEFAULT_XAI_MODEL,
                "usage": {
                    "input_tokens": 5,
                    "input_tokens_details": {"cached_tokens": 0},
                    "output_tokens": 7,
                    "output_tokens_details": {"reasoning_tokens": 0},
                },
                "output": [
                    {
                        "type": "web_search_call",
                        "id": "ws_1",
                        "status": "completed",
                    },
                    {
                        "type": "message",
                        "role": "assistant",
                        "content": [
                            {"type": "output_text", "text": "Done."},
                        ],
                    },
                ],
            }
        )

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)

    provider = XAIProvider(_make_settings())
    response = provider.request_turn(
        user_message="bitcoin price?",
        display=display_spy,
        session_usage=TokenUsage(model=DEFAULT_XAI_MODEL),
        turn_usage=TokenUsage(model=DEFAULT_XAI_MODEL),
    )

    assert response.text == "Done."
    assert response.had_web_search_call is True
    assert display_spy.markdown_calls == ["Done."]
    assert display_spy.function_counts == [1]
    assert display_spy.function_results == [
        {
            "name": "web_search",
            "success": True,
            "call_id": "",
            "arguments": {"queries": [], "sources": []},
        }
    ]
    assert display_spy.tool_group_end_count == 1


def test_xai_web_search_tool_included_when_enabled() -> None:
    provider = XAIProvider(_make_settings(web_search=True))
    assert {"type": "web_search"} in provider._tools


def test_xai_web_search_tool_excluded_when_disabled() -> None:
    provider = XAIProvider(_make_settings(web_search=False))
    assert {"type": "web_search"} not in provider._tools


def test_xai_parse_response_extracts_web_search_sources() -> None:
    provider = XAIProvider(_make_settings())

    result = provider._parse_response(
        {
            "id": "resp_ws",
            "model": DEFAULT_XAI_MODEL,
            "usage": {
                "input_tokens": 50,
                "input_tokens_details": {"cached_tokens": 0},
                "output_tokens": 20,
                "output_tokens_details": {"reasoning_tokens": 0},
            },
            "output": [
                {
                    "type": "web_search_call",
                    "id": "ws_1",
                    "status": "completed",
                },
                {
                    "type": "message",
                    "role": "assistant",
                    "content": [
                        {
                            "type": "output_text",
                            "text": "Here is the answer.",
                            "annotations": [
                                {
                                    "type": "url_citation",
                                    "title": "Example Article",
                                    "url": "https://example.com/article",
                                },
                                {
                                    "type": "url_citation",
                                    "title": "Another Source",
                                    "url": "https://example.com/another",
                                },
                            ],
                        }
                    ],
                },
            ],
        }
    )

    assert result.text == "Here is the answer."
    assert len(result.web_search_sources) == 2
    assert result.web_search_sources[0].title == "Example Article"
    assert result.web_search_sources[0].url == "https://example.com/article"
    assert result.web_search_sources[1].title == "Another Source"


def test_xai_parse_response_extracts_web_search_action_sources() -> None:
    provider = XAIProvider(_make_settings())

    result = provider._parse_response(
        {
            "id": "resp_ws_action",
            "model": DEFAULT_XAI_MODEL,
            "usage": {
                "input_tokens": 10,
                "input_tokens_details": {"cached_tokens": 0},
                "output_tokens": 5,
                "output_tokens_details": {"reasoning_tokens": 0},
            },
            "output": [
                {
                    "type": "web_search_call",
                    "id": "ws_1",
                    "status": "completed",
                    "action": {
                        "type": "search",
                        "queries": ["bitcoin price"],
                        "sources": [
                            {"type": "url", "url": "https://example.com/btc"},
                            {"type": "url", "url": "https://example.com/chart"},
                        ],
                    },
                },
                {
                    "type": "message",
                    "role": "assistant",
                    "content": [
                        {"type": "output_text", "text": "Done."},
                    ],
                },
            ],
        }
    )

    assert len(result.web_search_sources) == 2
    assert result.web_search_sources[0].title == "example.com"
    assert result.web_search_sources[0].url == "https://example.com/btc"
    assert result.web_search_sources[1].title == "example.com"
    assert result.web_search_sources[1].url == "https://example.com/chart"


def test_xai_web_search_sources_deduplicate_urls_and_prefer_non_numeric_titles() -> None:
    provider = XAIProvider(_make_settings())

    result = provider._parse_response(
        {
            "id": "resp_dup",
            "model": DEFAULT_XAI_MODEL,
            "usage": {
                "input_tokens": 10,
                "input_tokens_details": {"cached_tokens": 0},
                "output_tokens": 5,
                "output_tokens_details": {"reasoning_tokens": 0},
            },
            "output": [
                {
                    "type": "web_search_call",
                    "id": "ws_1",
                    "status": "completed",
                    "action": {
                        "type": "search",
                        "queries": ["bitcoin price"],
                        "sources": [
                            {
                                "type": "url",
                                "title": "CoinMarketCap",
                                "url": "https://example.com/same",
                            }
                        ],
                    },
                },
                {
                    "type": "message",
                    "role": "assistant",
                    "content": [
                        {
                            "type": "output_text",
                            "text": "Answer.",
                            "annotations": [
                                {
                                    "type": "url_citation",
                                    "title": "1",
                                    "url": "https://example.com/same",
                                },
                                {
                                    "type": "url_citation",
                                    "title": "2",
                                    "url": "https://example.com/same",
                                },
                            ],
                        }
                    ],
                },
            ],
        }
    )

    assert len(result.web_search_sources) == 1
    assert result.web_search_sources[0].title == "CoinMarketCap"
    assert result.web_search_sources[0].url == "https://example.com/same"


def test_xai_request_turn_preserves_web_search_order_from_output(
    monkeypatch,
    display_spy,
    make_http_response,
) -> None:
    events: list[tuple[str, object]] = []

    original_render_markdown = display_spy.render_markdown
    original_function_result = display_spy.function_result

    def capture_markdown(text: str) -> None:
        events.append(("message", text))
        original_render_markdown(text)

    def capture_function_result(
        *,
        name: str,
        success: bool,
        call_id: str,
        arguments: object,
    ) -> None:
        events.append(("tool", name))
        original_function_result(
            name=name,
            success=success,
            call_id=call_id,
            arguments=arguments,
        )

    display_spy.render_markdown = capture_markdown
    display_spy.function_result = capture_function_result

    def fake_urlopen(
        request: urllib.request.Request,
        timeout: float,
    ) -> _FakeHTTPResponse:
        del request, timeout
        return make_http_response(
            {
                "id": "resp_ws_order",
                "model": DEFAULT_XAI_MODEL,
                "usage": {
                    "input_tokens": 5,
                    "input_tokens_details": {"cached_tokens": 0},
                    "output_tokens": 7,
                    "output_tokens_details": {"reasoning_tokens": 0},
                },
                "output": [
                    {
                        "type": "web_search_call",
                        "id": "ws_1",
                        "status": "completed",
                        "action": {
                            "type": "search",
                            "queries": ["finance: BTC"],
                        },
                    },
                    {
                        "type": "message",
                        "role": "assistant",
                        "content": [
                            {"type": "output_text", "text": "Done."},
                        ],
                    },
                ],
            }
        )

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)

    provider = XAIProvider(_make_settings())
    provider.request_turn(
        user_message="bitcoin price?",
        display=display_spy,
        session_usage=TokenUsage(model=DEFAULT_XAI_MODEL),
        turn_usage=TokenUsage(model=DEFAULT_XAI_MODEL),
    )

    assert events == [("tool", "web_search"), ("message", "Done.")]


def test_xai_request_turn_coalesces_adjacent_web_search_calls_with_same_query(
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
                "id": "resp_ws_merge",
                "model": DEFAULT_XAI_MODEL,
                "usage": {
                    "input_tokens": 5,
                    "input_tokens_details": {"cached_tokens": 0},
                    "output_tokens": 7,
                    "output_tokens_details": {"reasoning_tokens": 0},
                },
                "output": [
                    {
                        "type": "web_search_call",
                        "id": "ws_1",
                        "status": "completed",
                        "action": {
                            "type": "search",
                            "queries": ["current bitcoin price USD"],
                        },
                    },
                    {
                        "type": "web_search_call",
                        "id": "ws_2",
                        "status": "completed",
                        "action": {
                            "type": "search",
                            "queries": ["current bitcoin price USD"],
                            "sources": [
                                {
                                    "type": "url",
                                    "url": "https://example.com/btc",
                                    "title": "BTC",
                                }
                            ],
                        },
                    },
                    {
                        "type": "message",
                        "role": "assistant",
                        "content": [
                            {"type": "output_text", "text": "Done."},
                        ],
                    },
                ],
            }
        )

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)

    provider = XAIProvider(_make_settings())
    provider.request_turn(
        user_message="bitcoin price?",
        display=display_spy,
        session_usage=TokenUsage(model=DEFAULT_XAI_MODEL),
        turn_usage=TokenUsage(model=DEFAULT_XAI_MODEL),
    )

    assert display_spy.function_counts == [1]
    assert display_spy.function_results == [
        {
            "name": "web_search",
            "success": True,
            "call_id": "",
            "arguments": {
                "queries": ["current bitcoin price USD"],
                "sources": [
                    {
                        "title": "BTC",
                        "url": "https://example.com/btc",
                        "snippet": "",
                    }
                ],
            },
        }
    ]


def test_xai_web_search_call_not_in_function_calls() -> None:
    provider = XAIProvider(_make_settings())

    result = provider._parse_response(
        {
            "id": "resp_ws2",
            "model": DEFAULT_XAI_MODEL,
            "usage": {
                "input_tokens": 10,
                "input_tokens_details": {"cached_tokens": 0},
                "output_tokens": 5,
                "output_tokens_details": {"reasoning_tokens": 0},
            },
            "output": [
                {
                    "type": "web_search_call",
                    "id": "ws_1",
                    "status": "completed",
                },
                {
                    "type": "message",
                    "role": "assistant",
                    "content": [
                        {"type": "output_text", "text": "Done."},
                    ],
                },
            ],
        }
    )

    assert result.function_calls == []
    assert not result.has_tool_calls
