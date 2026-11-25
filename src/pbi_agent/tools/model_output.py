"""Token-efficient, provider-agnostic rendering of tool results for the model.

Tool handlers return structured payloads (kept for display, tracing and hooks).
The model sees the plain text produced here instead of a JSON envelope: no
escaped newlines/quotes, and fields are printed only when they carry
information.
"""

from __future__ import annotations

import json
from typing import Any

from pbi_agent.tools.types import ToolSpec

_WALL_TIME_THRESHOLD_MS = 1000


def render_error(error_type: str, message: str) -> str:
    """Render a harness-level tool error (disabled/unknown tool, hook block...)."""
    return f"error {error_type}: {message}"


def render_tool_output(
    payload: Any,
    *,
    spec: ToolSpec | None = None,
    is_error: bool = False,
) -> str:
    """Render a tool handler payload as model-facing text."""
    renderer = spec.render_output if spec is not None else None
    text = renderer(payload) if renderer is not None else render_generic(payload)
    if is_error and not text.startswith("error"):
        return f"error: {text}" if "\n" not in text else f"error\n{text}"
    return text


def render_generic(payload: Any) -> str:
    """Render any JSON-like payload compactly.

    Strings pass through; dicts become ``key: value`` lines (empty values
    skipped, nested values as compact JSON); lists of records become one
    compact JSON object per line.
    """
    if isinstance(payload, str):
        return payload
    if payload is None:
        return "ok"
    if isinstance(payload, dict):
        return _render_mapping(payload)
    if isinstance(payload, list):
        if not payload:
            return "(none)"
        return "\n".join(
            item if isinstance(item, str) else compact_json(item) for item in payload
        )
    return compact_json(payload)


def _render_mapping(payload: dict[str, Any]) -> str:
    lines: list[str] = []
    for key, value in payload.items():
        if _is_empty(value):
            continue
        if isinstance(value, str):
            if "\n" in value:
                lines.append(f"{key}:\n{value}")
            else:
                lines.append(f"{key}: {value}")
        elif isinstance(value, bool):
            lines.append(f"{key}: true")
        elif isinstance(value, (int, float)):
            lines.append(f"{key}: {value}")
        elif (
            isinstance(value, list)
            and value
            and all(isinstance(item, dict) for item in value)
        ):
            lines.append(f"{key}:")
            lines.extend(compact_json(item) for item in value)
        else:
            lines.append(f"{key}: {compact_json(value)}")
    if lines:
        return "\n".join(lines)
    # Only empty/false values: keep them visible instead of claiming success.
    return compact_json(payload) if payload else "ok"


def _is_empty(value: Any) -> bool:
    return value is None or value is False or value == "" or value in ([], {})


def compact_json(value: Any) -> str:
    return json.dumps(value, separators=(",", ":"), ensure_ascii=False, default=str)


# ---------------------------------------------------------------------------
# Shell-shaped payloads (foreground shell, background task reads/results)
# ---------------------------------------------------------------------------


def format_seconds(duration_ms: int | float) -> str:
    return f"{duration_ms / 1000:.1f}s"


def shell_status_line(payload: dict[str, Any]) -> str:
    """Return the one-line status header for a shell-shaped payload."""
    duration_ms = payload.get("duration_ms")
    elapsed = payload.get("elapsed_seconds")
    if not isinstance(duration_ms, (int, float)) and isinstance(elapsed, (int, float)):
        duration_ms = elapsed * 1000
    status = payload.get("status")
    task_id = payload.get("task_id")
    if payload.get("interrupted"):
        head = "interrupted"
    elif payload.get("timed_out"):
        head = "timeout"
        if isinstance(duration_ms, (int, float)):
            return f"{head} {format_seconds(duration_ms)}"
    elif status == "running" and task_id:
        head = f"background {task_id}"
    elif status in {"killed", "timed_out"}:
        head = "killed" if status == "killed" else "timeout"
    elif payload.get("exit_code") is not None:
        head = f"exit {payload['exit_code']}"
    elif status:
        head = str(status)
    else:
        head = "done"
    if task_id and not head.startswith("background"):
        head = f"{task_id} {head}"
    if isinstance(duration_ms, (int, float)) and duration_ms >= _WALL_TIME_THRESHOLD_MS:
        head = f"{head} · {format_seconds(duration_ms)}"
    return head


def shell_output_tags(payload: dict[str, Any]) -> str | None:
    """Return the one-line ``[...]`` notice for lossy or partial output."""
    tags: list[str] = []
    if payload.get("stdout_compressed") or payload.get("stderr_compressed"):
        tags.append("compressed")
    if payload.get("stdout_truncated") or payload.get("stderr_truncated"):
        tags.append("truncated")
    if payload.get("stdout_middle_dropped") or payload.get("stderr_middle_dropped"):
        tags.append("middle dropped")
    earlier = payload.get("earlier_chars")
    if isinstance(earlier, int) and earlier > 0:
        tags.append(f"{earlier} earlier chars already shown")
    raw_path = payload.get("raw_output_path")
    if raw_path:
        tags.append(f"full: {raw_path}")
    elif (
        tags
        and payload.get("status") == "running"
        and ("compressed" in tags or "truncated" in tags)
    ):
        tags.append("full output saved when the task finishes")
    if not tags:
        return None
    return f"[{'; '.join(tags)}]"


def render_shell_output(payload: Any) -> str:
    """Render a shell-shaped payload: status line, stdout, stderr, notice."""
    if not isinstance(payload, dict):
        return render_generic(payload)
    has_streams = "stdout" in payload or "stderr" in payload
    error = payload.get("error")
    if not has_streams and "exit_code" not in payload and "status" not in payload:
        if isinstance(error, str) and error:
            return f"error: {error}"
        return render_generic(payload)

    lines = [shell_status_line(payload)]
    if (
        isinstance(error, str)
        and error
        and not payload.get("timed_out")
        and not payload.get("interrupted")
    ):
        lines.append(f"error: {error}")
    handoff_error = payload.get("handoff_error")
    if isinstance(handoff_error, str) and handoff_error:
        lines.append(f"killed, not moved to background: {handoff_error}")
    stdout = str(payload.get("stdout") or "")
    stderr = str(payload.get("stderr") or "")
    if stdout:
        lines.append(stdout.rstrip("\n"))
    if stderr:
        lines.append("[stderr]")
        lines.append(stderr.rstrip("\n"))
    if has_streams and not stdout and not stderr:
        lines.append("(no output)")
    tags = shell_output_tags(payload)
    if tags:
        lines.append(tags)
    return "\n".join(lines)


def render_sub_agent_output(payload: Any) -> str:
    """Render a sub-agent result: the final answer only, or a terse status."""
    if not isinstance(payload, dict):
        return render_generic(payload)
    status = payload.get("status")
    if status == "completed" and isinstance(payload.get("final_output"), str):
        return payload["final_output"] or "(no output)"
    if status == "running" and payload.get("task_id"):
        return f"background {payload['task_id']}"
    error = payload.get("error")
    if isinstance(error, dict):
        return render_error(
            str(error.get("type") or "error"), str(error.get("message") or "")
        )
    if isinstance(error, str) and error:
        return f"error: {error}"
    return render_generic(payload)


def render_background_task_output(payload: Any) -> str:
    """Render ``background_task`` results (list, status, output, input, kill)."""
    if not isinstance(payload, dict):
        return render_generic(payload)
    tasks = payload.get("tasks")
    if isinstance(tasks, list):
        if not tasks:
            return "(no background tasks)"
        return "\n".join(_background_task_line(task) for task in tasks)
    if "task_id" in payload and "status" in payload:
        if payload.get("kill_requested") and payload["status"] == "running":
            return f"kill requested {payload['task_id']}"
        if payload.get("kind") == "sub_agent" and "stdout" not in payload:
            return _background_task_line(payload)
        return render_shell_output(payload)
    return render_shell_output(payload)


def _background_task_line(task: Any) -> str:
    if not isinstance(task, dict):
        return compact_json(task)
    line = shell_status_line(task)
    label = task.get("intent") or task.get("command")
    if task.get("kind") == "sub_agent":
        line = f"{line} sub_agent"
    return f"{line} — {label}" if label else line
