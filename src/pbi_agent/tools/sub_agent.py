"""Delegated ``sub_agent`` tool."""

from __future__ import annotations

from typing import Any

from pbi_agent.agent.sub_agent_discovery import discover_project_sub_agents
from pbi_agent.tools.types import ToolContext, ToolSpec

_DEFAULT_AGENT_TYPE = "default"


def build_spec() -> ToolSpec:
    agent_type_values = [_DEFAULT_AGENT_TYPE]
    agent_type_values.extend(agent.name for agent in discover_project_sub_agents())

    return ToolSpec(
        name="sub_agent",
        description="Delegate a scoped task to a stateless child agent with the same tools.",
        parameters_schema={
            "type": "object",
            "properties": {
                "task_instruction": {
                    "type": "string",
                    "description": "The delegated task and any context the child agent needs.",
                },
                "agent_type": {
                    "type": "string",
                    "enum": agent_type_values,
                    "description": (
                        "Project sub-agent name to invoke. Use "
                        f"`{_DEFAULT_AGENT_TYPE}` for the built-in generalist sub-agent."
                    ),
                },
            },
            "required": ["task_instruction"],
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

    settings = context.settings
    display = context.display
    session_usage = context.session_usage
    turn_usage = context.turn_usage
    sub_agent_depth = context.sub_agent_depth
    tool_catalog = context.tool_catalog

    if sub_agent_depth > 0:
        return {
            "status": "failed",
            "error": {
                "type": "nested_sub_agent_disabled",
                "message": "Nested sub-agent runs are disabled in this version.",
            },
        }

    if any(value is None for value in (settings, display, session_usage, turn_usage)):
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
    )
