from __future__ import annotations

import json
import urllib.request

from pbi_agent.auth.models import OAuthSessionAuth
from pbi_agent.auth.providers.github_copilot import GITHUB_COPILOT_RESPONSES_URL
from pbi_agent.config import DEFAULT_MAX_TOKENS, Settings
from pbi_agent.models.messages import TokenUsage, UserTurnInput
from pbi_agent.providers.github_copilot_backend import (
    GITHUB_COPILOT_CHAT_COMPLETIONS_URL,
)
from pbi_agent.providers.github_copilot_provider import GitHubCopilotProvider


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

    def render_thinking(self, *_: object, **__: object) -> str | None:
        return None

    def render_markdown(self, text: str) -> None:
        self.markdown = text

    def function_start(self, count: int) -> None:
        self.function_count = count

    def function_result(self, **_: object) -> None:
        return None

    def tool_group_end(self) -> None:
        return None

    def web_search_sources(self, _: object) -> None:
        return None


class _FakeHTTPResponse:
    def __init__(self, payload: str, *, headers: dict[str, str] | None = None) -> None:
        self._payload = payload
        self.headers = headers or {}

    def read(self) -> bytes:
        return self._payload.encode("utf-8")

    def __enter__(self) -> _FakeHTTPResponse:
        return self

    def __exit__(self, *_: object) -> None:
        return None


def _make_settings(**overrides: object) -> Settings:
    defaults: dict[str, object] = {
        "api_key": "",
        "auth": OAuthSessionAuth(
            provider_id="copilot-main",
            backend="github_copilot",
            access_token="gho_test_token",
            refresh_token=None,
            plan_type="github_copilot",
        ),
        "provider": "github_copilot",
        "responses_url": GITHUB_COPILOT_RESPONSES_URL,
        "model": "gpt-5.4",
        "max_tokens": DEFAULT_MAX_TOKENS,
        "reasoning_effort": "high",
        "max_retries": 0,
        "compact_threshold": 150000,
    }
    defaults.update(overrides)
    return Settings(**defaults)


def test_github_copilot_openai_model_uses_responses_headers_and_omits_max_tokens(
    monkeypatch,
) -> None:
    request_details: dict[str, object] = {}

    def fake_urlopen(
        request: urllib.request.Request,
        timeout: float,
    ) -> _FakeHTTPResponse:
        del timeout
        request_details["url"] = request.full_url
        request_details["headers"] = dict(request.header_items())
        request_details["body"] = json.loads(request.data.decode("utf-8"))
        return _FakeHTTPResponse(
            """event: response.created
data: {"type":"response.created","response":{"id":"resp_1","model":"gpt-5.4","created_at":1}}

event: response.output_item.added
data: {"type":"response.output_item.added","output_index":0,"item":{"type":"message","id":"msg_1"}}

event: response.output_text.delta
data: {"type":"response.output_text.delta","item_id":"enc_a","delta":"Hello"}

event: response.output_text.delta
data: {"type":"response.output_text.delta","item_id":"enc_b","delta":" world"}

event: response.output_item.done
data: {"type":"response.output_item.done","output_index":0,"item":{"type":"message","id":"msg_1"}}

event: response.completed
data: {"type":"response.completed","response":{"id":"resp_1","model":"gpt-5.4","usage":{"input_tokens":5,"input_tokens_details":{"cached_tokens":0},"output_tokens":3,"output_tokens_details":{"reasoning_tokens":0},"total_tokens":8}}}

"""
        )

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)

    provider = GitHubCopilotProvider(_make_settings())
    display = _DisplayStub()
    session_usage = TokenUsage(model="gpt-5.4")
    turn_usage = TokenUsage(model="gpt-5.4")

    response = provider.request_turn(
        user_input=UserTurnInput(text="Hello"),
        session_id="session-123",
        display=display,
        session_usage=session_usage,
        turn_usage=turn_usage,
    )

    headers = request_details["headers"]
    body = request_details["body"]

    assert response.text == "Hello world"
    assert request_details["url"] == GITHUB_COPILOT_RESPONSES_URL
    assert headers["Authorization"] == "Bearer gho_test_token"
    assert headers["Accept"] == "text/event-stream"
    assert headers["Openai-intent"] == "conversation-edits"
    assert headers["X-initiator"] == "user"
    assert "max_output_tokens" not in body
    assert "store" not in body
    assert "prompt_cache_retention" not in body
    assert "context_management" not in body
    assert body["stream"] is True


def test_github_copilot_openai_model_replays_local_history_without_previous_response_id(
    monkeypatch,
) -> None:
    request_bodies: list[dict[str, object]] = []
    responses = [
        """event: response.created
data: {"type":"response.created","response":{"id":"resp_1","model":"gpt-5.4","created_at":1}}

event: response.output_item.added
data: {"type":"response.output_item.added","output_index":0,"item":{"type":"message","id":"msg_1"}}

event: response.output_text.delta
data: {"type":"response.output_text.delta","item_id":"enc_a","delta":"First"}

event: response.output_item.done
data: {"type":"response.output_item.done","output_index":0,"item":{"type":"message","id":"msg_1"}}

event: response.completed
data: {"type":"response.completed","response":{"id":"resp_1","model":"gpt-5.4","usage":{"input_tokens":5,"input_tokens_details":{"cached_tokens":0},"output_tokens":1,"output_tokens_details":{"reasoning_tokens":0},"total_tokens":6}}}

""",
        """event: response.created
data: {"type":"response.created","response":{"id":"resp_2","model":"gpt-5.4","created_at":2}}

event: response.output_item.added
data: {"type":"response.output_item.added","output_index":0,"item":{"type":"message","id":"msg_2"}}

event: response.output_text.delta
data: {"type":"response.output_text.delta","item_id":"enc_b","delta":"Second"}

event: response.output_item.done
data: {"type":"response.output_item.done","output_index":0,"item":{"type":"message","id":"msg_2"}}

event: response.completed
data: {"type":"response.completed","response":{"id":"resp_2","model":"gpt-5.4","usage":{"input_tokens":9,"input_tokens_details":{"cached_tokens":0},"output_tokens":1,"output_tokens_details":{"reasoning_tokens":0},"total_tokens":10}}}

""",
    ]

    def fake_urlopen(
        request: urllib.request.Request,
        timeout: float,
    ) -> _FakeHTTPResponse:
        del timeout
        request_bodies.append(json.loads(request.data.decode("utf-8")))
        return _FakeHTTPResponse(responses[len(request_bodies) - 1])

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)

    provider = GitHubCopilotProvider(_make_settings())
    display = _DisplayStub()

    provider.request_turn(
        user_input=UserTurnInput(text="Hello"),
        display=display,
        session_usage=TokenUsage(model="gpt-5.4"),
        turn_usage=TokenUsage(model="gpt-5.4"),
    )
    provider.request_turn(
        user_input=UserTurnInput(text="Again"),
        display=display,
        session_usage=TokenUsage(model="gpt-5.4"),
        turn_usage=TokenUsage(model="gpt-5.4"),
    )

    second_body = request_bodies[1]
    second_input = second_body["input"]

    assert "previous_response_id" not in second_body
    assert isinstance(second_input, list)
    assert len(second_input) >= 3
    assert any(item.get("role") == "assistant" for item in second_input)
    assert any(
        item.get("role") == "user" and item.get("content") == "Hello"
        for item in second_input
        if isinstance(item, dict)
    )
    assert any(
        item.get("role") == "user" and item.get("content") == "Again"
        for item in second_input
        if isinstance(item, dict)
    )


def test_github_copilot_non_openai_model_uses_chat_completions(
    monkeypatch,
) -> None:
    request_details: dict[str, object] = {}

    def fake_urlopen(
        request: urllib.request.Request,
        timeout: float,
    ) -> _FakeHTTPResponse:
        del timeout
        request_details["url"] = request.full_url
        request_details["headers"] = dict(request.header_items())
        request_details["body"] = json.loads(request.data.decode("utf-8"))
        return _FakeHTTPResponse(
            json.dumps(
                {
                    "id": "chatcmpl_1",
                    "model": "claude-sonnet-4",
                    "choices": [
                        {
                            "index": 0,
                            "message": {
                                "role": "assistant",
                                "content": "Hello from Claude",
                            },
                            "finish_reason": "stop",
                        }
                    ],
                    "usage": {
                        "prompt_tokens": 7,
                        "completion_tokens": 4,
                        "total_tokens": 11,
                    },
                }
            )
        )

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)

    provider = GitHubCopilotProvider(_make_settings(model="claude-sonnet-4"))
    display = _DisplayStub()
    session_usage = TokenUsage(model="claude-sonnet-4")
    turn_usage = TokenUsage(model="claude-sonnet-4")

    response = provider.request_turn(
        user_input=UserTurnInput(text="Hello"),
        display=display,
        session_usage=session_usage,
        turn_usage=turn_usage,
    )

    headers = request_details["headers"]
    body = request_details["body"]

    assert response.text == "Hello from Claude"
    assert request_details["url"] == GITHUB_COPILOT_CHAT_COMPLETIONS_URL
    assert headers["Authorization"] == "Bearer gho_test_token"
    assert headers["Accept"] == "application/json"
    assert headers["Openai-intent"] == "conversation-edits"
    assert headers["X-initiator"] == "user"
    assert body["model"] == "claude-sonnet-4"
    assert body["stream"] is False
    assert body["messages"][1] == {"role": "user", "content": "Hello"}


def test_github_copilot_parser_uses_output_index_for_function_calls_and_reasoning(
    monkeypatch,
) -> None:
    def fake_urlopen(
        request: urllib.request.Request,
        timeout: float,
    ) -> _FakeHTTPResponse:
        del request, timeout
        return _FakeHTTPResponse(
            """event: response.created
data: {"type":"response.created","response":{"id":"resp_2","model":"gpt-5.4","created_at":1}}

event: response.output_item.added
data: {"type":"response.output_item.added","output_index":0,"item":{"type":"reasoning","id":"rs_1","encrypted_content":"opaque"}}

event: response.reasoning_summary_part.added
data: {"type":"response.reasoning_summary_part.added","item_id":"enc_rs_1","summary_index":0}

event: response.reasoning_summary_text.delta
data: {"type":"response.reasoning_summary_text.delta","item_id":"enc_rs_2","summary_index":0,"delta":"Thinking"}

event: response.output_item.done
data: {"type":"response.output_item.done","output_index":0,"item":{"type":"reasoning","id":"rs_1","encrypted_content":"opaque"}}

event: response.output_item.added
data: {"type":"response.output_item.added","output_index":1,"item":{"type":"function_call","id":"fc_1","call_id":"call_1","name":"read_file","arguments":""}}

event: response.function_call_arguments.delta
data: {"type":"response.function_call_arguments.delta","item_id":"enc_fc_1","output_index":1,"delta":"{\\"path\\":\\"README.md\\"}"}

event: response.output_item.done
data: {"type":"response.output_item.done","output_index":1,"item":{"type":"function_call","id":"fc_2","call_id":"call_1","name":"read_file","arguments":"{\\"path\\":\\"README.md\\"}","status":"completed"}}

event: response.completed
data: {"type":"response.completed","response":{"id":"resp_2","model":"gpt-5.4","usage":{"input_tokens":5,"input_tokens_details":{"cached_tokens":0},"output_tokens":3,"output_tokens_details":{"reasoning_tokens":1},"total_tokens":8}}}

"""
        )

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)

    provider = GitHubCopilotProvider(_make_settings())
    display = _DisplayStub()
    session_usage = TokenUsage(model="gpt-5.4")
    turn_usage = TokenUsage(model="gpt-5.4")

    response = provider.request_turn(
        user_input=UserTurnInput(text="Inspect"),
        display=display,
        session_usage=session_usage,
        turn_usage=turn_usage,
    )

    assert response.reasoning_summary == "Thinking"
    assert len(response.function_calls) == 1
    assert response.function_calls[0].call_id == "call_1"
    assert response.function_calls[0].name == "read_file"
    assert response.function_calls[0].arguments == {"path": "README.md"}
