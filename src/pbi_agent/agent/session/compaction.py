from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass, replace
import json
from typing import Any

from pbi_agent.agent.compaction_prompt import COMPACTION_PROMPT
from pbi_agent.config import ResolvedRuntime, Settings
from pbi_agent.display.protocol import DisplayProtocol
from pbi_agent.hooks.runtime import HookRuntime
from pbi_agent.hooks.schemas import HookEventName
from pbi_agent.models.messages import TokenUsage, ToolCall
from pbi_agent.observability import RunTracer
from pbi_agent.providers.base import Provider
from pbi_agent.session_store import MessageRecord, SessionStore
from pbi_agent.tools.catalog import ToolCatalog

from pbi_agent.agent.session.history import (
    add_message as _add_message,
    delete_message as _delete_message,
    refresh_provider_history_from_store as _refresh_provider_history_from_store,
    update_session_after_turn as _update_session_after_turn,
)
from pbi_agent.agent.session.shared import (
    COMPACTION_CONTINUATION_PROMPT,
    COMPACTION_MARKER,
    COMPACTION_SUMMARY_PREFIX,
    log as _log,
    run_reasoning_metadata as _run_reasoning_metadata,
    selected_model as _selected_model,
)


@contextmanager
def _open_compaction_provider(settings: Settings):
    compact_settings = replace(settings, allowed_tools=())
    from pbi_agent.agent.session.runtime import open_runtime_provider

    with open_runtime_provider(
        compact_settings,
        system_prompt=COMPACTION_PROMPT,
        tool_catalog=ToolCatalog(),
    ) as provider:
        yield provider


def _active_context_messages(
    messages: list[MessageRecord] | tuple[MessageRecord, ...],
) -> list[MessageRecord]:
    marker_index = _latest_compaction_marker_index(messages)
    if marker_index is None:
        return list(messages)
    return list(messages[marker_index + 1 :])


def _latest_compaction_marker_index(
    messages: list[MessageRecord] | tuple[MessageRecord, ...],
) -> int | None:
    for index in range(len(messages) - 1, -1, -1):
        if _is_compaction_marker(messages[index]):
            return index
    return None


def _is_compaction_marker(message: MessageRecord) -> bool:
    return message.role == "assistant" and message.content.strip() == COMPACTION_MARKER


def _is_compaction_summary(message: MessageRecord) -> bool:
    return message.role == "assistant" and message.content.strip().startswith(
        COMPACTION_SUMMARY_PREFIX
    )


def _strip_compaction_summary_prefix(content: str) -> str:
    stripped = content.strip()
    if stripped.startswith(COMPACTION_SUMMARY_PREFIX):
        return stripped[len(COMPACTION_SUMMARY_PREFIX) :].strip()
    return stripped


def _latest_compaction_summary(messages: list[MessageRecord]) -> str | None:
    marker_index = _latest_compaction_marker_index(messages)
    if marker_index is None:
        return None
    for message in messages[marker_index + 1 :]:
        if _is_compaction_summary(message):
            return _strip_compaction_summary_prefix(message.content)
    return None


def _provider_has_server_side_compaction(provider: Provider) -> bool:
    request_options = getattr(provider, "_responses_request_options", None)
    if not callable(request_options):
        return False
    try:
        options = request_options()
    except Exception:
        _log.debug(
            "Failed to inspect provider context-management support",
            exc_info=True,
        )
        return False
    return bool(getattr(options, "include_context_management", False))


def _compaction_continuation_prompt(last_user_message: str | None) -> str:
    return COMPACTION_CONTINUATION_PROMPT.format(
        last_user_message=(last_user_message or "").strip() or "(not available)"
    )


def _should_auto_compact(
    *,
    session_usage: TokenUsage,
    settings: Settings,
    store: SessionStore | None,
    session_id: str | None,
) -> bool:
    threshold = max(settings.compact_threshold, 0)
    if threshold <= 0:
        return False
    context_tokens = session_usage.snapshot().context_tokens
    if context_tokens <= 0:
        context_tokens = _estimate_active_context_tokens(store, session_id)
    return context_tokens >= threshold


def _estimate_active_context_tokens(
    store: SessionStore | None,
    session_id: str | None,
) -> int:
    if store is None or session_id is None:
        return 0
    try:
        messages = _active_context_messages(store.list_messages(session_id))
    except Exception:
        _log.warning("Failed to estimate active context size", exc_info=True)
        return 0
    chars = sum(len(message.role) + len(message.content) + 8 for message in messages)
    return max(1, chars // 4) if chars else 0


@dataclass(slots=True)
class _CompactionContext:
    previous_summary: str | None
    head_messages: list[MessageRecord]
    tail_messages: list[MessageRecord]


def _split_messages_for_compaction(
    messages: list[MessageRecord],
    settings: Settings,
) -> _CompactionContext:
    previous_summary = _latest_compaction_summary(messages)
    active_messages = _active_context_messages(messages)
    candidates = [
        message
        for message in active_messages
        if message.role in {"user", "assistant"}
        and not _is_compaction_marker(message)
        and not _is_compaction_summary(message)
    ]
    tail_start = _compaction_tail_start_index(candidates, settings)
    if tail_start is None:
        return _CompactionContext(
            previous_summary=previous_summary,
            head_messages=candidates,
            tail_messages=[],
        )
    return _CompactionContext(
        previous_summary=previous_summary,
        head_messages=candidates[:tail_start],
        tail_messages=candidates[tail_start:],
    )


def _compaction_tail_start_index(
    messages: list[MessageRecord],
    settings: Settings,
) -> int | None:
    tail_turns = max(settings.compact_tail_turns, 0)
    budget = max(settings.compact_preserve_recent_tokens, 0)
    if tail_turns <= 0 or budget <= 0:
        return None
    user_indexes = [
        index for index, message in enumerate(messages) if message.role == "user"
    ]
    if not user_indexes:
        return None
    selected = user_indexes[-tail_turns:]
    while len(selected) > 1:
        estimated = _estimate_messages_tokens(messages[selected[0] :])
        if estimated <= budget:
            break
        selected.pop(0)
    return selected[0]


def _estimate_messages_tokens(messages: list[MessageRecord]) -> int:
    chars = sum(len(message.role) + len(message.content) + 8 for message in messages)
    return max(1, chars // 4) if chars else 0


def _rewrite_compacted_context(
    store: SessionStore,
    session_id: str,
    runtime: ResolvedRuntime,
    *,
    compaction_context: _CompactionContext,
    summary_content: str,
) -> None:
    for message in [
        *compaction_context.head_messages,
        *compaction_context.tail_messages,
    ]:
        _delete_message(store, message.id)
    _add_message(store, session_id, runtime, "assistant", COMPACTION_MARKER)
    _add_message(store, session_id, runtime, "assistant", summary_content)
    for message in compaction_context.tail_messages:
        _add_message(
            store,
            session_id,
            runtime,
            message.role,
            message.content,
            file_paths=message.file_paths,
            image_attachments=message.image_attachments,
        )


def _compact_live_session(
    *,
    provider: Provider,
    store: SessionStore | None,
    session_id: str | None,
    runtime: ResolvedRuntime,
    display: DisplayProtocol,
    session_usage: TokenUsage,
    reason: str,
    pending_tool_calls: list[ToolCall] | None = None,
    pending_tool_result_items: list[dict[str, Any]] | None = None,
    pending_tool_exchanges: (
        list[tuple[list[ToolCall], list[dict[str, Any]]]] | None
    ) = None,
    hook_runtime: HookRuntime | None = None,
) -> int:
    if store is None or session_id is None:
        return session_usage.snapshot().context_tokens
    try:
        messages = store.list_messages(session_id)
    except Exception:
        _log.warning("Failed to load session context for compaction", exc_info=True)
        return session_usage.snapshot().context_tokens
    compaction_context = _split_messages_for_compaction(messages, runtime.settings)
    tool_exchanges = _normalize_tool_exchanges_for_compaction(
        pending_tool_exchanges=pending_tool_exchanges,
        pending_tool_calls=pending_tool_calls,
        pending_tool_result_items=pending_tool_result_items,
    )
    has_pending_tool_exchange = bool(tool_exchanges)
    summary_input_messages = (
        compaction_context.head_messages or compaction_context.tail_messages
    )
    if (
        not summary_input_messages
        and not compaction_context.previous_summary
        and not has_pending_tool_exchange
    ):
        display.render_markdown("No completed session context to compact yet.")
        return 0
    if hook_runtime is not None:
        pre_compact = hook_runtime.run(
            HookEventName.PRE_COMPACT,
            matcher_value=reason,
            payload={
                "reason": reason,
                "input_message_count": len(summary_input_messages),
                "pending_tool_exchange": has_pending_tool_exchange,
            },
        )
        if pre_compact.blocked:
            display.render_markdown(
                pre_compact.block_reason or "Context compaction stopped by hook."
            )
            return session_usage.snapshot().context_tokens

    compaction_usage = TokenUsage(
        model=_selected_model(runtime.settings),
        service_tier=runtime.settings.service_tier or "",
    )
    tracer = RunTracer.start(
        store=store,
        session_id=session_id,
        agent_name="main",
        agent_type="compaction",
        provider=runtime.settings.provider,
        provider_id=runtime.provider_id,
        profile_id=runtime.profile_id,
        model=_selected_model(runtime.settings),
        metadata={
            **_run_reasoning_metadata(runtime.settings),
            "reason": reason,
            "input_message_count": len(summary_input_messages),
            "tail_message_count": len(compaction_context.tail_messages),
            "pending_tool_exchange": has_pending_tool_exchange,
        },
    )
    display.render_markdown("Compacting live session context...")
    try:
        tracer.log_event(
            "agent_step_start",
            metadata={"step": "compaction_summary"},
        )
        summary = _summarize_session_context(
            messages=summary_input_messages,
            runtime=runtime,
            display=display,
            session_usage=session_usage,
            turn_usage=compaction_usage,
            tracer=tracer,
            previous_summary=compaction_context.previous_summary,
            pending_tool_exchanges=tool_exchanges,
        )
        tracer.log_event(
            "agent_step_end",
            metadata={"step": "compaction_summary"},
        )
    except Exception as exc:
        tracer.log_error(str(exc), metadata={"phase": "compaction"})
        tracer.finish(
            status="failed",
            usage=compaction_usage,
            metadata={"reason": reason, "error_message": str(exc)},
        )
        raise
    finally:
        display.wait_stop()
    if not summary:
        display.render_markdown("Context compaction did not produce a summary.")
        tracer.finish(
            status="failed",
            usage=compaction_usage,
            metadata={"reason": reason, "empty_summary": True},
        )
        return session_usage.snapshot().context_tokens

    summary_content = f"{COMPACTION_SUMMARY_PREFIX}\n\n{summary}"
    _rewrite_compacted_context(
        store,
        session_id,
        runtime,
        compaction_context=compaction_context,
        summary_content=summary_content,
    )
    _refresh_provider_history_from_store(
        provider,
        store,
        session_id,
        reason="compaction",
    )
    _update_session_after_turn(
        store,
        session_id,
        runtime,
        session_usage,
    )
    estimated_context_tokens = max(1, len(summary_content) // 4)
    display.render_markdown(
        f"Context compacted ({reason}); future turns will use the summary."
    )
    if hook_runtime is not None:
        post_compact = hook_runtime.run(
            HookEventName.POST_COMPACT,
            matcher_value=reason,
            payload={
                "reason": reason,
                "summary_chars": len(summary_content),
                "estimated_context_tokens": estimated_context_tokens,
            },
            tracer=tracer,
        )
        if post_compact.blocked:
            display.render_markdown(
                post_compact.block_reason
                or "Post-compaction hook requested stop after compaction."
            )
    tracer.finish(
        status="completed",
        usage=compaction_usage,
        metadata={
            "reason": reason,
            "summary_chars": len(summary_content),
            "estimated_context_tokens": estimated_context_tokens,
            "pending_tool_exchange": has_pending_tool_exchange,
        },
    )
    return estimated_context_tokens


def _summarize_session_context(
    *,
    messages: list[MessageRecord],
    runtime: ResolvedRuntime,
    display: DisplayProtocol,
    session_usage: TokenUsage,
    turn_usage: TokenUsage,
    tracer: RunTracer | None = None,
    previous_summary: str | None = None,
    pending_tool_calls: list[ToolCall] | None = None,
    pending_tool_result_items: list[dict[str, Any]] | None = None,
    pending_tool_exchanges: (
        list[tuple[list[ToolCall], list[dict[str, Any]]]] | None
    ) = None,
) -> str:
    transcript = _format_messages_for_compaction(
        messages,
        tool_output_max_chars=runtime.settings.compact_tool_output_max_chars,
        pending_tool_calls=pending_tool_calls,
        pending_tool_result_items=pending_tool_result_items,
        pending_tool_exchanges=pending_tool_exchanges,
    )
    previous_summary = (previous_summary or "").strip() or None
    if not transcript and previous_summary is None:
        return ""
    user_message = _build_compaction_request(
        transcript=transcript,
        previous_summary=previous_summary,
    )
    with _open_compaction_provider(runtime.settings) as compact_provider:
        response = compact_provider.request_turn(
            user_message=user_message,
            display=display,
            session_usage=session_usage,
            turn_usage=turn_usage,
            tracer=tracer,
        )
    return response.text.strip()


def _build_compaction_request(
    *,
    transcript: str,
    previous_summary: str | None,
) -> str:
    if previous_summary:
        sections = [
            "Update the anchored compacted summary using the new context below. ",
            "Preserve still-true details, remove stale details, and merge new facts.",
            "<previous_summary>",
            previous_summary,
            "</previous_summary>",
            "<new_context_to_merge>",
            transcript,
            "</new_context_to_merge>",
        ]
        return "\n".join(sections)
    return f"<session_transcript>\n{transcript}\n</session_transcript>"


def _format_messages_for_compaction(
    messages: list[MessageRecord],
    *,
    tool_output_max_chars: int = 2000,
    pending_tool_calls: list[ToolCall] | None = None,
    pending_tool_result_items: list[dict[str, Any]] | None = None,
    pending_tool_exchanges: (
        list[tuple[list[ToolCall], list[dict[str, Any]]]] | None
    ) = None,
) -> str:
    chunks: list[str] = []
    for message in messages:
        if message.role not in {"user", "assistant"}:
            continue
        if _is_compaction_marker(message):
            continue
        content = message.content.strip()
        if not content:
            continue
        chunks.extend([f"<{message.role}>", content, f"</{message.role}>"])
    tool_exchange = _format_tool_exchanges_for_compaction(
        _normalize_tool_exchanges_for_compaction(
            pending_tool_exchanges=pending_tool_exchanges,
            pending_tool_calls=pending_tool_calls,
            pending_tool_result_items=pending_tool_result_items,
        ),
        tool_output_max_chars=tool_output_max_chars,
    )
    if tool_exchange:
        chunks.append(tool_exchange)
    return "\n".join(chunks)


def _normalize_tool_exchanges_for_compaction(
    *,
    pending_tool_exchanges: (
        list[tuple[list[ToolCall], list[dict[str, Any]]]] | None
    ) = None,
    pending_tool_calls: list[ToolCall] | None = None,
    pending_tool_result_items: list[dict[str, Any]] | None = None,
) -> list[tuple[list[ToolCall], list[dict[str, Any]]]]:
    exchanges: list[tuple[list[ToolCall], list[dict[str, Any]]]] = []
    for calls, results in pending_tool_exchanges or []:
        normalized_calls = list(calls or [])
        normalized_results = list(results or [])
        if normalized_calls or normalized_results:
            exchanges.append((normalized_calls, normalized_results))
    if not exchanges and (pending_tool_calls or pending_tool_result_items):
        exchanges.append(
            (list(pending_tool_calls or []), list(pending_tool_result_items or []))
        )
    return exchanges


def _format_tool_exchanges_for_compaction(
    tool_exchanges: list[tuple[list[ToolCall], list[dict[str, Any]]]],
    *,
    tool_output_max_chars: int = 2000,
) -> str:
    if not tool_exchanges:
        return ""
    if len(tool_exchanges) == 1:
        return _format_one_tool_exchange_for_compaction(
            "pending_tool_exchange",
            tool_exchanges[0][0],
            tool_exchanges[0][1],
            tool_output_max_chars=tool_output_max_chars,
        )
    chunks = ["<current_turn_tool_exchanges>"]
    for index, (calls, results) in enumerate(tool_exchanges, start=1):
        chunks.append(
            _format_one_tool_exchange_for_compaction(
                f'tool_exchange index="{index}"',
                calls,
                results,
                tool_output_max_chars=tool_output_max_chars,
            )
        )
    chunks.append("</current_turn_tool_exchanges>")
    return "\n".join(chunks)


def _format_one_tool_exchange_for_compaction(
    tag: str,
    calls: list[ToolCall],
    results: list[dict[str, Any]],
    *,
    tool_output_max_chars: int = 2000,
) -> str:
    if not calls and not results:
        return ""
    chunks = [f"<{tag}>"]
    if calls:
        chunks.append("<tool_calls>")
        for call in calls:
            chunks.append(
                _safe_json_dumps(
                    {
                        "call_id": call.call_id,
                        "name": call.name,
                        "arguments": call.arguments,
                    }
                )
            )
        chunks.append("</tool_calls>")
    if results:
        chunks.append("<tool_results>")
        for item in results:
            chunks.append(
                _safe_json_dumps(
                    _truncate_for_compaction(item, max_chars=tool_output_max_chars)
                )
            )
        chunks.append("</tool_results>")
    tag_name = tag.split(maxsplit=1)[0]
    chunks.append(f"</{tag_name}>")
    return "\n".join(chunks)


def _safe_json_dumps(value: Any) -> str:
    try:
        return json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)
    except TypeError:
        return repr(value)


def _truncate_for_compaction(value: Any, *, max_chars: int) -> Any:
    if max_chars <= 0:
        if isinstance(value, str):
            return _compaction_truncation_notice(value, kept_chars=0)
        if isinstance(value, dict):
            return {
                key: _truncate_for_compaction(item, max_chars=max_chars)
                for key, item in value.items()
            }
        if isinstance(value, list):
            return [
                _truncate_for_compaction(item, max_chars=max_chars) for item in value
            ]
        return value
    if isinstance(value, str):
        if len(value) <= max_chars:
            return value
        return (
            value[:max_chars]
            + "\n"
            + _compaction_truncation_notice(value, kept_chars=max_chars)
        )
    if isinstance(value, dict):
        return {
            key: (
                item
                if _is_tool_result_metadata_key(key)
                else _truncate_for_compaction(item, max_chars=max_chars)
            )
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [_truncate_for_compaction(item, max_chars=max_chars) for item in value]
    return value


def _compaction_truncation_notice(value: str, *, kept_chars: int) -> str:
    return (
        "[truncated for compaction: "
        f"original_chars={len(value)}, kept_chars={kept_chars}]"
    )


def _is_tool_result_metadata_key(key: object) -> bool:
    return key in {
        "type",
        "call_id",
        "id",
        "name",
        "status",
        "exit_code",
        "returncode",
        "path",
        "file_path",
    }


open_compaction_provider = _open_compaction_provider
active_context_messages = _active_context_messages
is_compaction_summary = _is_compaction_summary
provider_has_server_side_compaction = _provider_has_server_side_compaction
compaction_continuation_prompt = _compaction_continuation_prompt
should_auto_compact = _should_auto_compact
compact_live_session = _compact_live_session
