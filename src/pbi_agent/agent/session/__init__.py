from __future__ import annotations

from types import ModuleType
import sys

from pbi_agent.agent.session import (
    commands as session_commands,
    compaction as session_compaction,
    history as session_history,
    runtime as session_runtime,
    shared as session_shared,
    subagents as session_subagents,
)

_MODULES: tuple[ModuleType, ...] = (
    session_shared,
    session_runtime,
    session_history,
    session_compaction,
    session_subagents,
    session_commands,
)

for _module in _MODULES:
    for _name, _value in vars(_module).items():
        if not _name.startswith("__"):
            globals()[_name] = _value

run_session_loop = session_runtime.run_session_loop
run_single_turn = session_runtime.run_single_turn
run_sub_agent_task = session_runtime.run_sub_agent_task
_open_runtime_provider = session_runtime.open_runtime_provider

active_mcp_tool_names = session_commands.active_mcp_tool_names
_normalize_user_command = session_commands.normalize_user_command
_parse_init_command_force = session_commands.parse_init_command_force

_open_compaction_provider = session_compaction.open_compaction_provider

_resume_session = session_history.resume_session
_create_session = session_history.create_session

_runtime_from_settings = session_shared.runtime_from_settings

COMPACT_COMMAND = session_shared.COMPACT_COMMAND
COMPACTION_MARKER = session_shared.COMPACTION_MARKER
INIT_COMMAND = session_shared.INIT_COMMAND
INTERACTIVE_ONLY_TOOLS = session_shared.INTERACTIVE_ONLY_TOOLS
MCP_COMMAND = session_shared.MCP_COMMAND
NEW_SESSION_SENTINEL = session_shared.NEW_SESSION_SENTINEL
RELOAD_COMMAND = session_shared.RELOAD_COMMAND
SKILLS_COMMAND = session_shared.SKILLS_COMMAND
TEMPORARY_LOCAL_COMMANDS = session_shared.TEMPORARY_LOCAL_COMMANDS
AGENTS_COMMAND = session_shared.AGENTS_COMMAND
HOOKS_COMMAND = session_shared.HOOKS_COMMAND
SessionTurnInterrupted = session_shared.SessionTurnInterrupted

_ALIAS_TARGETS = {
    "_open_runtime_provider": ("open_runtime_provider",),
    "open_runtime_provider": ("_open_runtime_provider",),
    "_open_compaction_provider": ("open_compaction_provider",),
    "open_compaction_provider": ("_open_compaction_provider",),
}


class _SessionFacadeModule(ModuleType):
    def __setattr__(self, name: str, value: object) -> None:
        super().__setattr__(name, value)
        propagated_names = (name, *_ALIAS_TARGETS.get(name, ()))
        for propagated_name in propagated_names[1:]:
            super().__setattr__(propagated_name, value)
        for module in _MODULES:
            for propagated_name in propagated_names:
                if hasattr(module, propagated_name):
                    setattr(module, propagated_name, value)


sys.modules[__name__].__class__ = _SessionFacadeModule

del _module, _name, _value
