from __future__ import annotations

from contextlib import ExitStack, contextmanager
from dataclasses import replace
from pathlib import Path
import time
from typing import Any, Callable

from pbi_agent.agent.skill_discovery import format_project_skills_markdown
from pbi_agent.agent.skill_discovery import extract_explicit_skill_names
from pbi_agent.agent.sub_agent_discovery import (
    extract_explicit_agent_names,
    format_project_sub_agents_markdown,
    get_project_sub_agent_by_name,
    reset_active_explicit_agent_names,
    set_active_explicit_agent_names,
)
from pbi_agent.agent.system_prompt import (
    get_sub_agent_system_prompt,
    get_system_prompt,
)
from pbi_agent.config import (
    ResolvedRuntime,
    Settings,
    resolve_runtime_for_profile_id,
)
from pbi_agent.display.protocol import DisplayProtocol, QueuedInput, QueuedRuntimeChange
from pbi_agent.extensions import (
    find_extension_for_slash,
    format_extensions_markdown,
    run_extension,
    tool_catalog_with_extensions,
)
from pbi_agent.init_agents import format_init_agents_result, init_agents_file
from pbi_agent.mcp import format_project_mcp_servers_markdown
from pbi_agent.models.messages import (
    AgentOutcome,
    CompletedResponse,
    ImageAttachment,
    TokenUsage,
    ToolCall,
)
from pbi_agent.observability import RunTracer
from pbi_agent.providers import create_provider
from pbi_agent.session_store import MessageImageAttachment, SessionStore
from pbi_agent.tools.catalog import ToolCatalog
from pbi_agent.tools.types import ParentContextSnapshot

from pbi_agent.agent.session.commands import (
    build_user_turn_input as _build_user_turn_input,
    close_store as _close_store,
    format_extension_run_markdown as _format_extension_run_markdown,
    mcp_workspace_key as _mcp_workspace_key,
    normalize_user_command as _normalize_user_command,
    parse_init_command_force as _parse_init_command_force,
    reload_provider_initialization as _reload_provider_initialization,
    remove_active_mcp_tool_names as _remove_active_mcp_tool_names,
    request_user_turn as _request_user_turn,
    reserved_slash_extension_names as _reserved_slash_extension_names,
    session_title_for_user_turn as _session_title_for_user_turn,
    user_turn_history_text as _user_turn_history_text,
)
from pbi_agent.agent.session.compaction import (
    compact_live_session as _compact_live_session,
    compaction_continuation_prompt as _compaction_continuation_prompt,
    provider_has_server_side_compaction as _provider_has_server_side_compaction,
    should_auto_compact as _should_auto_compact,
)
from pbi_agent.agent.session.history import (
    add_message as _add_message,
    create_session as _create_session,
    delete_message as _delete_message,
    discard_interrupted_turn as _discard_interrupted_turn,
    open_store as _open_store,
    persist_runtime_change as _persist_runtime_change,
    publish_persisted_message as _publish_persisted_message,
    refresh_provider_history_from_store as _refresh_provider_history_from_store,
    resume_session as _resume_session,
    update_session_after_turn as _update_session_after_turn,
    update_session_title as _update_session_title,
)
from pbi_agent.agent.session.shared import (
    AGENTS_COMMAND,
    COMPACT_COMMAND,
    EXTENSIONS_COMMAND,
    INTERACTIVE_ONLY_TOOLS,
    MCP_COMMAND,
    NEW_SESSION_SENTINEL,
    RELOAD_COMMAND,
    RESUME_SESSION_PREFIX,
    SKILLS_COMMAND,
    SUB_AGENT_DISABLED_TOOLS,
    SUB_AGENT_MAX_ELAPSED_SECONDS,
    SUB_AGENT_MAX_REQUESTS,
    SessionTurnInterrupted,
    SubAgentRunError,
    active_mcp_tool_names_by_workspace as _ACTIVE_MCP_TOOL_NAMES_BY_WORKSPACE,
    active_mcp_tool_names_context as _ACTIVE_MCP_TOOL_NAMES,
    active_mcp_tool_names_lock as _ACTIVE_MCP_TOOL_NAMES_LOCK,
    agent_definition_declares_tool_availability as _agent_definition_declares_tool_availability,
    bind_session as _bind_session,
    coerce_runtime as _coerce_runtime,
    extract_active_command as _extract_active_command,
    log as _log,
    raise_if_interrupted as _raise_if_interrupted,
    requires_provider_reopen as _requires_provider_reopen,
    run_reasoning_metadata as _run_reasoning_metadata,
    runtime_for_active_command as _runtime_for_active_command,
    runtime_from_provider as _runtime_from_provider,
    selected_model as _selected_model,
    selected_sub_agent_model as _selected_sub_agent_model,
    set_provider_runtime_settings as _set_provider_runtime_settings,
    set_provider_tool_availability_overridden as _set_provider_tool_availability_overridden,
    settings_with_tool_availability as _settings_with_tool_availability,
    turn_instructions as _turn_instructions,
)
from pbi_agent.agent.session.subagents import (
    apply_sub_agent_parent_context as _apply_sub_agent_parent_context,
    build_parent_context_snapshot as _build_parent_context_snapshot,
    build_sub_agent_initial_message as _build_sub_agent_initial_message,
)


def run_single_turn(
    prompt: str,
    settings: Settings | ResolvedRuntime,
    display: DisplayProtocol,
    *,
    single_turn_hint: str | None = None,
    resume_session_id: str | None = None,
    image_paths: list[str] | None = None,
    images: list[ImageAttachment] | None = None,
    persisted_user_message_id: int | None = None,
    replay_history: bool = True,
    include_tool_history: bool = False,
    workspace_root: Path | None = None,
    workspace_directory_key: str | None = None,
) -> AgentOutcome:
    runtime = _coerce_runtime(settings)
    store = _open_store(runtime.settings)
    settings = runtime.settings
    session_start = time.monotonic()
    prompt_text = prompt
    active_command = _extract_active_command(prompt)
    if active_command is not None:
        runtime = _runtime_for_active_command(runtime, active_command)
        settings = runtime.settings
    active_command_instructions = (
        active_command.instructions if active_command is not None else None
    )
    workspace = (workspace_root or Path.cwd()).resolve()
    explicit_skill_names = extract_explicit_skill_names(prompt_text)
    explicit_agent_names = extract_explicit_agent_names(prompt_text)
    turn_instructions = _turn_instructions(
        active_command_instructions,
        settings=settings,
        excluded_tools=INTERACTIVE_ONLY_TOOLS,
        cwd=workspace,
        user_input=prompt_text,
        workspace_directory_key=workspace_directory_key,
    )
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
    turn_usage = TokenUsage(model=model, service_tier=_tier)

    user_input = _build_user_turn_input(
        text=prompt_text,
        image_paths=image_paths or [],
        images=images,
        settings=settings,
        workspace_root=workspace,
    )
    user_turn_history_text = _user_turn_history_text(user_input)
    session_id = resume_session_id or _create_session(
        store,
        runtime,
        title=_session_title_for_user_turn(user_input),
        directory_key=workspace_directory_key,
    )
    tracer = RunTracer.start(
        store=store,
        session_id=session_id,
        agent_name="main",
        agent_type="single_turn",
        provider=settings.provider,
        provider_id=runtime.provider_id,
        profile_id=runtime.profile_id,
        model=model,
        metadata={
            **_run_reasoning_metadata(settings),
            "single_turn_hint": single_turn_hint,
            "resumed": resume_session_id is not None,
        },
    )

    try:
        with _open_runtime_provider(
            settings,
            system_prompt=get_system_prompt(
                settings=settings,
                excluded_tools=INTERACTIVE_ONLY_TOOLS,
                cwd=workspace,
                explicit_skill_names=explicit_skill_names,
                explicit_agent_names=explicit_agent_names,
                workspace_directory_key=workspace_directory_key,
            ),
            excluded_tools=INTERACTIVE_ONLY_TOOLS,
            tool_availability_overridden=runtime.tool_availability_overridden,
            workspace_root=workspace,
            workspace_directory_key=workspace_directory_key,
            explicit_agent_names=explicit_agent_names,
        ) as provider:
            display.assistant_start()
            _resume_session(
                provider=provider,
                store=store,
                session_id=resume_session_id,
                session_usage=session_usage,
                display=display,
                before_message_id=persisted_user_message_id,
                replay_history=replay_history,
                include_tool_history=include_tool_history,
            )
            if persisted_user_message_id is None:
                user_message_id = _add_message(
                    store,
                    session_id,
                    runtime,
                    "user",
                    user_turn_history_text,
                )
                _publish_persisted_message(display, store, user_message_id)
            tracer.log_event(
                "agent_step_start",
                metadata={"step": "initial_model_request"},
            )
            response = _request_user_turn(
                provider=provider,
                user_input=user_input,
                session_id=session_id,
                instructions=turn_instructions,
                display=display,
                session_usage=session_usage,
                turn_usage=turn_usage,
                tracer=tracer,
            )
            tracer.log_event(
                "agent_step_end",
                metadata={"step": "initial_model_request"},
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
                instructions=turn_instructions,
                tracer=tracer,
                current_turn_tool_exchanges=[],
            )
            assistant_message_id = _add_message(
                store,
                session_id,
                runtime,
                "assistant",
                response.text,
            )
            _publish_persisted_message(display, store, assistant_message_id)
            _update_session_after_turn(
                store,
                session_id,
                runtime,
                session_usage,
            )
            _refresh_provider_history_from_store(
                provider,
                store,
                session_id,
                reason="turn",
                include_tool_history=include_tool_history,
            )
            display.assistant_stop()
            elapsed = time.monotonic() - session_start
            display.turn_usage(turn_usage, elapsed)
            display.session_usage(session_usage)
            tracer.finish(
                status="completed",
                usage=turn_usage,
                metadata={"tool_errors": had_tool_errors},
            )
            return AgentOutcome(
                response_id=response.response_id,
                text=response.text,
                tool_errors=had_tool_errors,
                session_id=session_id,
            )
    except Exception as exc:
        display.assistant_stop()
        tracer.log_error(str(exc), metadata={"phase": "run_single_turn"})
        tracer.finish(
            status="failed",
            usage=turn_usage,
            metadata={"error_message": str(exc)},
        )
        raise
    finally:
        _close_store(store)


def run_session_loop(
    settings: Settings | ResolvedRuntime,
    display: DisplayProtocol,
    *,
    resume_session_id: str | None = None,
    run_session_id: str | None = None,
    on_reload: Callable[[], None] | None = None,
    excluded_tools: set[str] | None = None,
    include_tool_history: bool = False,
    workspace_root: Path | None = None,
    workspace_directory_key: str | None = None,
) -> int:
    current_runtime = _coerce_runtime(settings)
    workspace = (workspace_root or Path.cwd()).resolve()
    saved_session_runtime = current_runtime
    store = _open_store(current_runtime.settings)
    session_id: str | None = resume_session_id
    title_set = bool(resume_session_id)
    resume_session_to_restore = resume_session_id
    replay_history_on_restore = resume_session_id is not None
    provider_history_include_tool_history: bool | None = None
    should_exit = False
    base_excluded_tools = set(excluded_tools) if excluded_tools is not None else set()

    def _render_temporary_command_markdown(text: str) -> None:
        render_transient = getattr(display, "render_transient_markdown", None)
        if callable(render_transient):
            render_transient(text)
        else:
            display.render_markdown(text)

    def _turn_excluded_tools(*, interactive_mode: bool = False) -> set[str]:
        return base_excluded_tools | (
            set()
            if interactive_mode and excluded_tools is None
            else INTERACTIVE_ONLY_TOOLS
        )

    def _reset_session(
        active_runtime: ResolvedRuntime, *, clear_display: bool = False
    ) -> TokenUsage:
        if clear_display:
            display.reset_session()
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

    session_usage = _reset_session(current_runtime)
    _bind_session(display, session_id)
    had_tool_errors = False
    while not should_exit:
        with _open_runtime_provider(
            current_runtime.settings,
            system_prompt=get_system_prompt(
                settings=current_runtime.settings,
                excluded_tools=_turn_excluded_tools(interactive_mode=False),
                cwd=workspace,
                workspace_directory_key=workspace_directory_key,
            ),
            excluded_tools=_turn_excluded_tools(interactive_mode=False),
            tool_availability_overridden=(current_runtime.tool_availability_overridden),
            workspace_root=workspace,
            workspace_directory_key=workspace_directory_key,
        ) as provider:
            if resume_session_to_restore is not None:
                _resume_session(
                    provider=provider,
                    store=store,
                    session_id=resume_session_to_restore,
                    session_usage=session_usage,
                    display=display,
                    replay_history=replay_history_on_restore,
                    include_tool_history=include_tool_history,
                )
                resume_session_to_restore = None
                replay_history_on_restore = False
                provider_history_include_tool_history = include_tool_history
            while True:
                queued_input = display.user_prompt()
                file_paths: list[str] = []
                image_paths: list[str] = []
                queued_images: list[ImageAttachment] = []
                message_image_attachments: list[MessageImageAttachment] = []
                if isinstance(queued_input, QueuedRuntimeChange):
                    current_runtime = queued_input.runtime
                    if queued_input.persist:
                        saved_session_runtime = current_runtime
                        _persist_runtime_change(
                            store,
                            session_id,
                            saved_session_runtime,
                        )
                    elif queued_input.saved_runtime is not None:
                        saved_session_runtime = queued_input.saved_runtime
                    session_usage = _reset_session(
                        current_runtime,
                    )
                    if session_id is not None:
                        resume_session_to_restore = session_id
                        replay_history_on_restore = False
                        provider_history_include_tool_history = None
                        _bind_session(display, session_id)
                    break
                if isinstance(queued_input, QueuedInput):
                    user_input = queued_input.text.strip()
                    file_paths = queued_input.file_paths
                    image_paths = queued_input.image_paths
                    queued_images = queued_input.images
                    message_image_attachments = queued_input.image_attachments
                    turn_interactive_mode = queued_input.interactive_mode
                    turn_include_tool_history = queued_input.include_tool_history
                    queued_item_id = queued_input.item_id
                else:
                    user_input = queued_input.strip()
                    turn_interactive_mode = False
                    turn_include_tool_history = include_tool_history
                    queued_item_id = None
                if user_input == NEW_SESSION_SENTINEL:
                    provider.reset_conversation()
                    session_usage = _reset_session(
                        current_runtime,
                        clear_display=True,
                    )
                    had_tool_errors = False
                    session_id = None
                    title_set = False
                    provider_history_include_tool_history = None
                    _bind_session(display, session_id)
                    continue
                if user_input.startswith(RESUME_SESSION_PREFIX):
                    resume_id = user_input[len(RESUME_SESSION_PREFIX) :]
                    provider.reset_conversation()
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
                        provider_history_include_tool_history = None
                        break
                    else:
                        _bind_session(display, session_id)
                    continue
                if user_input.lower() in {"exit", "quit"}:
                    should_exit = True
                    break
                normalized_command = _normalize_user_command(user_input)
                if normalized_command == SKILLS_COMMAND:
                    _render_temporary_command_markdown(
                        format_project_skills_markdown(
                            workspace,
                            directory_key=workspace_directory_key,
                        )
                    )
                    continue
                if normalized_command == MCP_COMMAND:
                    _render_temporary_command_markdown(
                        format_project_mcp_servers_markdown(workspace)
                    )
                    continue
                if normalized_command == AGENTS_COMMAND:
                    _render_temporary_command_markdown(
                        format_project_sub_agents_markdown(
                            workspace,
                            directory_key=workspace_directory_key,
                        )
                    )
                    continue
                if normalized_command == EXTENSIONS_COMMAND:
                    _render_temporary_command_markdown(
                        format_extensions_markdown(
                            workspace,
                            reserved_names=_reserved_slash_extension_names(workspace),
                        )
                    )
                    continue
                init_force = _parse_init_command_force(user_input)
                if init_force is not None:
                    result = init_agents_file(workspace=workspace, force=init_force)
                    _render_temporary_command_markdown(
                        format_init_agents_result(result)
                    )
                    continue
                if normalized_command == RELOAD_COMMAND:
                    _reload_provider_initialization(
                        provider,
                        workspace,
                        workspace_directory_key=workspace_directory_key,
                    )
                    if on_reload is not None:
                        on_reload()
                    _render_temporary_command_markdown(
                        "Reloaded workspace instructions, project rules, skills, "
                        "sub-agents, tool definitions, and file mention cache. "
                        "MCP servers are not reloaded; restart the session after "
                        "changing MCP config."
                    )
                    continue
                extension = None
                if normalized_command:
                    extension = find_extension_for_slash(
                        normalized_command.split(maxsplit=1)[0],
                        workspace,
                        reserved_names=_reserved_slash_extension_names(workspace),
                    )
                if extension is not None:
                    parts = user_input.split(maxsplit=1)
                    result = run_extension(
                        extension,
                        {"text": parts[1] if len(parts) > 1 else ""},
                        workspace=workspace,
                    )
                    _render_temporary_command_markdown(
                        _format_extension_run_markdown(extension.name, result)
                    )
                    continue
                if normalized_command == COMPACT_COMMAND:
                    if session_id is None:
                        display.render_markdown(
                            "No active session context to compact yet."
                        )
                        continue
                    session_usage.context_tokens = _compact_live_session(
                        provider=provider,
                        store=store,
                        session_id=session_id,
                        runtime=current_runtime,
                        display=display,
                        session_usage=session_usage,
                        reason="manual",
                    )
                    display.session_usage(session_usage)
                    provider_history_include_tool_history = False
                    continue
                active_command = _extract_active_command(user_input)
                active_command_instructions = (
                    active_command.instructions if active_command is not None else None
                )
                if not user_input and not image_paths and not queued_images:
                    continue

                turn_runtime = current_runtime
                if active_command is not None:
                    turn_runtime = _runtime_for_active_command(
                        current_runtime, active_command
                    )
                    turn_settings = turn_runtime.settings
                else:
                    turn_settings = turn_runtime.settings
                turn_excluded_tools = _turn_excluded_tools(
                    interactive_mode=turn_interactive_mode
                )
                explicit_skill_names = extract_explicit_skill_names(user_input)
                explicit_agent_names = extract_explicit_agent_names(user_input)
                turn_instructions = _turn_instructions(
                    active_command_instructions,
                    settings=turn_settings,
                    excluded_tools=turn_excluded_tools,
                    cwd=workspace,
                    user_input=user_input,
                    workspace_directory_key=workspace_directory_key,
                )
                if turn_instructions is None and (
                    explicit_skill_names or explicit_agent_names
                ):
                    turn_instructions = get_system_prompt(
                        settings=turn_settings,
                        excluded_tools=turn_excluded_tools,
                        cwd=workspace,
                        explicit_skill_names=explicit_skill_names,
                        explicit_agent_names=explicit_agent_names,
                        workspace_directory_key=workspace_directory_key,
                    )
                if turn_instructions is None and turn_interactive_mode:
                    turn_instructions = get_system_prompt(
                        settings=turn_settings,
                        excluded_tools=turn_excluded_tools,
                        cwd=workspace,
                        explicit_skill_names=explicit_skill_names,
                        explicit_agent_names=explicit_agent_names,
                        workspace_directory_key=workspace_directory_key,
                    )
                turn_input = _build_user_turn_input(
                    text=user_input,
                    image_paths=image_paths,
                    images=queued_images,
                    settings=turn_settings,
                    workspace_root=workspace,
                )
                turn_history_text = _user_turn_history_text(turn_input)

                if session_id is None:
                    session_id = _create_session(
                        store,
                        saved_session_runtime,
                        title=_session_title_for_user_turn(turn_input),
                        directory_key=workspace_directory_key,
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
                    model=_selected_model(turn_settings),
                    service_tier=turn_settings.service_tier or "",
                )
                turn_tracer = RunTracer.start(
                    store=store,
                    run_session_id=run_session_id,
                    session_id=session_id,
                    agent_name="main",
                    agent_type="session_turn",
                    provider=turn_settings.provider,
                    provider_id=turn_runtime.provider_id,
                    profile_id=turn_runtime.profile_id,
                    model=_selected_model(turn_settings),
                    metadata={
                        **_run_reasoning_metadata(turn_settings),
                        "resumed": resume_session_id is not None,
                    },
                )
                display.assistant_start()
                user_message_id: int | None = None
                turn_provider = provider
                reset_provider_settings = False
                try:
                    _raise_if_interrupted(display)
                    with ExitStack() as turn_provider_stack:
                        if (
                            _requires_provider_reopen(
                                current_runtime.settings,
                                turn_settings,
                            )
                            or explicit_agent_names
                        ):
                            turn_provider = turn_provider_stack.enter_context(
                                _open_runtime_provider(
                                    turn_settings,
                                    system_prompt=turn_instructions,
                                    excluded_tools=turn_excluded_tools,
                                    tool_availability_overridden=(
                                        turn_runtime.tool_availability_overridden
                                    ),
                                    workspace_root=workspace,
                                    workspace_directory_key=workspace_directory_key,
                                    explicit_agent_names=explicit_agent_names,
                                )
                            )
                            _refresh_provider_history_from_store(
                                turn_provider,
                                store,
                                session_id,
                                reason="command profile",
                                include_tool_history=turn_include_tool_history,
                            )
                        else:
                            provider.set_excluded_tools(turn_excluded_tools)
                            if (
                                turn_settings != current_runtime.settings
                                or turn_runtime.tool_availability_overridden
                                != current_runtime.tool_availability_overridden
                            ):
                                _set_provider_runtime_settings(
                                    provider,
                                    turn_settings,
                                    tool_availability_overridden=(
                                        turn_runtime.tool_availability_overridden
                                    ),
                                )
                                reset_provider_settings = True
                            if (
                                provider_history_include_tool_history is not None
                                and provider_history_include_tool_history
                                != turn_include_tool_history
                            ):
                                _refresh_provider_history_from_store(
                                    provider,
                                    store,
                                    session_id,
                                    reason="turn preferences",
                                    include_tool_history=turn_include_tool_history,
                                )
                                provider_history_include_tool_history = (
                                    turn_include_tool_history
                                )
                        user_message_id = _add_message(
                            store,
                            session_id,
                            turn_runtime,
                            "user",
                            turn_history_text,
                            file_paths=file_paths,
                            image_attachments=message_image_attachments,
                        )
                        _publish_persisted_message(
                            display,
                            store,
                            user_message_id,
                            previous_item_id=queued_item_id,
                        )
                        turn_tracer.log_event(
                            "agent_step_start",
                            metadata={"step": "initial_model_request"},
                        )
                        response = _request_user_turn(
                            provider=turn_provider,
                            user_input=turn_input,
                            session_id=session_id,
                            instructions=turn_instructions,
                            display=display,
                            session_usage=session_usage,
                            turn_usage=turn_usage,
                            tracer=turn_tracer,
                        )
                        _raise_if_interrupted(display)
                        turn_tracer.log_event(
                            "agent_step_end",
                            metadata={"step": "initial_model_request"},
                        )
                        response, loop_had_errors, _ = _run_tool_iterations(
                            provider=turn_provider,
                            response=response,
                            max_workers=turn_settings.max_tool_workers,
                            display=display,
                            session_usage=session_usage,
                            turn_usage=turn_usage,
                            store=store,
                            session_id=session_id,
                            current_user_turn_text=turn_history_text,
                            instructions=turn_instructions,
                            tracer=turn_tracer,
                            current_turn_tool_exchanges=[],
                        )
                        _raise_if_interrupted(display)

                        assistant_message_id = _add_message(
                            store,
                            session_id,
                            turn_runtime,
                            "assistant",
                            response.text,
                        )
                        _publish_persisted_message(
                            display,
                            store,
                            assistant_message_id,
                        )
                        _update_session_after_turn(
                            store,
                            session_id,
                            saved_session_runtime,
                            session_usage,
                        )
                        _refresh_provider_history_from_store(
                            turn_provider,
                            store,
                            session_id,
                            reason="turn",
                            include_tool_history=turn_include_tool_history,
                        )
                        if turn_provider is provider:
                            provider_history_include_tool_history = (
                                turn_include_tool_history
                            )
                        if turn_provider is not provider:
                            _refresh_provider_history_from_store(
                                provider,
                                store,
                                session_id,
                                reason="turn",
                                include_tool_history=turn_include_tool_history,
                            )
                            provider_history_include_tool_history = (
                                turn_include_tool_history
                            )
                    had_tool_errors = had_tool_errors or loop_had_errors
                    display.assistant_stop()
                    elapsed = time.monotonic() - turn_start
                    display.turn_usage(turn_usage, elapsed)
                    display.session_usage(session_usage)
                    turn_tracer.finish(
                        status="completed",
                        usage=turn_usage,
                        metadata={"tool_errors": loop_had_errors},
                    )
                    if reset_provider_settings:
                        _set_provider_runtime_settings(
                            provider,
                            current_runtime.settings,
                            tool_availability_overridden=(
                                current_runtime.tool_availability_overridden
                            ),
                        )
                except SessionTurnInterrupted:
                    if reset_provider_settings:
                        _set_provider_runtime_settings(
                            provider,
                            current_runtime.settings,
                            tool_availability_overridden=(
                                current_runtime.tool_availability_overridden
                            ),
                        )
                    display.assistant_stop()
                    turn_tracer.log_event(
                        "turn_interrupted",
                        metadata={"phase": "run_session_loop"},
                    )
                    turn_tracer.finish(
                        status="interrupted",
                        usage=turn_usage,
                    )
                    _discard_interrupted_turn(
                        provider=turn_provider,
                        store=store,
                        session_id=session_id,
                        user_message_id=user_message_id,
                        include_tool_history=turn_include_tool_history,
                    )
                    if turn_provider is provider:
                        provider_history_include_tool_history = (
                            turn_include_tool_history
                        )
                    if turn_provider is not provider:
                        _refresh_provider_history_from_store(
                            provider,
                            store,
                            session_id,
                            reason="interrupt",
                            include_tool_history=turn_include_tool_history,
                        )
                        provider_history_include_tool_history = (
                            turn_include_tool_history
                        )
                    clear_interrupt = getattr(display, "clear_interrupt", None)
                    if callable(clear_interrupt):
                        clear_interrupt()
                    continue
                except Exception as exc:
                    if reset_provider_settings:
                        _set_provider_runtime_settings(
                            provider,
                            current_runtime.settings,
                            tool_availability_overridden=(
                                current_runtime.tool_availability_overridden
                            ),
                        )
                    display.assistant_stop()
                    turn_tracer.log_error(
                        str(exc), metadata={"phase": "run_session_loop"}
                    )
                    turn_tracer.finish(
                        status="failed",
                        usage=turn_usage,
                        metadata={"error_message": str(exc)},
                    )
                    if user_message_id is not None:
                        _delete_message(store, user_message_id)
                    raise

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
    parent_tool_availability_overridden: bool = False,
    parent_context: ParentContextSnapshot | None = None,
    parent_tracer: RunTracer | None = None,
    workspace_root: Path | None = None,
    workspace_directory_key: str | None = None,
) -> dict[str, Any]:
    workspace = (workspace_root or Path.cwd()).resolve()
    agent_definition = None
    if agent_type is not None:
        if workspace_directory_key is None:
            agent_definition = get_project_sub_agent_by_name(agent_type, workspace)
        else:
            agent_definition = get_project_sub_agent_by_name(
                agent_type,
                workspace,
                directory_key=workspace_directory_key,
            )
        if agent_definition is None:
            return {
                "status": "failed",
                "error": {
                    "type": "unknown_agent_type",
                    "message": f"No project sub-agent named '{agent_type}' is loaded.",
                },
            }

    agent_model_profile_id = (
        getattr(agent_definition, "model_profile_id", None)
        if agent_definition is not None
        else None
    )
    agent_declares_tool_availability = _agent_definition_declares_tool_availability(
        agent_definition
    )
    from pbi_agent.agent.names import pick_deity_name

    child_name = (
        agent_definition.name if agent_definition is not None else pick_deity_name()
    )
    child_display: DisplayProtocol | None = None
    child_tracer: RunTracer | None = None
    child_session_usage: TokenUsage | None = None
    child_turn_usage: TokenUsage | None = None
    started_at = time.monotonic()
    request_count = 0

    try:
        child_provider_id: str | None = None
        child_profile_id: str | None = None
        if agent_model_profile_id:
            child_runtime = resolve_runtime_for_profile_id(
                agent_model_profile_id,
                verbose=settings.verbose,
            )
            child_settings = child_runtime.settings
            child_provider_id = child_runtime.provider_id
            child_profile_id = child_runtime.profile_id
            if (
                parent_tool_availability_overridden
                and not agent_declares_tool_availability
            ):
                child_settings = _settings_with_tool_availability(
                    child_settings,
                    allowed_tools=settings.allowed_tools,
                )
        else:
            child_settings = replace(
                settings,
                model=_selected_sub_agent_model(settings),
            )
        if agent_declares_tool_availability:
            child_settings = _settings_with_tool_availability(
                child_settings,
                allowed_tools=getattr(agent_definition, "allowed_tools", None),
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
        child_tracer = (
            parent_tracer.child(
                agent_name=child_name,
                agent_type=agent_type or "default",
                provider=child_settings.provider,
                provider_id=child_provider_id,
                profile_id=child_profile_id,
                model=_selected_model(child_settings),
                metadata={
                    **_run_reasoning_metadata(child_settings),
                    "include_context": include_context,
                },
            )
            if parent_tracer is not None
            else RunTracer.start(
                store=None,
                session_id=None,
                agent_name=child_name,
                agent_type=agent_type or "default",
                provider=child_settings.provider,
                provider_id=child_provider_id,
                profile_id=child_profile_id,
                model=_selected_model(child_settings),
                metadata={"include_context": include_context},
            )
        )
        child_display.session_usage(child_session_usage)
        with _open_runtime_provider(
            child_settings,
            system_prompt=get_sub_agent_system_prompt(
                agent_prompt_override=(
                    agent_definition.system_prompt
                    if agent_definition is not None
                    else None
                ),
                settings=child_settings,
                excluded_tools=SUB_AGENT_DISABLED_TOOLS,
                cwd=workspace,
                explicit_skill_names=extract_explicit_skill_names(task_instruction),
                workspace_directory_key=workspace_directory_key,
            ),
            excluded_tools=SUB_AGENT_DISABLED_TOOLS,
            tool_catalog=tool_catalog,
            workspace_root=workspace,
            workspace_directory_key=workspace_directory_key,
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
            child_display.render_user_message(child_user_message)
            _raise_if_sub_agent_timed_out(started_at)
            response = provider.request_turn(
                user_message=child_user_message,
                display=child_display,
                session_usage=child_session_usage,
                turn_usage=child_turn_usage,
                tracer=child_tracer,
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
                tracer=child_tracer,
            )
            elapsed = time.monotonic() - started_at
            child_display.turn_usage(child_turn_usage, elapsed)
            child_display.finish_sub_agent(status="completed")
            child_tracer.finish(
                status="completed",
                usage=child_session_usage,
                metadata={"tool_errors": had_tool_errors},
            )
            return {
                "status": "completed",
                "final_output": response.text,
            }
    except SubAgentRunError as exc:
        child_display = child_display or display.begin_sub_agent(
            task_instruction=task_instruction,
            reasoning_effort=settings.reasoning_effort,
            name=child_name,
        )
        _fallback_tier = settings.service_tier or ""
        child_session_usage = child_session_usage or TokenUsage(
            model=_selected_model(settings), service_tier=_fallback_tier
        )
        child_turn_usage = child_turn_usage or TokenUsage(
            model=_selected_model(settings), service_tier=_fallback_tier
        )
        child_tracer = child_tracer or RunTracer.start(
            store=None,
            session_id=None,
            agent_name=child_name,
            agent_type=agent_type or "default",
            provider=settings.provider,
            provider_id=None,
            profile_id=None,
            model=_selected_model(settings),
            metadata={"include_context": include_context},
        )
        child_display.error(exc.message)
        child_display.finish_sub_agent(status="failed")
        child_tracer.log_error(exc.message, metadata={"phase": "run_sub_agent_task"})
        child_tracer.finish(
            status="failed",
            usage=child_session_usage,
            metadata={"error_message": exc.message},
        )
        return {
            "status": "failed",
            "error": {"type": exc.error_type, "message": exc.message},
        }
    except Exception as exc:
        message = str(exc) or exc.__class__.__name__
        child_display = child_display or display.begin_sub_agent(
            task_instruction=task_instruction,
            reasoning_effort=settings.reasoning_effort,
            name=child_name,
        )
        _fallback_tier = settings.service_tier or ""
        child_session_usage = child_session_usage or TokenUsage(
            model=_selected_model(settings), service_tier=_fallback_tier
        )
        child_turn_usage = child_turn_usage or TokenUsage(
            model=_selected_model(settings), service_tier=_fallback_tier
        )
        child_tracer = child_tracer or RunTracer.start(
            store=None,
            session_id=None,
            agent_name=child_name,
            agent_type=agent_type or "default",
            provider=settings.provider,
            provider_id=None,
            profile_id=None,
            model=_selected_model(settings),
            metadata={"include_context": include_context},
        )
        child_display.error(message)
        child_display.finish_sub_agent(status="failed")
        child_tracer.log_error(message, metadata={"phase": "run_sub_agent_task"})
        child_tracer.finish(
            status="failed",
            usage=child_session_usage,
            metadata={"error_message": message},
        )
        return {
            "status": "failed",
            "error": {"type": "sub_agent_failed", "message": message},
        }
    finally:
        if child_session_usage is not None:
            parent_session_usage.add_sub_agent(child_session_usage)
        if child_turn_usage is not None:
            parent_turn_usage.add_sub_agent(child_turn_usage)
        if child_session_usage is not None or child_turn_usage is not None:
            display.session_usage(parent_session_usage)


@contextmanager
def _open_runtime_provider(
    settings: Settings | ResolvedRuntime,
    *,
    system_prompt: str | None = None,
    excluded_tools: set[str] | None = None,
    tool_catalog: "ToolCatalog | None" = None,
    tool_availability_overridden: bool | None = None,
    workspace_root: Path | None = None,
    workspace_directory_key: str | None = None,
    explicit_agent_names: set[str] | None = None,
):
    from pbi_agent.mcp import McpServerPool

    runtime = _coerce_runtime(settings)
    runtime_settings = runtime.settings
    workspace = (workspace_root or Path.cwd()).resolve()
    explicit_agent_names = explicit_agent_names or set()
    explicit_agent_token = set_active_explicit_agent_names(explicit_agent_names)
    active_system_prompt = system_prompt or get_system_prompt(
        settings=runtime_settings,
        excluded_tools=excluded_tools,
        cwd=workspace,
        explicit_agent_names=explicit_agent_names,
        workspace_directory_key=workspace_directory_key,
    )
    effective_tool_availability_overridden = (
        runtime.tool_availability_overridden
        if tool_availability_overridden is None
        else tool_availability_overridden
    )
    try:
        if tool_catalog is not None:
            provider = create_provider(
                runtime_settings,
                system_prompt=active_system_prompt,
                excluded_tools=excluded_tools,
                tool_catalog=tool_catalog,
            )
            setattr(provider, "_workspace_root", workspace)
            setattr(provider, "_workspace_directory_key", workspace_directory_key)
            _set_provider_tool_availability_overridden(
                provider, effective_tool_availability_overridden
            )
            with provider:
                yield provider
        else:
            with McpServerPool(workspace) as mcp_pool:
                mcp_tool_catalog = mcp_pool.to_tool_catalog(
                    directory_key=workspace_directory_key,
                )
                mcp_tool_names = frozenset(mcp_tool_catalog.names())
                mcp_tool_names_token = _ACTIVE_MCP_TOOL_NAMES.set(mcp_tool_names)
                workspace_key = _mcp_workspace_key(workspace)
                with _ACTIVE_MCP_TOOL_NAMES_LOCK:
                    _ACTIVE_MCP_TOOL_NAMES_BY_WORKSPACE[workspace_key] = (
                        *_ACTIVE_MCP_TOOL_NAMES_BY_WORKSPACE.get(workspace_key, ()),
                        mcp_tool_names,
                    )
                tool_catalog, _extension_diagnostics = tool_catalog_with_extensions(
                    mcp_tool_catalog,
                    workspace,
                    reserved_names=lambda: _reserved_slash_extension_names(workspace),
                )
                try:
                    provider = create_provider(
                        runtime_settings,
                        system_prompt=active_system_prompt,
                        excluded_tools=excluded_tools,
                        tool_catalog=tool_catalog,
                    )
                    setattr(provider, "_workspace_root", workspace)
                    setattr(
                        provider, "_workspace_directory_key", workspace_directory_key
                    )
                    _set_provider_tool_availability_overridden(
                        provider, effective_tool_availability_overridden
                    )
                    with provider:
                        yield provider
                finally:
                    with _ACTIVE_MCP_TOOL_NAMES_LOCK:
                        remaining_workspace_mcp_names = _remove_active_mcp_tool_names(
                            _ACTIVE_MCP_TOOL_NAMES_BY_WORKSPACE.get(workspace_key, ()),
                            mcp_tool_names,
                        )
                        if remaining_workspace_mcp_names:
                            _ACTIVE_MCP_TOOL_NAMES_BY_WORKSPACE[workspace_key] = (
                                remaining_workspace_mcp_names
                            )
                        else:
                            _ACTIVE_MCP_TOOL_NAMES_BY_WORKSPACE.pop(workspace_key, None)
                    _ACTIVE_MCP_TOOL_NAMES.reset(mcp_tool_names_token)
    finally:
        reset_active_explicit_agent_names(explicit_agent_token)


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
    instructions: str | None = None,
    tracer: RunTracer | None = None,
    current_turn_tool_exchanges: (
        list[tuple[list[ToolCall], list[dict[str, Any]]]] | None
    ) = None,
) -> tuple[CompletedResponse, bool, int]:
    had_errors = False
    tool_exchanges = current_turn_tool_exchanges
    if tool_exchanges is None:
        tool_exchanges = []

    while response.has_tool_calls:
        _raise_if_interrupted(display)
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
            if tracer is not None:
                tracer.log_event(
                    "agent_step_start",
                    metadata={
                        "step": "tool_iteration",
                        "tool_count": len(response.function_calls),
                    },
                )
            effective_max_workers = (
                1
                if any(call.name == "ask_user" for call in response.function_calls)
                else max_workers
            )
            tool_result_items, loop_errors = provider.execute_tool_calls(
                response,
                max_workers=effective_max_workers,
                display=display,
                session_usage=session_usage,
                turn_usage=turn_usage,
                sub_agent_depth=sub_agent_depth,
                parent_context=parent_context,
                tracer=tracer,
            )
            _raise_if_interrupted(display)
        except SessionTurnInterrupted:
            raise
        except Exception:
            _log.exception("Tool execution failed inside provider.execute_tool_calls")
            raise
        had_errors = had_errors or loop_errors
        if response.function_calls or tool_result_items:
            tool_exchanges.append(
                (list(response.function_calls), list(tool_result_items))
            )

        compacted_after_tools = False
        if (
            bool(tool_result_items)
            and store is not None
            and session_id is not None
            and _should_auto_compact(
                session_usage=session_usage,
                settings=provider.settings,
                store=store,
                session_id=session_id,
            )
        ):
            if _provider_has_server_side_compaction(provider):
                display.render_markdown(
                    "Context compaction is handled by the provider; "
                    "continuing with native tool results."
                )
            else:
                session_usage.context_tokens = _compact_live_session(
                    provider=provider,
                    store=store,
                    session_id=session_id,
                    runtime=_runtime_from_provider(provider),
                    display=display,
                    session_usage=session_usage,
                    reason="auto",
                    pending_tool_exchanges=tool_exchanges,
                )
                tool_exchanges.clear()
                display.session_usage(session_usage)
                compacted_after_tools = True

        if not tool_result_items:
            _log.debug("No tool_result_items returned; stopping tool loop")
            if tracer is not None:
                tracer.log_event(
                    "agent_step_end",
                    metadata={"step": "tool_iteration", "empty_result": True},
                )
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
            if compacted_after_tools:
                response = provider.request_turn(
                    user_message=_compaction_continuation_prompt(
                        current_user_turn_text
                    ),
                    instructions=instructions,
                    session_id=session_id,
                    display=display,
                    session_usage=session_usage,
                    turn_usage=turn_usage,
                    tracer=tracer,
                )
            else:
                response = provider.request_turn(
                    tool_result_items=tool_result_items,
                    instructions=instructions,
                    session_id=session_id,
                    display=display,
                    session_usage=session_usage,
                    turn_usage=turn_usage,
                    tracer=tracer,
                )
            _raise_if_interrupted(display)
            if tracer is not None:
                tracer.log_event(
                    "agent_step_end",
                    metadata={"step": "tool_iteration"},
                )
            request_count += 1
        except SessionTurnInterrupted:
            raise
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


open_runtime_provider = _open_runtime_provider


# ---------------------------------------------------------------------------
# Session store helpers (fail-safe: never crash the main loop)
# ---------------------------------------------------------------------------
