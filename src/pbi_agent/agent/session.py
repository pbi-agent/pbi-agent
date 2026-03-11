from __future__ import annotations

import logging
import time

from pbi_agent.config import Settings
from pbi_agent.models.messages import AgentOutcome, TokenUsage
from pbi_agent.providers import create_provider
from pbi_agent.ui.display_protocol import DisplayProtocol

_log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Public entry-points
# ---------------------------------------------------------------------------


def _selected_model(settings: Settings) -> str:
    return settings.model


def run_single_turn(
    prompt: str,
    settings: Settings,
    display: DisplayProtocol,
    *,
    single_turn_hint: str | None = None,
) -> AgentOutcome:
    display.welcome(
        interactive=False,
        model=_selected_model(settings),
        reasoning_effort=settings.reasoning_effort,
        single_turn_hint=single_turn_hint,
    )
    model = _selected_model(settings)
    session_usage = TokenUsage(model=model)
    display.session_usage(session_usage)
    session_start = time.monotonic()
    turn_usage = TokenUsage(model=model)

    provider = create_provider(settings)
    with provider:
        response = provider.request_turn(
            user_message=prompt,
            display=display,
            session_usage=session_usage,
            turn_usage=turn_usage,
        )
        response, had_tool_errors = _run_tool_iterations(
            provider=provider,
            response=response,
            max_workers=settings.max_tool_workers,
            display=display,
            session_usage=session_usage,
            turn_usage=turn_usage,
        )
        elapsed = time.monotonic() - session_start
        display.turn_usage(turn_usage, elapsed)
        display.session_usage(session_usage)
        return AgentOutcome(
            response_id=response.response_id,
            text=response.text,
            tool_errors=had_tool_errors,
        )


def run_chat_loop(settings: Settings, display: DisplayProtocol) -> int:
    display.welcome(
        model=_selected_model(settings),
        reasoning_effort=settings.reasoning_effort,
    )
    model = _selected_model(settings)
    session_usage = TokenUsage(model=model)
    display.session_usage(session_usage)
    had_tool_errors = False

    provider = create_provider(settings)
    with provider:
        while True:
            user_input = display.user_prompt().strip()
            if user_input.lower() in {"exit", "quit"}:
                break
            if not user_input:
                continue

            turn_start = time.monotonic()
            turn_usage = TokenUsage(model=model)
            display.assistant_start()
            response = provider.request_turn(
                user_message=user_input,
                display=display,
                session_usage=session_usage,
                turn_usage=turn_usage,
            )
            response, loop_had_errors = _run_tool_iterations(
                provider=provider,
                response=response,
                max_workers=settings.max_tool_workers,
                display=display,
                session_usage=session_usage,
                turn_usage=turn_usage,
            )

            had_tool_errors = had_tool_errors or loop_had_errors
            elapsed = time.monotonic() - turn_start
            display.turn_usage(turn_usage, elapsed)
            display.session_usage(session_usage)

    return 4 if had_tool_errors else 0


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
) -> tuple:
    had_errors = False

    while response.has_tool_calls:
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
            )
        except Exception:
            _log.exception("Tool execution failed inside provider.execute_tool_calls")
            raise
        had_errors = had_errors or loop_errors

        if not tool_result_items:
            _log.debug("No tool_result_items returned; stopping tool loop")
            break

        try:
            response = provider.request_turn(
                tool_result_items=tool_result_items,
                display=display,
                session_usage=session_usage,
                turn_usage=turn_usage,
            )
        except Exception:
            _log.exception("Follow-up request after tool execution failed")
            raise

    return response, had_errors
