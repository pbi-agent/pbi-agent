from __future__ import annotations

from contextlib import contextmanager
import json
import os
import urllib.error
import urllib.request

import pytest

from pbi_agent.agent.session import (
    AGENTS_COMMAND,
    AGENTS_RELOAD_COMMAND,
    MCP_COMMAND,
    NEW_CHAT_SENTINEL,
    SKILLS_COMMAND,
    run_chat_loop,
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
from pbi_agent.providers.google_provider import GoogleProvider
from pbi_agent.providers.openai_provider import OpenAIProvider
from pbi_agent.session_store import SessionStore
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
        self.reset_chat_calls = 0

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

    def reset_chat(self) -> None:
        self.reset_chat_calls += 1

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

    def restore_messages(self, messages) -> None:
        self.restored_messages = list(messages)

    def request_turn(
        self,
        *,
        user_message: str | None = None,
        user_input: UserTurnInput | None = None,
        tool_result_items: list[dict[str, object]] | None = None,
        instructions: str | None = None,
        display,
        session_usage: TokenUsage,
        turn_usage: TokenUsage,
    ) -> CompletedResponse:
        if user_input is not None and user_message is None:
            user_message = user_input.text
        self.request_calls.append(
            {
                "user_message": user_message,
                "tool_result_items": tool_result_items,
                "instructions": instructions,
            }
        )
        del display
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
    ) -> tuple[list[dict[str, object]], bool]:
        del display, session_usage, turn_usage, sub_agent_depth
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


def test_run_single_turn_uses_mode_specific_instructions_for_full_turn(
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
    assert "<active_mode>\nPlan before coding.\n</active_mode>" in str(
        provider.request_calls[0]["instructions"]
    )
    assert (
        provider.request_calls[1]["instructions"]
        == provider.request_calls[0]["instructions"]
    )


def test_run_single_turn_does_not_activate_mode_when_command_file_is_missing(
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


class _ChatDisplaySpy(_DisplaySpy):
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
        return None

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
        display,
        session_usage: TokenUsage,
        turn_usage: TokenUsage,
    ) -> CompletedResponse:
        del display, tool_result_items
        if user_input is not None:
            self.request_inputs.append(user_input)
        if user_input is not None and user_message is None:
            user_message = user_input.text
        self.request_messages.append(user_message)
        self.request_instructions.append(instructions)
        response = CompletedResponse(
            response_id="resp_chat",
            text="Ack",
            usage=TokenUsage(input_tokens=2, output_tokens=1, model=DEFAULT_MODEL),
        )
        session_usage.add(response.usage)
        turn_usage.add(response.usage)
        return response


def test_run_chat_loop_resets_welcome_and_usage_on_new_chat(monkeypatch) -> None:
    provider = _ChatProviderStub()
    display = _ChatDisplaySpy(["hello", NEW_CHAT_SENTINEL, "after reset", "quit"])
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

    exit_code = run_chat_loop(settings, display)

    assert exit_code == 0
    assert provider.request_messages == ["hello", "after reset"]
    assert provider.reset_calls == 1
    assert len(display.welcome_calls) == 2
    assert display.welcome_calls[0]["interactive"] is True
    assert display.welcome_calls[1]["interactive"] is True
    assert [usage.total_tokens for usage in display.session_usage_calls] == [0, 3, 0, 3]
    assert display.reset_chat_calls == 1
    assert display.assistant_start_calls == 2


def test_run_chat_loop_handles_skills_command_locally(monkeypatch) -> None:
    provider = _ChatProviderStub()
    display = _ChatDisplaySpy([SKILLS_COMMAND, "quit"])
    settings = Settings(api_key="test-key", provider="openai", max_tool_workers=2)

    monkeypatch.setattr(
        "pbi_agent.agent.session._open_runtime_provider",
        _stub_runtime_provider(provider),
    )
    monkeypatch.setattr(
        "pbi_agent.agent.session.format_project_skills_markdown",
        lambda: "### Project Skills\n\n- `repo-skill`: Demo skill",
    )

    exit_code = run_chat_loop(settings, display)

    assert exit_code == 0
    assert provider.request_messages == []
    assert display.markdown_calls == [
        "### Project Skills\n\n- `repo-skill`: Demo skill"
    ]
    assert display.assistant_start_calls == 0


def test_run_chat_loop_handles_mcp_command_locally(monkeypatch) -> None:
    provider = _ChatProviderStub()
    display = _ChatDisplaySpy([MCP_COMMAND, "quit"])
    settings = Settings(api_key="test-key", provider="openai", max_tool_workers=2)

    monkeypatch.setattr(
        "pbi_agent.agent.session._open_runtime_provider",
        _stub_runtime_provider(provider),
    )
    monkeypatch.setattr(
        "pbi_agent.agent.session.format_project_mcp_servers_markdown",
        lambda: "### MCP Servers\n\n- `echo`: `uv run server.py`",
    )

    exit_code = run_chat_loop(settings, display)

    assert exit_code == 0
    assert provider.request_messages == []
    assert display.markdown_calls == ["### MCP Servers\n\n- `echo`: `uv run server.py`"]
    assert display.assistant_start_calls == 0


def test_run_chat_loop_handles_agents_command_locally(monkeypatch) -> None:
    provider = _ChatProviderStub()
    display = _ChatDisplaySpy([AGENTS_COMMAND, "quit"])
    settings = Settings(api_key="test-key", provider="openai", max_tool_workers=2)

    monkeypatch.setattr(
        "pbi_agent.agent.session._open_runtime_provider",
        _stub_runtime_provider(provider),
    )
    monkeypatch.setattr(
        "pbi_agent.agent.session.format_project_sub_agents_markdown",
        lambda reloaded=False: "### Sub-Agents\n\n- `reviewer`: Reviews code",
    )

    exit_code = run_chat_loop(settings, display)

    assert exit_code == 0
    assert provider.request_messages == []
    assert display.markdown_calls == ["### Sub-Agents\n\n- `reviewer`: Reviews code"]
    assert display.assistant_start_calls == 0


def test_run_chat_loop_handles_agents_reload_command_locally(monkeypatch) -> None:
    provider = _ChatProviderStub()
    display = _ChatDisplaySpy([AGENTS_RELOAD_COMMAND, "quit"])
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

    exit_code = run_chat_loop(settings, display)

    assert exit_code == 0
    assert provider.request_messages == []
    assert provider.system_prompts == ["updated prompt"]
    assert provider.refresh_tools_calls == 1
    assert display.markdown_calls == ["### Sub-Agents\n\nReloaded"]
    assert display.assistant_start_calls == 0


def test_run_chat_loop_keeps_mode_alias_and_uses_turn_specific_instructions(
    monkeypatch,
    tmp_path,
) -> None:
    monkeypatch.chdir(tmp_path)
    provider = _ChatProviderStub()
    display = _ChatDisplaySpy(["/plan draft the approach", "quit"])
    settings = Settings(api_key="test-key", provider="openai", max_tool_workers=2)
    _write_command(tmp_path, "plan", "Plan before coding.")

    monkeypatch.setattr(
        "pbi_agent.agent.session._open_runtime_provider",
        _stub_runtime_provider(provider),
    )

    exit_code = run_chat_loop(settings, display)

    assert exit_code == 0
    assert provider.request_messages == ["/plan draft the approach"]
    assert provider.request_instructions[0] is not None
    assert "<active_mode>\nPlan before coding.\n</active_mode>" in str(
        provider.request_instructions[0]
    )


def test_run_chat_loop_accepts_mode_only_turn(monkeypatch, tmp_path) -> None:
    monkeypatch.chdir(tmp_path)
    provider = _ChatProviderStub()
    display = _ChatDisplaySpy(["/plan", "quit"])
    settings = Settings(api_key="test-key", provider="openai", max_tool_workers=2)
    _write_command(tmp_path, "plan", "Plan before coding.")

    monkeypatch.setattr(
        "pbi_agent.agent.session._open_runtime_provider",
        _stub_runtime_provider(provider),
    )

    exit_code = run_chat_loop(settings, display)

    assert exit_code == 0
    assert provider.request_messages == ["/plan"]


def test_run_chat_loop_keeps_local_command_precedence_over_modes(monkeypatch) -> None:
    provider = _ChatProviderStub()
    display = _ChatDisplaySpy([SKILLS_COMMAND, "quit"])
    settings = Settings(api_key="test-key", provider="openai", max_tool_workers=2)

    monkeypatch.setattr(
        "pbi_agent.agent.session._open_runtime_provider",
        _stub_runtime_provider(provider),
    )
    monkeypatch.setattr(
        "pbi_agent.agent.session.format_project_skills_markdown",
        lambda: "### Project Skills\n\n- `repo-skill`: Demo skill",
    )

    exit_code = run_chat_loop(settings, display)

    assert exit_code == 0
    assert provider.request_messages == []
    assert display.markdown_calls == [
        "### Project Skills\n\n- `repo-skill`: Demo skill"
    ]


def test_run_chat_loop_passes_queued_image_paths_to_provider(monkeypatch) -> None:
    provider = _ChatProviderStub()
    display = _ChatDisplaySpy(
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

    exit_code = run_chat_loop(settings, display)

    assert exit_code == 0
    assert provider.request_messages == ["describe this"]
    assert len(provider.request_inputs) == 1
    assert provider.request_inputs[0].images[0].path == "chart.png"


def test_run_chat_loop_processes_attachment_only_queued_images(monkeypatch) -> None:
    provider = _ChatProviderStub()
    display = _ChatDisplaySpy(
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

    exit_code = run_chat_loop(settings, display)

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


def test_run_chat_loop_does_not_persist_unanswered_user_turn(monkeypatch) -> None:
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
            display,
            session_usage: TokenUsage,
            turn_usage: TokenUsage,
        ) -> CompletedResponse:
            del (
                user_message,
                user_input,
                tool_result_items,
                instructions,
                display,
                session_usage,
                turn_usage,
            )
            raise RuntimeError("boom")

    display = _ChatDisplaySpy(["hello"])
    settings = Settings(api_key="test-key", provider="openai", max_tool_workers=2)

    monkeypatch.setattr(
        "pbi_agent.agent.session._open_runtime_provider",
        _stub_runtime_provider(_FailingProvider()),
    )

    with pytest.raises(RuntimeError, match="boom"):
        run_chat_loop(settings, display)

    with SessionStore() as store:
        sessions = store.list_sessions(os.getcwd(), limit=10)
        assert len(sessions) == 1
        assert store.list_messages(sessions[0].session_id) == []


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

    provider = OpenAIProvider(Settings(api_key="test-key", provider="openai"))
    display = _ChatDisplaySpy([])
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
    display = _ChatDisplaySpy([])
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
    display = _ChatDisplaySpy([])
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


def test_run_chat_loop_resumed_session_bootstraps_once_then_uses_previous_response_id(
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
    display = _ChatDisplaySpy(["continue", "more", "quit"])
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

    exit_code = run_chat_loop(
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
    assert requests[1]["previous_response_id"] == "resp_recovered"
    assert requests[1]["input"] == [{"role": "user", "content": "more"}]
