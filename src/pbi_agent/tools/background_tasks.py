"""Background shell task manager.

Runs shell commands detached from the current tool call, keeps bounded
output tails, and reports completion through a callback so the owning
session can deliver results (checkpoint steering or idle wake-up).
"""

from __future__ import annotations

import os
import subprocess
import threading
import time
import uuid
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal, cast

BackgroundTaskStatus = Literal["running", "completed", "failed", "killed", "timed_out"]
BackgroundTaskKind = Literal["shell", "sub_agent"]

DEFAULT_BACKGROUND_TIMEOUT_MS = 30 * 60 * 1000
MAX_BACKGROUND_TIMEOUT_MS = 2 * 60 * 60 * 1000
MAX_CONCURRENT_BACKGROUND_TASKS = 4
TAIL_MAX_CHARS = 64_000
_READ_CHUNK = 4096


@dataclass(slots=True)
class _StreamTail:
    chunks: deque[str] = field(default_factory=deque)
    size: int = 0
    dropped: bool = False

    def append(self, text: str) -> None:
        if not text:
            return
        if len(text) > TAIL_MAX_CHARS:
            # Keep the tail of an oversized chunk instead of discarding it whole.
            text = text[-TAIL_MAX_CHARS:]
            self.chunks.clear()
            self.size = 0
            self.dropped = True
        self.chunks.append(text)
        self.size += len(text)
        while self.size > TAIL_MAX_CHARS and self.chunks:
            removed = self.chunks.popleft()
            self.size -= len(removed)
            self.dropped = True

    def text(self) -> str:
        return "".join(self.chunks)


@dataclass(slots=True)
class BackgroundTask:
    task_id: str
    command: str
    working_directory: str
    tool_call_id: str | None
    timeout_ms: int
    compression: bool
    started_at: float
    status: BackgroundTaskStatus = "running"
    ended_at: float | None = None
    exit_code: int | None = None
    process: subprocess.Popen[bytes] | None = field(default=None, repr=False)
    stdout: _StreamTail = field(default_factory=_StreamTail, repr=False)
    stderr: _StreamTail = field(default_factory=_StreamTail, repr=False)
    kill_reason: BackgroundTaskStatus | None = None
    intent: str = ""
    kind: BackgroundTaskKind = "shell"
    sub_agent_id: str | None = None
    cancel_event: threading.Event | None = field(default=None, repr=False)
    raw_output_path: Path | None = field(default=None, repr=False)

    def summary(self) -> dict[str, Any]:
        end = self.ended_at if self.ended_at is not None else time.time()
        return {
            "task_id": self.task_id,
            "command": self.command,
            "intent": self.intent,
            "kind": self.kind,
            "sub_agent_id": self.sub_agent_id,
            "working_directory": self.working_directory,
            "tool_call_id": self.tool_call_id,
            "status": self.status,
            "exit_code": self.exit_code,
            "started_at": self.started_at,
            "ended_at": self.ended_at,
            "elapsed_seconds": round(max(0.0, end - self.started_at), 1),
        }


FinishedCallback = Callable[[BackgroundTask], None]
SubAgentRunner = Callable[
    [threading.Event, Callable[[str | None], None]], dict[str, Any]
]
ChangedCallback = Callable[[], None]


class BackgroundTaskManager:
    """Owns background processes for one session."""

    def __init__(
        self,
        *,
        on_finished: FinishedCallback | None = None,
        on_changed: ChangedCallback | None = None,
        max_concurrent: int = MAX_CONCURRENT_BACKGROUND_TASKS,
    ) -> None:
        self._tasks: dict[str, BackgroundTask] = {}
        self._lock = threading.Lock()
        self._on_finished = on_finished
        self._on_changed = on_changed
        self._max_concurrent = max_concurrent
        self._closed = False

    # -- lifecycle -----------------------------------------------------

    def start(
        self,
        command: str,
        *,
        display_command: str,
        intent: str = "",
        working_directory: str,
        shell_executable: str | None,
        timeout_ms: int,
        compression: bool,
        tool_call_id: str | None,
    ) -> BackgroundTask:
        with self._lock:
            if self._closed:
                raise RuntimeError("Background tasks are no longer accepted.")
            running = sum(1 for t in self._tasks.values() if t.status == "running")
            if running >= self._max_concurrent:
                raise RuntimeError(
                    f"Too many background tasks running ({running}/"
                    f"{self._max_concurrent}). Kill or wait for one first."
                )
            task = BackgroundTask(
                task_id=f"bg-{uuid.uuid4().hex[:8]}",
                command=display_command,
                intent=intent,
                working_directory=working_directory,
                tool_call_id=tool_call_id,
                timeout_ms=timeout_ms,
                compression=compression,
                started_at=time.time(),
            )
            popen_kwargs: dict[str, Any] = {}
            if os.name == "nt":
                popen_kwargs["creationflags"] = getattr(
                    subprocess, "CREATE_NEW_PROCESS_GROUP", 0
                )
            else:
                popen_kwargs["start_new_session"] = True
            task.process = cast(
                subprocess.Popen[bytes],
                subprocess.Popen(
                    command,
                    cwd=working_directory,
                    stdin=subprocess.DEVNULL,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=False,
                    shell=True,
                    executable=shell_executable,
                    **popen_kwargs,
                ),
            )
            self._tasks[task.task_id] = task
        threading.Thread(
            target=self._watch,
            args=(task,),
            daemon=True,
            name=f"pbi-agent-bg-{task.task_id}",
        ).start()
        self._notify_changed()
        return task

    def start_sub_agent(
        self,
        run: SubAgentRunner,
        *,
        task_instruction: str,
        intent: str,
        working_directory: str,
        timeout_ms: int,
        tool_call_id: str | None,
    ) -> BackgroundTask:
        """Run a sub-agent callable in a background thread."""
        with self._lock:
            if self._closed:
                raise RuntimeError("Background tasks are no longer accepted.")
            running = sum(1 for t in self._tasks.values() if t.status == "running")
            if running >= self._max_concurrent:
                raise RuntimeError(
                    f"Too many background tasks running ({running}/"
                    f"{self._max_concurrent}). Kill or wait for one first."
                )
            task = BackgroundTask(
                task_id=f"bg-{uuid.uuid4().hex[:8]}",
                command=task_instruction,
                intent=intent,
                working_directory=working_directory,
                tool_call_id=tool_call_id,
                timeout_ms=timeout_ms,
                compression=False,
                started_at=time.time(),
                kind="sub_agent",
                cancel_event=threading.Event(),
            )
            self._tasks[task.task_id] = task
        threading.Thread(
            target=self._watch_sub_agent,
            args=(task, run),
            daemon=True,
            name=f"pbi-agent-bg-{task.task_id}",
        ).start()
        self._notify_changed()
        return task

    def kill(self, task_id: str) -> BackgroundTask:
        task = self.get(task_id)
        if task is None:
            raise KeyError(task_id)
        self._terminate(task, reason="killed")
        return task

    def close(self) -> None:
        """Stop accepting tasks and kill every running process."""
        with self._lock:
            self._closed = True
            tasks = list(self._tasks.values())
        for task in tasks:
            self._terminate(task, reason="killed")

    # -- queries -------------------------------------------------------

    def get(self, task_id: str) -> BackgroundTask | None:
        with self._lock:
            return self._tasks.get(task_id)

    def list(self) -> list[dict[str, Any]]:
        with self._lock:
            tasks = list(self._tasks.values())
        return [task.summary() for task in tasks]

    def running_count(self) -> int:
        with self._lock:
            return sum(1 for t in self._tasks.values() if t.status == "running")

    def output(self, task_id: str) -> dict[str, Any]:
        task = self.get(task_id)
        if task is None:
            raise KeyError(task_id)
        return {
            **task.summary(),
            "stdout": task.stdout.text(),
            "stderr": task.stderr.text(),
            "stdout_truncated": task.stdout.dropped,
            "stderr_truncated": task.stderr.dropped,
        }

    # -- internals -----------------------------------------------------

    def _terminate(self, task: BackgroundTask, *, reason: BackgroundTaskStatus) -> None:
        from pbi_agent.tools.shell import _kill_process_tree

        if task.kind == "sub_agent":
            if task.status == "running" and task.cancel_event is not None:
                task.kill_reason = reason
                task.cancel_event.set()
            return
        process = task.process
        if task.status != "running" or process is None or process.poll() is not None:
            return
        task.kill_reason = reason
        try:
            _kill_process_tree(process)
        except Exception:
            if process.poll() is None:
                process.kill()

    def _watch(self, task: BackgroundTask) -> None:
        process = task.process
        assert process is not None
        readers = [
            threading.Thread(
                target=_pump, args=(process.stdout, task.stdout), daemon=True
            ),
            threading.Thread(
                target=_pump, args=(process.stderr, task.stderr), daemon=True
            ),
        ]
        for reader in readers:
            reader.start()
        try:
            process.wait(timeout=task.timeout_ms / 1000.0)
        except subprocess.TimeoutExpired:
            self._terminate(task, reason="timed_out")
            try:
                process.wait(timeout=5.0)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()
        for reader in readers:
            reader.join(timeout=2.0)
        with self._lock:
            task.ended_at = time.time()
            task.exit_code = process.returncode
            if task.kill_reason is not None:
                task.status = task.kill_reason
                if task.kill_reason == "timed_out":
                    task.exit_code = None
            else:
                task.status = "completed" if process.returncode == 0 else "failed"
            closed = self._closed
        self._notify_changed()
        if self._on_finished is not None and not closed:
            try:
                self._on_finished(task)
            except Exception:
                pass

    def _watch_sub_agent(self, task: BackgroundTask, run: SubAgentRunner) -> None:
        assert task.cancel_event is not None
        cancel_event = task.cancel_event
        timer = threading.Timer(
            task.timeout_ms / 1000.0,
            lambda: self._terminate(task, reason="timed_out"),
        )
        timer.daemon = True
        timer.start()

        def on_started(sub_agent_id: str | None) -> None:
            if sub_agent_id:
                task.sub_agent_id = sub_agent_id
                self._notify_changed()

        try:
            result = run(cancel_event, on_started)
        except Exception as exc:  # pragma: no cover - defensive
            result = {
                "status": "failed",
                "error": {"type": "sub_agent_failed", "message": str(exc)},
            }
        finally:
            timer.cancel()
        final_output = result.get("final_output")
        if isinstance(final_output, str):
            task.stdout.append(final_output)
        error = result.get("error")
        if isinstance(error, dict) and error.get("message"):
            task.stderr.append(str(error["message"]))
        with self._lock:
            task.ended_at = time.time()
            if task.kill_reason is not None:
                task.status = task.kill_reason
            else:
                task.status = (
                    "completed" if result.get("status") == "completed" else "failed"
                )
            closed = self._closed
        self._notify_changed()
        if self._on_finished is not None and not closed:
            try:
                self._on_finished(task)
            except Exception:
                pass

    def _notify_changed(self) -> None:
        if self._on_changed is None:
            return
        try:
            self._on_changed()
        except Exception:
            pass


def _pump(stream: Any, tail: _StreamTail) -> None:
    from pbi_agent.tools.output import decode_output

    if stream is None:
        return
    try:
        while True:
            chunk = (
                stream.read1(_READ_CHUNK)
                if hasattr(stream, "read1")
                else stream.read(_READ_CHUNK)
            )
            if not chunk:
                return
            tail.append(decode_output(chunk))
    except (OSError, ValueError):
        return
    finally:
        try:
            stream.close()
        except Exception:
            pass


BACKGROUND_RESULT_TAG = "background_task_result"


def is_background_result_text(text: str) -> bool:
    """Return whether ``text`` is a synthetic background-result user input."""
    return text.lstrip().startswith(f"<{BACKGROUND_RESULT_TAG} ")


def render_background_result(task: BackgroundTask) -> str:
    """Render a finished task as a model-facing synthetic user input."""
    if task.kind == "sub_agent":
        return _render_sub_agent_result(task)
    payload = background_output_payload(
        task,
        stdout=task.stdout.text(),
        stderr=task.stderr.text(),
        stdout_dropped=task.stdout.dropped,
        stderr_dropped=task.stderr.dropped,
        compression=task.compression,
    )
    duration = task.summary()["elapsed_seconds"]
    exit_code = "none" if task.exit_code is None else str(task.exit_code)
    lines = [
        f'<{BACKGROUND_RESULT_TAG} task_id="{task.task_id}" status="{task.status}" '
        f'exit_code="{exit_code}" duration_seconds="{duration}">',
        *([f"intent: {task.intent}"] if task.intent else []),
        f"command: {task.command}",
    ]
    if payload.get("stdout_tail_dropped") or payload.get("stdout_truncated"):
        lines.append("stdout (truncated):")
    else:
        lines.append("stdout:")
    lines.append(payload["stdout"])
    if payload["stderr"]:
        lines.append("stderr:")
        lines.append(payload["stderr"])
    if payload.get("notice"):
        lines.append(payload["notice"])
    lines.append(f"</{BACKGROUND_RESULT_TAG}>")
    lines.append(
        "This background shell task you started has finished. Continue the task "
        "using this result."
    )
    return "\n".join(lines)


TAIL_DROPPED_NOTE = (
    f"Background output keeps only the last {TAIL_MAX_CHARS} chars per stream; "
    "earlier output was dropped and cannot be recovered."
)


def background_output_payload(
    task: BackgroundTask,
    *,
    stdout: str,
    stderr: str,
    stdout_dropped: bool,
    stderr_dropped: bool,
    compression: bool,
    status: BackgroundTaskStatus | None = None,
) -> dict[str, Any]:
    """Bound/compress a background task output snapshot for the model.

    ``stdout``/``stderr``, the ``*_dropped`` flags, and ``status`` (read before
    the text) must come from the same snapshot; ``status`` defaults to the
    task's current status. ``*_tail_dropped`` marks head loss in the retained tail, distinct
    from ``*_truncated`` (bounded for display). A raw output file is written
    only once a task has finished, then reused for later reads.
    """
    from pbi_agent.tools.raw_output import raw_output_notice, save_raw_output
    from pbi_agent.tools.shell import _build_output_payload

    payload = _build_output_payload(
        stdout=stdout, stderr=stderr, compression=compression, save_raw=False
    )
    if stdout_dropped:
        payload["stdout_tail_dropped"] = True
    if stderr_dropped:
        payload["stderr_tail_dropped"] = True
    compressed = bool(
        payload.get("stdout_compressed") or payload.get("stderr_compressed")
    )
    truncated = bool(payload.get("stdout_truncated") or payload.get("stderr_truncated"))
    tail_note = TAIL_DROPPED_NOTE if stdout_dropped or stderr_dropped else None
    if not (compressed or truncated):
        if tail_note:
            payload["notice"] = tail_note
        return payload
    if (status or task.status) == "running":
        notice = (
            "Output compressed or truncated. A raw output file is saved once the "
            "task finishes; read the task output again then."
        )
        payload["notice"] = f"{notice} {tail_note}" if tail_note else notice
        return payload
    if task.raw_output_path is None:
        task.raw_output_path = save_raw_output(stdout=stdout, stderr=stderr)
    if task.raw_output_path is not None:
        payload["raw_output_path"] = str(task.raw_output_path)
        payload["notice"] = raw_output_notice(
            task.raw_output_path,
            compressed=compressed,
            truncated=truncated,
            extra_note=tail_note,
        )
    elif tail_note:
        payload["notice"] = tail_note
    return payload


def _render_sub_agent_result(task: BackgroundTask) -> str:
    duration = task.summary()["elapsed_seconds"]
    lines = [
        f'<{BACKGROUND_RESULT_TAG} task_id="{task.task_id}" status="{task.status}" '
        f'exit_code="none" kind="sub_agent" duration_seconds="{duration}">',
        *([f"intent: {task.intent}"] if task.intent else []),
        "final_output:",
        task.stdout.text() or "(no output)",
    ]
    if task.stderr.text():
        lines.append("error:")
        lines.append(task.stderr.text())
    lines.append(f"</{BACKGROUND_RESULT_TAG}>")
    lines.append(
        "This background sub-agent you started has finished. Continue the task "
        "using this result."
    )
    return "\n".join(lines)
