from __future__ import annotations

from contextlib import contextmanager
from dataclasses import replace
import logging
import os
import time
from pathlib import Path
from typing import TYPE_CHECKING, Any

from pbi_agent.agent.system_prompt import (
    get_custom_excluded_tools,
    get_sub_agent_system_prompt,
    get_system_prompt,
)
from pbi_agent.agent.sub_agent_discovery import (
    format_project_sub_agents_markdown,
    get_project_sub_agent_by_name,
)
from pbi_agent.agent.skill_discovery import format_project_skills_markdown
from pbi_agent.config import ResolvedRuntime, Settings, resolve_runtime_for_profile_id
from pbi_agent.media import load_workspace_image
from pbi_agent.mcp import format_project_mcp_servers_markdown
from pbi_agent.models.messages import (
    AgentOutcome,
    CompletedResponse,
    ImageAttachment,
    TokenUsage,
    UserTurnInput,
)
from pbi_agent.providers import create_provider
from pbi_agent.providers.base import Provider

if TYPE_CHECKING:
    from pbi_agent.tools.catalog import ToolCatalog
from pbi_agent.providers.capabilities import provider_supports_images
from pbi_agent.session_store import MessageImageAttachment, SessionStore
from pbi_agent.tools.types import ParentContextSnapshot
from pbi_agent.display.protocol import (
    DisplayProtocol,
    QueuedInput,
    QueuedRuntimeChange,
)

_log = logging.getLogger(__name__)

NEW_CHAT_SENTINEL = "__new_chat__"
RESUME_SESSION_PREFIX = "__resume_session__:"
SUB_AGENT_MAX_REQUESTS = 50
SUB_AGENT_MAX_ELAPSED_SECONDS = 600.0
SUB_AGENT_DISABLED_TOOLS = {"sub_agent"}
SKILLS_COMMAND = "/skills"
MCP_COMMAND = "/mcp"
AGENTS_COMMAND = "/agents"
AGENTS_RELOAD_COMMAND = "/agents reload"


class SubAgentRunError(RuntimeError):
    def __init__(self, error_type: str, message: str) -> None:
        super().__init__(message)
        self.error_type = error_type
        self.message = message


# ---------------------------------------------------------------------------
# Public entry-points
# ---------------------------------------------------------------------------


def _selected_model(settings: Settings) -> str:
    return settings.model


def _selected_sub_agent_model(settings: Settings) -> str:
    return settings.sub_agent_model or settings.model


def _bind_session(display: DisplayProtocol, session_id: str | None) -> None:
    binder = getattr(display, "bind_session", None)
    if callable(binder):
        binder(session_id)


def _coerce_runtime(value: Settings | ResolvedRuntime) -> ResolvedRuntime:
    if isinstance(value, ResolvedRuntime):
        return value
    return ResolvedRuntime(
        settings=value,
        provider_id="",
        profile_id="",
    )


def run_single_turn(
    prompt: str,
    settings: Settings | ResolvedRuntime,
    display: DisplayProtocol,
    *,
    single_turn_hint: str | None = None,
    resume_session_id: str | None = None,
    image_paths: list[str] | None = None,
) -> AgentOutcome:
    runtime = _coerce_runtime(settings)
    store = _open_store(runtime.settings)
    if resume_session_id is not None:
        runtime = _runtime_for_saved_session(store, resume_session_id, runtime)
    settings = runtime.settings
    display.welcome(
        interactive=False,
        model=_selected_model(settings),
        reasoning_effort=settings.reasoning_effort,
        single_turn_hint=single_turn_hint,
    )
    model = _selected_model(settings)
    _tier = settings.service_tier or ""
    session_usage = TokenUsage(model=model, service_tier=_tier)
    display.session_usage(session_usage)
    session_start = time.monotonic()
    turn_usage = TokenUsage(model=model, service_tier=_tier)

    user_input = _build_user_turn_input(
        text=prompt,
        image_paths=image_paths or [],
        images=None,
        settings=settings,
    )
    user_turn_history_text = _user_turn_history_text(user_input)
    session_id = resume_session_id or _create_session(
        store,
        runtime,
        title=_session_title_for_user_turn(user_input),
    )

    with _open_runtime_provider(
        settings,
        excluded_tools=get_custom_excluded_tools(),
    ) as provider:
        _resume_session(
            provider=provider,
            store=store,
            session_id=resume_session_id,
            session_usage=session_usage,
            display=display,
        )
        response = _request_user_turn(
            provider=provider,
            user_input=user_input,
            display=display,
            session_usage=session_usage,
            turn_usage=turn_usage,
        )
        response, had_tool_errors, _ = _run_tool_iterations(
            provider=provider,
            response=response,
            max_workers=settings.max_tool_workers,
            display=display,
            session_usage=session_usage,
            turn_usage=turn_usage,
            store=store,
            session_id=session_id,
            current_user_turn_text=user_turn_history_text,
        )
        _add_message(
            store,
            session_id,
            runtime,
            "user",
            user_turn_history_text,
        )
        _add_message(store, session_id, runtime, "assistant", response.text)
        _update_session_after_turn(
            store,
            session_id,
            runtime,
            _conversation_checkpoint_for_resume(provider, response.response_id),
            session_usage,
        )
        elapsed = time.monotonic() - session_start
        display.turn_usage(turn_usage, elapsed)
        display.session_usage(session_usage)
        _close_store(store)
        return AgentOutcome(
            response_id=response.response_id,
            text=response.text,
            tool_errors=had_tool_errors,
            session_id=session_id,
        )


def run_chat_loop(
    settings: Settings | ResolvedRuntime,
    display: DisplayProtocol,
    *,
    resume_session_id: str | None = None,
) -> int:
    current_runtime = _coerce_runtime(settings)
    store = _open_store(current_runtime.settings)
    session_id: str | None = resume_session_id
    title_set = bool(resume_session_id)
    resume_session_to_restore = resume_session_id
    replay_history_on_restore = resume_session_id is not None
    should_exit = False

    def _reset_session(
        active_runtime: ResolvedRuntime, *, clear_display: bool = False
    ) -> TokenUsage:
        if clear_display:
            display.reset_chat()
        active_settings = active_runtime.settings
        display.welcome(
            model=_selected_model(active_settings),
            reasoning_effort=active_settings.reasoning_effort,
        )
        new_usage = TokenUsage(
            model=_selected_model(active_settings),
            service_tier=active_settings.service_tier or "",
        )
        display.session_usage(new_usage)
        return new_usage

    if resume_session_id is not None:
        current_runtime = _runtime_for_saved_session(
            store,
            resume_session_id,
            current_runtime,
        )
    session_usage = _reset_session(current_runtime)
    _bind_session(display, session_id)
    had_tool_errors = False
    while not should_exit:
        with _open_runtime_provider(
            current_runtime.settings,
            excluded_tools=get_custom_excluded_tools(),
        ) as provider:
            if resume_session_to_restore is not None:
                _resume_session(
                    provider=provider,
                    store=store,
                    session_id=resume_session_to_restore,
                    session_usage=session_usage,
                    display=display,
                    replay_history=replay_history_on_restore,
                )
                resume_session_to_restore = None
                replay_history_on_restore = False
            while True:
                queued_input = display.user_prompt()
                file_paths: list[str] = []
                image_paths: list[str] = []
                queued_images: list[ImageAttachment] = []
                message_image_attachments: list[MessageImageAttachment] = []
                if isinstance(queued_input, QueuedRuntimeChange):
                    current_runtime = queued_input.runtime
                    _persist_runtime_change(
                        store,
                        session_id,
                        current_runtime,
                    )
                    session_usage = _reset_session(
                        current_runtime,
                    )
                    if session_id is not None:
                        resume_session_to_restore = session_id
                        replay_history_on_restore = False
                        _bind_session(display, session_id)
                    break
                if isinstance(queued_input, QueuedInput):
                    user_input = queued_input.text.strip()
                    file_paths = queued_input.file_paths
                    image_paths = queued_input.image_paths
                    queued_images = queued_input.images
                    message_image_attachments = queued_input.image_attachments
                else:
                    user_input = queued_input.strip()
                if user_input == NEW_CHAT_SENTINEL:
                    provider.reset_conversation()
                    session_usage = _reset_session(
                        current_runtime,
                        clear_display=True,
                    )
                    had_tool_errors = False
                    session_id = None
                    title_set = False
                    _bind_session(display, session_id)
                    continue
                if user_input.startswith(RESUME_SESSION_PREFIX):
                    resume_id = user_input[len(RESUME_SESSION_PREFIX) :]
                    provider.reset_conversation()
                    current_runtime = _runtime_for_saved_session(
                        store,
                        resume_id,
                        current_runtime,
                    )
                    session_usage = _reset_session(
                        current_runtime,
                        clear_display=True,
                    )
                    had_tool_errors = False
                    session_id = None
                    title_set = False
                    if store:
                        session_id = resume_id
                        title_set = True
                        _bind_session(display, session_id)
                        resume_session_to_restore = resume_id
                        replay_history_on_restore = True
                        break
                    else:
                        _bind_session(display, session_id)
                    continue
                if user_input.lower() in {"exit", "quit"}:
                    should_exit = True
                    break
                normalized_command = _normalize_user_command(user_input)
                if normalized_command == SKILLS_COMMAND:
                    display.render_markdown(format_project_skills_markdown())
                    continue
                if normalized_command == MCP_COMMAND:
                    display.render_markdown(format_project_mcp_servers_markdown())
                    continue
                if normalized_command == AGENTS_COMMAND:
                    display.render_markdown(format_project_sub_agents_markdown())
                    continue
                if normalized_command == AGENTS_RELOAD_COMMAND:
                    _reload_provider_sub_agents(provider)
                    display.render_markdown(
                        format_project_sub_agents_markdown(reloaded=True)
                    )
                    continue
                if not user_input and not image_paths and not queued_images:
                    continue

                turn_input = _build_user_turn_input(
                    text=user_input,
                    image_paths=image_paths,
                    images=queued_images,
                    settings=current_runtime.settings,
                )
                turn_history_text = _user_turn_history_text(turn_input)

                if session_id is None:
                    session_id = _create_session(
                        store,
                        current_runtime,
                        title=_session_title_for_user_turn(turn_input),
                    )
                    title_set = True
                    _bind_session(display, session_id)
                elif not title_set:
                    _update_session_title(
                        store,
                        session_id,
                        _session_title_for_user_turn(turn_input),
                    )
                    title_set = True

                turn_start = time.monotonic()
                turn_usage = TokenUsage(
                    model=_selected_model(current_runtime.settings),
                    service_tier=current_runtime.settings.service_tier or "",
                )
                display.assistant_start()
                response = _request_user_turn(
                    provider=provider,
                    user_input=turn_input,
                    display=display,
                    session_usage=session_usage,
                    turn_usage=turn_usage,
                )
                response, loop_had_errors, _ = _run_tool_iterations(
                    provider=provider,
                    response=response,
                    max_workers=current_runtime.settings.max_tool_workers,
                    display=display,
                    session_usage=session_usage,
                    turn_usage=turn_usage,
                    store=store,
                    session_id=session_id,
                    current_user_turn_text=turn_history_text,
                )

                _add_message(
                    store,
                    session_id,
                    current_runtime,
                    "user",
                    turn_history_text,
                    file_paths=file_paths,
                    image_attachments=message_image_attachments,
                )
                _add_message(
                    store,
                    session_id,
                    current_runtime,
                    "assistant",
                    response.text,
                )
                _update_session_after_turn(
                    store,
                    session_id,
                    current_runtime,
                    _conversation_checkpoint_for_resume(
                        provider,
                        response.response_id,
                    ),
                    session_usage,
                )
                had_tool_errors = had_tool_errors or loop_had_errors
                elapsed = time.monotonic() - turn_start
                display.turn_usage(turn_usage, elapsed)
                display.session_usage(session_usage)

    _close_store(store)
    return 4 if had_tool_errors else 0


def run_sub_agent_task(
    task_instruction: str,
    settings: Settings,
    display: DisplayProtocol,
    *,
    parent_session_usage: TokenUsage,
    parent_turn_usage: TokenUsage,
    sub_agent_depth: int = 0,
    tool_catalog: "ToolCatalog | None" = None,
    agent_type: str | None = None,
    include_context: bool = False,
    parent_context: ParentContextSnapshot | None = None,
) -> dict[str, Any]:
    agent_definition = None
    if agent_type is not None:
        agent_definition = get_project_sub_agent_by_name(agent_type)
        if agent_definition is None:
            return {
                "status": "failed",
                "error": {
                    "type": "unknown_agent_type",
                    "message": f"No project sub-agent named '{agent_type}' is loaded.",
                },
            }

    child_settings = replace(
        settings,
        model=getattr(agent_definition, "model", None)
        or _selected_sub_agent_model(settings),
        reasoning_effort=getattr(agent_definition, "reasoning_effort", None)
        or settings.reasoning_effort,
    )
    from pbi_agent.agent.names import pick_deity_name

    child_name = (
        agent_definition.name if agent_definition is not None else pick_deity_name()
    )
    child_display = display.begin_sub_agent(
        task_instruction=task_instruction,
        reasoning_effort=child_settings.reasoning_effort,
        name=child_name,
    )
    _child_tier = child_settings.service_tier or ""
    child_session_usage = TokenUsage(
        model=_selected_model(child_settings), service_tier=_child_tier
    )
    child_turn_usage = TokenUsage(
        model=_selected_model(child_settings), service_tier=_child_tier
    )
    child_display.session_usage(child_session_usage)
    started_at = time.monotonic()
    request_count = 0

    try:
        with _open_runtime_provider(
            child_settings,
            system_prompt=get_sub_agent_system_prompt(
                agent_prompt_override=(
                    agent_definition.system_prompt
                    if agent_definition is not None
                    else None
                )
            ),
            excluded_tools=SUB_AGENT_DISABLED_TOOLS | get_custom_excluded_tools(),
            tool_catalog=tool_catalog,
        ) as provider:
            _apply_sub_agent_parent_context(
                provider=provider,
                provider_name=child_settings.provider,
                include_context=include_context,
                parent_context=parent_context,
            )
            child_user_message = _build_sub_agent_initial_message(
                task_instruction,
                provider_name=child_settings.provider,
                include_context=include_context,
                parent_context=parent_context,
            )
            _raise_if_sub_agent_timed_out(started_at)
            response = provider.request_turn(
                user_message=child_user_message,
                display=child_display,
                session_usage=child_session_usage,
                turn_usage=child_turn_usage,
            )
            request_count += 1
            response, had_tool_errors, request_count = _run_tool_iterations(
                provider=provider,
                response=response,
                max_workers=child_settings.max_tool_workers,
                display=child_display,
                session_usage=child_session_usage,
                turn_usage=child_turn_usage,
                sub_agent_depth=sub_agent_depth + 1,
                max_requests=SUB_AGENT_MAX_REQUESTS,
                request_count=request_count,
                started_at=started_at,
                max_elapsed_seconds=SUB_AGENT_MAX_ELAPSED_SECONDS,
            )
            elapsed = time.monotonic() - started_at
            child_display.turn_usage(child_turn_usage, elapsed)
            child_display.finish_sub_agent(status="completed")
            return {
                "status": "completed",
                "final_output": response.text,
            }
    except SubAgentRunError as exc:
        child_display.error(exc.message)
        child_display.finish_sub_agent(status="failed")
        return {
            "status": "failed",
            "error": {"type": exc.error_type, "message": exc.message},
        }
    except Exception as exc:
        message = str(exc) or exc.__class__.__name__
        child_display.error(message)
        child_display.finish_sub_agent(status="failed")
        return {
            "status": "failed",
            "error": {"type": "sub_agent_failed", "message": message},
        }
    finally:
        parent_session_usage.add_sub_agent(child_session_usage)
        parent_turn_usage.add_sub_agent(child_turn_usage)
        display.session_usage(parent_session_usage)


@contextmanager
def _open_runtime_provider(
    settings: Settings,
    *,
    system_prompt: str | None = None,
    excluded_tools: set[str] | None = None,
    tool_catalog: "ToolCatalog | None" = None,
):
    from pbi_agent.mcp import McpServerPool

    if tool_catalog is not None:
        provider = create_provider(
            settings,
            system_prompt=system_prompt,
            excluded_tools=excluded_tools,
            tool_catalog=tool_catalog,
        )
        with provider:
            yield provider
    else:
        with McpServerPool(Path.cwd()) as mcp_pool:
            provider = create_provider(
                settings,
                system_prompt=system_prompt,
                excluded_tools=excluded_tools,
                tool_catalog=mcp_pool.to_tool_catalog(),
            )
            with provider:
                yield provider


# ---------------------------------------------------------------------------
# Tool iteration loop
# ---------------------------------------------------------------------------


def _run_tool_iterations(
    *,
    provider,
    response,
    max_workers: int,
    display: DisplayProtocol,
    session_usage: TokenUsage,
    turn_usage: TokenUsage,
    sub_agent_depth: int = 0,
    max_requests: int | None = None,
    request_count: int = 0,
    started_at: float | None = None,
    max_elapsed_seconds: float | None = None,
    store: SessionStore | None = None,
    session_id: str | None = None,
    current_user_turn_text: str | None = None,
) -> tuple[CompletedResponse, bool, int]:
    had_errors = False

    while response.has_tool_calls:
        if started_at is not None and max_elapsed_seconds is not None:
            _raise_if_sub_agent_timed_out(
                started_at,
                max_elapsed_seconds=max_elapsed_seconds,
            )
        display.debug("model requested tool execution")
        _log.debug(
            "Executing tool iteration: %d function call(s)",
            len(response.function_calls),
        )

        try:
            parent_context = None
            if any(call.name == "sub_agent" for call in response.function_calls):
                parent_context = _build_parent_context_snapshot(
                    provider=provider,
                    store=store,
                    session_id=session_id,
                    current_user_turn_text=current_user_turn_text,
                )
            tool_result_items, loop_errors = provider.execute_tool_calls(
                response,
                max_workers=max_workers,
                display=display,
                session_usage=session_usage,
                turn_usage=turn_usage,
                sub_agent_depth=sub_agent_depth,
                parent_context=parent_context,
            )
        except Exception:
            _log.exception("Tool execution failed inside provider.execute_tool_calls")
            raise
        had_errors = had_errors or loop_errors

        if not tool_result_items:
            _log.debug("No tool_result_items returned; stopping tool loop")
            break

        if max_requests is not None and request_count >= max_requests:
            raise SubAgentRunError(
                "request_limit_exceeded",
                (
                    "Sub-agent exceeded the maximum provider request limit "
                    f"({max_requests})."
                ),
            )

        try:
            response = provider.request_turn(
                tool_result_items=tool_result_items,
                display=display,
                session_usage=session_usage,
                turn_usage=turn_usage,
            )
            request_count += 1
        except Exception:
            _log.exception("Follow-up request after tool execution failed")
            raise

    return response, had_errors, request_count


def _raise_if_sub_agent_timed_out(
    started_at: float,
    *,
    max_elapsed_seconds: float = SUB_AGENT_MAX_ELAPSED_SECONDS,
) -> None:
    elapsed = time.monotonic() - started_at
    if elapsed > max_elapsed_seconds:
        raise SubAgentRunError(
            "timeout",
            (f"Sub-agent exceeded the wall-clock limit ({int(max_elapsed_seconds)}s)."),
        )


# ---------------------------------------------------------------------------
# Session store helpers (fail-safe: never crash the main loop)
# ---------------------------------------------------------------------------


def _open_store(settings: Settings) -> SessionStore | None:
    try:
        return SessionStore()
    except Exception:
        _log.warning("Failed to open session store", exc_info=True)
        return None


def _runtime_for_saved_session(
    store: SessionStore | None,
    session_id: str,
    fallback: ResolvedRuntime,
) -> ResolvedRuntime:
    if store is None:
        return fallback
    try:
        rec = store.get_session(session_id)
    except Exception:
        _log.warning("Failed to load saved session runtime", exc_info=True)
        return fallback
    if rec is None or not rec.profile_id:
        return fallback
    try:
        return resolve_runtime_for_profile_id(
            rec.profile_id,
            verbose=fallback.settings.verbose,
        )
    except Exception:
        _log.warning("Failed to resolve saved session runtime", exc_info=True)
        return fallback


def _persist_runtime_change(
    store: SessionStore | None,
    session_id: str | None,
    runtime: ResolvedRuntime,
) -> None:
    if store is None or session_id is None:
        return
    try:
        store.update_session(
            session_id,
            provider=runtime.settings.provider,
            provider_id=runtime.provider_id or None,
            model=runtime.settings.model,
            profile_id=runtime.profile_id or None,
            clear_previous_id=True,
        )
    except Exception:
        _log.warning("Failed to persist runtime change", exc_info=True)


def _create_session(
    store: SessionStore | None,
    runtime: ResolvedRuntime,
    *,
    title: str = "",
) -> str | None:
    if store is None:
        return None
    try:
        settings = runtime.settings
        return store.create_session(
            directory=os.getcwd(),
            provider=settings.provider,
            provider_id=runtime.provider_id or None,
            model=settings.model,
            profile_id=runtime.profile_id or None,
            title=title,
        )
    except Exception:
        _log.warning("Failed to create session", exc_info=True)
        return None


def _open_session_store(
    runtime: ResolvedRuntime,
    *,
    resume_session_id: str | None = None,
    title: str = "",
) -> tuple[SessionStore | None, str | None]:
    store = _open_store(runtime.settings)
    if store is None:
        return None, None
    if resume_session_id:
        return store, resume_session_id
    sid = _create_session(store, runtime, title=title)
    return store, sid


def _update_session_after_turn(
    store: SessionStore | None,
    session_id: str | None,
    runtime: ResolvedRuntime,
    response_id: str | None,
    session_usage: TokenUsage,
) -> None:
    if store is None or session_id is None:
        return
    try:
        snap = session_usage.snapshot()
        store.update_session(
            session_id,
            provider=runtime.settings.provider,
            provider_id=runtime.provider_id or None,
            model=runtime.settings.model,
            profile_id=runtime.profile_id or None,
            previous_id=response_id or None,
            total_tokens=snap.total_tokens,
            input_tokens=snap.input_tokens,
            output_tokens=snap.output_tokens,
            cost_usd=snap.estimated_cost_usd,
        )
    except Exception:
        _log.warning("Failed to update session after turn", exc_info=True)


def _conversation_checkpoint_for_resume(
    provider: Provider,
    response_id: str | None,
) -> str | None:
    try:
        checkpoint = provider.get_conversation_checkpoint()
    except Exception:
        _log.warning(
            "Failed to capture provider conversation checkpoint", exc_info=True
        )
        checkpoint = None
    return checkpoint or response_id


def _update_session_title(
    store: SessionStore | None,
    session_id: str | None,
    title: str,
) -> None:
    if store is None or session_id is None:
        return
    try:
        store.update_session(session_id, title=title)
    except Exception:
        _log.warning("Failed to update session title", exc_info=True)


def _add_message(
    store: SessionStore | None,
    session_id: str | None,
    runtime: ResolvedRuntime,
    role: str,
    content: str,
    *,
    file_paths: list[str] | None = None,
    image_attachments: list[MessageImageAttachment] | None = None,
) -> None:
    if store is None or session_id is None:
        return
    try:
        store.add_message(
            session_id,
            role,
            content,
            file_paths=file_paths,
            provider_id=runtime.provider_id or None,
            profile_id=runtime.profile_id or None,
            image_attachments=image_attachments,
        )
    except Exception:
        _log.warning("Failed to add message to session store", exc_info=True)


def _resume_session(
    *,
    provider: Any,
    store: SessionStore | None,
    session_id: str | None,
    session_usage: TokenUsage,
    display: DisplayProtocol,
    replay_history: bool = True,
) -> None:
    if store is None or session_id is None:
        return
    messages = []
    try:
        messages = store.list_messages(session_id)
    except Exception:
        _log.warning("Failed to restore session history", exc_info=True)

    try:
        rec = store.get_session(session_id)
        if rec and (rec.input_tokens or rec.output_tokens):
            provider_name = provider.settings.provider
            restored_usage = TokenUsage(
                input_tokens=rec.input_tokens,
                output_tokens=rec.output_tokens,
                model=session_usage.model,
            )
            if provider_name == "google":
                restored_usage.provider_total_tokens = rec.total_tokens
            session_usage.add(restored_usage)
            display.session_usage(session_usage)
    except Exception:
        _log.warning("Failed to restore session state", exc_info=True)
    if messages:
        try:
            provider.restore_messages(messages)
            if replay_history:
                display.replay_history(messages)
        except Exception:
            _log.warning("Failed to apply restored session history", exc_info=True)


def _build_parent_context_snapshot(
    *,
    provider: Provider,
    store: SessionStore | None,
    session_id: str | None,
    current_user_turn_text: str | None,
) -> ParentContextSnapshot | None:
    messages: tuple = ()
    if store is not None and session_id is not None:
        try:
            messages = tuple(store.list_messages(session_id))
        except Exception:
            _log.warning("Failed to capture parent session history", exc_info=True)

    continuation_id: str | None = None
    try:
        continuation_id = provider.get_conversation_checkpoint()
    except Exception:
        _log.warning(
            "Failed to capture provider conversation checkpoint", exc_info=True
        )

    current_turn = (current_user_turn_text or "").strip() or None
    if not messages and current_turn is None and continuation_id is None:
        return None

    provider_name = getattr(provider.settings, "provider", "")
    return ParentContextSnapshot(
        provider=provider_name,
        continuation_id=continuation_id,
        messages=messages,
        current_user_turn=current_turn,
    )


def _apply_sub_agent_parent_context(
    *,
    provider: Provider,
    provider_name: str,
    include_context: bool,
    parent_context: ParentContextSnapshot | None,
) -> None:
    if not include_context or parent_context is None:
        return

    if provider_name not in {"openai", "google"}:
        return

    continuation_id = (parent_context.continuation_id or "").strip()
    if continuation_id:
        provider.set_previous_response_id(continuation_id)


def _build_sub_agent_initial_message(
    task_instruction: str,
    *,
    provider_name: str,
    include_context: bool,
    parent_context: ParentContextSnapshot | None,
) -> str:
    if not include_context or parent_context is None:
        return task_instruction

    if provider_name in {"openai", "google"}:
        if (parent_context.continuation_id or "").strip():
            return task_instruction

    transcript_lines: list[str] = []
    for message in parent_context.messages:
        if message.role not in {"user", "assistant"}:
            continue
        content = message.content.strip()
        if not content:
            continue
        transcript_lines.extend(
            [
                f"<{message.role}>",
                content,
                f"</{message.role}>",
            ]
        )

    current_user_turn = (parent_context.current_user_turn or "").strip()
    if current_user_turn:
        last_message = parent_context.messages[-1] if parent_context.messages else None
        if not (
            last_message
            and last_message.role == "user"
            and last_message.content.strip() == current_user_turn
        ):
            transcript_lines.extend(
                [
                    "<user>",
                    current_user_turn,
                    "</user>",
                ]
            )

    if not transcript_lines:
        return task_instruction

    sections = [
        "Use the parent conversation below as context for the delegated task.",
        "",
        "<parent_conversation>",
        *transcript_lines,
        "</parent_conversation>",
        "",
        "<delegated_task>",
        task_instruction,
        "</delegated_task>",
    ]
    return "\n".join(sections)


def _close_store(store: SessionStore | None) -> None:
    if store is None:
        return
    try:
        store.close()
    except Exception:
        _log.warning("Failed to close session store", exc_info=True)


def _build_user_turn_input(
    *,
    text: str,
    image_paths: list[str],
    images: list[ImageAttachment] | None,
    settings: Settings,
) -> UserTurnInput:
    resolved_images = list(images or [])
    if image_paths:
        if not provider_supports_images(settings.provider):
            raise ValueError(
                f"Provider '{settings.provider}' does not support image inputs in this build."
            )
        root = Path.cwd().resolve()
        resolved_images.extend(load_workspace_image(root, path) for path in image_paths)
    elif resolved_images and not provider_supports_images(settings.provider):
        raise ValueError(
            f"Provider '{settings.provider}' does not support image inputs in this build."
        )
    return UserTurnInput(text=text, images=resolved_images)


def _normalize_user_command(value: str) -> str:
    return " ".join(value.strip().lower().split())


def _reload_provider_sub_agents(provider: Provider) -> None:
    provider.set_system_prompt(get_system_prompt())
    provider.refresh_tools()


def _request_user_turn(
    *,
    provider: Any,
    user_input: UserTurnInput,
    display: DisplayProtocol,
    session_usage: TokenUsage,
    turn_usage: TokenUsage,
) -> CompletedResponse:
    return provider.request_turn(
        user_input=user_input,
        display=display,
        session_usage=session_usage,
        turn_usage=turn_usage,
    )


def _user_turn_history_text(user_input: UserTurnInput) -> str:
    text = user_input.text.strip()
    if not user_input.images:
        return text

    attachment_label = ", ".join(image.path for image in user_input.images)
    if text:
        return f"{text}\n\n[attached images: {attachment_label}]"
    return f"[attached images: {attachment_label}]"


def _session_title_for_user_turn(user_input: UserTurnInput) -> str:
    return _user_turn_history_text(user_input)[:80]
