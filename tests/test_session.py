from __future__ import annotations

from contextlib import contextmanager
import json
import os
from pathlib import Path
import urllib.error
import urllib.request

import pytest

from pbi_agent.agent.skill_discovery import format_project_skills_markdown
from pbi_agent.agent import session as session_module
from pbi_agent.agent.compaction_prompt import COMPACTION_PROMPT
from pbi_agent.agent.system_prompt import get_system_prompt
from pbi_agent.agent.session import (
    AGENTS_COMMAND,
    AGENTS_RELOAD_COMMAND,
    MCP_COMMAND,
    COMPACT_COMMAND,
    COMPACTION_MARKER,
    _open_compaction_provider,
    NEW_SESSION_SENTINEL,
    _resume_session,
    SKILLS_COMMAND,
    run_session_loop,
    run_sub_agent_task,
    run_single_turn,
)
from pbi_agent.config import (
    DEFAULT_GOOGLE_INTERACTIONS_URL,
    DEFAULT_GOOGLE_MODEL,
    DEFAULT_MAX_TOKENS,
    DEFAULT_MODEL,
    Settings,
)
from pbi_agent.models.messages import (
    CompletedResponse,
    ImageAttachment,
    TokenUsage,
    ToolCall,
    UserTurnInput,
)
from pbi_agent.observability import RunTracer
from pbi_agent.providers.google_provider import GoogleProvider
from pbi_agent.providers.openai_provider import OpenAIProvider
from pbi_agent.session_store import SessionStore
from pbi_agent.tools.catalog import ToolCatalog
from pbi_agent.display.protocol import QueuedInput


def _write_command(root, name: str, content: str) -> None:
    commands_dir = root / ".agents" / "commands"
    commands_dir.mkdir(parents=True, exist_ok=True)
    (commands_dir / f"{name}.md").write_text(content, encoding="utf-8")


class _DisplaySpy:
    def __init__(self) -> None:
        self.welcome_calls: list[dict[str, object | None]] = []
        self.session_usage_calls: list[TokenUsage] = []
        self.turn_usage_calls: list[tuple[TokenUsage, float]] = []
        self.debug_messages: list[str] = []
        self.markdown_calls: list[str] = []
        self.reset_session_calls = 0
        self.assistant_start_calls = 0
        self.assistant_stop_calls = 0
        self.wait_stop_calls = 0

    def welcome(
        self,
        *,
        interactive: bool = True,
        model: str | None = None,
        reasoning_effort: str | None = None,
        single_turn_hint: str | None = None,
    ) -> None:
        self.welcome_calls.append(
            {
                "interactive": interactive,
                "model": model,
                "reasoning_effort": reasoning_effort,
                "single_turn_hint": single_turn_hint,
            }
        )

    def session_usage(self, usage: TokenUsage) -> None:
        self.session_usage_calls.append(usage.snapshot())

    def turn_usage(self, usage: TokenUsage, elapsed_seconds: float) -> None:
        self.turn_usage_calls.append((usage.snapshot(), elapsed_seconds))

    def debug(self, message: str) -> None:
        self.debug_messages.append(message)

    def render_markdown(self, text: str) -> None:
        self.markdown_calls.append(text)

    def reset_session(self) -> None:
        self.reset_session_calls += 1

    def assistant_start(self) -> None:
        self.assistant_start_calls += 1

    def assistant_stop(self) -> None:
        self.assistant_stop_calls += 1

    def replay_history(self, messages) -> None:
        pass

    def begin_sub_agent(
        self,
        *,
        task_instruction: str,
        reasoning_effort: str | None = None,
        name: str = "sub_agent",
    ) -> _DisplaySpy:
        del task_instruction, reasoning_effort, name
        return self

    def finish_sub_agent(self, *, status: str) -> None:
        del status


class _ProviderStub:
    def __init__(self, *, tool_name: str = "shell") -> None:
        self.connected = False
        self.request_calls: list[dict[str, object | None]] = []
        self.execute_calls: list[dict[str, object]] = []
        self.previous_response_ids: list[str | None] = []
        self.conversation_checkpoint = "resp_current"
        self.settings = Settings(api_key="test-key", provider="openai")
        self.tool_name = tool_name

    def __enter__(self) -> _ProviderStub:
        self.connect()
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def connect(self) -> None:
        self.connected = True

    def close(self) -> None:
        self.connected = False

    def get_conversation_checkpoint(self) -> str | None:
        return self.conversation_checkpoint

    def set_previous_response_id(self, response_id: str | None) -> None:
        self.previous_response_ids.append(response_id)

    def restore_messages(self, messages) -> None:
        self.restored_messages = list(messages)

    def request_turn(
        self,
        *,
        user_message: str | None = None,
        user_input: UserTurnInput | None = None,
        tool_result_items: list[dict[str, object]] | None = None,
        instructions: str | None = None,
        session_id: str | None = None,
        display,
        session_usage: TokenUsage,
        turn_usage: TokenUsage,
        tracer=None,
    ) -> CompletedResponse:
        if user_input is not None and user_message is None:
            user_message = user_input.text
        self.request_calls.append(
            {
                "user_message": user_message,
                "tool_result_items": tool_result_items,
                "instructions": instructions,
                "session_id": session_id,
            }
        )
        del display, tracer
        if user_message is not None:
            response = CompletedResponse(
                response_id="resp_1",
                text="",
                usage=TokenUsage(input_tokens=5, output_tokens=1, model=DEFAULT_MODEL),
                function_calls=[
                    ToolCall(
                        call_id="call_1",
                        name=self.tool_name,
                        arguments=(
                            {"command": "pwd"}
                            if self.tool_name == "shell"
                            else {"task_instruction": "Inspect the workspace"}
                        ),
                    )
                ],
            )
        else:
            response = CompletedResponse(
                response_id="resp_2",
                text="All set.",
                usage=TokenUsage(input_tokens=3, output_tokens=2, model=DEFAULT_MODEL),
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
    ) -> tuple[list[dict[str, object]], bool]:
        del display, session_usage, turn_usage, sub_agent_depth, tracer
        self.execute_calls.append(
            {
                "response_id": response.response_id,
                "max_workers": max_workers,
                "call_count": len(response.function_calls),
                "parent_context": parent_context,
            }
        )
        return (
            [
                {
                    "type": "function_call_output",
                    "call_id": "call_1",
                    "output": '{"ok": true, "result": "/workspace"}',
                }
            ],
            True,
        )


def _stub_runtime_provider(provider):
    @contextmanager
    def _open_runtime_provider(*args, **kwargs):
        del args, kwargs
        yield provider

    return _open_runtime_provider


def test_run_single_turn_executes_tool_loop_and_aggregates_usage(monkeypatch) -> None:
    provider = _ProviderStub()
    display = _DisplaySpy()
    settings = Settings(api_key="test-key", provider="openai", max_tool_workers=3)
    monotonic_values = iter([10.0, 13.5])

    monkeypatch.setattr(
        "pbi_agent.agent.session._open_runtime_provider",
        _stub_runtime_provider(provider),
    )
    monkeypatch.setattr(
        "pbi_agent.agent.session.time.monotonic",
        lambda: next(monotonic_values),
    )

    outcome = run_single_turn(
        "Inspect the workspace",
        settings,
        display,
        single_turn_hint="Single-turn test",
    )

    assert outcome.response_id == "resp_2"
    assert outcome.text == "All set."
    assert outcome.tool_errors is True
    assert provider.request_calls == [
        {
            "user_message": "Inspect the workspace",
            "tool_result_items": None,
            "instructions": None,
            "session_id": outcome.session_id,
        },
        {
            "user_message": None,
            "tool_result_items": [
                {
                    "type": "function_call_output",
                    "call_id": "call_1",
                    "output": '{"ok": true, "result": "/workspace"}',
                }
            ],
            "instructions": None,
            "session_id": outcome.session_id,
        },
    ]
    assert len(provider.execute_calls) == 1
    assert provider.execute_calls[0]["response_id"] == "resp_1"
    assert provider.execute_calls[0]["max_workers"] == 3
    assert provider.execute_calls[0]["call_count"] == 1
    assert provider.execute_calls[0]["parent_context"] is None
    assert display.welcome_calls == [
        {
            "interactive": False,
            "model": DEFAULT_MODEL,
            "reasoning_effort": "xhigh",
            "single_turn_hint": "Single-turn test",
        }
    ]
    assert display.debug_messages == ["model requested tool execution"]
    assert display.session_usage_calls[0].total_tokens == 0
    assert display.session_usage_calls[-1].input_tokens == 8
    assert display.session_usage_calls[-1].output_tokens == 3
    assert display.turn_usage_calls == [
        (
            TokenUsage(
                input_tokens=8,
                output_tokens=3,
                model=DEFAULT_MODEL,
            ),
            3.5,
        )
    ]


def test_run_single_turn_uses_command_specific_instructions_for_full_turn(
    monkeypatch,
    tmp_path,
) -> None:
    monkeypatch.chdir(tmp_path)
    provider = _ProviderStub()
    display = _DisplaySpy()
    settings = Settings(api_key="test-key", provider="openai", max_tool_workers=3)
    monotonic_values = iter([10.0, 13.5])
    _write_command(tmp_path, "plan", "Plan before coding.")

    monkeypatch.setattr(
        "pbi_agent.agent.session._open_runtime_provider",
        _stub_runtime_provider(provider),
    )
    monkeypatch.setattr(
        "pbi_agent.agent.session.time.monotonic",
        lambda: next(monotonic_values),
    )

    run_single_turn("/plan inspect the workspace", settings, display)

    assert provider.request_calls[0]["user_message"] == "/plan inspect the workspace"
    assert provider.request_calls[0]["instructions"] is not None
    assert provider.request_calls[0]["session_id"] is not None
    assert "<active_command>\nPlan before coding.\n</active_command>" in str(
        provider.request_calls[0]["instructions"]
    )
    assert (
        provider.request_calls[1]["instructions"]
        == provider.request_calls[0]["instructions"]
    )
    assert (
        provider.request_calls[1]["session_id"]
        == provider.request_calls[0]["session_id"]
    )


def test_run_single_turn_uses_command_instructions_when_body_starts_on_next_line(
    monkeypatch,
    tmp_path,
) -> None:
    monkeypatch.chdir(tmp_path)
    provider = _ProviderStub()
    display = _DisplaySpy()
    settings = Settings(api_key="test-key", provider="openai", max_tool_workers=3)
    monotonic_values = iter([10.0, 13.5])
    _write_command(tmp_path, "plan", "Plan before coding.")

    monkeypatch.setattr(
        "pbi_agent.agent.session._open_runtime_provider",
        _stub_runtime_provider(provider),
    )
    monkeypatch.setattr(
        "pbi_agent.agent.session.time.monotonic",
        lambda: next(monotonic_values),
    )

    prompt = "/plan\n# Task\nTask A\n\n## Goal\nInvestigate"
    run_single_turn(prompt, settings, display)

    assert provider.request_calls[0]["user_message"] == prompt
    assert provider.request_calls[0]["instructions"] is not None
    assert "<active_command>\nPlan before coding.\n</active_command>" in str(
        provider.request_calls[0]["instructions"]
    )


def test_run_single_turn_does_not_activate_command_when_command_file_is_missing(
    monkeypatch,
    tmp_path,
) -> None:
    monkeypatch.chdir(tmp_path)
    provider = _ProviderStub()
    display = _DisplaySpy()
    settings = Settings(api_key="test-key", provider="openai", max_tool_workers=3)
    monotonic_values = iter([10.0, 13.5])

    monkeypatch.setattr(
        "pbi_agent.agent.session._open_runtime_provider",
        _stub_runtime_provider(provider),
    )
    monkeypatch.setattr(
        "pbi_agent.agent.session.time.monotonic",
        lambda: next(monotonic_values),
    )

    run_single_turn("/plan inspect the workspace", settings, display)

    assert provider.request_calls[0]["user_message"] == "/plan inspect the workspace"
    assert provider.request_calls[0]["instructions"] is None


def test_run_single_turn_persists_provider_checkpoint_for_resume(
    monkeypatch,
    tmp_path,
) -> None:
    db_path = tmp_path / "sessions.db"
    monkeypatch.setenv("PBI_AGENT_SESSION_DB_PATH", str(db_path))

    provider = _ProviderStub()
    provider.conversation_checkpoint = "resp_resume"
    display = _DisplaySpy()
    settings = Settings(api_key="test-key", provider="openai", max_tool_workers=3)
    monotonic_values = iter([10.0, 13.5])

    monkeypatch.setattr(
        "pbi_agent.agent.session._open_runtime_provider",
        _stub_runtime_provider(provider),
    )
    monkeypatch.setattr(
        "pbi_agent.agent.session.time.monotonic",
        lambda: next(monotonic_values),
    )

    outcome = run_single_turn("Inspect the workspace", settings, display)

    with SessionStore(db_path=db_path) as store:
        session = store.get_session(outcome.session_id)

    assert session is not None
    assert session.previous_id == "resp_resume"


def test_run_single_turn_persists_observability_run_and_events(
    monkeypatch,
    tmp_path,
) -> None:
    db_path = tmp_path / "sessions.db"
    monkeypatch.setenv("PBI_AGENT_SESSION_DB_PATH", str(db_path))

    provider = _ProviderStub()
    display = _DisplaySpy()
    settings = Settings(api_key="test-key", provider="openai", max_tool_workers=3)
    monotonic_values = iter([10.0, 13.5])

    monkeypatch.setattr(
        "pbi_agent.agent.session._open_runtime_provider",
        _stub_runtime_provider(provider),
    )
    monkeypatch.setattr(
        "pbi_agent.agent.session.time.monotonic",
        lambda: next(monotonic_values),
    )

    outcome = run_single_turn("Inspect the workspace", settings, display)

    with SessionStore(db_path=db_path) as store:
        runs = store.list_run_sessions(outcome.session_id)
        events = store.list_observability_events(run_session_id=runs[0].run_session_id)

    assert len(runs) == 1
    assert runs[0].status == "completed"
    assert runs[0].total_api_calls == 0
    assert runs[0].total_tool_calls == 0
    assert events[0].event_type == "run_start"
    assert events[-1].event_type == "run_end"


def test_run_tracer_finish_merges_start_and_finish_metadata(tmp_path) -> None:
    db_path = tmp_path / "sessions.db"

    with SessionStore(db_path=db_path) as store:
        session_id = store.create_session(str(tmp_path), "openai", "gpt-5", "trace me")
        tracer = RunTracer.start(
            store=store,
            session_id=session_id,
            agent_name="main",
            agent_type="single_turn",
            provider="openai",
            provider_id=None,
            profile_id=None,
            model="gpt-5",
            metadata={
                "single_turn_hint": "summarize",
                "resumed": True,
                "include_context": False,
            },
        )

        tracer.finish(status="completed", metadata={"tool_errors": False})
        run = store.list_run_sessions(session_id)[0]

    assert json.loads(run.metadata_json) == {
        "single_turn_hint": "summarize",
        "resumed": True,
        "include_context": False,
        "tool_errors": False,
    }


def test_run_sub_agent_task_creates_nested_run_session(tmp_path, monkeypatch) -> None:
    db_path = tmp_path / "sessions.db"
    parent_display = _DisplaySpy()
    provider = _ProviderStub()

    monkeypatch.setenv("PBI_AGENT_SESSION_DB_PATH", str(db_path))
    monkeypatch.setattr(
        "pbi_agent.agent.session._open_runtime_provider",
        _stub_runtime_provider(provider),
    )

    with SessionStore(db_path=db_path) as store:
        session_id = store.create_session(str(tmp_path), "openai", "gpt-5", "trace me")
        parent_tracer = RunTracer.start(
            store=store,
            session_id=session_id,
            agent_name="main",
            agent_type="session_turn",
            provider="openai",
            provider_id=None,
            profile_id=None,
            model="gpt-5",
        )
        result = run_sub_agent_task(
            "Inspect the sub-agent path",
            Settings(api_key="test-key", provider="openai", model="gpt-5"),
            parent_display,
            parent_session_usage=TokenUsage(model="gpt-5"),
            parent_turn_usage=TokenUsage(model="gpt-5"),
            tool_catalog=ToolCatalog.from_builtin_registry(),
            parent_tracer=parent_tracer,
        )
        parent_tracer.finish(status="completed")
        runs = store.list_run_sessions(session_id)

    assert result["status"] == "completed"
    assert len(runs) == 2
    assert runs[1].parent_run_session_id == runs[0].run_session_id


class _SessionDisplaySpy(_DisplaySpy):
    def __init__(self, prompts: list[str | QueuedInput]) -> None:
        super().__init__()
        self.prompts = prompts
        self.prompt_calls = 0
        self.assistant_start_calls = 0
        self.bound_session_ids: list[str | None] = []
        self.replayed_history = []
        self.retry_notices: list[tuple[int, int]] = []

    def user_prompt(self) -> str | QueuedInput:
        value = self.prompts[self.prompt_calls]
        self.prompt_calls += 1
        return value

    def assistant_start(self) -> None:
        self.assistant_start_calls += 1

    def bind_session(self, session_id: str | None) -> None:
        self.bound_session_ids.append(session_id)

    def replay_history(self, messages) -> None:
        self.replayed_history = list(messages)

    def wait_start(self, message: str = "") -> None:
        self.last_wait_message = message

    def wait_stop(self) -> None:
        self.wait_stop_calls += 1

    def retry_notice(self, attempt: int, max_retries: int) -> None:
        self.retry_notices.append((attempt, max_retries))

    def rate_limit_notice(
        self,
        *,
        wait_seconds: float,
        attempt: int,
        max_retries: int,
    ) -> None:
        self.rate_limit_notice_call = (wait_seconds, attempt, max_retries)

    def overload_notice(
        self,
        *,
        wait_seconds: float,
        attempt: int,
        max_retries: int,
    ) -> None:
        self.overload_notice_call = (wait_seconds, attempt, max_retries)

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

    def web_search_sources(self, sources) -> None:
        self.last_web_search_sources = list(sources)


class _ChatProviderStub:
    def __init__(self) -> None:
        self.request_messages: list[str | None] = []
        self.request_inputs: list[UserTurnInput] = []
        self.request_instructions: list[str | None] = []
        self.reset_calls = 0
        self.system_prompts: list[str] = []
        self.refresh_tools_calls = 0

    def __enter__(self) -> _ChatProviderStub:
        return self

    def __exit__(self, *_: object) -> None:
        return None

    def reset_conversation(self) -> None:
        self.reset_calls += 1

    def set_system_prompt(self, system_prompt: str) -> None:
        self.system_prompts.append(system_prompt)

    def refresh_tools(self) -> None:
        self.refresh_tools_calls += 1

    def request_turn(
        self,
        *,
        user_message: str | None = None,
        user_input: UserTurnInput | None = None,
        tool_result_items: list[dict[str, object]] | None = None,
        instructions: str | None = None,
        session_id: str | None = None,
        display,
        session_usage: TokenUsage,
        turn_usage: TokenUsage,
        tracer=None,
    ) -> CompletedResponse:
        del display, tool_result_items, tracer, session_id
        if user_input is not None:
            self.request_inputs.append(user_input)
        if user_input is not None and user_message is None:
            user_message = user_input.text
        self.request_messages.append(user_message)
        self.request_instructions.append(instructions)
        response = CompletedResponse(
            response_id="resp_session",
            text="Ack",
            usage=TokenUsage(input_tokens=2, output_tokens=1, model=DEFAULT_MODEL),
        )
        session_usage.add(response.usage)
        turn_usage.add(response.usage)
        return response


class _CompactProviderStub(_ChatProviderStub):
    def __init__(self) -> None:
        super().__init__()
        self.restored_messages = []

    def restore_messages(self, messages) -> None:
        self.restored_messages = list(messages)


class _AutoCompactToolProviderStub(_CompactProviderStub):
    @property
    def settings(self) -> Settings:
        return Settings(
            api_key="test-key",
            provider="openai",
            max_tool_workers=2,
            compact_threshold=10,
        )

    def __init__(self) -> None:
        super().__init__()
        self.execute_calls = []
        self.request_tool_result_items = []
        self._responses = [
            CompletedResponse(
                response_id="resp_tool",
                text="",
                usage=TokenUsage(
                    input_tokens=50, context_tokens=50, model=DEFAULT_MODEL
                ),
                function_calls=[
                    ToolCall(
                        call_id="call_1", name="shell", arguments={"command": "pwd"}
                    )
                ],
            ),
            CompletedResponse(
                response_id="resp_done",
                text="Done after compacted context.",
                usage=TokenUsage(input_tokens=2, output_tokens=1, model=DEFAULT_MODEL),
            ),
        ]

    def request_turn(self, **kwargs) -> CompletedResponse:
        if kwargs.get("user_input") is not None:
            self.request_inputs.append(kwargs["user_input"])
            self.request_messages.append(kwargs["user_input"].text)
        else:
            self.request_messages.append(kwargs.get("user_message"))
        self.request_tool_result_items.append(kwargs.get("tool_result_items"))
        self.request_instructions.append(kwargs.get("instructions"))
        if kwargs.get("tool_result_items") is not None:
            raise AssertionError(
                "auto-compaction continuation must not send stale tool results"
            )
        response = self._responses.pop(0)
        kwargs["session_usage"].add(response.usage)
        kwargs["turn_usage"].add(response.usage)
        return response

    def execute_tool_calls(self, response: CompletedResponse, **kwargs):
        self.execute_calls.append({"response_id": response.response_id})
        return (
            [{"type": "function_call_output", "call_id": "call_1", "output": "ok"}],
            False,
        )


class _CompactionSummaryProviderStub(_ChatProviderStub):
    def request_turn(
        self,
        *,
        user_message: str | None = None,
        user_input: UserTurnInput | None = None,
        tool_result_items: list[dict[str, object]] | None = None,
        instructions: str | None = None,
        session_id: str | None = None,
        display,
        session_usage: TokenUsage,
        turn_usage: TokenUsage,
        tracer=None,
    ) -> CompletedResponse:
        if user_input is not None and user_message is None:
            user_message = user_input.text
        self.request_messages.append(user_message)
        self.request_instructions.append(instructions)
        del display, tool_result_items, session_id
        response = CompletedResponse(
            response_id="resp_compact",
            text="Goal: continue implementing context compaction.",
            usage=TokenUsage(
                input_tokens=11,
                output_tokens=5,
                context_tokens=16,
                model=DEFAULT_MODEL,
            ),
        )
        session_usage.add(response.usage)
        turn_usage.add(response.usage)
        if tracer is not None:
            tracer.log_model_call(
                provider="openai",
                model=DEFAULT_MODEL,
                url="https://example.test/compact",
                request_config={"provider": "openai"},
                request_payload={"input": user_message},
                response_payload={"output": response.text},
                duration_ms=1,
                prompt_tokens=response.usage.input_tokens,
                completion_tokens=response.usage.output_tokens,
                total_tokens=response.usage.total_tokens,
                status_code=200,
                success=True,
                metadata={"stub": "compaction"},
            )
        return response


def test_run_session_loop_resets_welcome_and_usage_on_new_session(monkeypatch) -> None:
    provider = _ChatProviderStub()
    display = _SessionDisplaySpy(["hello", NEW_SESSION_SENTINEL, "after reset", "quit"])
    settings = Settings(api_key="test-key", provider="openai", max_tool_workers=2)
    monotonic_values = iter([5.0, 6.5, 10.0, 11.0])

    monkeypatch.setattr(
        "pbi_agent.agent.session._open_runtime_provider",
        _stub_runtime_provider(provider),
    )
    monkeypatch.setattr(
        "pbi_agent.agent.session.time.monotonic",
        lambda: next(monotonic_values),
    )
    exit_code = run_session_loop(settings, display)

    assert exit_code == 0
    assert provider.request_messages == ["hello", "after reset"]
    assert provider.reset_calls == 1
    assert len(display.welcome_calls) == 2
    assert display.welcome_calls[0]["interactive"] is True
    assert display.welcome_calls[1]["interactive"] is True
    assert [usage.total_tokens for usage in display.session_usage_calls] == [0, 3, 0, 3]
    assert display.reset_session_calls == 1
    assert display.assistant_start_calls == 2


def test_run_session_loop_persists_per_turn_usage_in_run_sessions(
    monkeypatch,
    tmp_path,
) -> None:
    db_path = tmp_path / "sessions.db"
    provider = _ChatProviderStub()
    display = _SessionDisplaySpy(["hello", "again", "quit"])
    settings = Settings(api_key="test-key", provider="openai", max_tool_workers=2)
    monotonic_values = iter([5.0, 6.5, 10.0, 11.0])

    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("PBI_AGENT_SESSION_DB_PATH", str(db_path))
    monkeypatch.setattr(
        "pbi_agent.agent.session._open_runtime_provider",
        _stub_runtime_provider(provider),
    )
    monkeypatch.setattr(
        "pbi_agent.agent.session.time.monotonic",
        lambda: next(monotonic_values),
    )
    exit_code = run_session_loop(settings, display)

    with SessionStore(db_path=db_path) as store:
        session = store.list_all_sessions(limit=1)[0]
        runs = store.list_run_sessions(session.session_id)

    assert exit_code == 0
    assert len(runs) == 2
    assert [(run.input_tokens, run.output_tokens) for run in runs] == [(2, 1), (2, 1)]


def test_run_session_loop_failed_run_uses_current_turn_usage_only(
    monkeypatch,
    tmp_path,
) -> None:
    class _FailingAfterUsageChatProvider(_ChatProviderStub):
        def request_turn(
            self,
            *,
            user_message: str | None = None,
            user_input: UserTurnInput | None = None,
            tool_result_items: list[dict[str, object]] | None = None,
            instructions: str | None = None,
            session_id: str | None = None,
            display,
            session_usage: TokenUsage,
            turn_usage: TokenUsage,
            tracer=None,
        ) -> CompletedResponse:
            if user_input is not None and user_message is None:
                user_message = user_input.text
            if user_message == "second":
                if user_input is not None:
                    self.request_inputs.append(user_input)
                self.request_messages.append(user_message)
                self.request_instructions.append(instructions)
                usage = TokenUsage(input_tokens=4, output_tokens=2, model=DEFAULT_MODEL)
                session_usage.add(usage)
                turn_usage.add(usage)
                raise RuntimeError("boom")
            return super().request_turn(
                user_message=user_message,
                user_input=user_input,
                tool_result_items=tool_result_items,
                instructions=instructions,
                session_id=session_id,
                display=display,
                session_usage=session_usage,
                turn_usage=turn_usage,
                tracer=tracer,
            )

    db_path = tmp_path / "sessions.db"
    provider = _FailingAfterUsageChatProvider()
    display = _SessionDisplaySpy(["first", "second"])
    settings = Settings(api_key="test-key", provider="openai", max_tool_workers=2)
    monotonic_values = iter([5.0, 6.5, 10.0])

    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("PBI_AGENT_SESSION_DB_PATH", str(db_path))
    monkeypatch.setattr(
        "pbi_agent.agent.session._open_runtime_provider",
        _stub_runtime_provider(provider),
    )
    monkeypatch.setattr(
        "pbi_agent.agent.session.time.monotonic",
        lambda: next(monotonic_values),
    )

    with pytest.raises(RuntimeError, match="boom"):
        run_session_loop(settings, display)

    with SessionStore(db_path=db_path) as store:
        session = store.list_all_sessions(limit=1)[0]
        runs = store.list_run_sessions(session.session_id)

    assert [(run.status, run.input_tokens, run.output_tokens) for run in runs] == [
        ("completed", 2, 1),
        ("failed", 4, 2),
    ]


def test_run_session_loop_handles_skills_command_locally(monkeypatch) -> None:
    provider = _ChatProviderStub()
    display = _SessionDisplaySpy([SKILLS_COMMAND, "quit"])
    settings = Settings(api_key="test-key", provider="openai", max_tool_workers=2)

    monkeypatch.setattr(
        "pbi_agent.agent.session._open_runtime_provider",
        _stub_runtime_provider(provider),
    )
    monkeypatch.setattr(
        "pbi_agent.agent.session.format_project_skills_markdown",
        lambda: "### Project Skills\n\n- `repo-skill`: Demo skill",
    )

    exit_code = run_session_loop(settings, display)

    assert exit_code == 0
    assert provider.request_messages == []
    assert display.markdown_calls == [
        "### Project Skills\n\n- `repo-skill`: Demo skill"
    ]
    assert display.assistant_start_calls == 0


def test_run_session_loop_handles_mcp_command_locally(monkeypatch) -> None:
    provider = _ChatProviderStub()
    display = _SessionDisplaySpy([MCP_COMMAND, "quit"])
    settings = Settings(api_key="test-key", provider="openai", max_tool_workers=2)

    monkeypatch.setattr(
        "pbi_agent.agent.session._open_runtime_provider",
        _stub_runtime_provider(provider),
    )
    monkeypatch.setattr(
        "pbi_agent.agent.session.format_project_mcp_servers_markdown",
        lambda: "### MCP Servers\n\n- `echo`: `uv run server.py`",
    )

    exit_code = run_session_loop(settings, display)

    assert exit_code == 0
    assert provider.request_messages == []
    assert display.markdown_calls == ["### MCP Servers\n\n- `echo`: `uv run server.py`"]
    assert display.assistant_start_calls == 0


def test_run_session_loop_handles_agents_command_locally(monkeypatch) -> None:
    provider = _ChatProviderStub()
    display = _SessionDisplaySpy([AGENTS_COMMAND, "quit"])
    settings = Settings(api_key="test-key", provider="openai", max_tool_workers=2)

    monkeypatch.setattr(
        "pbi_agent.agent.session._open_runtime_provider",
        _stub_runtime_provider(provider),
    )
    monkeypatch.setattr(
        "pbi_agent.agent.session.format_project_sub_agents_markdown",
        lambda reloaded=False: "### Sub-Agents\n\n- `reviewer`: Reviews code",
    )

    exit_code = run_session_loop(settings, display)

    assert exit_code == 0
    assert provider.request_messages == []
    assert display.markdown_calls == ["### Sub-Agents\n\n- `reviewer`: Reviews code"]
    assert display.assistant_start_calls == 0


def test_run_session_loop_handles_agents_reload_command_locally(monkeypatch) -> None:
    provider = _ChatProviderStub()
    display = _SessionDisplaySpy([AGENTS_RELOAD_COMMAND, "quit"])
    settings = Settings(api_key="test-key", provider="openai", max_tool_workers=2)

    monkeypatch.setattr(
        "pbi_agent.agent.session._open_runtime_provider",
        _stub_runtime_provider(provider),
    )
    monkeypatch.setattr(
        "pbi_agent.agent.session.get_system_prompt",
        lambda: "updated prompt",
    )
    monkeypatch.setattr(
        "pbi_agent.agent.session.format_project_sub_agents_markdown",
        lambda reloaded=False: (
            "### Sub-Agents\n\nReloaded" if reloaded else "### Sub-Agents\n\nInitial"
        ),
    )

    exit_code = run_session_loop(settings, display)

    assert exit_code == 0
    assert provider.request_messages == []
    assert provider.system_prompts == ["updated prompt"]
    assert provider.refresh_tools_calls == 1
    assert display.markdown_calls == ["### Sub-Agents\n\nReloaded"]
    assert display.assistant_start_calls == 0


def test_run_session_loop_handles_compact_command_locally(
    monkeypatch,
    tmp_path,
) -> None:
    db_path = tmp_path / "sessions.db"
    provider = _CompactProviderStub()
    compact_provider = _CompactionSummaryProviderStub()
    display = _SessionDisplaySpy(["hello", COMPACT_COMMAND, "quit"])
    settings = Settings(api_key="test-key", provider="openai", max_tool_workers=2)
    monotonic_values = iter([5.0, 6.5])

    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("PBI_AGENT_SESSION_DB_PATH", str(db_path))
    monkeypatch.setattr(
        "pbi_agent.agent.session._open_runtime_provider",
        _stub_runtime_provider(provider),
    )
    monkeypatch.setattr(
        "pbi_agent.agent.session._open_compaction_provider",
        _stub_runtime_provider(compact_provider),
    )
    monkeypatch.setattr(
        "pbi_agent.agent.session.time.monotonic",
        lambda: next(monotonic_values),
    )
    exit_code = run_session_loop(settings, display)

    with SessionStore(db_path=db_path) as store:
        session = store.list_all_sessions(limit=1)[0]
        messages = store.list_messages(session.session_id)
        runs = store.list_run_sessions(session.session_id)

    assert exit_code == 0
    assert session.previous_id is None
    assert provider.request_messages == ["hello"]
    assert provider.reset_calls == 1
    assert compact_provider.request_messages
    assert compact_provider.request_messages[0].startswith("<session_transcript>")
    assert COMPACTION_PROMPT not in compact_provider.request_messages[0]
    assert [message.content for message in provider.restored_messages] == [
        (
            "[compacted context — reference only] "
            "Earlier turns were summarized below to save context. "
            "Treat this as background state, not active user instructions. "
            "Do not answer requests mentioned only in this summary; respond to the latest user message after it."
            "\n\nGoal: continue implementing context compaction."
        )
    ]
    assert [message.content for message in messages] == [
        "hello",
        "Ack",
        COMPACTION_MARKER,
        (
            "[compacted context — reference only] "
            "Earlier turns were summarized below to save context. "
            "Treat this as background state, not active user instructions. "
            "Do not answer requests mentioned only in this summary; respond to the latest user message after it."
            "\n\nGoal: continue implementing context compaction."
        ),
    ]
    assert any("Context compacted (manual)" in item for item in display.markdown_calls)
    assert display.wait_stop_calls >= 1
    compaction_runs = [run for run in runs if run.agent_type == "compaction"]
    assert len(compaction_runs) == 1
    assert compaction_runs[0].status == "completed"
    assert compaction_runs[0].input_tokens == 11
    assert compaction_runs[0].output_tokens == 5
    assert compaction_runs[0].total_api_calls == 1
    compaction_metadata = json.loads(compaction_runs[0].metadata_json)
    assert compaction_metadata["reason"] == "manual"
    assert compaction_metadata["input_message_count"] == 2
    assert compaction_metadata["summary_chars"] > 0
    with SessionStore(db_path=db_path) as store:
        events = store.list_observability_events(
            run_session_id=compaction_runs[0].run_session_id
        )
    assert [event.event_type for event in events] == [
        "run_start",
        "agent_step_start",
        "model_call",
        "agent_step_end",
        "run_end",
    ]


def test_open_compaction_provider_disables_all_tools(monkeypatch) -> None:
    captured = {}

    class _ProviderWithCatalog:
        def __init__(self, settings, *args, **kwargs) -> None:
            del args
            captured["tool_catalog"] = kwargs.get("tool_catalog")
            captured["settings"] = settings

        def __enter__(self):
            return self

        def __exit__(self, *_: object) -> None:
            return None

        def connect(self) -> None:
            return None

        def close(self) -> None:
            return None

    monkeypatch.setattr(
        "pbi_agent.providers.openai_provider.OpenAIProvider",
        _ProviderWithCatalog,
    )

    with _open_compaction_provider(
        Settings(api_key="test-key", provider="openai", web_search=True)
    ):
        pass

    assert captured["settings"].web_search is False
    assert captured["tool_catalog"].get_specs() == []


def test_open_compaction_provider_uses_compaction_prompt_as_system_prompt(
    monkeypatch,
) -> None:
    captured = {}

    class _ProviderWithSystemPrompt:
        def __init__(self, settings, *args, **kwargs) -> None:
            del args
            captured["settings"] = settings
            captured["system_prompt"] = kwargs.get("system_prompt")

        def __enter__(self):
            return self

        def __exit__(self, *_: object) -> None:
            return None

        def connect(self) -> None:
            return None

        def close(self) -> None:
            return None

    monkeypatch.setattr(
        "pbi_agent.providers.openai_provider.OpenAIProvider",
        _ProviderWithSystemPrompt,
    )

    with _open_compaction_provider(Settings(api_key="test-key", provider="openai")):
        pass

    assert captured["system_prompt"] == COMPACTION_PROMPT
    assert captured["system_prompt"] != get_system_prompt()


def test_run_session_loop_restores_only_active_context_after_compaction(
    tmp_path,
) -> None:
    db_path = tmp_path / "sessions.db"
    provider = _CompactProviderStub()
    display = _SessionDisplaySpy([])
    settings = Settings(api_key="test-key", provider="openai")

    with SessionStore(db_path=db_path) as store:
        session_id = store.create_session(str(tmp_path), "openai", DEFAULT_MODEL)
        store.add_message(session_id, "user", "old user")
        store.add_message(session_id, "assistant", "old assistant")
        store.add_message(session_id, "assistant", COMPACTION_MARKER)
        store.add_message(
            session_id, "assistant", "Compacted session context:\n\nSummary"
        )
        store.add_message(session_id, "user", "new user")
        store.add_message(session_id, "assistant", "new assistant")
        _resume_session(
            provider=provider,
            store=store,
            session_id=session_id,
            session_usage=TokenUsage(model=settings.model),
            display=display,
        )

    assert [message.content for message in provider.restored_messages] == [
        "Compacted session context:\n\nSummary",
        "new user",
        "new assistant",
    ]
    assert [message.content for message in display.replayed_history] == [
        "old user",
        "old assistant",
        COMPACTION_MARKER,
        "Compacted session context:\n\nSummary",
        "new user",
        "new assistant",
    ]


def test_run_session_loop_auto_compacts_between_tool_iterations(
    monkeypatch,
    tmp_path,
) -> None:
    db_path = tmp_path / "sessions.db"
    provider = _AutoCompactToolProviderStub()
    compact_provider = _CompactionSummaryProviderStub()
    display = _SessionDisplaySpy(["hello", "quit"])
    settings = Settings(
        api_key="test-key",
        provider="openai",
        max_tool_workers=2,
        compact_threshold=10,
    )
    monotonic_values = iter([5.0, 6.5])

    def _compact_between_tools(**kwargs) -> int:
        kwargs["provider"].restore_messages(
            [
                type(
                    "Message",
                    (),
                    {
                        "content": (
                            "Compacted session context:\n\n"
                            "Goal: continue implementing context compaction."
                        )
                    },
                )()
            ]
        )
        compact_provider.request_messages.append(
            "<session_transcript>stub</session_transcript>"
        )
        kwargs["display"].render_markdown(
            "Context compacted (auto); future turns will use the summary."
        )
        return 1

    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("PBI_AGENT_SESSION_DB_PATH", str(db_path))
    monkeypatch.setattr(
        "pbi_agent.agent.session._open_runtime_provider",
        _stub_runtime_provider(provider),
    )
    monkeypatch.setattr(
        "pbi_agent.agent.session._open_compaction_provider",
        _stub_runtime_provider(compact_provider),
    )
    monkeypatch.setattr(
        "pbi_agent.agent.session.time.monotonic",
        lambda: next(monotonic_values),
    )
    monkeypatch.setattr(
        session_module,
        "_should_auto_compact",
        lambda **kwargs: bool(kwargs["session_usage"].snapshot().context_tokens),
    )
    monkeypatch.setattr(session_module, "_compact_live_session", _compact_between_tools)

    exit_code = run_session_loop(settings, display)

    assert exit_code == 0
    assert compact_provider.request_messages
    assert [message.content for message in provider.restored_messages] == [
        "Compacted session context:\n\nGoal: continue implementing context compaction."
    ]
    assert provider.request_tool_result_items == [None, None]
    assert provider.request_messages[1] == session_module.COMPACTION_CONTINUATION_PROMPT
    assert any("Context compacted (auto)" in item for item in display.markdown_calls)


def test_format_messages_for_compaction_includes_pending_tool_exchange() -> None:
    message = type(
        "Message",
        (),
        {"role": "user", "content": "Inspect workspace"},
    )()

    transcript = session_module._format_messages_for_compaction(
        [message],
        pending_tool_calls=[
            ToolCall(call_id="call_1", name="shell", arguments={"command": "pwd"})
        ],
        pending_tool_result_items=[
            {"type": "function_call_output", "call_id": "call_1", "output": "ok"}
        ],
    )

    assert "<pending_tool_exchange>" in transcript
    assert '"name": "shell"' in transcript
    assert '"command": "pwd"' in transcript
    assert '"call_id": "call_1"' in transcript
    assert '"output": "ok"' in transcript


def test_run_session_loop_auto_compaction_summary_includes_pending_tool_exchange(
    monkeypatch,
    tmp_path,
) -> None:
    db_path = tmp_path / "sessions.db"
    provider = _AutoCompactToolProviderStub()
    compact_provider = _CompactionSummaryProviderStub()
    display = _SessionDisplaySpy(["hello", "quit"])
    settings = Settings(
        api_key="test-key",
        provider="openai",
        max_tool_workers=2,
        compact_threshold=10,
    )
    provider._responses[1] = CompletedResponse(
        response_id="resp_done",
        text="Done after compacted context.",
        usage=TokenUsage(input_tokens=2, output_tokens=1, model=DEFAULT_MODEL),
    )
    monotonic_values = iter([5.0, 6.5])

    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("PBI_AGENT_SESSION_DB_PATH", str(db_path))
    monkeypatch.setattr(
        "pbi_agent.agent.session._open_runtime_provider",
        _stub_runtime_provider(provider),
    )
    monkeypatch.setattr(
        "pbi_agent.agent.session._open_compaction_provider",
        _stub_runtime_provider(compact_provider),
    )
    monkeypatch.setattr(
        session_module,
        "_should_auto_compact",
        lambda **kwargs: bool(kwargs["session_usage"].snapshot().context_tokens),
    )
    monkeypatch.setattr(
        "pbi_agent.agent.session.time.monotonic",
        lambda: next(monotonic_values),
    )
    exit_code = run_session_loop(settings, display)

    assert exit_code == 0
    assert compact_provider.request_messages
    compaction_request = compact_provider.request_messages[0]
    assert "<pending_tool_exchange>" in compaction_request
    assert '"name": "shell"' in compaction_request
    assert '"command": "pwd"' in compaction_request
    assert '"call_id": "call_1"' in compaction_request
    assert '"output": "ok"' in compaction_request
    assert provider.request_tool_result_items == [None, None]
    assert provider.request_messages[1] == session_module.COMPACTION_CONTINUATION_PROMPT


def test_run_session_loop_does_not_auto_compact_after_final_response(
    monkeypatch,
    tmp_path,
) -> None:
    def _fail_auto_compact(**_kwargs):
        raise AssertionError("auto compaction must not run after the final response")

    db_path = tmp_path / "sessions.db"
    provider = _CompactProviderStub()
    compact_provider = _CompactionSummaryProviderStub()
    display = _SessionDisplaySpy(["hello", "quit"])
    settings = Settings(
        api_key="test-key",
        provider="openai",
        max_tool_workers=2,
        compact_threshold=10,
    )
    monotonic_values = iter([5.0, 6.5])

    original_request_turn = provider.request_turn

    def _large_final_request_turn(**kwargs) -> CompletedResponse:
        response = original_request_turn(**kwargs)
        large_usage = TokenUsage(context_tokens=50, model=DEFAULT_MODEL)
        kwargs["session_usage"].add(large_usage)
        kwargs["turn_usage"].add(large_usage)
        return response

    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("PBI_AGENT_SESSION_DB_PATH", str(db_path))
    monkeypatch.setattr(provider, "request_turn", _large_final_request_turn)
    monkeypatch.setattr(
        "pbi_agent.agent.session._open_runtime_provider",
        _stub_runtime_provider(provider),
    )
    monkeypatch.setattr(
        "pbi_agent.agent.session._open_compaction_provider",
        _stub_runtime_provider(compact_provider),
    )
    monkeypatch.setattr(session_module, "_compact_live_session", _fail_auto_compact)
    monkeypatch.setattr(
        "pbi_agent.agent.session.time.monotonic",
        lambda: next(monotonic_values),
    )

    exit_code = run_session_loop(settings, display)

    assert exit_code == 0
    assert not compact_provider.request_messages
    assert not any(
        "Context compacted (auto)" in item for item in display.markdown_calls
    )


def test_run_session_loop_keeps_command_alias_and_uses_turn_specific_instructions(
    monkeypatch,
    tmp_path,
) -> None:
    monkeypatch.chdir(tmp_path)
    provider = _ChatProviderStub()
    display = _SessionDisplaySpy(["/plan draft the approach", "quit"])
    settings = Settings(api_key="test-key", provider="openai", max_tool_workers=2)
    _write_command(tmp_path, "plan", "Plan before coding.")

    monkeypatch.setattr(
        "pbi_agent.agent.session._open_runtime_provider",
        _stub_runtime_provider(provider),
    )

    exit_code = run_session_loop(settings, display)

    assert exit_code == 0
    assert provider.request_messages == ["/plan draft the approach"]
    assert provider.request_instructions[0] is not None
    assert "<active_command>\nPlan before coding.\n</active_command>" in str(
        provider.request_instructions[0]
    )


def test_run_session_loop_uses_command_instructions_when_body_starts_on_next_line(
    monkeypatch,
    tmp_path,
) -> None:
    monkeypatch.chdir(tmp_path)
    provider = _ChatProviderStub()
    prompt = "/plan\n# Task\nTask A\n\n## Goal\nInvestigate"
    display = _SessionDisplaySpy([prompt, "quit"])
    settings = Settings(api_key="test-key", provider="openai", max_tool_workers=2)
    _write_command(tmp_path, "plan", "Plan before coding.")

    monkeypatch.setattr(
        "pbi_agent.agent.session._open_runtime_provider",
        _stub_runtime_provider(provider),
    )

    exit_code = run_session_loop(settings, display)

    assert exit_code == 0
    assert provider.request_messages == [prompt]
    assert provider.request_instructions[0] is not None
    assert "<active_command>\nPlan before coding.\n</active_command>" in str(
        provider.request_instructions[0]
    )


def test_run_session_loop_accepts_command_only_turn(monkeypatch, tmp_path) -> None:
    monkeypatch.chdir(tmp_path)
    provider = _ChatProviderStub()
    display = _SessionDisplaySpy(["/plan", "quit"])
    settings = Settings(api_key="test-key", provider="openai", max_tool_workers=2)
    _write_command(tmp_path, "plan", "Plan before coding.")

    monkeypatch.setattr(
        "pbi_agent.agent.session._open_runtime_provider",
        _stub_runtime_provider(provider),
    )

    exit_code = run_session_loop(settings, display)

    assert exit_code == 0
    assert provider.request_messages == ["/plan"]


def test_run_session_loop_keeps_local_command_precedence_over_command_files(
    monkeypatch,
) -> None:
    provider = _ChatProviderStub()
    display = _SessionDisplaySpy([SKILLS_COMMAND, "quit"])
    settings = Settings(api_key="test-key", provider="openai", max_tool_workers=2)

    monkeypatch.setattr(
        "pbi_agent.agent.session._open_runtime_provider",
        _stub_runtime_provider(provider),
    )
    monkeypatch.setattr(
        "pbi_agent.agent.session.format_project_skills_markdown",
        lambda: "### Project Skills\n\n- `repo-skill`: Demo skill",
    )

    exit_code = run_session_loop(settings, display)

    assert exit_code == 0
    assert provider.request_messages == []
    assert display.markdown_calls == [
        "### Project Skills\n\n- `repo-skill`: Demo skill"
    ]


def test_format_project_skills_markdown_hides_skill_manifest_paths(
    tmp_path: Path,
) -> None:
    skill_dir = tmp_path / ".agents" / "skills" / "repo-skill"
    skill_dir.mkdir(parents=True)
    skill_path = skill_dir / "SKILL.md"
    skill_path.write_text(
        "---\nname: repo-skill\ndescription: Demo skill\n---\n\n# Repo Skill\n",
        encoding="utf-8",
    )

    rendered = format_project_skills_markdown(workspace=tmp_path)

    assert rendered == "### Project Skills\n\n- `repo-skill`: Demo skill"
    assert str(skill_path.resolve()) not in rendered


def test_run_session_loop_passes_queued_image_paths_to_provider(monkeypatch) -> None:
    provider = _ChatProviderStub()
    display = _SessionDisplaySpy(
        [QueuedInput(text="describe this", image_paths=["chart.png"]), "quit"]
    )
    settings = Settings(api_key="test-key", provider="openai", max_tool_workers=2)
    monotonic_values = iter([5.0, 6.5])

    monkeypatch.setattr(
        "pbi_agent.agent.session._open_runtime_provider",
        _stub_runtime_provider(provider),
    )
    monkeypatch.setattr(
        "pbi_agent.agent.session.time.monotonic",
        lambda: next(monotonic_values),
    )
    monkeypatch.setattr(
        "pbi_agent.agent.session.load_workspace_image",
        lambda root, path: ImageAttachment(
            path=path,
            mime_type="image/png",
            data_base64="abcd",
            byte_count=4,
        ),
    )

    exit_code = run_session_loop(settings, display)

    assert exit_code == 0
    assert provider.request_messages == ["describe this"]
    assert len(provider.request_inputs) == 1
    assert provider.request_inputs[0].images[0].path == "chart.png"


def test_run_session_loop_processes_attachment_only_queued_images(monkeypatch) -> None:
    provider = _ChatProviderStub()
    display = _SessionDisplaySpy(
        [
            QueuedInput(
                text="",
                images=[
                    ImageAttachment(
                        path="chart.png",
                        mime_type="image/png",
                        data_base64="abcd",
                        byte_count=4,
                    )
                ],
            ),
            "quit",
        ]
    )
    settings = Settings(api_key="test-key", provider="openai", max_tool_workers=2)
    monotonic_values = iter([5.0, 6.5])

    monkeypatch.setattr(
        "pbi_agent.agent.session._open_runtime_provider",
        _stub_runtime_provider(provider),
    )
    monkeypatch.setattr(
        "pbi_agent.agent.session.time.monotonic",
        lambda: next(monotonic_values),
    )

    exit_code = run_session_loop(settings, display)

    assert exit_code == 0
    assert provider.request_messages == [""]
    assert len(provider.request_inputs) == 1
    assert provider.request_inputs[0].images[0].path == "chart.png"

    with SessionStore() as store:
        sessions = store.list_sessions(os.getcwd(), limit=10)
        assert len(sessions) == 1
        messages = store.list_messages(sessions[0].session_id)

    assert [message.role for message in messages] == ["user", "assistant"]
    assert messages[0].content == "[attached images: chart.png]"
    assert messages[1].content == "Ack"


def test_run_session_loop_does_not_persist_unanswered_user_turn(monkeypatch) -> None:
    class _FailingProvider:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def reset_conversation(self) -> None:
            return None

        def request_turn(
            self,
            *,
            user_message: str | None = None,
            user_input: UserTurnInput | None = None,
            tool_result_items: list[dict[str, object]] | None = None,
            instructions: str | None = None,
            session_id: str | None = None,
            display,
            session_usage: TokenUsage,
            turn_usage: TokenUsage,
            tracer=None,
        ) -> CompletedResponse:
            del (
                user_message,
                user_input,
                tool_result_items,
                instructions,
                session_id,
                display,
                session_usage,
                turn_usage,
                tracer,
            )
            raise RuntimeError("boom")

    display = _SessionDisplaySpy(["hello"])
    settings = Settings(api_key="test-key", provider="openai", max_tool_workers=2)

    monkeypatch.setattr(
        "pbi_agent.agent.session._open_runtime_provider",
        _stub_runtime_provider(_FailingProvider()),
    )

    with pytest.raises(RuntimeError, match="boom"):
        run_session_loop(settings, display)

    with SessionStore() as store:
        sessions = store.list_sessions(os.getcwd(), limit=10)
        assert len(sessions) == 1
        assert store.list_messages(sessions[0].session_id) == []


def test_run_session_loop_interrupt_deletes_user_turn_and_accepts_next_input(
    monkeypatch,
) -> None:
    class _InterruptThenSucceedProvider:
        def __init__(self) -> None:
            self.calls = 0

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def reset_conversation(self) -> None:
            return None

        def get_conversation_checkpoint(self) -> str | None:
            return "checkpoint-ok"

        def request_turn(
            self,
            *,
            user_message: str | None = None,
            user_input: UserTurnInput | None = None,
            tool_result_items: list[dict[str, object]] | None = None,
            instructions: str | None = None,
            session_id: str | None = None,
            display,
            session_usage: TokenUsage,
            turn_usage: TokenUsage,
            tracer=None,
        ) -> CompletedResponse:
            del user_message, tool_result_items, instructions, session_id, tracer
            self.calls += 1
            if self.calls == 1:
                display.request_interrupt(item_id="user-optimistic")
                response = CompletedResponse(
                    response_id="interrupted-response",
                    text="discard me",
                    usage=TokenUsage(
                        input_tokens=1, output_tokens=1, model=DEFAULT_MODEL
                    ),
                )
            else:
                assert user_input is not None
                response = CompletedResponse(
                    response_id="final-response",
                    text=f"Ack {user_input.text}",
                    usage=TokenUsage(
                        input_tokens=2, output_tokens=3, model=DEFAULT_MODEL
                    ),
                )
            session_usage.add(response.usage)
            turn_usage.add(response.usage)
            return response

    class _InterruptDisplay(_SessionDisplaySpy):
        def __init__(self) -> None:
            super().__init__(["first", "second", "exit"])
            self.interrupt = False
            self.clear_interrupt_calls = 0

        def request_interrupt(
            self, *, item_id: str | None = None, input_text: str | None = None
        ) -> None:
            del item_id, input_text
            self.interrupt = True

        def clear_interrupt(self) -> None:
            self.clear_interrupt_calls += 1
            self.interrupt = False

        def interrupt_requested(self) -> bool:
            return self.interrupt

    provider = _InterruptThenSucceedProvider()
    display = _InterruptDisplay()
    settings = Settings(api_key="test-key", provider="openai", max_tool_workers=2)
    monkeypatch.setattr(
        "pbi_agent.agent.session._open_runtime_provider",
        _stub_runtime_provider(provider),
    )

    assert run_session_loop(settings, display) == 0

    with SessionStore() as store:
        sessions = store.list_sessions(os.getcwd(), limit=10)
        assert len(sessions) == 1
        messages = store.list_messages(sessions[0].session_id)
        assert [(message.role, message.content) for message in messages] == [
            ("user", "second"),
            ("assistant", "Ack second"),
        ]
        assert sessions[0].previous_id == "checkpoint-ok"
    assert display.clear_interrupt_calls == 1
    assert display.assistant_stop_calls == 2


def test_run_single_turn_passes_parent_context_snapshot_to_tool_execution(
    monkeypatch, tmp_path
) -> None:
    db_path = tmp_path / "sessions.db"
    monkeypatch.setenv("PBI_AGENT_SESSION_DB_PATH", str(db_path))

    with SessionStore() as store:
        session_id = store.create_session(
            directory=os.getcwd(),
            provider="openai",
            model=DEFAULT_MODEL,
            title="existing",
        )
        store.add_message(session_id, "user", "What does the CLI do?")
        store.add_message(session_id, "assistant", "It routes commands in cli.py.")

    provider = _ProviderStub(tool_name="sub_agent")
    display = _DisplaySpy()
    settings = Settings(api_key="test-key", provider="openai", max_tool_workers=3)
    monotonic_values = iter([10.0, 13.5])

    monkeypatch.setattr(
        "pbi_agent.agent.session._open_runtime_provider",
        _stub_runtime_provider(provider),
    )
    monkeypatch.setattr(
        "pbi_agent.agent.session.time.monotonic",
        lambda: next(monotonic_values),
    )

    run_single_turn(
        "Inspect the sub-agent path",
        settings,
        display,
        resume_session_id=session_id,
    )

    parent_context = provider.execute_calls[0]["parent_context"]
    assert parent_context is not None
    assert parent_context.continuation_id == "resp_current"
    assert [message.content for message in parent_context.messages] == [
        "What does the CLI do?",
        "It routes commands in cli.py.",
    ]
    assert parent_context.current_user_turn == "Inspect the sub-agent path"


def test_run_single_turn_resumed_session_uses_provided_runtime(
    monkeypatch, tmp_path
) -> None:
    monkeypatch.chdir(tmp_path)
    db_path = tmp_path / "sessions.db"
    monkeypatch.setenv("PBI_AGENT_SESSION_DB_PATH", str(db_path))

    with SessionStore(db_path=db_path) as store:
        session_id = store.create_session(
            directory=os.getcwd(),
            provider="xai",
            model="grok-4",
            title="existing",
            profile_id="analysis",
        )
        store.add_message(session_id, "user", "hello")
        store.add_message(session_id, "assistant", "hi")

    provider = _ProviderStub()
    display = _DisplaySpy()
    monotonic_values = iter([10.0, 13.5])

    monkeypatch.setattr(
        "pbi_agent.agent.session._open_runtime_provider",
        _stub_runtime_provider(provider),
    )
    monkeypatch.setattr(
        "pbi_agent.agent.session.time.monotonic",
        lambda: next(monotonic_values),
    )

    run_single_turn(
        "continue",
        Settings(api_key="test-key", provider="openai", model="gpt-5.4-mini"),
        display,
        resume_session_id=session_id,
    )

    assert display.welcome_calls[0]["model"] == "gpt-5.4-mini"


def test_run_single_turn_resumed_session_bootstraps_from_history_without_previous_id(
    monkeypatch, tmp_path
) -> None:
    monkeypatch.chdir(tmp_path)
    db_path = tmp_path / "sessions.db"
    monkeypatch.setenv("PBI_AGENT_SESSION_DB_PATH", str(db_path))

    with SessionStore(db_path=db_path) as store:
        session_id = store.create_session(
            directory=os.getcwd(),
            provider="openai",
            model=DEFAULT_MODEL,
            title="existing",
        )
        store.update_session(session_id, previous_id="resp_parent")
        store.add_message(session_id, "user", "hello")
        store.add_message(session_id, "assistant", "hi")
        store.add_message(session_id, "user", "failed earlier")

    provider = OpenAIProvider(Settings(api_key="test-key", provider="openai"))
    display = _SessionDisplaySpy([])
    requests: list[dict[str, object]] = []
    monotonic_values = iter([10.0, 12.5])

    class _FakeHTTPResponse:
        def __init__(self, payload: dict[str, object]) -> None:
            self._payload = payload

        def read(self) -> bytes:
            return json.dumps(self._payload).encode("utf-8")

        def __enter__(self) -> _FakeHTTPResponse:
            return self

        def __exit__(self, *_: object) -> None:
            return None

    def fake_urlopen(
        request: urllib.request.Request,
        timeout: float,
    ) -> _FakeHTTPResponse:
        del timeout
        payload = request.data.decode("utf-8") if request.data else "{}"
        requests.append(json.loads(payload))
        return _FakeHTTPResponse(
            {
                "id": "resp_recovered",
                "model": DEFAULT_MODEL,
                "usage": {
                    "input_tokens": 7,
                    "input_tokens_details": {"cached_tokens": 0},
                    "output_tokens": 3,
                    "output_tokens_details": {"reasoning_tokens": 0},
                },
                "output": [
                    {
                        "type": "message",
                        "role": "assistant",
                        "content": [{"type": "output_text", "text": "Recovered."}],
                    }
                ],
            }
        )

    monkeypatch.setattr(
        "pbi_agent.agent.session._open_runtime_provider",
        _stub_runtime_provider(provider),
    )
    monkeypatch.setattr(
        "pbi_agent.agent.session.time.monotonic",
        lambda: next(monotonic_values),
    )
    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)

    outcome = run_single_turn(
        "continue",
        Settings(api_key="test-key", provider="openai"),
        display,
        resume_session_id=session_id,
    )

    assert outcome.response_id == "resp_recovered"
    assert len(requests) == 1
    assert "previous_response_id" not in requests[0]
    assert requests[0]["input"] == [
        {"role": "user", "content": "hello"},
        {"role": "assistant", "content": "hi"},
        {"role": "user", "content": "continue"},
    ]


def test_resume_session_does_not_restore_trailing_user_only_turn(
    tmp_path,
    monkeypatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    db_path = tmp_path / "sessions.db"
    monkeypatch.setenv("PBI_AGENT_SESSION_DB_PATH", str(db_path))

    with SessionStore(db_path=db_path) as store:
        session_id = store.create_session(
            directory=os.getcwd(),
            provider="openai",
            model=DEFAULT_MODEL,
            title="existing",
        )
        store.add_message(session_id, "user", "hello")
        store.add_message(session_id, "assistant", "hi")
        store.add_message(session_id, "user", "failed earlier")

        provider = _ProviderStub()
        display = _DisplaySpy()

        _resume_session(
            provider=provider,
            store=store,
            session_id=session_id,
            session_usage=TokenUsage(model=DEFAULT_MODEL),
            display=display,
        )

    assert [message.content for message in provider.restored_messages] == [
        "hello",
        "hi",
    ]


def test_resume_session_restores_previous_response_id_when_history_missing(
    tmp_path,
    monkeypatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    db_path = tmp_path / "sessions.db"
    monkeypatch.setenv("PBI_AGENT_SESSION_DB_PATH", str(db_path))

    with SessionStore(db_path=db_path) as store:
        session_id = store.create_session(
            directory=os.getcwd(),
            provider="openai",
            model=DEFAULT_MODEL,
            title="existing",
        )
        store.update_session(session_id, previous_id="resp_parent")

        provider = _ProviderStub()
        display = _DisplaySpy()

        _resume_session(
            provider=provider,
            store=store,
            session_id=session_id,
            session_usage=TokenUsage(model=DEFAULT_MODEL),
            display=display,
        )

    assert provider.previous_response_ids == ["resp_parent"]


def test_run_single_turn_resumed_openai_session_increments_total_usage(
    monkeypatch, tmp_path
) -> None:
    monkeypatch.chdir(tmp_path)
    db_path = tmp_path / "sessions.db"
    monkeypatch.setenv("PBI_AGENT_SESSION_DB_PATH", str(db_path))

    with SessionStore(db_path=db_path) as store:
        session_id = store.create_session(
            directory=os.getcwd(),
            provider="openai",
            model=DEFAULT_MODEL,
            title="existing",
        )
        store.update_session(
            session_id,
            previous_id="resp_parent",
            total_tokens=15,
            input_tokens=10,
            output_tokens=5,
            cost_usd=0.01,
        )
        store.add_message(session_id, "user", "hello")
        store.add_message(session_id, "assistant", "hi")

    provider = OpenAIProvider(Settings(api_key="test-key", provider="openai"))
    display = _SessionDisplaySpy([])
    monotonic_values = iter([20.0, 21.5])

    class _FakeHTTPResponse:
        def __init__(self, payload: dict[str, object]) -> None:
            self._payload = payload

        def read(self) -> bytes:
            return json.dumps(self._payload).encode("utf-8")

        def __enter__(self) -> _FakeHTTPResponse:
            return self

        def __exit__(self, *_: object) -> None:
            return None

    def fake_urlopen(
        request: urllib.request.Request,
        timeout: float,
    ) -> _FakeHTTPResponse:
        del request, timeout
        return _FakeHTTPResponse(
            {
                "id": "resp_recovered",
                "model": DEFAULT_MODEL,
                "usage": {
                    "input_tokens": 7,
                    "input_tokens_details": {"cached_tokens": 0},
                    "output_tokens": 3,
                    "output_tokens_details": {"reasoning_tokens": 0},
                },
                "output": [
                    {
                        "type": "message",
                        "role": "assistant",
                        "content": [{"type": "output_text", "text": "Recovered."}],
                    }
                ],
            }
        )

    monkeypatch.setattr(
        "pbi_agent.agent.session._open_runtime_provider",
        _stub_runtime_provider(provider),
    )
    monkeypatch.setattr(
        "pbi_agent.agent.session.time.monotonic",
        lambda: next(monotonic_values),
    )
    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)

    outcome = run_single_turn(
        "continue",
        Settings(api_key="test-key", provider="openai"),
        display,
        resume_session_id=session_id,
    )

    assert outcome.response_id == "resp_recovered"
    assert display.session_usage_calls[-1].input_tokens == 17
    assert display.session_usage_calls[-1].output_tokens == 8
    assert display.session_usage_calls[-1].total_tokens == 25


def test_run_single_turn_resumed_google_session_restores_provider_total_tokens(
    monkeypatch, tmp_path
) -> None:
    monkeypatch.chdir(tmp_path)
    db_path = tmp_path / "sessions.db"
    monkeypatch.setenv("PBI_AGENT_SESSION_DB_PATH", str(db_path))

    with SessionStore(db_path=db_path) as store:
        session_id = store.create_session(
            directory=os.getcwd(),
            provider="google",
            model=DEFAULT_GOOGLE_MODEL,
            title="existing",
        )
        store.update_session(
            session_id,
            previous_id="resp_parent",
            total_tokens=15,
            input_tokens=10,
            output_tokens=5,
            cost_usd=0.01,
        )
        store.add_message(session_id, "user", "hello")
        store.add_message(session_id, "assistant", "hi")

    provider = GoogleProvider(
        Settings(
            api_key="test-key",
            provider="google",
            responses_url=DEFAULT_GOOGLE_INTERACTIONS_URL,
            model=DEFAULT_GOOGLE_MODEL,
            max_tokens=DEFAULT_MAX_TOKENS,
            reasoning_effort="xhigh",
            max_retries=0,
        )
    )
    display = _SessionDisplaySpy([])
    monotonic_values = iter([30.0, 31.5])

    class _FakeHTTPResponse:
        def __init__(self, payload: dict[str, object]) -> None:
            self._payload = payload

        def read(self) -> bytes:
            return json.dumps(self._payload).encode("utf-8")

        def __enter__(self) -> _FakeHTTPResponse:
            return self

        def __exit__(self, *_: object) -> None:
            return None

    def fake_urlopen(
        request: urllib.request.Request,
        timeout: float,
    ) -> _FakeHTTPResponse:
        del request, timeout
        return _FakeHTTPResponse(
            {
                "id": "resp_google",
                "model": DEFAULT_GOOGLE_MODEL,
                "usage": {
                    "total_input_tokens": 7,
                    "total_output_tokens": 3,
                    "total_tokens": 10,
                },
                "output": [
                    {
                        "type": "message",
                        "role": "assistant",
                        "content": [{"type": "output_text", "text": "Recovered."}],
                    }
                ],
            }
        )

    monkeypatch.setattr(
        "pbi_agent.agent.session._open_runtime_provider",
        _stub_runtime_provider(provider),
    )
    monkeypatch.setattr(
        "pbi_agent.agent.session.time.monotonic",
        lambda: next(monotonic_values),
    )
    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)

    outcome = run_single_turn(
        "continue",
        Settings(
            api_key="test-key",
            provider="google",
            responses_url=DEFAULT_GOOGLE_INTERACTIONS_URL,
            model=DEFAULT_GOOGLE_MODEL,
            max_tokens=DEFAULT_MAX_TOKENS,
            reasoning_effort="xhigh",
            max_retries=0,
        ),
        display,
        resume_session_id=session_id,
    )

    assert outcome.response_id == "resp_google"
    assert display.session_usage_calls[-1].input_tokens == 17
    assert display.session_usage_calls[-1].output_tokens == 8
    assert display.session_usage_calls[-1].provider_total_tokens == 25
    assert display.session_usage_calls[-1].total_tokens == 25


def test_run_session_loop_resumed_session_bootstraps_without_previous_id_between_turns(
    monkeypatch, tmp_path
) -> None:
    monkeypatch.chdir(tmp_path)
    db_path = tmp_path / "sessions.db"
    monkeypatch.setenv("PBI_AGENT_SESSION_DB_PATH", str(db_path))

    with SessionStore(db_path=db_path) as store:
        session_id = store.create_session(
            directory=os.getcwd(),
            provider="openai",
            model=DEFAULT_MODEL,
            title="existing",
        )
        store.update_session(session_id, previous_id="resp_parent")
        store.add_message(session_id, "user", "hello")
        store.add_message(session_id, "assistant", "hi")

    provider = OpenAIProvider(Settings(api_key="test-key", provider="openai"))
    display = _SessionDisplaySpy(["continue", "more", "quit"])
    requests: list[dict[str, object]] = []
    monotonic_values = iter([5.0, 6.0, 10.0, 11.0])

    class _FakeHTTPResponse:
        def __init__(self, payload: dict[str, object]) -> None:
            self._payload = payload

        def read(self) -> bytes:
            return json.dumps(self._payload).encode("utf-8")

        def __enter__(self) -> _FakeHTTPResponse:
            return self

        def __exit__(self, *_: object) -> None:
            return None

    def fake_urlopen(
        request: urllib.request.Request,
        timeout: float,
    ) -> _FakeHTTPResponse:
        del timeout
        payload = request.data.decode("utf-8") if request.data else "{}"
        requests.append(json.loads(payload))
        if len(requests) == 1:
            return _FakeHTTPResponse(
                {
                    "id": "resp_recovered",
                    "model": DEFAULT_MODEL,
                    "usage": {
                        "input_tokens": 7,
                        "input_tokens_details": {"cached_tokens": 0},
                        "output_tokens": 3,
                        "output_tokens_details": {"reasoning_tokens": 0},
                    },
                    "output": [
                        {
                            "type": "message",
                            "role": "assistant",
                            "content": [{"type": "output_text", "text": "Recovered."}],
                        }
                    ],
                }
            )
        return _FakeHTTPResponse(
            {
                "id": "resp_next",
                "model": DEFAULT_MODEL,
                "usage": {
                    "input_tokens": 8,
                    "input_tokens_details": {"cached_tokens": 0},
                    "output_tokens": 2,
                    "output_tokens_details": {"reasoning_tokens": 0},
                },
                "output": [
                    {
                        "type": "message",
                        "role": "assistant",
                        "content": [{"type": "output_text", "text": "Next."}],
                    }
                ],
            }
        )

    monkeypatch.setattr(
        "pbi_agent.agent.session._open_runtime_provider",
        _stub_runtime_provider(provider),
    )
    monkeypatch.setattr(
        "pbi_agent.agent.session.time.monotonic",
        lambda: next(monotonic_values),
    )
    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)

    exit_code = run_session_loop(
        Settings(api_key="test-key", provider="openai"),
        display,
        resume_session_id=session_id,
    )

    assert exit_code == 0
    assert len(requests) == 2
    assert "previous_response_id" not in requests[0]
    assert requests[0]["input"] == [
        {"role": "user", "content": "hello"},
        {"role": "assistant", "content": "hi"},
        {"role": "user", "content": "continue"},
    ]
    assert "previous_response_id" not in requests[1]
    assert requests[1]["input"] == [
        {"role": "user", "content": "hello"},
        {"role": "assistant", "content": "hi"},
        {"role": "user", "content": "continue"},
        {"role": "assistant", "content": "Recovered."},
        {"role": "user", "content": "more"},
    ]


def test_run_session_loop_interrupted_openai_tool_call_does_not_poison_next_turn(
    monkeypatch, tmp_path
) -> None:
    monkeypatch.chdir(tmp_path)
    db_path = tmp_path / "sessions.db"
    monkeypatch.setenv("PBI_AGENT_SESSION_DB_PATH", str(db_path))

    with SessionStore(db_path=db_path) as store:
        session_id = store.create_session(
            directory=os.getcwd(),
            provider="openai",
            model=DEFAULT_MODEL,
            title="existing",
        )
        store.update_session(session_id, previous_id="resp_completed")
        store.add_message(session_id, "user", "summerize LICENSE")
        store.add_message(session_id, "assistant", "summary")

    provider = OpenAIProvider(Settings(api_key="test-key", provider="openai"))

    class _InterruptDisplay(_SessionDisplaySpy):
        def __init__(self) -> None:
            super().__init__(["read file", "summarize memory", "quit"])
            self.interrupt = False

        def request_interrupt(
            self, *, item_id: str | None = None, input_text: str | None = None
        ) -> None:
            del item_id, input_text
            self.interrupt = True

        def clear_interrupt(self) -> None:
            self.interrupt = False

        def interrupt_requested(self) -> bool:
            return self.interrupt

    display = _InterruptDisplay()
    requests: list[dict[str, object]] = []

    class _FakeHTTPResponse:
        def __init__(self, payload: dict[str, object]) -> None:
            self._payload = payload

        def read(self) -> bytes:
            return json.dumps(self._payload).encode("utf-8")

        def __enter__(self) -> _FakeHTTPResponse:
            return self

        def __exit__(self, *_: object) -> None:
            return None

    def fake_urlopen(
        request: urllib.request.Request,
        timeout: float,
    ) -> _FakeHTTPResponse:
        del timeout
        payload = request.data.decode("utf-8") if request.data else "{}"
        requests.append(json.loads(payload))
        if len(requests) == 1:
            display.request_interrupt()
            return _FakeHTTPResponse(
                {
                    "id": "resp_tool",
                    "model": DEFAULT_MODEL,
                    "usage": {
                        "input_tokens": 7,
                        "input_tokens_details": {"cached_tokens": 0},
                        "output_tokens": 3,
                        "output_tokens_details": {"reasoning_tokens": 0},
                    },
                    "output": [
                        {
                            "arguments": '{"path":"README.md"}',
                            "call_id": "call_1",
                            "id": "fc_1",
                            "name": "read_file",
                            "status": "completed",
                            "type": "function_call",
                        }
                    ],
                }
            )
        return _FakeHTTPResponse(
            {
                "id": "resp_ok",
                "model": DEFAULT_MODEL,
                "usage": {
                    "input_tokens": 8,
                    "input_tokens_details": {"cached_tokens": 0},
                    "output_tokens": 2,
                    "output_tokens_details": {"reasoning_tokens": 0},
                },
                "output": [
                    {
                        "type": "message",
                        "role": "assistant",
                        "content": [{"type": "output_text", "text": "ok"}],
                    }
                ],
            }
        )

    monkeypatch.setattr(
        "pbi_agent.agent.session._open_runtime_provider",
        _stub_runtime_provider(provider),
    )
    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)

    assert (
        run_session_loop(
            Settings(api_key="test-key", provider="openai"),
            display,
            resume_session_id=session_id,
        )
        == 0
    )

    assert len(requests) == 2
    assert "previous_response_id" not in requests[1]
    assert requests[1]["input"] == [
        {"role": "user", "content": "summerize LICENSE"},
        {"role": "assistant", "content": "summary"},
        {"role": "user", "content": "summarize memory"},
    ]
    with SessionStore(db_path=db_path) as store:
        sessions = store.list_sessions(os.getcwd(), limit=1)
        messages = store.list_messages(sessions[0].session_id)
    assert [(message.role, message.content) for message in messages] == [
        ("user", "summerize LICENSE"),
        ("assistant", "summary"),
        ("user", "summarize memory"),
        ("assistant", "ok"),
    ]
