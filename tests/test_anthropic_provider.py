from __future__ import annotations

import json
import urllib.request

from pbi_agent.agent.system_prompt import get_system_prompt
from pbi_agent.agent.tool_runtime import ToolExecutionBatch
from pbi_agent.config import (
    DEFAULT_ANTHROPIC_MODEL,
    DEFAULT_MAX_TOKENS,
    Settings,
)
from pbi_agent.models.messages import CompletedResponse, TokenUsage
from pbi_agent.providers.anthropic_provider import ANTHROPIC_API_URL, AnthropicProvider
from pbi_agent.tools.types import ToolResult


def _make_settings(**overrides: object) -> Settings:
    defaults: dict[str, object] = {
        "api_key": "test-key",
        "provider": "anthropic",
        "model": DEFAULT_ANTHROPIC_MODEL,
        "max_tokens": DEFAULT_MAX_TOKENS,
        "reasoning_effort": "xhigh",
        "max_retries": 1,
    }
    defaults.update(overrides)
    return Settings(**defaults)


def test_anthropic_parse_response_extracts_cache_usage_and_tool_calls() -> None:
    provider = AnthropicProvider(_make_settings())

    result = provider._parse_response(
        {
            "id": "msg_123",
            "content": [
                {"type": "thinking", "thinking": "Inspecting the report."},
                {"type": "redacted_thinking"},
                {"type": "text", "text": "I will inspect the model."},
                {
                    "type": "tool_use",
                    "id": "toolu_1",
                    "name": "shell",
                    "input": {"command": "pwd"},
                },
                {"type": "text", "text": "One command should be enough."},
            ],
            "usage": {
                "input_tokens": 100,
                "output_tokens": 30,
                "cache_read_input_tokens": 20,
                "cache_creation_input_tokens": 15,
                "cache_creation": {"ephemeral_1h_input_tokens": 5},
            },
        }
    )

    assert result.response_id == "msg_123"
    assert result.text == "I will inspect the model.\n\nOne command should be enough."
    assert len(result.function_calls) == 1
    assert result.function_calls[0].call_id == "toolu_1"
    assert result.function_calls[0].name == "shell"
    assert result.function_calls[0].arguments == {"command": "pwd"}
    assert result.usage.input_tokens == 135
    assert result.usage.cached_input_tokens == 20
    assert result.usage.cache_write_tokens == 10
    assert result.usage.cache_write_1h_tokens == 5
    assert result.usage.output_tokens == 30
    assert result.provider_data["thinking_parts"] == ["Inspecting the report."]
    assert result.provider_data["has_redacted_thinking"] is True
    assert len(result.provider_data["content_blocks"]) == 5


def test_anthropic_request_turn_preserves_history_and_wraps_tool_results(
    monkeypatch,
    display_spy,
    make_http_response,
) -> None:
    requests: list[dict[str, object]] = []
    first_content = [
        {"type": "thinking", "thinking": "Checking the workspace."},
        {"type": "redacted_thinking"},
        {
            "type": "tool_use",
            "id": "toolu_1",
            "name": "shell",
            "input": {"command": "pwd"},
        },
    ]
    responses = iter(
        [
            {
                "id": "msg_1",
                "content": first_content,
                "usage": {
                    "input_tokens": 10,
                    "output_tokens": 2,
                },
            },
            {
                "id": "msg_2",
                "content": [{"type": "text", "text": "You are in /workspace."}],
                "usage": {
                    "input_tokens": 12,
                    "output_tokens": 4,
                    "cache_read_input_tokens": 3,
                    "cache_creation_input_tokens": 5,
                    "cache_creation": {"ephemeral_1h_input_tokens": 2},
                },
            },
        ]
    )

    def fake_urlopen(
        request: urllib.request.Request,
        timeout: float,
    ):
        del timeout
        payload = request.data.decode("utf-8") if request.data else "{}"
        requests.append(json.loads(payload))
        return make_http_response(next(responses))

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)

    provider = AnthropicProvider(_make_settings())
    session_usage = TokenUsage()

    first = provider.request_turn(
        user_message="Where am I?",
        display=display_spy,
        session_usage=session_usage,
        turn_usage=TokenUsage(),
    )
    second = provider.request_turn(
        tool_result_items=[
            {
                "type": "tool_result",
                "tool_use_id": "toolu_1",
                "content": '{"ok": true, "result": "/workspace"}',
            }
        ],
        display=display_spy,
        session_usage=session_usage,
        turn_usage=TokenUsage(),
    )

    assert first.response_id == "msg_1"
    assert second.response_id == "msg_2"
    assert requests[0]["model"] == DEFAULT_ANTHROPIC_MODEL
    assert requests[0]["max_tokens"] == DEFAULT_MAX_TOKENS
    assert requests[0]["thinking"] == {"type": "adaptive"}
    assert requests[0]["output_config"] == {"effort": "max"}
    assert requests[0]["system"] == get_system_prompt()
    assert requests[0]["messages"] == [
        {
            "role": "user",
            "content": [{"type": "text", "text": "Where am I?"}],
        }
    ]
    assert requests[1]["messages"] == [
        {
            "role": "user",
            "content": [{"type": "text", "text": "Where am I?"}],
        },
        {"role": "assistant", "content": first_content},
        {
            "role": "user",
            "content": [
                {
                    "type": "tool_result",
                    "tool_use_id": "toolu_1",
                    "content": '{"ok": true, "result": "/workspace"}',
                }
            ],
        },
    ]
    assert display_spy.thinking_calls[0]["text"] == "Checking the workspace."
    assert display_spy.redacted_thinking_calls == 1
    assert display_spy.markdown_calls == ["You are in /workspace."]
    assert display_spy.session_usage_snapshots[-1].input_tokens == 30
    assert display_spy.session_usage_snapshots[-1].output_tokens == 6
    assert display_spy.session_usage_snapshots[-1].cached_input_tokens == 3
    assert display_spy.session_usage_snapshots[-1].cache_write_tokens == 3
    assert display_spy.session_usage_snapshots[-1].cache_write_1h_tokens == 2


def test_anthropic_execute_tool_calls_returns_tool_result_blocks(
    monkeypatch,
    display_spy,
) -> None:
    provider = AnthropicProvider(_make_settings())
    response = CompletedResponse(
        response_id="msg_1",
        text="",
        provider_data={
            "content_blocks": [
                {
                    "type": "tool_use",
                    "id": "toolu_1",
                    "name": "shell",
                    "input": {"command": "pwd"},
                },
                {
                    "type": "tool_use",
                    "id": "toolu_2",
                    "name": "init_report",
                    "input": {"dest": "."},
                },
            ]
        },
    )
    batch = ToolExecutionBatch(
        results=[
            ToolResult(
                call_id="toolu_1",
                output_json='{"ok": true, "result": "/workspace"}',
            ),
            ToolResult(
                call_id="toolu_2",
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
        "pbi_agent.providers.anthropic_provider._execute_tool_calls",
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
            "type": "tool_result",
            "tool_use_id": "toolu_1",
            "content": '{"ok": true, "result": "/workspace"}',
        },
        {
            "type": "tool_result",
            "tool_use_id": "toolu_2",
            "content": (
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
            "call_id": "toolu_1",
            "arguments": {"command": "pwd"},
        },
        {
            "name": "init_report",
            "success": False,
            "call_id": "toolu_2",
            "arguments": {"dest": "."},
        },
    ]
    assert display_spy.tool_group_end_count == 1


def test_anthropic_request_turn_retries_when_api_is_overloaded(
    monkeypatch,
    display_spy,
    make_http_error,
    make_http_response,
) -> None:
    waits: list[float] = []
    requests: list[dict[str, object]] = []
    response_payload = {
        "id": "msg_retry",
        "content": [{"type": "text", "text": "Recovered."}],
        "usage": {"input_tokens": 5, "output_tokens": 3},
    }

    def fake_urlopen(
        request: urllib.request.Request,
        timeout: float,
    ):
        del timeout
        payload = request.data.decode("utf-8") if request.data else "{}"
        requests.append(json.loads(payload))
        if len(requests) == 1:
            raise make_http_error(
                url=ANTHROPIC_API_URL,
                code=529,
                body='{"error":"overloaded"}',
            )
        return make_http_response(response_payload)

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    monkeypatch.setattr(
        "pbi_agent.providers.anthropic_provider.time.sleep",
        lambda seconds: waits.append(seconds),
    )

    provider = AnthropicProvider(_make_settings(max_retries=1))
    response = provider.request_turn(
        user_message="hello",
        display=display_spy,
        session_usage=TokenUsage(),
        turn_usage=TokenUsage(),
    )

    assert response.text == "Recovered."
    assert len(requests) == 2
    assert waits == [3.0]
    assert display_spy.rate_limit_notices == [(3.0, 1, 1)]
    assert display_spy.retry_notices == [(1, 1)]
