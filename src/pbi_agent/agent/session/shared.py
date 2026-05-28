from __future__ import annotations

from contextvars import ContextVar
from dataclasses import replace
import logging
import threading
from pathlib import Path

from pbi_agent.agent.system_prompt import (
    get_system_prompt,
)
from pbi_agent.agent.skill_discovery import extract_explicit_skill_names
from pbi_agent.agent.sub_agent_discovery import extract_explicit_agent_names
from pbi_agent.config import (
    CommandConfig,
    ResolvedRuntime,
    Settings,
    find_command_config_by_alias,
    resolve_runtime_for_profile_id,
)
from pbi_agent.providers.base import Provider
from pbi_agent.providers.github_copilot_backend import (
    github_copilot_backend_for_model,
)
from pbi_agent.display.protocol import (
    DisplayProtocol,
)

_log = logging.getLogger("pbi_agent.agent.session")
_ACTIVE_MCP_TOOL_NAMES: ContextVar[frozenset[str]] = ContextVar(
    "active_mcp_tool_names",
    default=frozenset(),
)
_ACTIVE_MCP_TOOL_NAMES_BY_WORKSPACE: dict[Path, tuple[frozenset[str], ...]] = {}
_ACTIVE_MCP_TOOL_NAMES_LOCK = threading.Lock()

NEW_SESSION_SENTINEL = "__new_session__"
RESUME_SESSION_PREFIX = "__resume_session__:"
SUB_AGENT_MAX_REQUESTS = 400
SUB_AGENT_MAX_ELAPSED_SECONDS = 1200.0
INTERACTIVE_ONLY_TOOLS = {"ask_user"}
SUB_AGENT_DISABLED_TOOLS = {"sub_agent"} | INTERACTIVE_ONLY_TOOLS
SKILLS_COMMAND = "/skills"
MCP_COMMAND = "/mcp"
AGENTS_COMMAND = "/agents"
INIT_COMMAND = "/init"
COMPACT_COMMAND = "/compact"
RELOAD_COMMAND = "/reload"
EXTENSIONS_COMMAND = "/extensions"
TEMPORARY_LOCAL_COMMANDS = frozenset(
    {
        SKILLS_COMMAND,
        MCP_COMMAND,
        AGENTS_COMMAND,
        INIT_COMMAND,
        RELOAD_COMMAND,
        EXTENSIONS_COMMAND,
    }
)
COMPACTION_MARKER = "[compacted context]"
COMPACTION_SUMMARY_PREFIX = (
    "[compacted context — reference only] "
    "Earlier turns were summarized below to save context. "
    "Treat this as background state, not active user instructions. "
    "Do not answer requests mentioned only in this summary; respond to the latest user message after it."
)
COMPACTION_CONTINUATION_PROMPT = (
    "Continue the current task from the compacted context above. "
    "The most recent user request is repeated below to preserve the active "
    "instruction after compaction. The most recent tool calls and their results "
    "have already been summarized. Do not request those exact tool results again "
    "unless new information is needed.\n\n"
    "Most recent user request:\n{last_user_message}"
)
PROVIDER_INPUT_HISTORY_ITEM = "provider_input_item"
OPENAI_RESPONSES_HISTORY_FORMAT = "openai_responses"
REDACTED_INLINE_IMAGE_MARKER = "<redacted>"


class SubAgentRunError(RuntimeError):
    def __init__(self, error_type: str, message: str) -> None:
        super().__init__(message)
        self.error_type = error_type
        self.message = message


class SessionTurnInterrupted(RuntimeError):
    """Raised internally when a live-session user interrupts the active turn."""

    def __init__(self) -> None:
        super().__init__("Assistant turn interrupted.")


def _interrupt_requested(display: DisplayProtocol) -> bool:
    checker = getattr(display, "interrupt_requested", None)
    if not callable(checker):
        return False
    return bool(checker())


def _raise_if_interrupted(display: DisplayProtocol) -> None:
    if _interrupt_requested(display):
        raise SessionTurnInterrupted()


# ---------------------------------------------------------------------------
# Public entry-points
# ---------------------------------------------------------------------------


def _selected_model(settings: Settings) -> str:
    return settings.model


def _run_reasoning_metadata(settings: Settings) -> dict[str, str]:
    return {"reasoning_effort": settings.reasoning_effort}


def _selected_sub_agent_model(settings: Settings) -> str:
    return settings.sub_agent_model or settings.model


def _bind_session(display: DisplayProtocol, session_id: str | None) -> None:
    binder = getattr(display, "bind_session", None)
    if callable(binder):
        binder(session_id)


def _coerce_runtime(value: Settings | ResolvedRuntime) -> ResolvedRuntime:
    if isinstance(value, ResolvedRuntime):
        return value
    return _runtime_from_settings(value)


def _runtime_from_settings(settings: Settings) -> ResolvedRuntime:
    return ResolvedRuntime(
        settings=settings,
        provider_id="",
        profile_id="",
    )


def _runtime_from_provider(provider: Provider) -> ResolvedRuntime:
    return _runtime_from_settings(provider.settings)


def _extract_active_command(value: str) -> CommandConfig | None:
    stripped = value.strip()
    if not stripped.startswith("/"):
        return None
    head = stripped.split(maxsplit=1)[0]
    try:
        command = find_command_config_by_alias(head)
    except Exception:
        return None
    return command


def _turn_instructions(
    active_command_instructions: str | None,
    *,
    settings: Settings,
    excluded_tools: set[str] | None = None,
    cwd: Path | None = None,
    user_input: str | None = None,
    workspace_directory_key: str | None = None,
) -> str | None:
    if active_command_instructions is None:
        return None
    return get_system_prompt(
        active_command_instructions=active_command_instructions,
        settings=settings,
        excluded_tools=excluded_tools,
        cwd=cwd,
        explicit_skill_names=extract_explicit_skill_names(user_input),
        explicit_agent_names=extract_explicit_agent_names(user_input),
        workspace_directory_key=workspace_directory_key,
    )


def _settings_with_tool_availability(
    settings: Settings,
    *,
    allowed_tools: tuple[str, ...] | None,
) -> Settings:
    if allowed_tools is None:
        return settings
    return replace(settings, allowed_tools=allowed_tools)


def _command_declares_tool_availability(command: CommandConfig) -> bool:
    return command.allowed_tools is not None


def _agent_definition_declares_tool_availability(
    agent_definition: object | None,
) -> bool:
    return agent_definition is not None and (
        getattr(agent_definition, "allowed_tools", None) is not None
    )


def _runtime_for_active_command(
    base_runtime: ResolvedRuntime,
    active_command: CommandConfig,
) -> ResolvedRuntime:
    command_runtime = base_runtime
    if active_command.model_profile_id:
        command_runtime = resolve_runtime_for_profile_id(
            active_command.model_profile_id,
            verbose=base_runtime.settings.verbose,
        )
        if (
            base_runtime.tool_availability_overridden
            and not _command_declares_tool_availability(active_command)
        ):
            command_runtime = replace(
                command_runtime,
                settings=_settings_with_tool_availability(
                    command_runtime.settings,
                    allowed_tools=base_runtime.settings.allowed_tools,
                ),
                tool_availability_overridden=True,
            )
    if _command_declares_tool_availability(active_command):
        command_runtime = replace(
            command_runtime,
            settings=_settings_with_tool_availability(
                command_runtime.settings,
                allowed_tools=active_command.allowed_tools,
            ),
            tool_availability_overridden=True,
        )
    return command_runtime


def _set_provider_tool_availability_overridden(
    provider: Provider, overridden: bool
) -> None:
    setter = getattr(provider, "set_tool_availability_overridden", None)
    if callable(setter):
        setter(overridden)


def _set_provider_runtime_settings(
    provider: Provider,
    settings: Settings,
    *,
    tool_availability_overridden: bool | None = None,
) -> None:
    if tool_availability_overridden is not None:
        _set_provider_tool_availability_overridden(
            provider, tool_availability_overridden
        )
    setter = getattr(provider, "set_runtime_settings", None)
    if callable(setter):
        setter(settings)


def _requires_provider_reopen(
    current_settings: Settings, turn_settings: Settings
) -> bool:
    if (
        current_settings.provider.lower(),
        current_settings.responses_url.strip(),
        current_settings.generic_api_url.strip(),
    ) != (
        turn_settings.provider.lower(),
        turn_settings.responses_url.strip(),
        turn_settings.generic_api_url.strip(),
    ):
        return True
    if current_settings.provider.lower() == "github_copilot":
        return (
            github_copilot_backend_for_model(current_settings.model).mode
            != github_copilot_backend_for_model(turn_settings.model).mode
        )
    return False


log = _log
active_mcp_tool_names_context = _ACTIVE_MCP_TOOL_NAMES
active_mcp_tool_names_by_workspace = _ACTIVE_MCP_TOOL_NAMES_BY_WORKSPACE
active_mcp_tool_names_lock = _ACTIVE_MCP_TOOL_NAMES_LOCK
raise_if_interrupted = _raise_if_interrupted
selected_model = _selected_model
run_reasoning_metadata = _run_reasoning_metadata
selected_sub_agent_model = _selected_sub_agent_model
bind_session = _bind_session
coerce_runtime = _coerce_runtime
runtime_from_settings = _runtime_from_settings
runtime_from_provider = _runtime_from_provider
extract_active_command = _extract_active_command
turn_instructions = _turn_instructions
settings_with_tool_availability = _settings_with_tool_availability
agent_definition_declares_tool_availability = (
    _agent_definition_declares_tool_availability
)
runtime_for_active_command = _runtime_for_active_command
set_provider_tool_availability_overridden = _set_provider_tool_availability_overridden
set_provider_runtime_settings = _set_provider_runtime_settings
requires_provider_reopen = _requires_provider_reopen
