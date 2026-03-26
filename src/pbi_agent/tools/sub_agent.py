"""Delegated ``sub_agent`` tool."""

from __future__ import annotations

from typing import Any

from pbi_agent.tools.types import ToolContext, ToolSpec

_REASONING_EFFORT_VALUES = ("low", "medium", "high")

SPEC = ToolSpec(
    name="sub_agent",
    description="Delegate a scoped task to a stateless child agent with the same tools.",
    parameters_schema={
        "type": "object",
        "properties": {
            "task_instruction": {
                "type": "string",
                "description": "The delegated task and any context the child agent needs.",
            },
            "reasoning_effort": {
                "type": "string",
                "enum": list(_REASONING_EFFORT_VALUES),
                "default": "low",
                "description": "Reasoning effort for the child agent. Defaults to low.",
            },
        },
        "required": ["task_instruction"],
        "additionalProperties": False,
    },
)


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

    reasoning_effort = arguments.get("reasoning_effort", "low")
    if (
        not isinstance(reasoning_effort, str)
        or reasoning_effort not in _REASONING_EFFORT_VALUES
    ):
        reasoning_effort = "low"

    settings = context.settings
    display = context.display
    session_usage = context.session_usage
    turn_usage = context.turn_usage
    sub_agent_depth = context.sub_agent_depth

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
        reasoning_effort=reasoning_effort,
        parent_session_usage=session_usage,
        parent_turn_usage=turn_usage,
        sub_agent_depth=sub_agent_depth,
    )
