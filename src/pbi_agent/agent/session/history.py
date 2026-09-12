from __future__ import annotations

from dataclasses import dataclass
import json
from typing import Any

from pbi_agent.config import ResolvedRuntime, Settings
from pbi_agent.display.protocol import DisplayProtocol
from pbi_agent.models.messages import TokenUsage
from pbi_agent.providers.base import Provider
from pbi_agent.providers.github_copilot_backend import (
    github_copilot_backend_for_model,
)
from pbi_agent.providers.protocols.openai_responses import (
    response_history_item_for_input,
)
from pbi_agent.session_store import MessageImageAttachment, MessageRecord, SessionStore
from pbi_agent.workspace_context import current_workspace_context

from pbi_agent.agent.session.shared import (
    OPENAI_RESPONSES_HISTORY_FORMAT,
    PROVIDER_INPUT_HISTORY_ITEM,
    REDACTED_INLINE_IMAGE_MARKER,
    log as _log,
)


@dataclass(frozen=True, slots=True)
class _RunUserInput:
    text: str
    timestamp: str


def _open_store(settings: Settings) -> SessionStore | None:
    try:
        return SessionStore()
    except Exception:
        _log.warning("Failed to open session store", exc_info=True)
        return None


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
    directory_key: str | None = None,
) -> str | None:
    if store is None:
        return None
    try:
        settings = runtime.settings
        return store.create_session(
            directory=directory_key or current_workspace_context().directory_key,
            provider=settings.provider,
            provider_id=runtime.provider_id or None,
            model=settings.model,
            profile_id=runtime.profile_id or None,
            title=title,
        )
    except Exception:
        _log.warning("Failed to create session", exc_info=True)
        return None


def _update_session_after_turn(
    store: SessionStore | None,
    session_id: str | None,
    runtime: ResolvedRuntime,
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
            clear_previous_id=True,
            total_tokens=snap.total_tokens,
            input_tokens=snap.input_tokens,
            output_tokens=snap.output_tokens,
            cost_usd=snap.estimated_cost_usd,
        )
    except Exception:
        _log.warning("Failed to update session after turn", exc_info=True)


def _refresh_provider_history_from_store(
    provider: Provider,
    store: SessionStore | None,
    session_id: str | None,
    *,
    reason: str,
    include_tool_history: bool = False,
) -> None:
    reset_conversation = getattr(provider, "reset_conversation", None)
    restore_messages = getattr(provider, "restore_messages", None)
    restore_history_items = getattr(provider, "restore_history_items", None)
    if not callable(reset_conversation) or not callable(restore_messages):
        return
    try:
        messages = []
        history_items = []
        if store is not None and session_id is not None:
            messages = _messages_for_provider_restore(
                store.list_messages(session_id),
                preserve_trailing_user=True,
            )
            if reason != "compaction" and (
                include_tool_history or _needs_run_history_lookup(messages)
            ):
                history_items = _history_items_for_provider_restore(
                    store,
                    session_id,
                    messages,
                    provider=provider,
                    include_completed_tools=include_tool_history,
                )
    except Exception:
        _log.warning(
            "Failed to load provider history after %s",
            reason,
            exc_info=True,
        )
        return
    try:
        reset_conversation()
        if history_items and callable(restore_history_items):
            restore_history_items(history_items)
        else:
            restore_messages(messages)
    except Exception:
        _log.warning(
            "Failed to refresh provider history after %s",
            reason,
            exc_info=True,
        )


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
) -> int | None:
    if store is None or session_id is None:
        return None
    try:
        return store.add_message(
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
        return None


def _publish_persisted_message(
    display: DisplayProtocol,
    store: SessionStore | None,
    message_id: int | None,
    *,
    previous_item_id: str | None = None,
) -> None:
    handler = getattr(display, "persisted_message", None)
    if store is None or message_id is None or not callable(handler):
        return
    try:
        message = store.get_message(message_id)
    except Exception:
        _log.warning("Failed to load persisted message for display", exc_info=True)
        return
    if message is None:
        return
    try:
        handler(message, previous_item_id=previous_item_id)
    except Exception:
        _log.warning("Failed to publish persisted message to display", exc_info=True)


def _delete_message(store: SessionStore | None, message_id: int | None) -> None:
    if store is None or message_id is None:
        return
    try:
        store.delete_message(message_id)
    except Exception:
        _log.warning("Failed to delete message from session store", exc_info=True)


def _discard_interrupted_turn(
    *,
    provider: Provider,
    store: SessionStore | None,
    session_id: str | None,
    user_message_id: int | None,
    include_tool_history: bool = False,
) -> None:
    _delete_message(store, user_message_id)
    _refresh_provider_history_from_store(
        provider,
        store,
        session_id,
        reason="interrupt",
        include_tool_history=include_tool_history,
    )


def _resume_session(
    *,
    provider: Any,
    store: SessionStore | None,
    session_id: str | None,
    session_usage: TokenUsage,
    display: DisplayProtocol,
    replay_history: bool = True,
    before_message_id: int | None = None,
    include_tool_history: bool = False,
) -> None:
    if store is None or session_id is None:
        return
    rec = None
    messages = []
    try:
        messages = store.list_messages(session_id)
        if before_message_id is not None:
            messages = [
                message for message in messages if message.id < before_message_id
            ]
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
        provider_messages = _messages_for_provider_restore(
            messages,
            preserve_trailing_user=True,
        )
        try:
            if include_tool_history or _needs_run_history_lookup(provider_messages):
                restore_history_items = getattr(provider, "restore_history_items", None)
                history_items = _history_items_for_provider_restore(
                    store,
                    session_id,
                    provider_messages,
                    provider=provider,
                    include_completed_tools=include_tool_history,
                )
                if callable(restore_history_items):
                    restore_history_items(history_items)
                elif provider_messages:
                    provider.restore_messages(provider_messages)
            elif provider_messages:
                provider.restore_messages(provider_messages)
            if replay_history:
                display.replay_history(messages)
        except Exception:
            _log.warning("Failed to apply restored session history", exc_info=True)


def _messages_for_provider_restore(
    messages: list[MessageRecord],
    *,
    preserve_trailing_user: bool = False,
) -> list[MessageRecord]:
    from pbi_agent.agent.session.compaction import (
        active_context_messages,
        is_compaction_summary,
    )

    restored = active_context_messages(messages)
    summary_indexes = [
        index
        for index, message in enumerate(restored)
        if is_compaction_summary(message)
    ]
    if summary_indexes:
        latest_summary_index = summary_indexes[-1]
        restored = [
            restored[latest_summary_index],
            *restored[:latest_summary_index],
            *restored[latest_summary_index + 1 :],
        ]
    while restored and restored[-1].role == "user" and not preserve_trailing_user:
        restored.pop()
    return restored


def _history_items_for_provider_restore(
    store: SessionStore,
    session_id: str,
    messages: list[MessageRecord],
    *,
    provider: Provider | None = None,
    include_completed_tools: bool = True,
) -> list[dict[str, Any]]:
    if _provider_prefers_response_input_history(provider):
        response_history_items = _response_history_items_for_provider_restore(
            store,
            session_id,
            messages,
            provider=provider,
            include_completed_tools=include_completed_tools,
        )
        if response_history_items:
            return response_history_items
    return _message_tool_history_items_for_provider_restore(
        store, session_id, messages, include_completed_tools=include_completed_tools
    )


def _needs_run_history_lookup(messages: list[MessageRecord]) -> bool:
    # Consecutive users may be checkpoints in a completed run, not failed turns.
    # This is only a fast path; replay eligibility is determined per run below.
    pending_user = False
    for message in messages:
        if message.role == "user":
            if pending_user:
                return True
            pending_user = True
        elif message.role == "assistant":
            pending_user = False
    return pending_user


def _message_history_items(messages: list[MessageRecord]) -> list[dict[str, Any]]:
    return [{"type": "message", "message": message} for message in messages]


def _compaction_history_cutoff(messages: list[MessageRecord]) -> str | None:
    from pbi_agent.agent.session.compaction import is_compaction_summary

    return max(
        (message.created_at for message in messages if is_compaction_summary(message)),
        default=None,
    )


def _history_turns_for_messages(
    histories: list[tuple[Any, ...]],
    messages: list[MessageRecord],
) -> list[tuple[list[MessageRecord], tuple[Any, ...] | None]]:
    histories_by_message_id = _run_histories_for_messages(histories, messages)
    turns: list[tuple[list[MessageRecord], tuple[Any, ...] | None]] = []
    for message in messages:
        history = histories_by_message_id.get(message.id)
        if turns and turns[-1][0][-1].role == "user":
            previous_messages, previous_history = turns[-1]
            if message.role != "user" or (
                history is not None and history is previous_history
            ):
                previous_messages.append(message)
                continue
        turns.append(([message], history))
    return turns


def _is_unfinished_run(run: Any, messages: list[MessageRecord]) -> bool:
    # The final message is persisted before the active tracer becomes completed.
    return run.status != "completed" and messages[-1].role == "user"


def _message_tool_history_items_for_provider_restore(
    store: SessionStore,
    session_id: str,
    messages: list[MessageRecord],
    *,
    include_completed_tools: bool = True,
) -> list[dict[str, Any]]:
    history_items: list[dict[str, Any]] = []
    run_tool_histories = _tool_history_by_run(
        store, session_id, after=_compaction_history_cutoff(messages)
    )
    for turn_messages, run_history in _history_turns_for_messages(
        run_tool_histories, messages
    ):
        history_items.extend(_message_history_items(turn_messages))
        if run_history is None:
            continue
        run, items, _intermediate_text, _user_inputs = run_history
        if _is_unfinished_run(run, turn_messages):
            history_items.extend(
                _interrupted_generic_run_items(run, turn_messages[0], items)
            )
        elif include_completed_tools:
            insertion = (
                len(history_items) - 1
                if turn_messages[-1].role == "assistant"
                else len(history_items)
            )
            history_items[insertion:insertion] = _completed_generic_run_items(items)
    return history_items


def _provider_prefers_response_input_history(provider: Provider | None) -> bool:
    settings = getattr(provider, "settings", None)
    if not isinstance(settings, Settings):
        return False
    provider_name = str(getattr(settings, "provider", "") or "").strip().lower()
    if provider_name in {"openai", "chatgpt", "xai"}:
        return True
    if provider_name == "github_copilot":
        try:
            return github_copilot_backend_for_model(settings.model).mode == "responses"
        except Exception:
            return False
    if provider_name == "azure":
        try:
            from pbi_agent.providers.azure import AzureEndpointKind, azure_endpoint_kind

            return (
                azure_endpoint_kind(settings.responses_url)
                == AzureEndpointKind.OPENAI_RESPONSES
            )
        except Exception:
            responses_url = str(getattr(settings, "responses_url", "") or "")
            return responses_url.rstrip("/").endswith("/responses")
    return False


def _provider_history_name(provider: Provider | None) -> str | None:
    settings = getattr(provider, "settings", None)
    if not isinstance(settings, Settings):
        return None
    provider_name = str(getattr(settings, "provider", "") or "").strip().lower()
    return provider_name or None


def _response_history_items_for_provider_restore(
    store: SessionStore,
    session_id: str,
    messages: list[MessageRecord],
    *,
    provider: Provider | None = None,
    include_completed_tools: bool = True,
) -> list[dict[str, Any]]:
    run_histories = _response_model_call_history_by_run(
        store, session_id, after=_compaction_history_cutoff(messages)
    )
    if not run_histories:
        return []

    history_items: list[dict[str, Any]] = []
    used_response_history = False
    current_provider = _provider_history_name(provider)

    for turn_messages, run_history in _history_turns_for_messages(
        run_histories, messages
    ):
        if run_history is None:
            history_items.extend(_message_history_items(turn_messages))
            continue
        run, events, completed_tool_results, _user_inputs = run_history
        unfinished = _is_unfinished_run(run, turn_messages)
        if not include_completed_tools and not unfinished:
            history_items.extend(_message_history_items(turn_messages))
            continue
        if current_provider is not None and _run_provider_name(run) != current_provider:
            return []
        turn_items = _response_history_items_for_run(
            events,
            turn_messages[0],
            completed_tool_results=completed_tool_results,
            require_completed_tool_exchange=unfinished,
        )
        if not turn_items:
            return []
        history_items.extend(turn_items)
        used_response_history = True

    return history_items if used_response_history else []


def _response_model_call_history_by_run(
    store: SessionStore,
    session_id: str,
    *,
    after: str | None = None,
) -> list[tuple[Any, list[Any], dict[str, Any], list[_RunUserInput]]]:
    histories: list[tuple[Any, list[Any], dict[str, Any], list[_RunUserInput]]] = []
    for run in store.list_run_sessions(session_id):
        if run.parent_run_session_id or run.agent_name not in {None, "main"}:
            continue
        if run.agent_type not in {"session_turn", "single_turn"}:
            continue
        run_events = store.list_observability_events(run_session_id=run.run_session_id)
        user_inputs = _run_user_inputs(run_events)
        if after is not None:
            run_events = [event for event in run_events if event.timestamp > after]
        events = [event for event in run_events if event.event_type == "model_call"]
        completed_tool_results = {
            event.tool_call_id: event
            for event in run_events
            if event.event_type == "tool_call" and event.tool_call_id
        }
        histories.append(
            (
                run,
                events,
                completed_tool_results,
                user_inputs,
            )
        )
    return histories


def _run_provider_name(run: Any) -> str | None:
    provider_name = str(getattr(run, "provider", "") or "").strip().lower()
    return provider_name or None


def _run_histories_for_messages(
    histories: list[tuple[Any, ...]],
    messages: list[MessageRecord],
) -> dict[int, tuple[Any, ...]]:
    ordered = sorted(histories, key=lambda item: (item[0].started_at, item[0].id))
    compaction_cutoff = _compaction_history_cutoff(messages)
    lower_bound = 0
    matched: dict[int, tuple[Any, ...]] = {}
    for history in ordered:
        user_inputs = history[-1]
        if not user_inputs:
            continue
        user_texts = [item.text for item in user_inputs]
        candidates = [
            (index, message)
            for index, message in enumerate(messages[lower_bound:], lower_bound)
            if message.role == "user"
            and (not history[0].ended_at or message.created_at <= history[0].ended_at)
        ]
        exact = [
            (index, message)
            for index, message in candidates
            if user_texts[0].strip() in _user_message_prompt_texts(message)
            and message.created_at <= user_inputs[0].timestamp
        ]
        initial_request_match = bool(exact)
        if (
            not exact
            and compaction_cutoff is not None
            and history[0].started_at <= compaction_cutoff
        ):
            # Compaction rewrites retained prompts/checkpoints with new times
            # and can remove the initial prompt. Only relax chronology here.
            exact = [
                (index, message)
                for index, message in candidates
                if user_texts[0].strip() in _user_message_prompt_texts(message)
                or _matches_checkpoint_input(user_texts[1:], message)
            ]
        provider_exact = [
            (index, message)
            for index, message in exact
            if message.provider_id
            and message.provider_id in {history[0].provider_id, history[0].provider}
        ]
        available = provider_exact or exact
        if not available:
            continue
        # The prompt can be persisted before or after run start. The last match
        # before the initial request excludes older untraced exchanges (e.g.
        # fork copies) and later identical checkpoints. Rewritten compaction
        # rows instead start at the first surviving prompt/checkpoint.
        index, message = available[-1] if initial_request_match else available[0]
        matched[message.id] = history
        lower_bound = index + 1
        for index, message in enumerate(messages[lower_bound:], lower_bound):
            if (
                message.role != "user"
                or (history[0].ended_at and message.created_at > history[0].ended_at)
                or not _matches_checkpoint_input(user_texts[1:], message)
            ):
                break
            # A single checkpoint request can contain several queued user rows.
            matched[message.id] = history
            lower_bound = index + 1
    return matched


def _user_message_prompt_texts(message: MessageRecord) -> tuple[str, ...]:
    # CLI image turns may have no attachment metadata. Keep the literal content
    # as well, since restored requests can already contain the display suffix.
    content = message.content.strip()
    if content.endswith("]"):
        prompt, separator, _attachments = content.rpartition("\n\n[attached images: ")
        if separator:
            return content, prompt.strip()
        if content.startswith("[attached images: "):
            return content, ""
    return (content,)


def _matches_checkpoint_input(texts: list[str], message: MessageRecord) -> bool:
    prompts = _user_message_prompt_texts(message)
    for text in texts:
        # The tool loop adds this wrapper when compaction and checkpoint drain
        # happen in the same iteration. Its single newline is not a user-row
        # boundary; the wrapped body still uses double newlines between rows.
        _, wrapper, follow_up = text.partition(
            "\n\nUser follow-up for the current turn:\n"
        )
        candidates = (text, follow_up) if wrapper else (text,)
        if any(
            prompt == candidate.strip()
            or (bool(prompt) and f"\n\n{prompt}\n\n" in f"\n\n{candidate.strip()}\n\n")
            for prompt in prompts
            for candidate in candidates
        ):
            return True
    return False


def _run_user_inputs(events: list[Any]) -> list[_RunUserInput]:
    return [
        _RunUserInput(text=text, timestamp=event.timestamp)
        for event in events
        if event.event_type == "model_call"
        and (text := _run_user_input_text([event])) is not None
    ]


def _run_user_input_text(events: list[Any]) -> str | None:
    for event in events:
        payload = _json_field(event.request_payload_json)
        if not isinstance(payload, dict):
            continue
        request_items = _request_input_items(payload)
        for item in reversed(request_items):
            if (
                str(item.get("role") or "").lower() == "user"
                or item.get("type") == "user_input"
            ):
                return _input_item_text(item.get("content"))
        # Fresh multimodal Google input is a content list rather than steps.
        if request_items and all(
            item.get("type") in {"text", "image"} for item in request_items
        ):
            return _input_item_text(request_items)
        messages = payload.get("messages")
        if isinstance(messages, list):
            for message in reversed(messages):
                if (
                    isinstance(message, dict)
                    and str(message.get("role") or "").lower() == "user"
                ):
                    return _input_item_text(message.get("content"))
        contents = payload.get("contents")
        if isinstance(contents, list):
            for content in reversed(contents):
                if (
                    isinstance(content, dict)
                    and str(content.get("role") or "").lower() == "user"
                ):
                    return _parts_text(content.get("parts"))
        steps = payload.get("steps")
        if isinstance(steps, list):
            for step in reversed(steps):
                if isinstance(step, dict) and step.get("type") == "user_input":
                    return _input_item_text(step.get("content"))
    return None


def _response_history_items_for_run(
    events: list[Any],
    user_message: MessageRecord,
    *,
    completed_tool_results: dict[str, Any] | None = None,
    require_completed_tool_exchange: bool = False,
) -> list[dict[str, Any]]:
    history_items: list[dict[str, Any]] = []
    turn_items: list[dict[str, Any]] = []
    item_batches: list[tuple[list[dict[str, Any]], list[dict[str, Any]]]] = []
    first_model_call = True
    failed_request_items: list[dict[str, Any]] | None = None
    saw_assistant_message_output = False
    request_output_ids = {
        call_id
        for event in events
        for item in _request_input_items(_json_field(event.request_payload_json))
        if (call_id := _response_tool_output_call_id(item)) is not None
    }

    for event in events:
        request_items = _request_input_items(_json_field(event.request_payload_json))
        if first_model_call:
            delta_items = _initial_turn_input_items(request_items, user_message)
            if not delta_items:
                return []
            first_model_call = False
        elif request_items == failed_request_items:
            # HTTP retries repeat incremental inputs without replaying the whole
            # turn. Keep that logical request once, but still process its result.
            delta_items = []
        else:
            delta_items = _new_input_delta(request_items, turn_items)
        failed_request_items = request_items if event.success == 0 else None
        if _contains_redacted_inline_image(delta_items):
            return []
        turn_items.extend(_clone_json_dict(item) for item in delta_items)

        response_items = (
            _provider_response_output_items(_json_field(event.response_payload_json))
            if event.success != 0
            else []
        )
        response_items.extend(
            _missing_response_tool_outputs(
                response_items,
                turn_items,
                completed_tool_results or {},
                request_output_ids,
            )
        )
        saw_assistant_message_output = saw_assistant_message_output or any(
            _is_assistant_message_output_item(item) for item in response_items
        )
        turn_items.extend(_clone_json_dict(item) for item in response_items)
        item_batches.append((delta_items, response_items))

    completed_call_ids = _completed_response_tool_call_ids(item_batches)
    for delta_items, response_items in item_batches:
        history_items.extend(
            _provider_input_history_items(
                _filter_incomplete_response_tool_items(
                    delta_items,
                    completed_call_ids,
                )
            )
        )
        history_items.extend(
            _provider_input_history_items(
                _filter_incomplete_response_tool_items(
                    response_items,
                    completed_call_ids,
                )
            )
        )
    if require_completed_tool_exchange and not completed_call_ids:
        return []
    if not saw_assistant_message_output and not require_completed_tool_exchange:
        return []
    return history_items


def _missing_response_tool_outputs(
    response_items: list[dict[str, Any]],
    previous_items: list[dict[str, Any]],
    completed_tool_results: dict[str, Any],
    request_output_ids: set[str],
) -> list[dict[str, Any]]:
    existing_output_ids = {
        call_id
        for item in [*previous_items, *response_items]
        if (call_id := _response_tool_output_call_id(item)) is not None
    }
    outputs: list[dict[str, Any]] = []
    for item in response_items:
        call_id = _response_tool_input_call_id(item)
        if (
            call_id is None
            or call_id in existing_output_ids
            or call_id in request_output_ids
            or call_id not in completed_tool_results
        ):
            continue
        event = completed_tool_results[call_id]
        output = _json_field(event.tool_output_json)
        outputs.append(
            {
                "type": (
                    "custom_tool_call_output"
                    if item.get("type") == "custom_tool_call"
                    else "function_call_output"
                ),
                "call_id": call_id,
                "output": (
                    output
                    if isinstance(output, str)
                    else json.dumps(output, separators=(",", ":"))
                ),
            }
        )
        existing_output_ids.add(call_id)
    return outputs


def _request_input_items(payload: Any) -> list[dict[str, Any]]:
    if not isinstance(payload, dict):
        return []
    raw_input = payload.get("input")
    if isinstance(raw_input, list):
        return [_clone_json_dict(item) for item in raw_input if isinstance(item, dict)]
    if isinstance(raw_input, str):
        return [{"role": "user", "content": raw_input}]
    return []


def _provider_response_output_items(payload: Any) -> list[dict[str, Any]]:
    if not isinstance(payload, dict):
        return []
    return [
        _clone_json_dict(item)
        for item in _response_output_items(payload)
        if isinstance(item, dict)
    ]


def _is_assistant_message_output_item(item: dict[str, Any]) -> bool:
    if item.get("type") != "message":
        return False
    role = item.get("role")
    return role is None or str(role).lower() == "assistant"


def _initial_turn_input_items(
    request_items: list[dict[str, Any]],
    user_message: MessageRecord,
) -> list[dict[str, Any]]:
    if not request_items:
        return []
    match_index = _matching_user_input_index(request_items, user_message)
    if match_index is not None:
        return [_clone_json_dict(item) for item in request_items[match_index:]]
    return []


def _matching_user_input_index(
    request_items: list[dict[str, Any]],
    user_message: MessageRecord,
) -> int | None:
    for index in range(len(request_items) - 1, -1, -1):
        if _input_item_matches_message(request_items[index], user_message):
            return index
    return None


def _input_item_matches_message(
    item: dict[str, Any],
    message: MessageRecord,
) -> bool:
    if str(item.get("role") or "").lower() != "user":
        return False
    actual = _input_item_text(item.get("content")).strip()
    return actual in _user_message_prompt_texts(message) and bool(
        actual or message.content.strip()
    )


def _input_item_text(content: Any) -> str:
    if isinstance(content, str):
        return content
    if not isinstance(content, list):
        return ""
    text_parts: list[str] = []
    for part in content:
        if not isinstance(part, dict):
            continue
        part_type = str(part.get("type") or "")
        if part_type in {"input_text", "output_text", "text"}:
            text = part.get("text")
            if isinstance(text, str):
                text_parts.append(text)
    return "".join(text_parts)


def _parts_text(parts: Any) -> str:
    if not isinstance(parts, list):
        return ""
    return "".join(
        str(part.get("text") or "")
        for part in parts
        if isinstance(part, dict) and not bool(part.get("thought"))
    )


def _new_input_delta(
    request_items: list[dict[str, Any]],
    existing_items: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    if not request_items:
        return []
    if not existing_items:
        return [_clone_json_dict(item) for item in request_items]
    # Stateless Responses follow-ups sanitize prior outputs for request input,
    # while traced outputs retain metadata (id/status, message annotations, etc.).
    # Compare the same input-safe form without changing the returned delta.
    normalized_request = [
        _response_history_item_for_input(item) for item in request_items
    ]
    normalized_existing = [
        _response_history_item_for_input(item) for item in existing_items
    ]
    if _json_item_sequence_startswith(normalized_request, normalized_existing):
        return [_clone_json_dict(item) for item in request_items[len(existing_items) :]]
    existing_start = _find_json_item_subsequence(
        normalized_request, normalized_existing
    )
    if existing_start is not None:
        return [
            _clone_json_dict(item)
            for item in request_items[existing_start + len(existing_items) :]
        ]
    return [_clone_json_dict(item) for item in request_items]


def _json_item_sequence_startswith(
    items: list[dict[str, Any]],
    prefix: list[dict[str, Any]],
) -> bool:
    return len(items) >= len(prefix) and items[: len(prefix)] == prefix


def _find_json_item_subsequence(
    items: list[dict[str, Any]],
    sequence: list[dict[str, Any]],
) -> int | None:
    if not sequence or len(sequence) > len(items):
        return None
    last_start = len(items) - len(sequence)
    for start in range(last_start, -1, -1):
        if items[start : start + len(sequence)] == sequence:
            return start
    return None


def _provider_input_history_items(
    items: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    return [
        {
            "type": PROVIDER_INPUT_HISTORY_ITEM,
            "format": OPENAI_RESPONSES_HISTORY_FORMAT,
            "item": _response_history_item_for_input(item),
        }
        for item in items
    ]


def _completed_response_tool_call_ids(
    item_batches: list[tuple[list[dict[str, Any]], list[dict[str, Any]]]],
) -> set[str]:
    call_ids: set[str] = set()
    output_ids: set[str] = set()
    for delta_items, response_items in item_batches:
        for item in [*delta_items, *response_items]:
            if call_id := _response_tool_output_call_id(item):
                output_ids.add(call_id)
        for item in response_items:
            if call_id := _response_tool_input_call_id(item):
                call_ids.add(call_id)
    return call_ids & output_ids


def _filter_incomplete_response_tool_items(
    items: list[dict[str, Any]],
    completed_call_ids: set[str],
) -> list[dict[str, Any]]:
    filtered: list[dict[str, Any]] = []
    for item in items:
        call_id = _response_tool_input_call_id(item)
        if call_id is not None:
            if call_id in completed_call_ids:
                filtered.append(item)
            continue
        call_id = _response_tool_output_call_id(item)
        if call_id is not None:
            if call_id in completed_call_ids:
                filtered.append(item)
            continue
        filtered.append(item)
    return filtered


def _response_tool_input_call_id(item: dict[str, Any]) -> str | None:
    if item.get("type") not in {"function_call", "custom_tool_call"}:
        return None
    call_id = item.get("call_id")
    return call_id if isinstance(call_id, str) and call_id else None


def _response_tool_output_call_id(item: dict[str, Any]) -> str | None:
    if item.get("type") not in {
        "function_call_output",
        "custom_tool_call_output",
    }:
        return None
    call_id = item.get("call_id")
    return call_id if isinstance(call_id, str) and call_id else None


def _response_history_item_for_input(item: dict[str, Any]) -> dict[str, Any]:
    return response_history_item_for_input(item)


def _contains_redacted_inline_image(value: Any) -> bool:
    if isinstance(value, dict):
        image_url = value.get("image_url")
        if isinstance(image_url, str) and image_url.endswith(
            f",{REDACTED_INLINE_IMAGE_MARKER}"
        ):
            return True
        return any(_contains_redacted_inline_image(item) for item in value.values())
    if isinstance(value, list):
        return any(_contains_redacted_inline_image(item) for item in value)
    return False


def _clone_json_dict(item: dict[str, Any]) -> dict[str, Any]:
    cloned = _clone_json_value(item)
    return cloned if isinstance(cloned, dict) else dict(item)


def _clone_json_value(value: Any) -> Any:
    return json.loads(json.dumps(value))


def _tool_history_by_run(
    store: SessionStore,
    session_id: str,
    *,
    after: str | None = None,
) -> list[tuple[Any, list[dict[str, Any]], str, list[_RunUserInput]]]:
    histories: list[tuple[Any, list[dict[str, Any]], str, list[_RunUserInput]]] = []
    for run in store.list_run_sessions(session_id):
        if run.parent_run_session_id or run.agent_name not in {None, "main"}:
            continue
        if run.agent_type not in {"session_turn", "single_turn"}:
            continue
        run_items: list[dict[str, Any]] = []
        seen_calls: dict[str, dict[str, Any]] = {}
        intermediate_parts: list[str] = []
        run_events = store.list_observability_events(run_session_id=run.run_session_id)
        for event in run_events:
            if after is not None and event.timestamp <= after:
                continue
            if event.event_type == "model_call":
                response_items = _generic_response_history_items(
                    _json_field(event.response_payload_json)
                )
                response_items = _group_response_tool_calls(response_items)
                for item in response_items:
                    if item.get("type") == "intermediate_text":
                        intermediate_parts.append(str(item.get("content") or ""))
                    elif item.get("type") == "tool_call":
                        seen_calls[item["call_id"]] = item
                    elif item.get("type") == "tool_call_group":
                        for call in item.get("calls", []):
                            if isinstance(call, dict) and call.get("call_id"):
                                seen_calls[call["call_id"]] = call
                    run_items.append(item)
            elif event.event_type == "tool_call" and event.tool_call_id:
                if event.tool_call_id not in seen_calls:
                    call = {
                        "type": "tool_call",
                        "call_id": event.tool_call_id,
                        "name": event.tool_name or "",
                        "arguments": _json_field(event.tool_input_json),
                        "kind": "function",
                    }
                    seen_calls[event.tool_call_id] = call
                    run_items.append(call)
                run_items.append(
                    {
                        "type": "tool_result",
                        "call_id": event.tool_call_id,
                        "name": event.tool_name or "",
                        "output": _json_field(event.tool_output_json),
                        "is_error": event.success == 0,
                        "error_message": event.error_message,
                        "kind": seen_calls[event.tool_call_id].get(
                            "kind",
                            "function",
                        ),
                    }
                )
        run_items = _filter_incomplete_tool_exchange_items(run_items)
        histories.append(
            (
                run,
                _group_parallel_tool_results(run_items),
                "\n\n".join(intermediate_parts),
                _run_user_inputs(run_events),
            )
        )
    return histories


def _interrupted_generic_run_items(
    run: Any,
    user_message: MessageRecord | None,
    items: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    restored: list[dict[str, Any]] = []
    for index, item in enumerate(items):
        if item.get("type") != "intermediate_text":
            restored.append(item)
            continue
        content = str(item.get("content") or "")
        if not content or user_message is None:
            continue
        restored.append(
            {
                "type": "message",
                "message": MessageRecord(
                    id=-(int(run.id) * 1000 + index + 1),
                    session_id=user_message.session_id,
                    role="assistant",
                    content=content,
                    created_at=run.started_at,
                    provider_id=run.provider_id,
                    profile_id=run.profile_id,
                ),
            }
        )
    return restored


def _completed_generic_run_items(
    items: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    return [item for item in items if item.get("type") != "intermediate_text"]


def _filter_incomplete_tool_exchange_items(
    items: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    completed_call_ids = _completed_tool_exchange_call_ids(items)
    filtered: list[dict[str, Any]] = []
    for item in items:
        item_type = item.get("type")
        if item_type == "tool_call":
            if item.get("call_id") in completed_call_ids:
                filtered.append(item)
        elif item_type == "tool_call_group":
            calls = [
                call
                for call in item.get("calls", [])
                if isinstance(call, dict) and call.get("call_id") in completed_call_ids
            ]
            if calls:
                filtered.append({**item, "calls": calls})
        elif item_type == "tool_result":
            if item.get("call_id") in completed_call_ids:
                filtered.append(item)
        else:
            filtered.append(item)
    return filtered


def _completed_tool_exchange_call_ids(items: list[dict[str, Any]]) -> set[str]:
    call_ids: set[str] = set()
    result_ids: set[str] = set()
    for item in items:
        item_type = item.get("type")
        if item_type == "tool_call":
            if call_id := item.get("call_id"):
                call_ids.add(str(call_id))
        elif item_type == "tool_call_group":
            for call in item.get("calls", []):
                if isinstance(call, dict) and (call_id := call.get("call_id")):
                    call_ids.add(str(call_id))
        elif item_type == "tool_result":
            if call_id := item.get("call_id"):
                result_ids.add(str(call_id))
    return call_ids & result_ids


def _group_parallel_tool_results(
    items: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    grouped: list[dict[str, Any]] = []
    index = 0
    while index < len(items):
        item = items[index]
        grouped.append(item)
        index += 1
        if item.get("type") != "tool_call_group":
            continue

        call_ids = {
            call.get("call_id")
            for call in item.get("calls", [])
            if isinstance(call, dict) and call.get("call_id")
        }
        result_items: list[dict[str, Any]] = []
        while (
            index < len(items)
            and items[index].get("type") == "tool_result"
            and items[index].get("call_id") in call_ids
        ):
            result_items.append(items[index])
            index += 1
        if len(result_items) > 1:
            grouped.append({"type": "tool_result_group", "results": result_items})
        else:
            grouped.extend(result_items)
    return grouped


def _tool_calls_from_response_payload(payload: Any) -> list[dict[str, Any]]:
    if not isinstance(payload, dict):
        return []
    calls: list[dict[str, Any]] = []
    for item in _response_output_items(payload):
        if not isinstance(item, dict):
            continue
        item_type = item.get("type")
        if item_type == "function" and isinstance(item.get("function"), dict):
            function = item["function"]
            item = {
                "type": "function_call",
                "call_id": item.get("id"),
                "name": function.get("name"),
                "arguments": function.get("arguments"),
            }
            item_type = "function_call"
        if item_type in {"function_call", "custom_tool_call"}:
            call_id = item.get("call_id") or item.get("id")
            name = item.get("name")
            arguments = item.get("arguments", item.get("input"))
            if isinstance(arguments, str):
                try:
                    arguments = json.loads(arguments)
                except json.JSONDecodeError:
                    pass
            if isinstance(call_id, str) and call_id:
                calls.append(
                    {
                        "type": "tool_call",
                        "call_id": call_id,
                        "name": name if isinstance(name, str) else "",
                        "arguments": arguments,
                        "kind": (
                            "custom" if item_type == "custom_tool_call" else "function"
                        ),
                    }
                )
    return calls


def _generic_response_history_items(payload: Any) -> list[dict[str, Any]]:
    if not isinstance(payload, dict):
        return []
    items: list[dict[str, Any]] = []
    choices = payload.get("choices")
    if isinstance(choices, list):
        for choice in choices:
            message = choice.get("message") if isinstance(choice, dict) else None
            if not isinstance(message, dict):
                continue
            if text := _input_item_text(message.get("content")):
                items.append({"type": "intermediate_text", "content": text})
            items.extend(
                _tool_calls_from_response_payload({"choices": [{"message": message}]})
            )
        return _deduplicate_adjacent_history_items(items)
    raw_items = _response_output_items(payload)
    for item in raw_items:
        if not isinstance(item, dict):
            continue
        if item.get("type") in {"message", "model_output"}:
            if text := _input_item_text(item.get("content")):
                items.append({"type": "intermediate_text", "content": text})
        items.extend(_tool_calls_from_response_payload({"output": [item]}))
    content = payload.get("content")
    if isinstance(content, list):
        for block in content:
            if not isinstance(block, dict):
                continue
            if block.get("type") == "text":
                text = block.get("text")
                if isinstance(text, str) and text:
                    items.append({"type": "intermediate_text", "content": text})
            elif block.get("type") == "tool_use":
                call_id = block.get("id")
                if isinstance(call_id, str) and call_id:
                    items.append(
                        {
                            "type": "tool_call",
                            "call_id": call_id,
                            "name": str(block.get("name") or ""),
                            "arguments": block.get("input"),
                            "kind": "function",
                        }
                    )
    candidates = payload.get("candidates")
    if isinstance(candidates, list):
        for candidate in candidates:
            content = candidate.get("content") if isinstance(candidate, dict) else None
            parts = content.get("parts") if isinstance(content, dict) else None
            if not isinstance(parts, list):
                continue
            for part in parts:
                if not isinstance(part, dict) or bool(part.get("thought")):
                    continue
                text = part.get("text")
                if isinstance(text, str) and text:
                    items.append({"type": "intermediate_text", "content": text})
                function_call = part.get("functionCall")
                if not isinstance(function_call, dict):
                    function_call = part.get("function_call")
                if isinstance(function_call, dict):
                    call_id = function_call.get("id") or function_call.get("call_id")
                    if isinstance(call_id, str) and call_id:
                        items.append(
                            {
                                "type": "tool_call",
                                "call_id": call_id,
                                "name": str(function_call.get("name") or ""),
                                "arguments": function_call.get("args") or {},
                                "kind": "function",
                            }
                        )
    return _deduplicate_adjacent_history_items(items)


def _deduplicate_adjacent_history_items(
    items: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    deduplicated: list[dict[str, Any]] = []
    for item in items:
        if deduplicated and item == deduplicated[-1]:
            continue
        deduplicated.append(item)
    return deduplicated


def _group_response_tool_calls(
    items: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    grouped: list[dict[str, Any]] = []
    index = 0
    while index < len(items):
        if items[index].get("type") != "tool_call":
            grouped.append(items[index])
            index += 1
            continue
        calls: list[dict[str, Any]] = []
        while index < len(items) and items[index].get("type") == "tool_call":
            calls.append(items[index])
            index += 1
        grouped.append(
            calls[0] if len(calls) == 1 else {"type": "tool_call_group", "calls": calls}
        )
    return grouped


def _response_output_items(payload: dict[str, Any]) -> list[Any]:
    output = payload.get("output")
    if isinstance(output, list):
        return output
    outputs = payload.get("outputs")
    if isinstance(outputs, list):
        return outputs
    steps = payload.get("steps")
    if isinstance(steps, list):
        return [step for step in steps if isinstance(step, dict)]
    choices = payload.get("choices")
    if not isinstance(choices, list):
        return []
    items: list[Any] = []
    for choice in choices:
        if not isinstance(choice, dict):
            continue
        message = choice.get("message")
        if isinstance(message, dict):
            items.extend(message.get("tool_calls", []) or [])
    return items


def _json_field(value: str | None) -> Any:
    if value is None:
        return None
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return value


open_store = _open_store
persist_runtime_change = _persist_runtime_change
create_session = _create_session
update_session_after_turn = _update_session_after_turn
refresh_provider_history_from_store = _refresh_provider_history_from_store
update_session_title = _update_session_title
add_message = _add_message
publish_persisted_message = _publish_persisted_message
delete_message = _delete_message
discard_interrupted_turn = _discard_interrupted_turn
resume_session = _resume_session
messages_for_provider_restore = _messages_for_provider_restore
history_items_for_provider_restore = _history_items_for_provider_restore
