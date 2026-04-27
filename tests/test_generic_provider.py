from __future__ import annotations

import json
import urllib.request
from unittest.mock import Mock

from pbi_agent.agent.system_prompt import get_system_prompt
from pbi_agent.agent.tool_runtime import ToolExecutionBatch
from pbi_agent.config import DEFAULT_GENERIC_API_URL, DEFAULT_MAX_TOKENS, Settings
from pbi_agent.models.messages import CompletedResponse, TokenUsage, ToolCall
from pbi_agent.providers.generic_provider import GenericProvider
from pbi_agent.session_store import MessageRecord
from pbi_agent.tools.types import ToolResult


def _make_settings(**overrides: object) -> Settings:
    defaults: dict[str, object] = {
        "api_key": "test-key",
        "provider": "generic",
        "generic_api_url": DEFAULT_GENERIC_API_URL,
        "model": "",
        "max_tokens": DEFAULT_MAX_TOKENS,
        "max_retries": 1,
    }
    defaults.update(overrides)
    return Settings(**defaults)


def test_azure_chat_completions_uses_api_key_header_and_endpoint(
    monkeypatch,
    display_spy,
    make_http_response,
) -> None:
    seen: dict[str, object] = {}

    def fake_urlopen(request: urllib.request.Request, timeout: float):
        del timeout
        seen["url"] = request.full_url
        seen["api_key"] = request.headers.get("Api-key")
        seen["authorization"] = request.get_header("Authorization")
        return make_http_response(
            {
                "id": "chatcmpl_azure",
                "model": "deployment",
                "choices": [{"message": {"role": "assistant", "content": "ok"}}],
            }
        )

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)

    provider = GenericProvider(
        _make_settings(
            provider="azure",
            responses_url="https://mca-resource.openai.azure.com/openai/v1",
            model="deployment",
        )
    )
    provider.request_turn(
        user_message="hi",
        display=display_spy,
        session_usage=TokenUsage(),
        turn_usage=TokenUsage(),
    )

    assert seen == {
        "url": "https://mca-resource.openai.azure.com/openai/v1/chat/completions",
        "api_key": "test-key",
        "authorization": None,
    }

    provider = GenericProvider(_make_settings())

    result = provider._parse_response(
        {
            "id": "chatcmpl_123",
            "model": "openrouter/auto",
            "usage": {
                "prompt_tokens": 21,
                "completion_tokens": 8,
                "completion_tokens_details": {"reasoning_tokens": 3},
            },
            "choices": [
                {
                    "message": {
                        "role": "assistant",
                        "content": [
                            {"type": "text", "text": "First line. "},
                            {"type": "output_text", "text": "Second line."},
                            {"type": "refusal", "refusal": "policy block"},
                        ],
                        "tool_calls": [
                            {
                                "id": "call_1",
                                "type": "function",
                                "function": {
                                    "name": "shell",
                                    "arguments": '{"command":"pwd"}',
                                },
                            },
                            {
                                "id": "call_2",
                                "type": "function",
                                "function": {
                                    "name": "read_file",
                                    "arguments": {"path": "README.md"},
                                },
                            },
                        ],
                    }
                }
            ],
        }
    )

    assert result.response_id == "chatcmpl_123"
    assert result.text == "First line. Second line."
    assert result.function_calls == [
        ToolCall(call_id="call_1", name="shell", arguments={"command": "pwd"}),
        ToolCall(call_id="call_2", name="read_file", arguments={"path": "README.md"}),
    ]
    assert result.usage.input_tokens == 21
    assert result.usage.output_tokens == 8
    assert result.usage.reasoning_tokens == 3
    assert result.usage.model == "openrouter/auto"

    assistant_message = result.provider_data["assistant_message"]
    assert assistant_message["role"] == "assistant"
    assert assistant_message["content"] == [
        {"type": "text", "text": "First line. "},
        {"type": "text", "text": "Second line."},
        {"type": "refusal", "refusal": "policy block"},
    ]
    assert [item["id"] for item in assistant_message["tool_calls"]] == [
        "call_1",
        "call_2",
    ]
    assert json.loads(assistant_message["tool_calls"][0]["function"]["arguments"]) == {
        "command": "pwd"
    }
    assert json.loads(assistant_message["tool_calls"][1]["function"]["arguments"]) == {
        "path": "README.md"
    }


def test_generic_parse_response_merges_split_choice_text_and_tool_calls() -> None:
    provider = GenericProvider(_make_settings())

    result = provider._parse_response(
        {
            "id": "chatcmpl_split",
            "model": "claude-opus-4.6",
            "usage": {"prompt_tokens": 12, "completion_tokens": 4},
            "choices": [
                {
                    "finish_reason": "tool_calls",
                    "message": {
                        "role": "assistant",
                        "content": "Let me inspect the file first.",
                    },
                },
                {
                    "finish_reason": "tool_calls",
                    "message": {
                        "role": "assistant",
                        "tool_calls": [
                            {
                                "id": "toolu_1",
                                "type": "function",
                                "function": {
                                    "name": "read_file",
                                    "arguments": '{"path":"src/app.py"}',
                                },
                            }
                        ],
                    },
                },
            ],
        }
    )

    assert result.text == "Let me inspect the file first."
    assert result.function_calls == [
        ToolCall(call_id="toolu_1", name="read_file", arguments={"path": "src/app.py"})
    ]
    assert result.has_tool_calls is True
    assert result.provider_data["assistant_message"] == {
        "role": "assistant",
        "content": "Let me inspect the file first.",
        "tool_calls": [
            {
                "id": "toolu_1",
                "type": "function",
                "function": {
                    "name": "read_file",
                    "arguments": '{"path":"src/app.py"}',
                },
            }
        ],
    }


def test_generic_request_turn_preserves_history_and_tool_results(
    monkeypatch,
    display_spy,
    make_http_response,
) -> None:
    requests: list[dict[str, object]] = []
    responses = iter(
        [
            {
                "id": "chatcmpl_1",
                "model": "openrouter/auto",
                "usage": {
                    "prompt_tokens": 10,
                    "completion_tokens": 2,
                    "completion_tokens_details": {"reasoning_tokens": 1},
                },
                "choices": [
                    {
                        "message": {
                            "role": "assistant",
                            "content": "Let me check.",
                            "tool_calls": [
                                {
                                    "id": "call_1",
                                    "type": "function",
                                    "function": {
                                        "name": "shell",
                                        "arguments": '{"command":"pwd"}',
                                    },
                                }
                            ],
                        }
                    }
                ],
            },
            {
                "id": "chatcmpl_2",
                "model": "openrouter/auto",
                "usage": {
                    "prompt_tokens": 12,
                    "completion_tokens": 5,
                    "completion_tokens_details": {"reasoning_tokens": 0},
                },
                "choices": [
                    {
                        "message": {
                            "role": "assistant",
                            "content": "You are in /workspace.",
                        }
                    }
                ],
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

    provider = GenericProvider(_make_settings())
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
                "role": "tool",
                "tool_call_id": "call_1",
                "content": '{"ok": true, "result": "/workspace"}',
            }
        ],
        display=display_spy,
        session_usage=session_usage,
        turn_usage=TokenUsage(),
    )

    assert first.response_id == "chatcmpl_1"
    assert second.response_id == "chatcmpl_2"
    assert requests[0] == {
        "messages": [
            {"role": "system", "content": get_system_prompt()},
            {"role": "user", "content": "Where am I?"},
        ],
        "max_tokens": DEFAULT_MAX_TOKENS,
        "tools": provider._tools,
        "tool_choice": "auto",
    }
    assert requests[1] == {
        "messages": [
            {"role": "system", "content": get_system_prompt()},
            {"role": "user", "content": "Where am I?"},
            {
                "role": "assistant",
                "content": "Let me check.",
                "tool_calls": [
                    {
                        "id": "call_1",
                        "type": "function",
                        "function": {
                            "name": "shell",
                            "arguments": '{"command":"pwd"}',
                        },
                    }
                ],
            },
            {
                "role": "tool",
                "tool_call_id": "call_1",
                "content": '{"ok": true, "result": "/workspace"}',
            },
        ],
        "max_tokens": DEFAULT_MAX_TOKENS,
        "tools": provider._tools,
        "tool_choice": "auto",
    }
    assert display_spy.markdown_calls == ["Let me check.", "You are in /workspace."]
    assert display_spy.session_usage_snapshots[-1].input_tokens == 22
    assert display_spy.session_usage_snapshots[-1].output_tokens == 7
    assert display_spy.session_usage_snapshots[-1].reasoning_tokens == 1


def test_generic_restore_messages_reuses_persisted_history(
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
                "id": "chatcmpl_3",
                "model": "openrouter/auto",
                "usage": {
                    "prompt_tokens": 11,
                    "completion_tokens": 4,
                    "completion_tokens_details": {"reasoning_tokens": 0},
                },
                "choices": [
                    {
                        "message": {
                            "role": "assistant",
                            "content": "Follow-up answer.",
                        }
                    }
                ],
            }
        )

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)

    provider = GenericProvider(_make_settings())
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

    assert requests[0] == {
        "messages": [
            {"role": "system", "content": get_system_prompt()},
            {"role": "user", "content": "Original question"},
            {"role": "assistant", "content": "Original answer"},
            {"role": "user", "content": "Follow-up question"},
        ],
        "max_tokens": DEFAULT_MAX_TOKENS,
        "tools": provider._tools,
        "tool_choice": "auto",
    }
    assert display_spy.markdown_calls == ["Follow-up answer."]


def test_generic_execute_tool_calls_returns_chat_completion_tool_messages(
    monkeypatch,
    display_spy,
) -> None:
    provider = GenericProvider(_make_settings())
    response = CompletedResponse(
        response_id="chatcmpl_1",
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
        "pbi_agent.providers.generic_provider._execute_tool_calls",
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
        response,
        max_workers=2,
        display=display_spy,
        session_usage=TokenUsage(),
        turn_usage=TokenUsage(),
    )

    assert had_errors is True
    assert tool_result_items == [
        {
            "role": "tool",
            "tool_call_id": "call_1",
            "content": '{"ok": true, "result": "/workspace"}',
        },
        {
            "role": "tool",
            "tool_call_id": "call_2",
            "content": (
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
            "name": "read_file",
            "success": False,
            "call_id": "call_2",
            "arguments": {"path": "README.md"},
        },
    ]
    assert display_spy.tool_group_end_count == 1


def test_generic_request_turn_retries_after_rate_limit(
    monkeypatch,
    display_spy,
    make_http_error,
    make_http_response,
) -> None:
    requests: list[dict[str, object]] = []
    waits: list[float] = []
    response_payload = {
        "id": "chatcmpl_retry",
        "model": "openrouter/my-model",
        "usage": {
            "prompt_tokens": 6,
            "completion_tokens": 4,
            "completion_tokens_details": {"reasoning_tokens": 0},
        },
        "choices": [
            {
                "message": {
                    "role": "assistant",
                    "content": "Recovered.",
                }
            }
        ],
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
                url=DEFAULT_GENERIC_API_URL,
                code=429,
                body='{"error":"slow down"}',
                headers={"Retry-After": "0.25"},
            )
        return make_http_response(response_payload)

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    monkeypatch.setattr(
        "pbi_agent.providers.generic_provider.time.sleep",
        lambda seconds: waits.append(seconds),
    )

    provider = GenericProvider(
        _make_settings(model="openrouter/my-model", max_retries=1)
    )
    response = provider.request_turn(
        user_message="hello",
        display=display_spy,
        session_usage=TokenUsage(),
        turn_usage=TokenUsage(),
    )

    assert response.text == "Recovered."
    assert len(requests) == 2
    assert requests[0]["model"] == "openrouter/my-model"
    assert requests[1]["model"] == "openrouter/my-model"
    assert waits == [1.25]
    assert display_spy.rate_limit_notices == [(1.25, 1, 1)]
    assert display_spy.retry_notices == [(1, 1)]


def test_generic_request_turn_records_observability(
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
                "id": "chatcmpl_trace",
                "model": "openrouter/auto",
                "usage": {
                    "prompt_tokens": 7,
                    "completion_tokens": 3,
                },
                "choices": [
                    {
                        "message": {
                            "role": "assistant",
                            "content": "Traced.",
                        }
                    }
                ],
            }
        )

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)

    provider = GenericProvider(_make_settings())
    provider.request_turn(
        user_message="hello",
        display=display_spy,
        session_usage=TokenUsage(),
        turn_usage=TokenUsage(),
        tracer=tracer,
    )

    tracer.log_model_call.assert_called_once()
    assert tracer.log_model_call.call_args.kwargs["url"] == DEFAULT_GENERIC_API_URL
