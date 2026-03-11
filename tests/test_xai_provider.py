from __future__ import annotations

import json
import urllib.request

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
from pbi_agent.models.messages import CompletedResponse, TokenUsage, ToolCall
from pbi_agent.providers.xai_provider import XAIProvider
from pbi_agent.tools.types import ToolResult


class _DisplayStub:
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
    assert body["include"] == ["reasoning.encrypted_content"]
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
    assert "include" not in body


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
        lambda calls, max_workers: batch,
    )

    tool_result_items, had_errors = provider.execute_tool_calls(
        response,
        max_workers=2,
        display=display_spy,
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
