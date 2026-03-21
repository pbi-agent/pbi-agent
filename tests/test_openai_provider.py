from __future__ import annotations

import json
import urllib.request

from pbi_agent.cli import build_parser
from pbi_agent.agent.system_prompt import get_system_prompt
from pbi_agent.agent.tool_runtime import ToolExecutionBatch
from pbi_agent.config import (
    DEFAULT_MAX_TOKENS,
    DEFAULT_MODEL,
    DEFAULT_RESPONSES_URL,
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
from pbi_agent.providers.openai_provider import OpenAIProvider
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
        "provider": "openai",
        "responses_url": DEFAULT_RESPONSES_URL,
        "model": DEFAULT_MODEL,
        "max_tokens": DEFAULT_MAX_TOKENS,
        "reasoning_effort": "xhigh",
        "max_retries": 0,
        "compact_threshold": 150000,
    }
    defaults.update(overrides)
    return Settings(**defaults)


def test_resolve_settings_uses_openai_xhigh_default(monkeypatch) -> None:
    for name in (
        "PBI_AGENT_PROVIDER",
        "PBI_AGENT_API_KEY",
        "PBI_AGENT_RESPONSES_URL",
        "PBI_AGENT_MODEL",
        "PBI_AGENT_REASONING_EFFORT",
    ):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("OPENAI_API_KEY", "openai-test-key")

    parser = build_parser()
    args = parser.parse_args(["--provider", "openai", "console"])
    settings = resolve_settings(args)

    assert settings.provider == "openai"
    assert settings.api_key == "openai-test-key"
    assert settings.responses_url == DEFAULT_RESPONSES_URL
    assert settings.model == DEFAULT_MODEL
    assert settings.reasoning_effort == "xhigh"
    settings.validate()


def test_openai_build_request_body_uses_http_responses_shape() -> None:
    provider = OpenAIProvider(_make_settings())

    body = provider._build_request_body(
        input_items=[{"role": "user", "content": "hello"}],
        instructions="be concise",
    )

    assert body["model"] == DEFAULT_MODEL
    assert body["max_output_tokens"] == DEFAULT_MAX_TOKENS
    assert body["stream"] is False
    assert body["store"] is True
    assert body["parallel_tool_calls"] is True
    assert body["prompt_cache_retention"] == "24h"
    assert body["context_management"] == [
        {"type": "compaction", "compact_threshold": 150000}
    ]
    assert body["reasoning"] == {"effort": "xhigh", "summary": "auto"}
    assert body["input"] == [
        {"role": "system", "content": "be concise"},
        {"role": "user", "content": "hello"},
    ]
    assert "instructions" not in body
    assert "previous_response_id" not in body


def test_openai_build_request_body_includes_service_tier() -> None:
    provider = OpenAIProvider(_make_settings(service_tier="flex"))

    body = provider._build_request_body(
        input_items=[{"role": "user", "content": "hello"}],
        instructions="be concise",
    )

    assert body["service_tier"] == "flex"


def test_openai_build_request_body_omits_service_tier_when_none() -> None:
    provider = OpenAIProvider(_make_settings())

    body = provider._build_request_body(
        input_items=[{"role": "user", "content": "hello"}],
        instructions="be concise",
    )

    assert "service_tier" not in body


def test_openai_provider_can_exclude_sub_agent_tool() -> None:
    provider = OpenAIProvider(_make_settings(), excluded_tools={"sub_agent"})

    assert "sub_agent" not in {
        tool["name"] for tool in provider._tools if "name" in tool
    }


def test_openai_parse_response_extracts_function_calls_reasoning_and_usage() -> None:
    provider = OpenAIProvider(_make_settings())

    result = provider._parse_response(
        {
            "id": "resp_123",
            "model": DEFAULT_MODEL,
            "usage": {
                "input_tokens": 376,
                "input_tokens_details": {"cached_tokens": 282},
                "output_tokens": 233,
                "output_tokens_details": {"reasoning_tokens": 207},
            },
            "reasoning": {"effort": "xhigh", "summary": "auto"},
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
    assert result.provider_data["reasoning"] == {"effort": "xhigh", "summary": "auto"}
    assert result.function_calls[0].call_id == "call_88263992"
    assert result.function_calls[0].name == "get_temperature"
    assert result.function_calls[0].arguments == {"location": "San Francisco"}
    assert result.usage.input_tokens == 376
    assert result.usage.cached_input_tokens == 282
    assert result.usage.output_tokens == 233
    assert result.usage.reasoning_tokens == 207
    assert result.usage.model == DEFAULT_MODEL


def test_openai_parse_response_preserves_distinct_assistant_messages() -> None:
    provider = OpenAIProvider(_make_settings())

    result = provider._parse_response(
        {
            "id": "resp_multi",
            "model": DEFAULT_MODEL,
            "output": [
                {
                    "type": "message",
                    "role": "assistant",
                    "content": [
                        {"type": "output_text", "text": "First update."},
                    ],
                },
                {
                    "type": "function_call",
                    "call_id": "call_1",
                    "name": "shell",
                    "arguments": '{"command":"pwd"}',
                },
                {
                    "type": "message",
                    "role": "assistant",
                    "content": [
                        {"type": "output_text", "text": "Second update."},
                    ],
                },
            ],
        }
    )

    assert result.assistant_messages == ["First update.", "Second update."]
    assert result.text == "First update.Second update."


def test_openai_request_turn_reuses_previous_response_id(monkeypatch) -> None:
    requests: list[dict[str, object]] = []
    responses = iter(
        [
            {
                "id": "resp_1",
                "model": DEFAULT_MODEL,
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
                "model": DEFAULT_MODEL,
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

    provider = OpenAIProvider(_make_settings())
    display = _DisplayStub()
    session_usage = TokenUsage(model=DEFAULT_MODEL)

    first_turn_usage = TokenUsage(model=DEFAULT_MODEL)
    first = provider.request_turn(
        user_message="What is the temperature in San Francisco?",
        display=display,
        session_usage=session_usage,
        turn_usage=first_turn_usage,
    )

    second_turn_usage = TokenUsage(model=DEFAULT_MODEL)
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
    assert requests[0]["stream"] is False
    assert requests[0]["reasoning"] == {"effort": "xhigh", "summary": "auto"}
    assert "previous_response_id" not in requests[0]
    assert requests[1]["previous_response_id"] == "resp_1"
    assert requests[1]["input"] == [
        {
            "type": "function_call_output",
            "call_id": "call_1",
            "output": '{"temperature":59}',
        }
    ]
    assert requests[1]["reasoning"] == {"effort": "xhigh", "summary": "auto"}


def test_openai_execute_tool_calls_returns_function_call_outputs(
    monkeypatch,
    display_spy,
) -> None:
    provider = OpenAIProvider(_make_settings())
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
        "pbi_agent.providers.openai_provider._execute_tool_calls",
        lambda calls, max_workers, context=None: batch,
    )

    tool_result_items, had_errors = provider.execute_tool_calls(
        response,
        max_workers=2,
        display=display_spy,
        session_usage=TokenUsage(model=DEFAULT_MODEL),
        turn_usage=TokenUsage(model=DEFAULT_MODEL),
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


def test_openai_execute_tool_calls_skips_generic_display_for_sub_agent(
    monkeypatch,
    display_spy,
) -> None:
    provider = OpenAIProvider(_make_settings())
    response = CompletedResponse(
        response_id="resp_1",
        text="",
        function_calls=[
            ToolCall(
                call_id="call_1",
                name="sub_agent",
                arguments={"task_instruction": "Inspect the repo"},
            )
        ],
    )
    batch = ToolExecutionBatch(
        results=[
            ToolResult(
                call_id="call_1",
                output_json='{"ok": true, "result": {"status":"completed"}}',
            )
        ],
        had_errors=False,
    )

    monkeypatch.setattr(
        "pbi_agent.providers.openai_provider._execute_tool_calls",
        lambda calls, max_workers, context=None: batch,
    )

    tool_result_items, had_errors = provider.execute_tool_calls(
        response,
        max_workers=1,
        display=display_spy,
        session_usage=TokenUsage(model=DEFAULT_MODEL),
        turn_usage=TokenUsage(model=DEFAULT_MODEL),
    )

    assert had_errors is False
    assert display_spy.function_counts == []
    assert display_spy.function_results == []
    assert display_spy.tool_group_end_count == 0
    assert tool_result_items == [
        {
            "type": "function_call_output",
            "call_id": "call_1",
            "output": '{"ok": true, "result": {"status":"completed"}}',
        }
    ]


def test_openai_request_turn_retries_after_rate_limit_and_renders_reasoning(
    monkeypatch,
    display_spy,
    make_http_error,
    make_http_response,
) -> None:
    requests: list[dict[str, object]] = []
    waits: list[float] = []
    response_payload = {
        "id": "resp_retry",
        "model": DEFAULT_MODEL,
        "usage": {
            "input_tokens": 6,
            "input_tokens_details": {"cached_tokens": 1},
            "output_tokens": 4,
            "output_tokens_details": {"reasoning_tokens": 2},
        },
        "reasoning": {"effort": "xhigh", "summary": "auto"},
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
                url=DEFAULT_RESPONSES_URL,
                code=429,
                body='{"error":"slow down"}',
                headers={"Retry-After": "0.25"},
            )
        return make_http_response(response_payload)

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    monkeypatch.setattr(
        "pbi_agent.providers.openai_provider.time.sleep",
        lambda seconds: waits.append(seconds),
    )

    provider = OpenAIProvider(_make_settings(max_retries=1))
    response = provider.request_turn(
        user_message="hello",
        display=display_spy,
        session_usage=TokenUsage(model=DEFAULT_MODEL),
        turn_usage=TokenUsage(model=DEFAULT_MODEL),
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


def test_openai_request_turn_retries_when_api_is_overloaded(
    monkeypatch,
    display_spy,
    make_http_error,
    make_http_response,
) -> None:
    requests: list[dict[str, object]] = []
    waits: list[float] = []
    response_payload = {
        "id": "resp_retry",
        "model": DEFAULT_MODEL,
        "usage": {
            "input_tokens": 6,
            "input_tokens_details": {"cached_tokens": 1},
            "output_tokens": 4,
            "output_tokens_details": {"reasoning_tokens": 2},
        },
        "reasoning": {"effort": "xhigh", "summary": "auto"},
        "output": [
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
                url=DEFAULT_RESPONSES_URL,
                code=503,
                body='{"error":{"message":"The engine is currently overloaded, please try again later"}}',
                headers={"Retry-After": "0.25"},
            )
        return make_http_response(response_payload)

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    monkeypatch.setattr(
        "pbi_agent.providers.openai_provider.time.sleep",
        lambda seconds: waits.append(seconds),
    )

    provider = OpenAIProvider(_make_settings(max_retries=1))
    response = provider.request_turn(
        user_message="hello",
        display=display_spy,
        session_usage=TokenUsage(model=DEFAULT_MODEL),
        turn_usage=TokenUsage(model=DEFAULT_MODEL),
    )

    assert response.text == "Recovered."
    assert len(requests) == 2
    assert waits == [1.25]
    assert display_spy.overload_notices == [(1.25, 1, 1)]
    assert display_spy.rate_limit_notices == []
    assert display_spy.retry_notices == [(1, 1)]
    assert display_spy.markdown_calls == ["Recovered."]


def test_openai_request_turn_renders_intermediate_assistant_messages(
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
                "id": "resp_intermediate",
                "model": DEFAULT_MODEL,
                "usage": {
                    "input_tokens": 5,
                    "input_tokens_details": {"cached_tokens": 0},
                    "output_tokens": 7,
                    "output_tokens_details": {"reasoning_tokens": 0},
                },
                "output": [
                    {
                        "type": "message",
                        "role": "assistant",
                        "content": [
                            {"type": "output_text", "text": "Let me check that."}
                        ],
                    },
                    {
                        "type": "function_call",
                        "call_id": "call_1",
                        "name": "shell",
                        "arguments": '{"command":"pwd"}',
                    },
                    {
                        "type": "message",
                        "role": "assistant",
                        "content": [
                            {"type": "output_text", "text": "I found the path."}
                        ],
                    },
                ],
            }
        )

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)

    provider = OpenAIProvider(_make_settings())
    response = provider.request_turn(
        user_message="where am i?",
        display=display_spy,
        session_usage=TokenUsage(model=DEFAULT_MODEL),
        turn_usage=TokenUsage(model=DEFAULT_MODEL),
    )

    assert response.assistant_messages == ["Let me check that.", "I found the path."]
    assert display_spy.markdown_calls == ["Let me check that.", "I found the path."]
    assert response.function_calls == [
        ToolCall(call_id="call_1", name="shell", arguments={"command": "pwd"})
    ]


def test_openai_request_turn_raises_for_failed_response_payload(
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
                    "code": "server_error",
                    "message": "Upstream processing failed.",
                },
            }
        )

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)

    provider = OpenAIProvider(_make_settings())

    try:
        provider.request_turn(
            user_message="hello",
            display=display_spy,
            session_usage=TokenUsage(model=DEFAULT_MODEL),
            turn_usage=TokenUsage(model=DEFAULT_MODEL),
        )
    except RuntimeError as exc:
        assert str(exc) == (
            "OpenAI response failed (server_error): Upstream processing failed."
        )
    else:
        raise AssertionError("Expected RuntimeError for failed OpenAI response")


def test_openai_request_turn_renders_web_search_as_tool_result(
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
                "model": DEFAULT_MODEL,
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

    provider = OpenAIProvider(_make_settings())
    response = provider.request_turn(
        user_message="bitcoin price?",
        display=display_spy,
        session_usage=TokenUsage(model=DEFAULT_MODEL),
        turn_usage=TokenUsage(model=DEFAULT_MODEL),
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
                ],
            },
        }
    ]
    assert display_spy.tool_group_end_count == 1
    assert display_spy.web_search_sources_calls == []


def test_openai_request_turn_renders_web_search_block_without_sources(
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
                "model": DEFAULT_MODEL,
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

    provider = OpenAIProvider(_make_settings())
    response = provider.request_turn(
        user_message="bitcoin price?",
        display=display_spy,
        session_usage=TokenUsage(model=DEFAULT_MODEL),
        turn_usage=TokenUsage(model=DEFAULT_MODEL),
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


def test_openai_request_turn_preserves_web_search_order_from_output(
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
                "model": DEFAULT_MODEL,
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

    provider = OpenAIProvider(_make_settings())
    provider.request_turn(
        user_message="bitcoin price?",
        display=display_spy,
        session_usage=TokenUsage(model=DEFAULT_MODEL),
        turn_usage=TokenUsage(model=DEFAULT_MODEL),
    )

    assert events == [("tool", "web_search"), ("message", "Done.")]


def test_openai_request_turn_serializes_user_input_images(monkeypatch) -> None:
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
                "id": "resp_1",
                "model": DEFAULT_MODEL,
                "output": [
                    {
                        "type": "message",
                        "content": [{"type": "output_text", "text": "done"}],
                    }
                ],
            }
        )

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)

    provider = OpenAIProvider(_make_settings())
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
        session_usage=TokenUsage(model=DEFAULT_MODEL),
        turn_usage=TokenUsage(model=DEFAULT_MODEL),
    )

    user_item = next(
        item for item in requests[0]["input"] if item.get("role") == "user"
    )
    assert user_item["content"] == [
        {"type": "input_text", "text": "Describe this image."},
        {
            "type": "input_image",
            "image_url": "data:image/png;base64,QUJDRA==",
            "detail": "original",
        },
    ]


def test_openai_execute_tool_calls_serializes_image_attachments(
    monkeypatch,
    display_spy,
) -> None:
    provider = OpenAIProvider(_make_settings())
    response = CompletedResponse(
        response_id="resp_1",
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
        "pbi_agent.providers.openai_provider._execute_tool_calls",
        lambda calls, max_workers, context=None: batch,
    )

    tool_result_items, had_errors = provider.execute_tool_calls(
        response,
        max_workers=1,
        display=display_spy,
        session_usage=TokenUsage(model=DEFAULT_MODEL),
        turn_usage=TokenUsage(model=DEFAULT_MODEL),
    )

    assert had_errors is False
    assert tool_result_items == [
        {
            "type": "function_call_output",
            "call_id": "call_1",
            "output": [
                {
                    "type": "input_text",
                    "text": '{"ok": true, "result": {"path": "chart.png"}}',
                },
                {
                    "type": "input_image",
                    "image_url": "data:image/png;base64,QUJDRA==",
                },
            ],
        }
    ]


def test_openai_web_search_tool_included_when_enabled() -> None:
    provider = OpenAIProvider(_make_settings(web_search=True))
    assert {"type": "web_search"} in provider._tools


def test_openai_web_search_tool_excluded_when_disabled() -> None:
    provider = OpenAIProvider(_make_settings(web_search=False))
    assert {"type": "web_search"} not in provider._tools


def test_openai_parse_response_extracts_web_search_sources() -> None:
    provider = OpenAIProvider(_make_settings())

    result = provider._parse_response(
        {
            "id": "resp_ws",
            "model": DEFAULT_MODEL,
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
    assert result.web_search_sources[1].url == "https://example.com/another"


def test_openai_web_search_call_not_in_function_calls() -> None:
    provider = OpenAIProvider(_make_settings())

    result = provider._parse_response(
        {
            "id": "resp_ws2",
            "model": DEFAULT_MODEL,
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


def test_openai_parse_response_extracts_web_search_action_sources() -> None:
    provider = OpenAIProvider(_make_settings())

    result = provider._parse_response(
        {
            "id": "resp_ws_action",
            "model": DEFAULT_MODEL,
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
    assert result.web_search_sources[0].title == "https://example.com/btc"
    assert result.web_search_sources[0].url == "https://example.com/btc"
    assert result.web_search_sources[1].title == "https://example.com/chart"
    assert result.web_search_sources[1].url == "https://example.com/chart"


def test_openai_web_search_sources_preserve_duplicate_urls() -> None:
    provider = OpenAIProvider(_make_settings())

    result = provider._parse_response(
        {
            "id": "resp_dedup",
            "model": DEFAULT_MODEL,
            "usage": {
                "input_tokens": 10,
                "input_tokens_details": {"cached_tokens": 0},
                "output_tokens": 5,
                "output_tokens_details": {"reasoning_tokens": 0},
            },
            "output": [
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
                                    "title": "Same Page",
                                    "url": "https://example.com/same",
                                },
                                {
                                    "type": "url_citation",
                                    "title": "Same Page (again)",
                                    "url": "https://example.com/same",
                                },
                            ],
                        }
                    ],
                },
            ],
        }
    )

    assert len(result.web_search_sources) == 2
    assert result.web_search_sources[0].url == "https://example.com/same"
    assert result.web_search_sources[1].url == "https://example.com/same"
