from __future__ import annotations

import json
import urllib.request
from unittest.mock import Mock

import pytest

from pbi_agent.agent.system_prompt import get_system_prompt
from pbi_agent.agent.tool_runtime import ToolExecutionBatch
from pbi_agent.config import (
    DEFAULT_ANTHROPIC_MODEL,
    DEFAULT_MAX_TOKENS,
    Settings,
)
from pbi_agent.models.messages import (
    CompletedResponse,
    ImageAttachment,
    TokenUsage,
    UserTurnInput,
)
from pbi_agent.providers.anthropic_provider import ANTHROPIC_API_URL, AnthropicProvider
from pbi_agent.session_store import MessageRecord
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


def test_anthropic_request_turn_omits_adaptive_thinking_for_haiku_models(
    monkeypatch,
    display_spy,
    make_http_response,
) -> None:
    requests: list[dict[str, object]] = []

    def fake_urlopen(
        request: urllib.request.Request,
        timeout: float,
    ):
        del timeout
        payload = request.data.decode("utf-8") if request.data else "{}"
        requests.append(json.loads(payload))
        return make_http_response(
            {
                "id": "msg_haiku",
                "content": [{"type": "text", "text": "Bitcoin is $1."}],
                "usage": {
                    "input_tokens": 8,
                    "output_tokens": 3,
                },
            }
        )

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)

    provider = AnthropicProvider(
        _make_settings(model="claude-haiku-4-5", reasoning_effort="low")
    )
    provider.request_turn(
        user_message="check bitcoin price",
        display=display_spy,
        session_usage=TokenUsage(),
        turn_usage=TokenUsage(),
    )

    assert "thinking" not in requests[0]
    assert "output_config" not in requests[0]


def test_anthropic_restore_messages_reuses_persisted_history(
    monkeypatch,
    display_spy,
    make_http_response,
) -> None:
    requests: list[dict[str, object]] = []

    def fake_urlopen(
        request: urllib.request.Request,
        timeout: float,
    ):
        del timeout
        payload = request.data.decode("utf-8") if request.data else "{}"
        requests.append(json.loads(payload))
        return make_http_response(
            {
                "id": "msg_3",
                "content": [{"type": "text", "text": "Follow-up answer."}],
                "usage": {
                    "input_tokens": 8,
                    "output_tokens": 3,
                },
            }
        )

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)

    provider = AnthropicProvider(_make_settings())
    provider.restore_messages(
        [
            MessageRecord(
                id=1,
                session_id="session-1",
                role="user",
                content="Original question",
                created_at="2026-03-19T10:00:00+00:00",
            ),
            MessageRecord(
                id=2,
                session_id="session-1",
                role="assistant",
                content="Original answer",
                created_at="2026-03-19T10:00:01+00:00",
            ),
        ]
    )

    provider.request_turn(
        user_message="Follow-up question",
        display=display_spy,
        session_usage=TokenUsage(),
        turn_usage=TokenUsage(),
    )

    assert requests[0]["messages"] == [
        {
            "role": "user",
            "content": [{"type": "text", "text": "Original question"}],
        },
        {
            "role": "assistant",
            "content": [{"type": "text", "text": "Original answer"}],
        },
        {
            "role": "user",
            "content": [{"type": "text", "text": "Follow-up question"}],
        },
    ]


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
                    "name": "read_file",
                    "input": {"path": "README.md"},
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
        lambda calls, max_workers, context=None, tool_catalog=None: batch,
    )

    tool_result_items, had_errors = provider.execute_tool_calls(
        response,
        max_workers=2,
        display=display_spy,
        session_usage=TokenUsage(),
        turn_usage=TokenUsage(),
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
            "name": "read_file",
            "success": False,
            "call_id": "toolu_2",
            "arguments": {"path": "README.md"},
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
    assert display_spy.overload_notices == [(3.0, 1, 1)]
    assert display_spy.rate_limit_notices == []
    assert display_spy.retry_notices == [(1, 1)]


def test_anthropic_request_turn_preserves_error_type_and_request_id(
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
            url=ANTHROPIC_API_URL,
            code=404,
            body=(
                '{"type":"error","error":{"type":"not_found_error",'
                '"message":"The requested resource could not be found."},'
                '"request_id":"req_404"}'
            ),
        )

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)

    provider = AnthropicProvider(_make_settings(max_retries=0))

    with pytest.raises(RuntimeError) as exc_info:
        provider.request_turn(
            user_message="hello",
            display=display_spy,
            session_usage=TokenUsage(),
            turn_usage=TokenUsage(),
        )

    assert str(exc_info.value) == (
        'Anthropic API error 404: {"error": {"message": "The requested resource '
        'could not be found.", "type": "not_found_error"}, "request_id": '
        '"req_404", "status": 404, "type": "error"}'
    )


def test_anthropic_request_turn_uses_request_id_header_for_413_errors(
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
            url=ANTHROPIC_API_URL,
            code=413,
            body="<html>Request Entity Too Large</html>",
            headers={"request-id": "req_413"},
        )

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)

    provider = AnthropicProvider(_make_settings(max_retries=0))

    with pytest.raises(RuntimeError) as exc_info:
        provider.request_turn(
            user_message="hello",
            display=display_spy,
            session_usage=TokenUsage(),
            turn_usage=TokenUsage(),
        )

    assert str(exc_info.value) == (
        'Anthropic API error 413: {"error": {"message": "Request exceeds the '
        'maximum allowed number of bytes.", "type": "request_too_large"}, '
        '"request_id": "req_413", "status": 413, "type": "error"}'
    )


def test_anthropic_request_turn_serializes_user_input_images(
    monkeypatch,
    display_spy,
    make_http_response,
) -> None:
    requests: list[dict[str, object]] = []

    def fake_urlopen(
        request: urllib.request.Request,
        timeout: float,
    ):
        del timeout
        payload = request.data.decode("utf-8") if request.data else "{}"
        requests.append(json.loads(payload))
        return make_http_response(
            {
                "id": "msg_1",
                "content": [{"type": "text", "text": "done"}],
                "usage": {"input_tokens": 1, "output_tokens": 1},
            }
        )

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)

    provider = AnthropicProvider(_make_settings())
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
        display=display_spy,
        session_usage=TokenUsage(),
        turn_usage=TokenUsage(),
    )

    assert requests[0]["messages"][0]["content"] == [
        {
            "type": "image",
            "source": {
                "type": "base64",
                "media_type": "image/png",
                "data": "QUJDRA==",
            },
        },
        {"type": "text", "text": "Describe this image."},
    ]


def test_anthropic_execute_tool_calls_serializes_image_attachments(
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
                    "name": "read_image",
                    "input": {"path": "chart.png"},
                }
            ]
        },
    )
    batch = ToolExecutionBatch(
        results=[
            ToolResult(
                call_id="toolu_1",
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
        "pbi_agent.providers.anthropic_provider._execute_tool_calls",
        lambda calls, max_workers, context=None, tool_catalog=None: batch,
    )

    tool_result_items, had_errors = provider.execute_tool_calls(
        response,
        max_workers=1,
        display=display_spy,
        session_usage=TokenUsage(),
        turn_usage=TokenUsage(),
    )

    assert had_errors is False
    assert tool_result_items == [
        {
            "type": "tool_result",
            "tool_use_id": "toolu_1",
            "content": [
                {
                    "type": "image",
                    "source": {
                        "type": "base64",
                        "media_type": "image/png",
                        "data": "QUJDRA==",
                    },
                },
                {
                    "type": "text",
                    "text": '{"ok": true, "result": {"path": "chart.png"}}',
                },
            ],
        }
    ]


def test_anthropic_web_search_tool_included_when_enabled() -> None:
    provider = AnthropicProvider(_make_settings(web_search=True))
    web_tool = {"type": "web_search_20260209", "name": "web_search"}
    assert web_tool in provider._tools


def test_anthropic_web_search_tool_uses_direct_callers_for_haiku_models() -> None:
    provider = AnthropicProvider(
        _make_settings(web_search=True, model="claude-haiku-4-5")
    )
    assert {
        "type": "web_search_20260209",
        "name": "web_search",
        "allowed_callers": ["direct"],
    } in provider._tools


def test_anthropic_web_search_tool_excluded_when_disabled() -> None:
    provider = AnthropicProvider(_make_settings(web_search=False))
    tool_types = [t.get("type") for t in provider._tools]
    assert "web_search_20260209" not in tool_types


def test_anthropic_parse_response_extracts_web_search_sources() -> None:
    provider = AnthropicProvider(_make_settings())

    result = provider._parse_response(
        {
            "id": "msg_ws",
            "content": [
                {
                    "type": "server_tool_use",
                    "id": "srvtoolu_1",
                    "name": "web_search_20250305",
                    "input": {"query": "test query"},
                },
                {
                    "type": "web_search_tool_result",
                    "tool_use_id": "srvtoolu_1",
                    "content": [
                        {
                            "type": "web_search_result",
                            "title": "Example Page",
                            "url": "https://example.com/page",
                            "page_snippet": "A snippet from the page.",
                        },
                        {
                            "type": "web_search_result",
                            "title": "Another Page",
                            "url": "https://example.com/another",
                            "page_snippet": "Another snippet.",
                        },
                    ],
                },
                {"type": "text", "text": "Here is the answer."},
            ],
            "usage": {
                "input_tokens": 100,
                "output_tokens": 30,
            },
        }
    )

    assert result.text == "Here is the answer."
    assert len(result.web_search_sources) == 2
    assert result.web_search_sources[0].title == "Example Page"
    assert result.web_search_sources[0].url == "https://example.com/page"
    assert result.web_search_sources[0].snippet == "A snippet from the page."
    assert result.web_search_sources[1].title == "Another Page"
    assert result.provider_data["display_items"] == [
        {
            "type": "web_search",
            "queries": ["test query"],
            "sources": [
                {
                    "title": "Example Page",
                    "url": "https://example.com/page",
                    "snippet": "A snippet from the page.",
                },
                {
                    "title": "Another Page",
                    "url": "https://example.com/another",
                    "snippet": "Another snippet.",
                },
            ],
        },
        {"type": "text", "text": "Here is the answer."},
    ]


def test_anthropic_web_search_sources_preserve_duplicate_urls() -> None:
    provider = AnthropicProvider(_make_settings())

    result = provider._parse_response(
        {
            "id": "msg_ws_dup",
            "content": [
                {
                    "type": "web_search_tool_result",
                    "tool_use_id": "srvtoolu_1",
                    "content": [
                        {
                            "type": "web_search_result",
                            "title": "Same Page",
                            "url": "https://example.com/same",
                            "page_snippet": "First snippet.",
                        },
                        {
                            "type": "web_search_result",
                            "title": "Same Page Again",
                            "url": "https://example.com/same",
                            "page_snippet": "Second snippet.",
                        },
                    ],
                },
                {"type": "text", "text": "Answer."},
            ],
            "usage": {
                "input_tokens": 10,
                "output_tokens": 5,
            },
        }
    )

    assert len(result.web_search_sources) == 2
    assert result.web_search_sources[0].url == "https://example.com/same"
    assert result.web_search_sources[1].url == "https://example.com/same"


def test_anthropic_server_tool_use_not_in_function_calls() -> None:
    provider = AnthropicProvider(_make_settings())

    result = provider._parse_response(
        {
            "id": "msg_ws2",
            "content": [
                {
                    "type": "server_tool_use",
                    "id": "srvtoolu_1",
                    "name": "web_search_20250305",
                    "input": {"query": "test"},
                },
                {
                    "type": "web_search_tool_result",
                    "tool_use_id": "srvtoolu_1",
                    "content": [],
                },
                {"type": "text", "text": "Done."},
            ],
            "usage": {
                "input_tokens": 10,
                "output_tokens": 5,
            },
        }
    )

    assert result.function_calls == []


def test_anthropic_request_turn_preserves_web_search_order_from_content_blocks(
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
    ):
        del request, timeout
        return make_http_response(
            {
                "id": "msg_ws_order",
                "content": [
                    {
                        "type": "text",
                        "text": "I'll search for the current Bitcoin price.",
                    },
                    {
                        "type": "server_tool_use",
                        "id": "srvtoolu_1",
                        "name": "web_search",
                        "input": {"query": "bitcoin price"},
                    },
                    {
                        "type": "web_search_tool_result",
                        "tool_use_id": "srvtoolu_1",
                        "content": [
                            {
                                "type": "web_search_result",
                                "title": "BTC",
                                "url": "https://example.com/btc",
                                "page_snippet": "Bitcoin price now.",
                            }
                        ],
                    },
                    {"type": "text", "text": "Bitcoin is $1."},
                ],
                "usage": {"input_tokens": 8, "output_tokens": 3},
            }
        )

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)

    provider = AnthropicProvider(_make_settings(model="claude-haiku-4-5"))
    provider.request_turn(
        user_message="check bitcoin price",
        display=display_spy,
        session_usage=TokenUsage(),
        turn_usage=TokenUsage(),
    )

    assert events == [
        ("message", "I'll search for the current Bitcoin price."),
        ("tool", "web_search"),
        ("message", "Bitcoin is $1."),
    ]


def test_anthropic_request_turn_records_observability(
    monkeypatch,
    display_spy,
    make_http_response,
) -> None:
    tracer = Mock()

    def fake_urlopen(
        request: urllib.request.Request,
        timeout: float,
    ):
        del request, timeout
        return make_http_response(
            {
                "id": "msg_trace",
                "content": [{"type": "text", "text": "Traced."}],
                "usage": {"input_tokens": 7, "output_tokens": 3},
            }
        )

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)

    provider = AnthropicProvider(_make_settings())
    provider.request_turn(
        user_message="hello",
        display=display_spy,
        session_usage=TokenUsage(),
        turn_usage=TokenUsage(),
        tracer=tracer,
    )

    tracer.log_model_call.assert_called_once()
    assert tracer.log_model_call.call_args.kwargs["url"] == ANTHROPIC_API_URL
