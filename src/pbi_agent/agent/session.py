from __future__ import annotations

from dataclasses import replace
import logging
import os
import time
from typing import Any

from pbi_agent.agent.system_prompt import get_sub_agent_system_prompt
from pbi_agent.config import Settings
from pbi_agent.models.messages import AgentOutcome, CompletedResponse, TokenUsage
from pbi_agent.providers import create_provider
from pbi_agent.session_store import SessionStore
from pbi_agent.ui.display_protocol import DisplayProtocol

_log = logging.getLogger(__name__)

NEW_CHAT_SENTINEL = "__new_chat__"
RESUME_SESSION_PREFIX = "__resume_session__:"
SUB_AGENT_MAX_REQUESTS = 30
SUB_AGENT_MAX_ELAPSED_SECONDS = 300.0
SUB_AGENT_DISABLED_TOOLS = {"sub_agent"}


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


def run_single_turn(
    prompt: str,
    settings: Settings,
    display: DisplayProtocol,
    *,
    single_turn_hint: str | None = None,
    resume_session_id: str | None = None,
) -> AgentOutcome:
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

    store, session_id = _open_session_store(
        settings,
        resume_session_id=resume_session_id,
        title=prompt[:80],
    )

    provider = create_provider(settings)
    _resume_session(
        provider=provider,
        store=store,
        session_id=resume_session_id,
        session_usage=session_usage,
        display=display,
    )

    with provider:
        response = provider.request_turn(
            user_message=prompt,
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
        )
        _add_message(store, session_id, "user", prompt)
        _add_message(store, session_id, "assistant", response.text)
        _update_session_after_turn(
            store, session_id, response.response_id, session_usage
        )
        elapsed = time.monotonic() - session_start
        display.turn_usage(turn_usage, elapsed)
        display.session_usage(session_usage)
        _close_store(store)
        return AgentOutcome(
            response_id=response.response_id,
            text=response.text,
            tool_errors=had_tool_errors,
        )


def run_chat_loop(
    settings: Settings,
    display: DisplayProtocol,
    *,
    resume_session_id: str | None = None,
) -> int:
    model = _selected_model(settings)
    _tier = settings.service_tier or ""
    store = _open_store(settings)
    session_id: str | None = resume_session_id
    title_set = bool(resume_session_id)

    def _reset_session(*, clear_display: bool = False) -> TokenUsage:
        if clear_display:
            display.reset_chat()
        display.welcome(
            model=model,
            reasoning_effort=settings.reasoning_effort,
        )
        new_usage = TokenUsage(model=model, service_tier=_tier)
        display.session_usage(new_usage)
        return new_usage

    session_usage = _reset_session()
    had_tool_errors = False

    provider = create_provider(settings)
    _resume_session(
        provider=provider,
        store=store,
        session_id=resume_session_id,
        session_usage=session_usage,
        display=display,
    )

    with provider:
        while True:
            user_input = display.user_prompt().strip()
            if user_input == NEW_CHAT_SENTINEL:
                provider.reset_conversation()
                session_usage = _reset_session(clear_display=True)
                had_tool_errors = False
                session_id = None
                title_set = False
                continue
            if user_input.startswith(RESUME_SESSION_PREFIX):
                resume_id = user_input[len(RESUME_SESSION_PREFIX) :]
                provider.reset_conversation()
                session_usage = _reset_session(clear_display=True)
                had_tool_errors = False
                if store:
                    session_id = resume_id
                    title_set = True
                    _resume_session(
                        provider=provider,
                        store=store,
                        session_id=resume_id,
                        session_usage=session_usage,
                        display=display,
                    )
                continue
            if user_input.lower() in {"exit", "quit"}:
                break
            if not user_input:
                continue

            if session_id is None:
                session_id = _create_session(
                    store,
                    settings,
                    title=user_input[:80],
                )
                title_set = True
            elif not title_set:
                _update_session_title(store, session_id, user_input[:80])
                title_set = True

            turn_start = time.monotonic()
            turn_usage = TokenUsage(model=model, service_tier=_tier)
            display.assistant_start()
            response = provider.request_turn(
                user_message=user_input,
                display=display,
                session_usage=session_usage,
                turn_usage=turn_usage,
            )
            response, loop_had_errors, _ = _run_tool_iterations(
                provider=provider,
                response=response,
                max_workers=settings.max_tool_workers,
                display=display,
                session_usage=session_usage,
                turn_usage=turn_usage,
            )

            _add_message(store, session_id, "user", user_input)
            _add_message(store, session_id, "assistant", response.text)
            _update_session_after_turn(
                store, session_id, response.response_id, session_usage
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
    reasoning_effort: str = "low",
    parent_session_usage: TokenUsage,
    parent_turn_usage: TokenUsage,
    sub_agent_depth: int = 0,
) -> dict[str, Any]:
    child_settings = replace(
        settings,
        model=_selected_sub_agent_model(settings),
        reasoning_effort=reasoning_effort,
    )
    from pbi_agent.ui.names import pick_deity_name

    child_display = display.begin_sub_agent(
        task_instruction=task_instruction,
        reasoning_effort=reasoning_effort,
        name=pick_deity_name(),
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
        provider = create_provider(
            child_settings,
            system_prompt=get_sub_agent_system_prompt(),
            excluded_tools=SUB_AGENT_DISABLED_TOOLS,
        )
        with provider:
            _raise_if_sub_agent_timed_out(started_at)
            response = provider.request_turn(
                user_message=task_instruction,
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
            tool_result_items, loop_errors = provider.execute_tool_calls(
                response,
                max_workers=max_workers,
                display=display,
                session_usage=session_usage,
                turn_usage=turn_usage,
                sub_agent_depth=sub_agent_depth,
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


def _create_session(
    store: SessionStore | None,
    settings: Settings,
    *,
    title: str = "",
) -> str | None:
    if store is None:
        return None
    try:
        return store.create_session(
            directory=os.getcwd(),
            provider=settings.provider,
            model=settings.model,
            title=title,
        )
    except Exception:
        _log.warning("Failed to create session", exc_info=True)
        return None


def _open_session_store(
    settings: Settings,
    *,
    resume_session_id: str | None = None,
    title: str = "",
) -> tuple[SessionStore | None, str | None]:
    store = _open_store(settings)
    if store is None:
        return None, None
    if resume_session_id:
        return store, resume_session_id
    sid = _create_session(store, settings, title=title)
    return store, sid


def _update_session_after_turn(
    store: SessionStore | None,
    session_id: str | None,
    response_id: str | None,
    session_usage: TokenUsage,
) -> None:
    if store is None or session_id is None:
        return
    try:
        snap = session_usage.snapshot()
        store.update_session(
            session_id,
            previous_id=response_id or None,
            total_tokens=snap.total_tokens,
            input_tokens=snap.input_tokens,
            output_tokens=snap.output_tokens,
            cost_usd=snap.estimated_cost_usd,
        )
    except Exception:
        _log.warning("Failed to update session after turn", exc_info=True)


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
    role: str,
    content: str,
) -> None:
    if store is None or session_id is None:
        return
    try:
        store.add_message(session_id, role, content)
    except Exception:
        _log.warning("Failed to add message to session store", exc_info=True)


def _resume_session(
    *,
    provider: Any,
    store: SessionStore | None,
    session_id: str | None,
    session_usage: TokenUsage,
    display: DisplayProtocol,
) -> None:
    if store is None or session_id is None:
        return
    try:
        rec = store.get_session(session_id)
        if rec and rec.previous_id:
            provider.set_previous_response_id(rec.previous_id)
        if rec and (rec.input_tokens or rec.output_tokens):
            session_usage.add(
                TokenUsage(
                    input_tokens=rec.input_tokens,
                    output_tokens=rec.output_tokens,
                    provider_total_tokens=rec.total_tokens,
                    model=session_usage.model,
                )
            )
            display.session_usage(session_usage)
    except Exception:
        _log.warning("Failed to restore session state", exc_info=True)
    try:
        messages = store.list_messages(session_id)
        if messages:
            provider.restore_messages(messages)
            display.replay_history(messages)
    except Exception:
        _log.warning("Failed to restore session history", exc_info=True)


def _close_store(store: SessionStore | None) -> None:
    if store is None:
        return
    try:
        store.close()
    except Exception:
        _log.warning("Failed to close session store", exc_info=True)
