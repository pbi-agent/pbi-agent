from __future__ import annotations

from pbi_agent.providers.base import Provider
from pbi_agent.session_store import SessionStore
from pbi_agent.tools.types import ParentContextSnapshot

from pbi_agent.agent.session.compaction import (
    active_context_messages as _active_context_messages,
)
from pbi_agent.agent.session.shared import log as _log


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
            messages = tuple(_active_context_messages(store.list_messages(session_id)))
        except Exception:
            _log.warning("Failed to capture parent session history", exc_info=True)

    current_turn = (current_user_turn_text or "").strip() or None
    if current_turn and messages:
        last_message = messages[-1]
        if last_message.role == "user" and last_message.content.strip() == current_turn:
            messages = messages[:-1]

    continuation_id: str | None = None
    try:
        continuation_id = provider.get_conversation_checkpoint()
    except Exception:
        _log.warning(
            "Failed to capture provider conversation checkpoint", exc_info=True
        )

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

    if provider_name not in {"openai", "azure", "google"}:
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

    if provider_name in {"openai", "azure", "google"}:
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


build_parent_context_snapshot = _build_parent_context_snapshot
apply_sub_agent_parent_context = _apply_sub_agent_parent_context
build_sub_agent_initial_message = _build_sub_agent_initial_message
