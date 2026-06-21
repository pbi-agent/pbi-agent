"""Delegated ``sub_agent`` tool."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from pbi_agent.agent.reference_resolution import resolve_sub_agent_references
from pbi_agent.agent.sub_agent_discovery import discover_project_sub_agents
from pbi_agent.tools.types import ToolContext, ToolSpec

_DEFAULT_AGENT_TYPE = "default"
_SUB_AGENT_MAX_DEPTH = 2


def visible_agent_type_values(
    workspace: Path | None = None,
    *,
    directory_key: str | None = None,
    visible_agent_names: tuple[str, ...] | None = None,
) -> tuple[str, ...]:
    if visible_agent_names is None:
        agent_type_values = [_DEFAULT_AGENT_TYPE]
        agent_type_values.extend(
            agent.name
            for agent in discover_project_sub_agents(
                workspace,
                directory_key=directory_key,
            )
        )
        return tuple(agent_type_values)

    resolved_agents = (
        resolve_sub_agent_references(
            visible_agent_names,
            workspace,
            directory_key=directory_key,
            strict=True,
            source_label="Command frontmatter",
        )
        or ()
    )
    return tuple(agent.name for agent in resolved_agents)


def build_spec(
    workspace: Path | None = None,
    *,
    directory_key: str | None = None,
    visible_agent_names: tuple[str, ...] | None = None,
    agent_type_values: tuple[str, ...] | None = None,
) -> ToolSpec:
    if agent_type_values is None:
        agent_type_values = visible_agent_type_values(
            workspace,
            directory_key=directory_key,
            visible_agent_names=visible_agent_names,
        )
    required = ["task_instruction"]
    if visible_agent_names is not None:
        required.append("agent_type")
    agent_type_description = (
        "Project sub-agent name to invoke. Use "
        f"`{_DEFAULT_AGENT_TYPE}` for the built-in generalist sub-agent."
    )
    if visible_agent_names is not None:
        agent_type_description = "Project sub-agent name to invoke."

    return ToolSpec(
        name="sub_agent",
        description=(
            "Delegate a scoped task to a child agent with the same tools. "
            "Set `include_context` to inherit the parent conversation context."
        ),
        prompt_usage=(
            "Use `sub_agent` only when the user requests delegation or a task "
            "benefits from isolated specialist work."
        ),
        parameters_schema={
            "type": "object",
            "properties": {
                "task_instruction": {
                    "type": "string",
                    "description": "The delegated task and any context the child agent needs.",
                },
                "include_context": {
                    "type": "boolean",
                    "description": (
                        "When true, the child agent inherits the parent "
                        "conversation context when supported by the provider."
                    ),
                },
                "agent_type": {
                    "type": "string",
                    "enum": list(agent_type_values),
                    "description": agent_type_description,
                },
            },
            "required": required,
            "additionalProperties": False,
        },
    )


SPEC = build_spec()


def handle(arguments: dict[str, Any], context: ToolContext) -> dict[str, Any]:
    task_instruction = arguments.get("task_instruction", "")
    if not isinstance(task_instruction, str) or not task_instruction.strip():
        return {
            "status": "failed",
            "error": {
                "type": "invalid_arguments",
                "message": "'task_instruction' must be a non-empty string.",
            },
        }

    agent_type = arguments.get("agent_type")
    if not isinstance(agent_type, str) or not agent_type.strip():
        agent_type = None
    else:
        agent_type = agent_type.strip()
        if agent_type == _DEFAULT_AGENT_TYPE:
            agent_type = None

    include_context = arguments.get("include_context", False)
    if not isinstance(include_context, bool):
        return {
            "status": "failed",
            "error": {
                "type": "invalid_arguments",
                "message": "'include_context' must be a boolean when provided.",
            },
        }

    settings = context.settings
    display = context.display
    session_usage = context.session_usage
    turn_usage = context.turn_usage
    sub_agent_depth = context.sub_agent_depth
    tool_catalog = context.tool_catalog
    parent_context = context.parent_context
    parent_tracer = context.tracer

    if sub_agent_depth >= _SUB_AGENT_MAX_DEPTH:
        return {
            "status": "failed",
            "error": {
                "type": "nested_sub_agent_depth_exceeded",
                "message": f"Nested sub-agent runs are limited to depth {_SUB_AGENT_MAX_DEPTH}.",
            },
        }

    allowed_agent_types = (
        context.tool_catalog.sub_agent_type_values()
        if context.tool_catalog is not None
        else ()
    )
    scoped_agent_types = bool(allowed_agent_types) and (
        _DEFAULT_AGENT_TYPE not in allowed_agent_types
    )
    if scoped_agent_types and (
        agent_type is None or agent_type not in allowed_agent_types
    ):
        return {
            "status": "failed",
            "error": {
                "type": "invalid_arguments",
                "message": (
                    "'agent_type' is required and must reference one of the "
                    "configured project sub-agents."
                ),
            },
        }

    if sub_agent_depth > 0:
        if (
            not allowed_agent_types
            or _DEFAULT_AGENT_TYPE in allowed_agent_types
            or agent_type is None
            or agent_type not in allowed_agent_types
        ):
            return {
                "status": "failed",
                "error": {
                    "type": "nested_sub_agent_disabled",
                    "message": (
                        "Nested sub-agent runs are disabled unless the current "
                        "project sub-agent frontmatter declares a scoped "
                        "'sub_agents' list."
                    ),
                },
            }

    if settings is None:
        return {
            "status": "failed",
            "error": {
                "type": "invalid_runtime_context",
                "message": "sub_agent requires runtime settings, display, session_usage, and turn_usage context.",
            },
        }
    if display is None:
        return {
            "status": "failed",
            "error": {
                "type": "invalid_runtime_context",
                "message": "sub_agent requires runtime settings, display, session_usage, and turn_usage context.",
            },
        }
    if session_usage is None:
        return {
            "status": "failed",
            "error": {
                "type": "invalid_runtime_context",
                "message": "sub_agent requires runtime settings, display, session_usage, and turn_usage context.",
            },
        }
    if turn_usage is None:
        return {
            "status": "failed",
            "error": {
                "type": "invalid_runtime_context",
                "message": "sub_agent requires runtime settings, display, session_usage, and turn_usage context.",
            },
        }

    from pbi_agent.agent.session import run_sub_agent_task

    return run_sub_agent_task(
        task_instruction.strip(),
        settings,
        display,
        parent_session_usage=session_usage,
        parent_turn_usage=turn_usage,
        sub_agent_depth=sub_agent_depth,
        tool_catalog=tool_catalog,
        agent_type=agent_type,
        include_context=include_context,
        parent_tool_availability_overridden=context.tool_availability_overridden,
        parent_context=parent_context,
        parent_tracer=parent_tracer,
        workspace_root=context.workspace_root,
        workspace_directory_key=context.workspace_directory_key,
    )
