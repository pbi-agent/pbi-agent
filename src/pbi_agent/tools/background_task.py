"""``background_task`` tool - list, inspect, read, and kill background shell tasks."""

from __future__ import annotations

from typing import Any

from pbi_agent.tools.shell import _background_manager, _build_output_payload
from pbi_agent.tools.types import ToolContext, ToolSpec

_ACTIONS = ("list", "status", "output", "kill")

SPEC = ToolSpec(
    name="background_task",
    description=(
        "Manage background shell tasks started with `shell` "
        "`run_in_background`: list them, check status, read output, or kill one."
    ),
    prompt_usage=(
        "Use `background_task` only to list, inspect, read output of, or kill "
        "tasks started by `shell` with `run_in_background`; never to run commands."
    ),
    parameters_schema={
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": list(_ACTIONS),
                "description": (
                    "`list` all tasks, or `status`/`output`/`kill` one task "
                    "given by `task_id`."
                ),
            },
            "task_id": {
                "type": "string",
                "description": (
                    "Task id returned by `shell` `run_in_background`. Required "
                    "for status, output, and kill; ignored for list."
                ),
            },
        },
        "required": ["action"],
        "additionalProperties": False,
    },
    is_destructive=True,
)


def handle(arguments: dict[str, Any], context: ToolContext) -> dict[str, Any]:
    if context.sub_agent_depth > 0:
        return {"error": "Background tasks are not available to sub-agents."}
    manager = _background_manager(context)
    if manager is None:
        return {"error": "Background tasks are not supported in this mode."}
    action = arguments.get("action")
    if action not in _ACTIONS:
        return {"error": "'action' must be one of: list, status, output, kill."}
    if action == "list":
        return {"tasks": manager.list()}
    raw_task_id = arguments.get("task_id")
    task_id = raw_task_id.strip() if isinstance(raw_task_id, str) else ""
    if not task_id:
        return {
            "error": (
                f"'task_id' is required for '{action}'. Use action 'list' to "
                "see task ids."
            )
        }
    try:
        if action == "kill":
            return {**manager.kill(task_id).summary(), "kill_requested": True}
        if action == "status":
            task = manager.get(task_id)
            if task is None:
                raise KeyError(task_id)
            return task.summary()
        data = manager.output(task_id)
    except KeyError:
        return {
            "error": (
                f"Unknown background task: {task_id}. Use action 'list' to see "
                "task ids."
            )
        }
    bounded = _build_output_payload(
        stdout=data.pop("stdout"), stderr=data.pop("stderr"), compression=False
    )
    return {**data, **bounded}
