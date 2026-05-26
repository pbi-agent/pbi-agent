from __future__ import annotations

import json
import shlex
from pathlib import Path
from typing import Any

from pbi_agent.agent.system_prompt import get_system_prompt
from pbi_agent.config import Settings, list_command_configs
from pbi_agent.display.protocol import DisplayProtocol
from pbi_agent.media import load_workspace_image
from pbi_agent.models.messages import (
    CompletedResponse,
    ImageAttachment,
    TokenUsage,
    UserTurnInput,
)
from pbi_agent.observability import RunTracer
from pbi_agent.providers.base import Provider
from pbi_agent.session_store import SessionStore
from pbi_agent.tools.catalog import ToolCatalog

from pbi_agent.agent.session.shared import (
    COMPACT_COMMAND,
    INIT_COMMAND,
    TEMPORARY_LOCAL_COMMANDS,
    active_mcp_tool_names_by_workspace as _ACTIVE_MCP_TOOL_NAMES_BY_WORKSPACE,
    active_mcp_tool_names_context as _ACTIVE_MCP_TOOL_NAMES,
    active_mcp_tool_names_lock as _ACTIVE_MCP_TOOL_NAMES_LOCK,
    log as _log,
)


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
    workspace_root: Path | None = None,
) -> UserTurnInput:
    resolved_images = list(images or [])
    if image_paths:
        root = (workspace_root or Path.cwd()).resolve()
        resolved_images.extend(load_workspace_image(root, path) for path in image_paths)
    return UserTurnInput(text=text, images=resolved_images)


def _normalize_user_command(value: str) -> str:
    return " ".join(value.strip().lower().split())


def _parse_init_command_force(value: str) -> bool | None:
    try:
        parts = shlex.split(value)
    except ValueError:
        return None
    if not parts or parts[0].lower() != INIT_COMMAND:
        return None
    flags = {part.lower() for part in parts[1:]}
    if flags <= {"--force", "--overwrite"}:
        return bool(flags)
    return None


def active_mcp_tool_names(workspace: Path | None = None) -> set[str]:
    if workspace is None:
        return set(_ACTIVE_MCP_TOOL_NAMES.get())
    with _ACTIVE_MCP_TOOL_NAMES_LOCK:
        active: set[str] = set()
        for names in _ACTIVE_MCP_TOOL_NAMES_BY_WORKSPACE.get(
            _mcp_workspace_key(workspace), ()
        ):
            active.update(names)
        return active


def _mcp_workspace_key(workspace: Path) -> Path:
    return workspace.expanduser().resolve()


def _remove_active_mcp_tool_names(
    entries: tuple[frozenset[str], ...],
    target: frozenset[str],
) -> tuple[frozenset[str], ...]:
    remaining = list(entries)
    for index in range(len(remaining) - 1, -1, -1):
        if remaining[index] == target:
            del remaining[index]
            break
    return tuple(remaining)


def _reserved_slash_extension_names(workspace: Path | None = None) -> set[str]:
    root = (workspace or Path.cwd()).resolve()
    reserved = {
        command.lstrip("/") for command in TEMPORARY_LOCAL_COMMANDS | {COMPACT_COMMAND}
    }
    reserved.update(ToolCatalog.from_builtin_registry().names())
    reserved.update(active_mcp_tool_names(root))
    for command in list_command_configs(root):
        reserved.add(command.slash_alias.lstrip("/"))
    return reserved


def _reload_provider_initialization(
    provider: Provider,
    workspace: Path | None = None,
    *,
    workspace_directory_key: str | None = None,
) -> None:
    provider.set_system_prompt(
        get_system_prompt(
            settings=provider.settings,
            cwd=workspace,
            workspace_directory_key=workspace_directory_key,
        )
    )
    provider.refresh_tools()


def _format_extension_run_markdown(name: str, result: Any) -> str:
    lines = [f"# Extension `/{name}`"]
    if result.ok:
        lines.append("")
        lines.append("Completed.")
        lines.append("")
        lines.append("```json")
        lines.append(json.dumps(result.result or {}, indent=2, sort_keys=True))
        lines.append("```")
    else:
        error = result.error or {}
        lines.append("")
        lines.append(f"Failed: {error.get('message') or 'Extension failed.'}")
    if result.stdout:
        lines.extend(["", "## stdout", "```", result.stdout, "```"])
    if result.stderr:
        lines.extend(["", "## stderr", "```", result.stderr, "```"])
    return "\n".join(lines)


def _request_user_turn(
    *,
    provider: Any,
    user_input: UserTurnInput,
    session_id: str | None,
    instructions: str | None,
    display: DisplayProtocol,
    session_usage: TokenUsage,
    turn_usage: TokenUsage,
    tracer: RunTracer | None = None,
) -> CompletedResponse:
    return provider.request_turn(
        user_input=user_input,
        instructions=instructions,
        session_id=session_id,
        display=display,
        session_usage=session_usage,
        turn_usage=turn_usage,
        tracer=tracer,
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


close_store = _close_store
build_user_turn_input = _build_user_turn_input
normalize_user_command = _normalize_user_command
parse_init_command_force = _parse_init_command_force
mcp_workspace_key = _mcp_workspace_key
remove_active_mcp_tool_names = _remove_active_mcp_tool_names
reserved_slash_extension_names = _reserved_slash_extension_names
reload_provider_initialization = _reload_provider_initialization
format_extension_run_markdown = _format_extension_run_markdown
request_user_turn = _request_user_turn
user_turn_history_text = _user_turn_history_text
session_title_for_user_turn = _session_title_for_user_turn
