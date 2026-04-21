from __future__ import annotations

from unittest.mock import ANY

import pytest

from pbi_agent.agent.session import run_sub_agent_task
from pbi_agent.models.messages import CompletedResponse, TokenUsage
from pbi_agent.session_store import MessageRecord
from pbi_agent.tools import sub_agent as sub_agent_tool
from pbi_agent.tools.catalog import ToolCatalog
from pbi_agent.tools.types import ParentContextSnapshot, ToolContext
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

    def submit_input(self, value: str, *, image_paths: list[str] | None = None) -> None:
        del value, image_paths

    def request_new_session(self) -> None:
        return None

    def reset_session(self) -> None:
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
        self.previous_response_ids: list[str | None] = []

    def __enter__(self) -> _ProviderStub:
        return self

    def __exit__(self, *_: object) -> None:
        return None

    def set_previous_response_id(self, response_id: str | None) -> None:
        self.previous_response_ids.append(response_id)

    def request_turn(
        self,
        *,
        user_message: str | None = None,
        tool_result_items=None,
        instructions: str | None = None,
        display,
        session_usage: TokenUsage,
        turn_usage: TokenUsage,
        tracer=None,
    ) -> CompletedResponse:
        del tool_result_items, display, tracer
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
        parent_context=None,
        tracer=None,
    ):
        del (
            response,
            max_workers,
            display,
            session_usage,
            turn_usage,
            sub_agent_depth,
            parent_context,
            tracer,
        )
        return [], False


def test_sub_agent_tool_blocks_nested_calls() -> None:
    result = sub_agent_tool.handle(
        {"task_instruction": "Inspect src"},
        ToolContext(sub_agent_depth=1),
    )

    assert result["status"] == "failed"
    assert result["error"]["type"] == "nested_sub_agent_disabled"


def test_sub_agent_tool_passes_agent_type_to_runtime(monkeypatch) -> None:
    captured: dict[str, object] = {}

    def fake_run_sub_agent_task(
        task_instruction: str,
        settings: Settings,
        display,
        *,
        parent_session_usage: TokenUsage,
        parent_turn_usage: TokenUsage,
        sub_agent_depth: int = 0,
        tool_catalog: ToolCatalog | None = None,
        agent_type: str | None = None,
        include_context: bool = False,
        parent_context: ParentContextSnapshot | None = None,
        parent_tracer=None,
    ) -> dict[str, object]:
        del (
            settings,
            display,
            parent_session_usage,
            parent_turn_usage,
            sub_agent_depth,
            parent_tracer,
        )
        captured["task_instruction"] = task_instruction
        captured["tool_catalog"] = tool_catalog
        captured["agent_type"] = agent_type
        captured["include_context"] = include_context
        captured["parent_context"] = parent_context
        return {"status": "completed", "final_output": "done"}

    monkeypatch.setattr(
        "pbi_agent.agent.session.run_sub_agent_task", fake_run_sub_agent_task
    )

    result = sub_agent_tool.handle(
        {
            "task_instruction": "Review the auth changes",
            "agent_type": "code-reviewer",
            "include_context": True,
        },
        ToolContext(
            settings=Settings(api_key="test-key", provider="openai", model="gpt-5"),
            display=_ParentDisplay(),
            session_usage=TokenUsage(model="gpt-5"),
            turn_usage=TokenUsage(model="gpt-5"),
            tool_catalog=ToolCatalog.from_builtin_registry(),
            parent_context=ParentContextSnapshot(
                provider="openai",
                continuation_id="resp_parent",
            ),
        ),
    )

    assert result == {"status": "completed", "final_output": "done"}
    assert captured == {
        "task_instruction": "Review the auth changes",
        "tool_catalog": ANY,
        "agent_type": "code-reviewer",
        "include_context": True,
        "parent_context": ParentContextSnapshot(
            provider="openai",
            continuation_id="resp_parent",
        ),
    }


def test_sub_agent_tool_maps_default_agent_type_to_generalist(monkeypatch) -> None:
    captured: dict[str, object] = {}

    def fake_run_sub_agent_task(
        task_instruction: str,
        settings: Settings,
        display,
        *,
        parent_session_usage: TokenUsage,
        parent_turn_usage: TokenUsage,
        sub_agent_depth: int = 0,
        tool_catalog: ToolCatalog | None = None,
        agent_type: str | None = None,
        include_context: bool = False,
        parent_context: ParentContextSnapshot | None = None,
        parent_tracer=None,
    ) -> dict[str, object]:
        del (
            task_instruction,
            settings,
            display,
            parent_session_usage,
            parent_turn_usage,
            sub_agent_depth,
            tool_catalog,
            include_context,
            parent_context,
            parent_tracer,
        )
        captured["agent_type"] = agent_type
        return {"status": "completed", "final_output": "done"}

    monkeypatch.setattr(
        "pbi_agent.agent.session.run_sub_agent_task", fake_run_sub_agent_task
    )

    result = sub_agent_tool.handle(
        {
            "task_instruction": "Summarize the repo structure",
            "agent_type": "default",
        },
        ToolContext(
            settings=Settings(api_key="test-key", provider="openai", model="gpt-5"),
            display=_ParentDisplay(),
            session_usage=TokenUsage(model="gpt-5"),
            turn_usage=TokenUsage(model="gpt-5"),
            tool_catalog=ToolCatalog.from_builtin_registry(),
        ),
    )

    assert result == {"status": "completed", "final_output": "done"}
    assert captured["agent_type"] is None


def test_sub_agent_tool_rejects_non_boolean_include_context() -> None:
    result = sub_agent_tool.handle(
        {"task_instruction": "Inspect src", "include_context": "yes"},
        ToolContext(),
    )

    assert result["status"] == "failed"
    assert result["error"]["type"] == "invalid_arguments"


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
        tool_catalog=None,
    ) -> _ProviderStub:
        captured["settings"] = settings
        captured["system_prompt"] = system_prompt
        captured["excluded_tools"] = excluded_tools
        captured["tool_catalog"] = tool_catalog
        return _ProviderStub()

    monkeypatch.setattr("pbi_agent.agent.session.create_provider", fake_create_provider)

    parent_display = _ParentDisplay()
    parent_session_usage = TokenUsage(model="gpt-5")
    parent_turn_usage = TokenUsage(model="gpt-5")
    catalog = ToolCatalog.from_builtin_registry()
    settings = Settings(
        api_key="test-key",
        provider="openai",
        model="gpt-5",
        sub_agent_model=sub_agent_model,
        reasoning_effort="xhigh",
    )

    result = run_sub_agent_task(
        "Summarize the repo structure",
        settings,
        parent_display,
        parent_session_usage=parent_session_usage,
        parent_turn_usage=parent_turn_usage,
        tool_catalog=catalog,
    )

    assert result == {
        "status": "completed",
        "final_output": "child complete",
    }
    assert parent_display.sub_agent_calls == [
        {
            "task_instruction": "Summarize the repo structure",
            "reasoning_effort": "xhigh",
            "name": ANY,
        }
    ]
    assert parent_display.child_display.finished_statuses == ["completed"]
    assert parent_session_usage.total_tokens == 6
    assert parent_session_usage.sub_agent_total_tokens == 6
    assert parent_turn_usage.total_tokens == 6
    assert parent_turn_usage.sub_agent_total_tokens == 6
    assert captured["excluded_tools"] == {"sub_agent"}
    assert captured["tool_catalog"] is not None
    assert "delegated sub-agent" in str(captured["system_prompt"])
    assert isinstance(captured["settings"], Settings)
    assert captured["settings"].model == expected_model
    assert captured["settings"].reasoning_effort == "xhigh"


def test_run_sub_agent_task_uses_parent_checkpoint_for_openai_context_inheritance(
    monkeypatch,
) -> None:
    child_provider = _ProviderStub()

    monkeypatch.setattr(
        "pbi_agent.agent.session.create_provider",
        lambda *args, **kwargs: child_provider,
    )

    result = run_sub_agent_task(
        "Summarize the repo structure",
        Settings(api_key="test-key", provider="openai", model="gpt-5"),
        _ParentDisplay(),
        parent_session_usage=TokenUsage(model="gpt-5"),
        parent_turn_usage=TokenUsage(model="gpt-5"),
        tool_catalog=ToolCatalog.from_builtin_registry(),
        include_context=True,
        parent_context=ParentContextSnapshot(
            provider="openai",
            continuation_id="resp_parent",
            current_user_turn="How is the CLI structured?",
        ),
    )

    assert result["status"] == "completed"
    assert child_provider.previous_response_ids == ["resp_parent"]
    assert child_provider.request_messages == ["Summarize the repo structure"]


def test_run_sub_agent_task_falls_back_to_transcript_for_xai_context_inheritance(
    monkeypatch,
) -> None:
    child_provider = _ProviderStub()

    monkeypatch.setattr(
        "pbi_agent.agent.session.create_provider",
        lambda *args, **kwargs: child_provider,
    )

    result = run_sub_agent_task(
        "Summarize the repo structure",
        Settings(api_key="test-key", provider="xai", model="grok-4"),
        _ParentDisplay(),
        parent_session_usage=TokenUsage(model="gpt-5"),
        parent_turn_usage=TokenUsage(model="gpt-5"),
        tool_catalog=ToolCatalog.from_builtin_registry(),
        include_context=True,
        parent_context=ParentContextSnapshot(
            provider="xai",
            continuation_id="resp_parent",
            messages=(
                MessageRecord(
                    id=1,
                    session_id="sess",
                    role="user",
                    content="How is the CLI structured?",
                    created_at="2026-03-27T00:00:00+00:00",
                ),
                MessageRecord(
                    id=2,
                    session_id="sess",
                    role="assistant",
                    content="The CLI routes commands through cli.py.",
                    created_at="2026-03-27T00:00:01+00:00",
                ),
            ),
            current_user_turn="Inspect the sub-agent tool path.",
        ),
    )

    assert result["status"] == "completed"
    assert child_provider.previous_response_ids == []
    assert child_provider.request_messages == [
        "Use the parent conversation below as context for the delegated task.\n\n"
        "<parent_conversation>\n"
        "<user>\n"
        "How is the CLI structured?\n"
        "</user>\n"
        "<assistant>\n"
        "The CLI routes commands through cli.py.\n"
        "</assistant>\n"
        "<user>\n"
        "Inspect the sub-agent tool path.\n"
        "</user>\n"
        "</parent_conversation>\n\n"
        "<delegated_task>\n"
        "Summarize the repo structure\n"
        "</delegated_task>"
    ]


def test_run_sub_agent_task_uses_selected_project_sub_agent_prompt(
    monkeypatch,
) -> None:
    captured: dict[str, object] = {}

    def fake_create_provider(
        settings: Settings,
        *,
        system_prompt: str | None = None,
        excluded_tools: set[str] | None = None,
        tool_catalog=None,
    ) -> _ProviderStub:
        captured["settings"] = settings
        captured["system_prompt"] = system_prompt
        captured["excluded_tools"] = excluded_tools
        captured["tool_catalog"] = tool_catalog
        return _ProviderStub()

    monkeypatch.setattr("pbi_agent.agent.session.create_provider", fake_create_provider)
    monkeypatch.setattr(
        "pbi_agent.agent.session.get_project_sub_agent_by_name",
        lambda name, workspace=None: type(
            "AgentDef",
            (),
            {
                "name": name,
                "description": "Reviews code.",
                "system_prompt": "You are a code reviewer.",
            },
        )(),
    )

    parent_display = _ParentDisplay()
    settings = Settings(api_key="test-key", provider="openai", model="gpt-5")

    result = run_sub_agent_task(
        "Review the latest patch",
        settings,
        parent_display,
        parent_session_usage=TokenUsage(model="gpt-5"),
        parent_turn_usage=TokenUsage(model="gpt-5"),
        tool_catalog=ToolCatalog.from_builtin_registry(),
        agent_type="code-reviewer",
    )

    assert result["status"] == "completed"
    assert parent_display.sub_agent_calls[0]["name"] == "code-reviewer"
    assert "You are a code reviewer." in str(captured["system_prompt"])
    assert isinstance(captured["settings"], Settings)
    assert captured["settings"].model == "gpt-5"
    assert captured["settings"].reasoning_effort == settings.reasoning_effort


def test_run_sub_agent_task_rejects_unknown_agent_type() -> None:
    result = run_sub_agent_task(
        "Review the latest patch",
        Settings(api_key="test-key", provider="openai", model="gpt-5"),
        _ParentDisplay(),
        parent_session_usage=TokenUsage(model="gpt-5"),
        parent_turn_usage=TokenUsage(model="gpt-5"),
        tool_catalog=ToolCatalog.from_builtin_registry(),
        agent_type="missing-agent",
    )

    assert result["status"] == "failed"
    assert result["error"]["type"] == "unknown_agent_type"
