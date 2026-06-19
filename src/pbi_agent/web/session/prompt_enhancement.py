from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any, Protocol

from pbi_agent.agent.session.runtime import open_runtime_provider
from pbi_agent.config import ResolvedRuntime
from pbi_agent.display.protocol import (
    DisplayProtocol,
    PendingToolCall,
    PendingUserQuestion,
    QueuedInput,
    QueuedRuntimeChange,
    UserQuestionAnswer,
)
from pbi_agent.models.messages import (
    ImageAttachment,
    TokenUsage,
    UserTurnInput,
    WebSearchSource,
)
from pbi_agent.observability import RunTracer
from pbi_agent.session_store import (
    MessageImageAttachment,
    MessageRecord,
    SessionRecord,
    SessionStore,
)
from pbi_agent.tools.catalog import ToolCatalog

_PROMPT_ENHANCEMENT_SYSTEM_PROMPT = (
    "Transform the user's task description into a concise, actionable, and domain-appropriate instruction for the agent. "
    "Identify the subject domain (such as software engineering, data analysis, DevOps, security, legal, medical, finance, or scientific work) and rewrite the draft using the correct, precise terminology, conventions, and phrasing native to that domain, while strictly preserving the user's intent, scope, language, and important ordering. "
    "Use direct imperative wording, remove filler, and fix grammar, typos, and unclear phrasing. Replace vague or colloquial terms with the accepted technical equivalent for the identified domain, but do not introduce new requirements, constraints, or domain assumptions beyond what the user implied. "
    "Ensure all composer tokens (such as @file references and $skill tags), file paths, code, commands, identifiers, API names, and quoted text remain exactly as provided. "
    "Do not answer the task, add requirements, make assumptions, ask questions, or omit important details. "
    "If the draft is already a clear, well-phrased domain instruction, only lightly polish it. "
    "Output only the enhanced instruction text, with no preamble, explanations, labels, newly added code fences, or surrounding quotation marks."
)


class _LiveSessionWithRuntime(Protocol):
    runtime: ResolvedRuntime


class _SavedRuntimeResolver(Protocol):
    def __call__(
        self,
        session_id: str,
        *,
        fallback: ResolvedRuntime,
    ) -> ResolvedRuntime: ...


@dataclass(slots=True)
class PromptEnhancementResult:
    text: str
    session: SessionRecord | None = None


class NoopPromptEnhancementDisplay:
    verbose = False

    def bind_session(self, session_id: str | None) -> None:
        del session_id

    def request_shutdown(self) -> None:
        return None

    def request_interrupt(
        self, *, item_id: str | None = None, input_text: str | None = None
    ) -> None:
        del item_id, input_text

    def clear_interrupt(self) -> None:
        return None

    def interrupt_requested(self) -> bool:
        return False

    def submit_input(
        self,
        value: str,
        *,
        file_paths: list[str] | None = None,
        image_paths: list[str] | None = None,
        images: list[ImageAttachment] | None = None,
        image_attachments: list[MessageImageAttachment] | None = None,
        interactive_mode: bool = False,
        include_tool_history: bool = False,
        item_id: str | None = None,
    ) -> None:
        del (
            value,
            file_paths,
            image_paths,
            images,
            image_attachments,
            interactive_mode,
            include_tool_history,
            item_id,
        )

    def request_new_session(self) -> None:
        return None

    def ask_user_questions(
        self, questions: list[PendingUserQuestion]
    ) -> list[UserQuestionAnswer]:
        del questions
        return []

    def reset_session(self) -> None:
        return None

    def begin_sub_agent(
        self,
        *,
        task_instruction: str,
        reasoning_effort: str | None = None,
        name: str = "sub_agent",
    ) -> DisplayProtocol:
        del task_instruction, reasoning_effort, name
        return self

    def finish_sub_agent(self, *, status: str) -> None:
        del status

    def welcome(
        self,
        *,
        interactive: bool = True,
        model: str | None = None,
        reasoning_effort: str | None = None,
        single_turn_hint: str | None = None,
    ) -> None:
        del interactive, model, reasoning_effort, single_turn_hint

    def user_prompt(self) -> str | QueuedInput | QueuedRuntimeChange:
        raise RuntimeError("Prompt enhancement does not read interactive input.")

    def assistant_start(self) -> None:
        return None

    def assistant_stop(self) -> None:
        return None

    def tool_execution_start(self, calls: list[PendingToolCall]) -> None:
        del calls

    def tool_execution_stop(self) -> None:
        return None

    def wait_start(self, message: str = "model is processing your request...") -> None:
        del message

    def wait_stop(self) -> None:
        return None

    def render_user_message(self, text: str) -> None:
        del text

    def render_markdown(self, text: str) -> None:
        del text

    def render_thinking(
        self,
        text: str | None = None,
        *,
        title: str | None = None,
        replace_existing: bool = False,
        widget_id: str | None = None,
    ) -> str | None:
        del text, title, replace_existing
        return widget_id

    def render_redacted_thinking(self) -> None:
        return None

    def session_usage(self, usage: TokenUsage) -> None:
        del usage

    def turn_usage(self, usage: TokenUsage, elapsed_seconds: float) -> None:
        del usage, elapsed_seconds

    def shell_start(self, commands: list[str]) -> None:
        del commands

    def shell_command(
        self,
        command: str,
        exit_code: int | None,
        timed_out: bool,
        *,
        call_id: str = "",
        working_directory: str = ".",
        timeout_ms: int | str = "default",
        result: Any = None,
    ) -> None:
        del (
            command,
            exit_code,
            timed_out,
            call_id,
            working_directory,
            timeout_ms,
            result,
        )

    def patch_start(self, count: int) -> None:
        del count

    def patch_result(
        self,
        path: str,
        operation: str,
        success: bool,
        *,
        call_id: str = "",
        detail: str = "",
        diff: str = "",
        diff_line_numbers: list[dict[str, int | None]] | None = None,
        tool_name: str = "apply_patch",
        arguments: Any = None,
        result: Any = None,
    ) -> None:
        del (
            path,
            operation,
            success,
            call_id,
            detail,
            diff,
            diff_line_numbers,
            tool_name,
            arguments,
            result,
        )

    def function_start(self, count: int) -> None:
        del count

    def function_result(
        self,
        name: str,
        success: bool,
        *,
        call_id: str = "",
        arguments: Any = None,
        result: Any = None,
    ) -> None:
        del name, success, call_id, arguments, result

    def tool_group_end(self) -> None:
        return None

    def retry_notice(self, attempt: int, max_retries: int) -> None:
        del attempt, max_retries

    def rate_limit_notice(
        self,
        *,
        wait_seconds: float,
        attempt: int,
        max_retries: int,
    ) -> None:
        del wait_seconds, attempt, max_retries

    def overload_notice(
        self,
        *,
        wait_seconds: float,
        attempt: int,
        max_retries: int,
    ) -> None:
        del wait_seconds, attempt, max_retries

    def error(self, message: str) -> None:
        del message

    def debug(self, message: str) -> None:
        del message

    def web_search_sources(self, sources: list[WebSearchSource]) -> None:
        del sources

    def replay_history(self, messages: list[MessageRecord]) -> None:
        del messages


class PromptEnhancementService:
    def __init__(
        self,
        *,
        directory_key: str,
        workspace_root: Path,
        default_runtime: ResolvedRuntime,
        resolve_runtime: Callable[[str | None], ResolvedRuntime],
        resolve_saved_session_runtime: _SavedRuntimeResolver,
        find_live_session: Callable[[str], _LiveSessionWithRuntime | None],
    ) -> None:
        self._directory_key = directory_key
        self._workspace_root = workspace_root
        self._default_runtime = default_runtime
        self._resolve_runtime = resolve_runtime
        self._resolve_saved_session_runtime = resolve_saved_session_runtime
        self._find_live_session = find_live_session

    def enhance_prompt(
        self,
        *,
        text: str,
        session_id: str | None = None,
    ) -> PromptEnhancementResult:
        self._validate_text(text)
        runtime = self._runtime(session_id)
        if session_id is None:
            enhanced_text, _turn_usage = self._request_enhancement(
                runtime=runtime,
                text=text,
                context_messages=[],
                session_id=None,
                tracer=None,
            )
            return PromptEnhancementResult(text=enhanced_text)

        with SessionStore() as store:
            record = self._require_session(store, session_id)
            context_messages = store.list_messages(session_id)
            tracer = self._start_tracer(store, session_id, runtime)
            enhanced_text, turn_usage = self._request_enhancement(
                runtime=runtime,
                text=text,
                context_messages=context_messages,
                session_id=session_id,
                tracer=tracer,
            )
            updated = self._record_usage(store, record, turn_usage)
            return PromptEnhancementResult(text=enhanced_text, session=updated)

    def _runtime(self, session_id: str | None) -> ResolvedRuntime:
        if session_id is None:
            return self._resolve_runtime(None)
        live_session = self._find_live_session(session_id)
        if live_session is not None:
            return live_session.runtime
        return self._resolve_saved_session_runtime(
            session_id,
            fallback=self._default_runtime,
        )

    def _request_enhancement(
        self,
        *,
        runtime: ResolvedRuntime,
        text: str,
        context_messages: list[MessageRecord],
        session_id: str | None,
        tracer: RunTracer | None,
    ) -> tuple[str, TokenUsage]:
        display: DisplayProtocol = NoopPromptEnhancementDisplay()
        session_usage = TokenUsage(
            model=runtime.settings.model,
            service_tier=runtime.settings.service_tier or "",
        )
        turn_usage = TokenUsage(
            model=runtime.settings.model,
            service_tier=runtime.settings.service_tier or "",
        )
        tracer_finished = False
        try:
            prompt_input = _prompt_enhancement_user_input(text, context_messages)
            no_tool_runtime = replace(
                runtime,
                settings=replace(runtime.settings, allowed_tools=()),
                tool_availability_overridden=True,
            )
            with open_runtime_provider(
                no_tool_runtime,
                system_prompt=_PROMPT_ENHANCEMENT_SYSTEM_PROMPT,
                tool_catalog=ToolCatalog(),
                tool_availability_overridden=True,
                workspace_root=self._workspace_root,
                workspace_directory_key=self._directory_key,
            ) as provider:
                response = provider.request_turn(
                    user_input=UserTurnInput(text=prompt_input),
                    instructions=None,
                    session_id=session_id,
                    display=display,
                    session_usage=session_usage,
                    turn_usage=turn_usage,
                    tracer=tracer,
                )

            if response.has_tool_calls:
                raise RuntimeError(
                    "Prompt enhancement returned an unsupported tool call."
                )
            if not response.text.strip():
                raise RuntimeError("Prompt enhancement returned an empty response.")

            if tracer is not None:
                tracer.finish(
                    status="completed",
                    usage=turn_usage,
                    metadata={"hidden": True},
                )
                tracer_finished = True
            return response.text, turn_usage
        except Exception as exc:
            if tracer is not None and not tracer_finished:
                tracer.log_error(str(exc), metadata={"phase": "prompt_enhancement"})
                tracer.finish(
                    status="failed",
                    usage=turn_usage,
                    metadata={"hidden": True, "error_message": str(exc)},
                )
            raise

    def _start_tracer(
        self,
        store: SessionStore,
        session_id: str,
        runtime: ResolvedRuntime,
    ) -> RunTracer:
        return RunTracer.start(
            store=store,
            session_id=session_id,
            agent_name="main",
            agent_type="prompt_enhancement",
            provider=runtime.settings.provider,
            provider_id=runtime.provider_id,
            profile_id=runtime.profile_id,
            model=runtime.settings.model,
            metadata={
                "hidden": True,
                "reasoning_effort": runtime.settings.reasoning_effort,
            },
        )

    def _require_session(self, store: SessionStore, session_id: str) -> SessionRecord:
        record = store.get_session(session_id)
        if record is None or record.directory != self._directory_key:
            raise KeyError(session_id)
        return record

    def _record_usage(
        self,
        store: SessionStore,
        record: SessionRecord,
        turn_usage: TokenUsage,
    ) -> SessionRecord:
        snap = turn_usage.snapshot()
        store.update_session(
            record.session_id,
            total_tokens=record.total_tokens + snap.total_tokens,
            input_tokens=record.input_tokens + snap.input_tokens,
            output_tokens=record.output_tokens + snap.output_tokens,
            cost_usd=record.cost_usd + snap.estimated_cost_usd,
        )
        updated = store.get_session(record.session_id)
        if updated is None:
            raise KeyError(record.session_id)
        return updated

    @staticmethod
    def _validate_text(text: str) -> None:
        stripped = text.strip()
        if not stripped:
            raise ValueError("Prompt text cannot be empty.")
        if stripped.startswith("/"):
            raise ValueError("Slash commands cannot be enhanced.")
        if stripped.startswith("!"):
            raise ValueError("Shell commands cannot be enhanced.")


def _prompt_enhancement_user_input(
    draft: str,
    messages: list[MessageRecord],
) -> str:
    last_user = next(
        (
            message.content
            for message in reversed(messages)
            if message.role == "user" and message.content.strip()
        ),
        None,
    )
    last_assistant = next(
        (
            message.content
            for message in reversed(messages)
            if message.role == "assistant" and message.content.strip()
        ),
        None,
    )
    sections = [
        "Turn the current composer draft into a concise, actionable instruction."
    ]
    if last_user or last_assistant:
        sections.append("Recent context for intent only:")
        if last_user:
            sections.extend(["Last user input:", last_user])
        if last_assistant:
            sections.extend(["Last assistant output:", last_assistant])
    sections.extend(["Current composer draft:", draft])
    return "\n\n".join(sections)
