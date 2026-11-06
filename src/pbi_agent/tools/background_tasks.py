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
from typing import Any, Literal, cast

BackgroundTaskStatus = Literal["running", "completed", "failed", "killed", "timed_out"]

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

    def summary(self) -> dict[str, Any]:
        end = self.ended_at if self.ended_at is not None else time.time()
        return {
            "task_id": self.task_id,
            "command": self.command,
            "working_directory": self.working_directory,
            "tool_call_id": self.tool_call_id,
            "status": self.status,
            "exit_code": self.exit_code,
            "started_at": self.started_at,
            "ended_at": self.ended_at,
            "elapsed_seconds": round(max(0.0, end - self.started_at), 1),
        }


FinishedCallback = Callable[[BackgroundTask], None]
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


def render_background_result(task: BackgroundTask) -> str:
    """Render a finished task as a model-facing synthetic user input."""
    from pbi_agent.tools.shell import _build_output_payload

    payload = _build_output_payload(
        stdout=task.stdout.text(),
        stderr=task.stderr.text(),
        compression=task.compression,
    )
    duration = task.summary()["elapsed_seconds"]
    exit_code = "none" if task.exit_code is None else str(task.exit_code)
    lines = [
        f'<background_task_result task_id="{task.task_id}" status="{task.status}" '
        f'exit_code="{exit_code}" duration_seconds="{duration}">',
        f"command: {task.command}",
    ]
    if task.stdout.dropped or payload.get("stdout_truncated"):
        lines.append("stdout (truncated):")
    else:
        lines.append("stdout:")
    lines.append(payload["stdout"])
    if payload["stderr"]:
        lines.append("stderr:")
        lines.append(payload["stderr"])
    lines.append("</background_task_result>")
    lines.append(
        "This background shell task you started has finished. Continue the task "
        "using this result."
    )
    return "\n".join(lines)
