"""``background_task`` tool - list, inspect, read, send input to, and kill tasks."""

from __future__ import annotations

from typing import Any

from pbi_agent.tools.background_tasks import read_task_output
from pbi_agent.tools.model_output import render_background_task_output
from pbi_agent.tools.shell import _background_manager
from pbi_agent.tools.types import ToolContext, ToolSpec

_ACTIONS = ("list", "status", "output", "input", "kill")
DEFAULT_INPUT_WAIT_MS = 1_000
MAX_INPUT_WAIT_MS = 30_000

SPEC = ToolSpec(
    name="background_task",
    description=(
        "Manage background tasks (started with `run_in_background` or moved "
        "there after `yield_time_ms`): list, status, read new output, send "
        "input to a `tty` task, or kill one."
    ),
    prompt_usage=(
        "Use `background_task` to list, inspect, read new output of, send "
        "input to, or kill background tasks; never to run commands. `output` "
        "and `input` return only output not shown yet."
    ),
    parameters_schema={
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": list(_ACTIONS),
                "description": (
                    "`list` all tasks, or `status`/`output`/`input`/`kill` one "
                    "task given by `task_id`."
                ),
            },
            "task_id": {
                "type": "string",
                "description": (
                    "Task id from `shell`/`sub_agent`. Required except for list."
                ),
            },
            "chars": {
                "type": "string",
                "description": (
                    "For `input`: text to type into the task's terminal (tasks "
                    "started with `tty: true`). Include `\\n` to press Enter; "
                    "`\\u0003` is Ctrl-C, `\\u0004` is Ctrl-D. Empty string "
                    "just waits for new output."
                ),
            },
            "wait_ms": {
                "type": "integer",
                "description": (
                    "For `input`: max wait for new output, in ms. Returns early "
                    "once output settles or the task exits. Default 1 000, "
                    "maximum 30 000."
                ),
            },
            "from_start": {
                "type": "boolean",
                "description": (
                    "For `output`: re-read all retained output instead of only "
                    "new output."
                ),
            },
        },
        "required": ["action"],
        "additionalProperties": False,
    },
    is_destructive=True,
    render_output=render_background_task_output,
)


def handle(arguments: dict[str, Any], context: ToolContext) -> dict[str, Any]:
    manager = _background_manager(context)
    if manager is None:
        return {"error": "Background tasks are not supported in this mode."}
    action = arguments.get("action")
    if action not in _ACTIONS:
        return {"error": f"'action' must be one of: {', '.join(_ACTIONS)}."}
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
    task = manager.get(task_id)
    if task is None:
        return {
            "error": (
                f"Unknown background task: {task_id}. Use action 'list' to see "
                "task ids."
            )
        }
    if action == "kill":
        return {**manager.kill(task_id).summary(), "kill_requested": True}
    if action == "status":
        return task.summary()
    if action == "input":
        chars = arguments.get("chars", "")
        if not isinstance(chars, str):
            return {"error": "'chars' must be a string."}
        try:
            wait_ms = _normalize_wait_ms(arguments.get("wait_ms"))
        except ValueError as exc:
            return {"error": str(exc)}
        if chars:
            try:
                manager.send_input(task_id, chars)
            except ValueError as exc:
                return {"error": str(exc)}
        manager.wait_for_output(task, wait_ms=wait_ms)
        return read_task_output(task)
    from_start = arguments.get("from_start", False)
    if not isinstance(from_start, bool):
        return {"error": "'from_start' must be a boolean."}
    return read_task_output(task, from_start=from_start)


def _normalize_wait_ms(raw: Any) -> int:
    if raw is None:
        return DEFAULT_INPUT_WAIT_MS
    if isinstance(raw, bool) or not isinstance(raw, int) or raw < 0:
        raise ValueError("'wait_ms' must be a non-negative integer.")
    return min(raw, MAX_INPUT_WAIT_MS)
