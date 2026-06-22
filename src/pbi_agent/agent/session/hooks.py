from __future__ import annotations

from pathlib import Path
from typing import Callable

from pbi_agent.config import Settings
from pbi_agent.display.protocol import DisplayProtocol
from pbi_agent.hooks.runtime import HookRuntime, HookRuntimeResult
from pbi_agent.hooks.schemas import HookEventName
from pbi_agent.models.messages import CompletedResponse, TokenUsage
from pbi_agent.observability import RunTracer
from pbi_agent.session_store import SessionStore

from pbi_agent.agent.session.shared import selected_model as _selected_model


ToolIterationRunner = Callable[..., tuple[CompletedResponse, bool, int]]


def append_hook_context(
    instructions: str | None, context_text: str | None
) -> str | None:
    if not context_text:
        return instructions
    hook_block = f"<hook_context>\n{context_text.strip()}\n</hook_context>"
    if instructions:
        return f"{instructions}\n\n{hook_block}"
    return hook_block


class SessionHookCoordinator:
    def __init__(self, hook_runtime: HookRuntime) -> None:
        self.hook_runtime = hook_runtime

    @classmethod
    def for_session_loop(
        cls,
        *,
        workspace: Path,
        settings: Settings,
        session_id: str | None,
        workspace_directory_key: str | None,
        tracer: RunTracer | None = None,
    ) -> "SessionHookCoordinator":
        return cls(
            HookRuntime(
                workspace=workspace,
                settings=settings,
                session_id=session_id,
                model=_selected_model(settings),
                provider=settings.provider,
                workspace_directory_key=workspace_directory_key,
                agent_name="main",
                agent_type="session_loop",
                tracer=tracer,
            )
        )

    def run_session_start(
        self,
        *,
        reason: str,
        tracer: RunTracer | None = None,
    ) -> str | None:
        result = self.hook_runtime.run(
            HookEventName.SESSION_START,
            matcher_value=reason,
            payload={"reason": reason},
            tracer=tracer,
        )
        return result.context_text

    def run_prompt_submit(
        self,
        prompt: str,
        *,
        tracer: RunTracer | None = None,
    ) -> HookRuntimeResult:
        return self.hook_runtime.run(
            HookEventName.USER_PROMPT_SUBMIT,
            payload={"prompt": prompt},
            tracer=tracer,
        )

    def run_stop(
        self,
        response: CompletedResponse,
        *,
        tracer: RunTracer | None = None,
    ) -> HookRuntimeResult:
        return self.hook_runtime.run(
            HookEventName.STOP,
            payload={"response": response.text},
            tracer=tracer,
        )

    def run_stop_continuation(
        self,
        *,
        provider,
        prompt: str,
        response: CompletedResponse,
        settings: Settings,
        display: DisplayProtocol,
        session_usage: TokenUsage,
        turn_usage: TokenUsage,
        store: SessionStore | None,
        session_id: str | None,
        instructions: str | None,
        tracer: RunTracer | None,
        current_user_turn_text: str | None,
        run_tool_iterations: ToolIterationRunner,
    ) -> tuple[CompletedResponse, bool]:
        if self.hook_runtime.stop_hook_active:
            return response, False
        self.hook_runtime.stop_hook_active = True
        try:
            continued = provider.request_turn(
                user_message=prompt,
                instructions=instructions,
                session_id=session_id,
                display=display,
                session_usage=session_usage,
                turn_usage=turn_usage,
                tracer=tracer,
            )
            continued, had_errors, _ = run_tool_iterations(
                provider=provider,
                response=continued,
                max_workers=settings.max_tool_workers,
                display=display,
                session_usage=session_usage,
                turn_usage=turn_usage,
                store=store,
                session_id=session_id,
                current_user_turn_text=current_user_turn_text,
                instructions=instructions,
                tracer=tracer,
                hook_runtime=self.hook_runtime,
                current_turn_tool_exchanges=[],
            )
            return continued, had_errors
        finally:
            self.hook_runtime.stop_hook_active = False

    def run_subagent_start(
        self,
        *,
        agent_type: str,
        task_instruction: str,
        subagent_name: str,
        tracer: RunTracer | None = None,
    ) -> str | None:
        result = self.hook_runtime.run(
            HookEventName.SUBAGENT_START,
            matcher_value=agent_type,
            payload={
                "task_instruction": task_instruction,
                "subagent_name": subagent_name,
                "subagent_type": agent_type,
            },
            tracer=tracer,
        )
        return result.context_text

    def run_subagent_stop(
        self,
        *,
        agent_type: str,
        task_instruction: str,
        subagent_name: str,
        response: CompletedResponse,
        tracer: RunTracer | None = None,
    ) -> None:
        self.hook_runtime.run(
            HookEventName.SUBAGENT_STOP,
            matcher_value=agent_type,
            payload={
                "task_instruction": task_instruction,
                "subagent_name": subagent_name,
                "subagent_type": agent_type,
                "response": response.text,
            },
            tracer=tracer,
        )
