from __future__ import annotations

from unittest.mock import ANY

import pytest

from pbi_agent.agent.session import run_sub_agent_task
from pbi_agent.models.messages import CompletedResponse, TokenUsage
from pbi_agent.tools import sub_agent as sub_agent_tool
from pbi_agent.tools.types import ToolContext
from pbi_agent.config import Settings


class _ChildDisplay:
    def __init__(self) -> None:
        self.finished_statuses: list[str] = []

    def begin_sub_agent(
        self,
        *,
        task_instruction: str,
        reasoning_effort: str | None = None,
        name: str = "sub_agent",
    ) -> _ChildDisplay:
        del task_instruction, reasoning_effort, name
        return self

    def finish_sub_agent(self, *, status: str) -> None:
        self.finished_statuses.append(status)

    def session_usage(self, usage: TokenUsage) -> None:
        self.session_usage_snapshot = usage.snapshot()

    def turn_usage(self, usage: TokenUsage, elapsed_seconds: float) -> None:
        self.turn_usage_snapshot = (usage.snapshot(), elapsed_seconds)

    def wait_start(self, message: str = "") -> None:
        self.last_wait_message = message

    def wait_stop(self) -> None:
        self.wait_stopped = True

    def render_markdown(self, text: str) -> None:
        self.markdown = text

    def render_thinking(self, *args, **kwargs):  # type: ignore[no-untyped-def]
        del args, kwargs
        return None

    def render_redacted_thinking(self) -> None:
        self.redacted = True

    def function_start(self, count: int) -> None:
        self.function_count = count

    def function_result(self, *args, **kwargs) -> None:  # type: ignore[no-untyped-def]
        del args, kwargs

    def tool_group_end(self) -> None:
        self.tool_group_closed = True

    def retry_notice(self, attempt: int, max_retries: int) -> None:
        self.retry = (attempt, max_retries)

    def rate_limit_notice(
        self, *, wait_seconds: float, attempt: int, max_retries: int
    ) -> None:
        self.rate_limit = (wait_seconds, attempt, max_retries)

    def overload_notice(
        self, *, wait_seconds: float, attempt: int, max_retries: int
    ) -> None:
        self.overload = (wait_seconds, attempt, max_retries)

    def error(self, message: str) -> None:
        self.error_message = message

    def debug(self, message: str) -> None:
        self.debug_message = message

    def request_shutdown(self) -> None:
        return None

    def submit_input(self, value: str) -> None:
        del value

    def request_new_chat(self) -> None:
        return None

    def reset_chat(self) -> None:
        return None

    def welcome(self, **kwargs) -> None:  # type: ignore[no-untyped-def]
        del kwargs

    def user_prompt(self) -> str:
        raise RuntimeError("not supported")

    def assistant_start(self) -> None:
        return None


class _ParentDisplay:
    def __init__(self) -> None:
        self.child_display = _ChildDisplay()
        self.sub_agent_calls: list[dict[str, str | None]] = []
        self.session_usage_calls: list[TokenUsage] = []

    def begin_sub_agent(
        self,
        *,
        task_instruction: str,
        reasoning_effort: str | None = None,
        name: str = "sub_agent",
    ) -> _ChildDisplay:
        self.sub_agent_calls.append(
            {
                "task_instruction": task_instruction,
                "reasoning_effort": reasoning_effort,
                "name": name,
            }
        )
        return self.child_display

    def finish_sub_agent(self, *, status: str) -> None:
        del status

    def session_usage(self, usage: TokenUsage) -> None:
        self.session_usage_calls.append(usage.snapshot())


class _ProviderStub:
    def __init__(self) -> None:
        self.request_messages: list[str | None] = []

    def __enter__(self) -> _ProviderStub:
        return self

    def __exit__(self, *_: object) -> None:
        return None

    def request_turn(
        self,
        *,
        user_message: str | None = None,
        tool_result_items=None,
        instructions: str | None = None,
        display,
        session_usage: TokenUsage,
        turn_usage: TokenUsage,
    ) -> CompletedResponse:
        del tool_result_items, display
        self.request_messages.append(user_message)
        self.instructions = instructions
        response = CompletedResponse(
            response_id="resp_child",
            text="child complete",
            usage=TokenUsage(input_tokens=4, output_tokens=2, model="gpt-5"),
        )
        session_usage.add(response.usage)
        turn_usage.add(response.usage)
        return response

    def execute_tool_calls(
        self,
        response: CompletedResponse,
        *,
        max_workers: int,
        display,
        session_usage: TokenUsage,
        turn_usage: TokenUsage,
        sub_agent_depth: int = 0,
    ):
        del response, max_workers, display, session_usage, turn_usage, sub_agent_depth
        return [], False


def test_sub_agent_tool_blocks_nested_calls() -> None:
    result = sub_agent_tool.handle(
        {"task_instruction": "Inspect src", "reasoning_effort": "medium"},
        ToolContext(sub_agent_depth=1),
    )

    assert result["status"] == "failed"
    assert result["error"]["type"] == "nested_sub_agent_disabled"


@pytest.mark.parametrize(
    ("sub_agent_model", "expected_model"),
    [
        ("gpt-5-mini", "gpt-5-mini"),
        (None, "gpt-5"),
    ],
)
def test_run_sub_agent_task_uses_child_prompt_and_aggregates_usage(
    monkeypatch, sub_agent_model: str | None, expected_model: str
) -> None:
    captured: dict[str, object] = {}

    def fake_create_provider(
        settings: Settings,
        *,
        system_prompt: str | None = None,
        excluded_tools: set[str] | None = None,
    ) -> _ProviderStub:
        captured["settings"] = settings
        captured["system_prompt"] = system_prompt
        captured["excluded_tools"] = excluded_tools
        return _ProviderStub()

    monkeypatch.setattr("pbi_agent.agent.session.create_provider", fake_create_provider)

    parent_display = _ParentDisplay()
    parent_session_usage = TokenUsage(model="gpt-5")
    parent_turn_usage = TokenUsage(model="gpt-5")
    settings = Settings(
        api_key="test-key",
        provider="openai",
        model="gpt-5",
        sub_agent_model=sub_agent_model,
    )

    result = run_sub_agent_task(
        "Summarize the repo structure",
        settings,
        parent_display,
        reasoning_effort="medium",
        parent_session_usage=parent_session_usage,
        parent_turn_usage=parent_turn_usage,
    )

    assert result == {
        "status": "completed",
        "final_output": "child complete",
    }
    assert parent_display.sub_agent_calls == [
        {
            "task_instruction": "Summarize the repo structure",
            "reasoning_effort": "medium",
            "name": ANY,
        }
    ]
    assert parent_display.child_display.finished_statuses == ["completed"]
    assert parent_session_usage.total_tokens == 6
    assert parent_session_usage.sub_agent_total_tokens == 6
    assert parent_turn_usage.total_tokens == 6
    assert parent_turn_usage.sub_agent_total_tokens == 6
    assert captured["excluded_tools"] == {"sub_agent"}
    assert "delegated sub-agent" in str(captured["system_prompt"])
    assert isinstance(captured["settings"], Settings)
    assert captured["settings"].model == expected_model
    assert captured["settings"].reasoning_effort == "medium"
