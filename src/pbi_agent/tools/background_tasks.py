"""Background shell task manager.

Runs shell commands detached from the current tool call, keeps bounded
output tails, and reports completion through a callback so the owning
session can deliver results (checkpoint steering or idle wake-up).
"""

from __future__ import annotations

import codecs
import contextlib
import os
import re
import subprocess
import threading
import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal, cast

from pbi_agent.tools.stream_buffer import HEAD_MAX_CHARS, TAIL_MAX_CHARS, StreamBuffer

BackgroundTaskStatus = Literal["running", "completed", "failed", "killed", "timed_out"]
BackgroundTaskKind = Literal["shell", "sub_agent"]

DEFAULT_BACKGROUND_TIMEOUT_MS = 30 * 60 * 1000
MAX_BACKGROUND_TIMEOUT_MS = 2 * 60 * 60 * 1000
MAX_CONCURRENT_BACKGROUND_TASKS = 4
OUTPUT_SETTLE_MS = 300
_READ_CHUNK = 4096


TTY_UNSUPPORTED_ERROR = "'tty' is not supported on Windows yet."
_ANSI_ESCAPE_RE = re.compile(r"\x1b(?:\[[0-?]*[ -/]*[@-~]|\][^\x07]*\x07|[@-Z\\-_])")


class TerminalInput:
    """Owns a PTY master fd; safe to write to until closed (no fd reuse)."""

    def __init__(self, fd: int) -> None:
        self._fd: int | None = fd
        self._lock = threading.Lock()

    @property
    def fd(self) -> int | None:
        return self._fd

    def write(self, data: bytes) -> None:
        with self._lock:
            if self._fd is None:
                raise OSError("terminal is closed")
            view = memoryview(data)
            while view:
                written = os.write(self._fd, view)
                view = view[written:]

    def close(self) -> None:
        with self._lock:
            fd, self._fd = self._fd, None
        if fd is not None:
            with contextlib.suppress(OSError):
                os.close(fd)


@dataclass(slots=True)
class AttachedProcess:
    """A running shell process whose output is pumped into stream buffers.

    With ``tty`` the process runs under a pseudo-terminal: stdout and stderr
    are merged into ``stdout`` and input can be written to ``terminal``.
    """

    process: subprocess.Popen[bytes]
    stdout: StreamBuffer
    stderr: StreamBuffer
    readers: list[threading.Thread]
    started_monotonic: float = field(default_factory=time.monotonic)
    tty: bool = False
    terminal: TerminalInput | None = None

    def join_readers(self, timeout: float = 2.0) -> None:
        for reader in self.readers:
            reader.join(timeout=timeout)


def clean_tty_text(text: str) -> str:
    """Strip terminal escape sequences and carriage returns from PTY output."""
    text = _ANSI_ESCAPE_RE.sub("", text)
    return text.replace("\r\n", "\n").replace("\r", "\n")


def spawn_attached_process(
    command: str,
    *,
    working_directory: str,
    shell_executable: str | None,
    tty: bool = False,
) -> AttachedProcess:
    """Start ``command`` in its own process group.

    Without ``tty`` stdin is closed, so commands that prompt fail fast.
    """
    if tty:
        return _spawn_tty_process(
            command,
            working_directory=working_directory,
            shell_executable=shell_executable,
        )
    popen_kwargs: dict[str, Any] = {}
    if os.name == "nt":
        popen_kwargs["creationflags"] = getattr(
            subprocess, "CREATE_NEW_PROCESS_GROUP", 0
        )
    else:
        popen_kwargs["start_new_session"] = True
    process = cast(
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
    stdout = StreamBuffer()
    stderr = StreamBuffer()
    readers = [
        threading.Thread(target=_pump, args=(process.stdout, stdout), daemon=True),
        threading.Thread(target=_pump, args=(process.stderr, stderr), daemon=True),
    ]
    for reader in readers:
        reader.start()
    return AttachedProcess(
        process=process, stdout=stdout, stderr=stderr, readers=readers
    )


def _spawn_tty_process(
    command: str,
    *,
    working_directory: str,
    shell_executable: str | None,
) -> AttachedProcess:
    if os.name == "nt":
        raise OSError(TTY_UNSUPPORTED_ERROR)
    import pty

    master_fd, slave_fd = pty.openpty()
    env = dict(os.environ)
    # A dumb terminal keeps colors and cursor tricks out of model-facing output.
    env["TERM"] = "dumb"
    try:
        process = cast(
            subprocess.Popen[bytes],
            subprocess.Popen(
                command,
                cwd=working_directory,
                stdin=slave_fd,
                stdout=slave_fd,
                stderr=slave_fd,
                shell=True,
                executable=shell_executable,
                env=env,
                start_new_session=True,
                close_fds=True,
                preexec_fn=_acquire_controlling_terminal,
            ),
        )
    except BaseException:
        os.close(master_fd)
        raise
    finally:
        os.close(slave_fd)
    terminal = TerminalInput(master_fd)
    stdout = StreamBuffer()
    reader = threading.Thread(
        target=_pump_terminal, args=(terminal, stdout), daemon=True
    )
    reader.start()
    return AttachedProcess(
        process=process,
        stdout=stdout,
        stderr=StreamBuffer(),
        readers=[reader],
        tty=True,
        terminal=terminal,
    )


def _acquire_controlling_terminal() -> None:  # pragma: no cover - runs in child
    """Make the PTY (stdin) the child's controlling terminal.

    Runs after ``setsid`` (``start_new_session``), so Ctrl-C/Ctrl-Z written to
    the terminal reach the foreground process group as signals.
    """
    import fcntl
    import termios

    fcntl.ioctl(0, termios.TIOCSCTTY, 0)


def _pump_terminal(terminal: TerminalInput, buffer: StreamBuffer) -> None:
    decoder = codecs.getincrementaldecoder("utf-8")(errors="replace")
    try:
        while True:
            fd = terminal.fd
            if fd is None:
                return
            try:
                chunk = os.read(fd, _READ_CHUNK)
            except OSError:  # EIO once the terminal's last writer exits
                chunk = b""
            if not chunk:
                buffer.append(decoder.decode(b"", final=True))
                return
            buffer.append(decoder.decode(chunk))
    finally:
        terminal.close()


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
    stdout: StreamBuffer = field(default_factory=StreamBuffer, repr=False)
    stderr: StreamBuffer = field(default_factory=StreamBuffer, repr=False)
    readers: list[threading.Thread] = field(default_factory=list, repr=False)
    tty: bool = False
    terminal: TerminalInput | None = field(default=None, repr=False)
    # Characters of each stream the model has already been shown.
    stdout_cursor: int = 0
    stderr_cursor: int = 0
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
        tty: bool = False,
    ) -> BackgroundTask:
        with self._lock:
            self._check_capacity()
            attached = spawn_attached_process(
                command,
                working_directory=working_directory,
                shell_executable=shell_executable,
                tty=tty,
            )
            task = self._register(
                attached,
                display_command=display_command,
                intent=intent,
                working_directory=working_directory,
                timeout_ms=timeout_ms,
                compression=compression,
                tool_call_id=tool_call_id,
                started_at=time.time(),
            )
        self._start_watch(task)
        return task

    def adopt(
        self,
        attached: AttachedProcess,
        *,
        display_command: str,
        intent: str = "",
        working_directory: str,
        timeout_ms: int,
        compression: bool,
        tool_call_id: str | None,
    ) -> BackgroundTask:
        """Take over a running foreground process instead of killing it.

        The process keeps its stream buffers and reader threads, so no output
        is lost. ``timeout_ms`` counts from the original process start.
        """
        elapsed = time.monotonic() - attached.started_monotonic
        with self._lock:
            self._check_capacity()
            task = self._register(
                attached,
                display_command=display_command,
                intent=intent,
                working_directory=working_directory,
                timeout_ms=timeout_ms,
                compression=compression,
                tool_call_id=tool_call_id,
                started_at=time.time() - elapsed,
            )
        self._start_watch(task)
        return task

    def _check_capacity(self) -> None:
        if self._closed:
            raise RuntimeError("Background tasks are no longer accepted.")
        running = sum(1 for t in self._tasks.values() if t.status == "running")
        if running >= self._max_concurrent:
            raise RuntimeError(
                f"Too many background tasks running ({running}/"
                f"{self._max_concurrent}). Kill or wait for one first."
            )

    def _register(
        self,
        attached: AttachedProcess,
        *,
        display_command: str,
        intent: str,
        working_directory: str,
        timeout_ms: int,
        compression: bool,
        tool_call_id: str | None,
        started_at: float,
    ) -> BackgroundTask:
        task = BackgroundTask(
            task_id=f"bg-{uuid.uuid4().hex[:8]}",
            command=display_command,
            intent=intent,
            working_directory=working_directory,
            tool_call_id=tool_call_id,
            timeout_ms=timeout_ms,
            compression=compression,
            started_at=started_at,
            process=attached.process,
            stdout=attached.stdout,
            stderr=attached.stderr,
            readers=attached.readers,
            tty=attached.tty,
            terminal=attached.terminal,
        )
        self._tasks[task.task_id] = task
        return task

    def _start_watch(self, task: BackgroundTask) -> None:
        threading.Thread(
            target=self._watch,
            args=(task,),
            daemon=True,
            name=f"pbi-agent-bg-{task.task_id}",
        ).start()
        self._notify_changed()

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
            self._check_capacity()
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

    def send_input(self, task_id: str, chars: str) -> BackgroundTask:
        """Write ``chars`` to a running ``tty`` task's terminal."""
        task = self.get(task_id)
        if task is None:
            raise KeyError(task_id)
        if task.status != "running":
            raise ValueError(f"Task {task_id} is not running ({task.status}).")
        if task.terminal is None:
            raise ValueError(
                f"Task {task_id} has no terminal input; start the command with "
                "'tty': true to send input."
            )
        try:
            task.terminal.write(chars.encode("utf-8"))
        except OSError as exc:
            raise ValueError(f"Could not write to task {task_id}: {exc}") from exc
        return task

    def wait_for_output(self, task: BackgroundTask, *, wait_ms: int) -> None:
        """Wait up to ``wait_ms`` for ``task`` to exit or its output to settle.

        Returns early once new output has arrived and then stayed quiet for
        ``OUTPUT_SETTLE_MS`` (e.g. a REPL answered and shows its prompt).
        """
        deadline = time.monotonic() + wait_ms / 1000.0
        seen = task.stdout.total + task.stderr.total
        settled_at: float | None = None
        while time.monotonic() < deadline and task.status == "running":
            time.sleep(0.05)
            current = task.stdout.total + task.stderr.total
            if current != seen:
                seen = current
                settled_at = time.monotonic()
            elif (
                settled_at is not None
                and time.monotonic() - settled_at >= OUTPUT_SETTLE_MS / 1000.0
            ):
                return
        if task.status != "running":
            for reader in task.readers:
                reader.join(timeout=1.0)

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

    def _terminate(
        self,
        task: BackgroundTask,
        *,
        reason: BackgroundTaskStatus,
        force: bool = False,
    ) -> None:
        from pbi_agent.tools.shell import _kill_process_tree

        if task.kind == "sub_agent":
            if task.status == "running" and task.cancel_event is not None:
                task.kill_reason = reason
                task.cancel_event.set()
            return
        process = task.process
        if task.status != "running" or process is None:
            return
        if process.poll() is not None and not force and not _readers_alive(task):
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
        elapsed = max(0.0, time.time() - task.started_at)
        remaining = max(0.0, task.timeout_ms / 1000.0 - elapsed)
        deadline = time.monotonic() + remaining
        try:
            process.wait(timeout=remaining)
            # Descendants (e.g. a REPL left behind when its shell got Ctrl-C)
            # may keep the output open after the shell exits: the task runs
            # until its output closes.
            for reader in task.readers:
                reader.join(timeout=max(0.0, deadline - time.monotonic()))
            if any(reader.is_alive() for reader in task.readers):
                raise subprocess.TimeoutExpired(task.command, remaining)
        except subprocess.TimeoutExpired:
            self._terminate(task, reason="timed_out", force=True)
            try:
                process.wait(timeout=5.0)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()
        for reader in task.readers:
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


def _readers_alive(task: BackgroundTask) -> bool:
    return any(reader.is_alive() for reader in task.readers)


def _pump(stream: Any, buffer: StreamBuffer) -> None:
    decoder = codecs.getincrementaldecoder("utf-8")(errors="replace")
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
                buffer.append(decoder.decode(b"", final=True))
                return
            buffer.append(decoder.decode(chunk))
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
    """Render a finished task as a model-facing synthetic user input.

    Shows only output the model has not seen yet and marks it as seen.
    """
    from pbi_agent.tools.model_output import render_shell_output

    if task.kind == "sub_agent":
        return _render_sub_agent_result(task)
    body = render_shell_output(read_task_output(task))
    header, _, rest = body.partition("\n")
    label = task.intent or task.command
    lines = [
        f'<{BACKGROUND_RESULT_TAG} task_id="{task.task_id}">',
        f"{header} — {label}" if label else header,
    ]
    if rest:
        lines.append(rest)
    lines.append(f"</{BACKGROUND_RESULT_TAG}>")
    return "\n".join(lines)


def read_task_output(
    task: BackgroundTask,
    *,
    from_start: bool = False,
) -> dict[str, Any]:
    """Return a model-facing snapshot of output not yet shown, and mark it seen.

    ``from_start`` re-reads everything retained. The payload carries the task
    summary, bounded ``stdout``/``stderr`` and ``earlier_chars`` (output the
    model was already shown).
    """
    status = task.status
    stdout_cursor = 0 if from_start else task.stdout_cursor
    stderr_cursor = 0 if from_start else task.stderr_cursor
    stdout_read = task.stdout.read_since(stdout_cursor)
    stderr_read = task.stderr.read_since(stderr_cursor)
    task.stdout_cursor = stdout_read.cursor
    task.stderr_cursor = stderr_read.cursor
    stdout = stdout_read.text
    stderr = stderr_read.text
    if task.tty:
        stdout = clean_tty_text(stdout)
        stderr = clean_tty_text(stderr)
    payload = {
        **task.summary(),
        "status": status,
        **background_output_payload(
            task,
            stdout=stdout,
            stderr=stderr,
            stdout_dropped=stdout_read.skipped > 0,
            stderr_dropped=stderr_read.skipped > 0,
            compression=task.compression,
            status=status,
        ),
    }
    earlier = stdout_cursor + stderr_cursor
    if earlier:
        payload["earlier_chars"] = earlier
    return payload


MIDDLE_DROPPED_NOTE = (
    f"Background output keeps only the first {HEAD_MAX_CHARS} and last "
    f"{TAIL_MAX_CHARS} chars per stream; the middle was dropped."
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

    ``stdout``/``stderr`` are the text to show; ``*_dropped`` marks output
    lost between the retained head and tail (``*_middle_dropped``), distinct
    from ``*_truncated`` (bounded for display). Once a lossy task has finished,
    its full retained output is written to one raw output file, reused for
    later reads.
    """
    from pbi_agent.tools.raw_output import raw_output_notice, save_raw_output
    from pbi_agent.tools.shell import _build_output_payload

    payload = _build_output_payload(
        stdout=stdout, stderr=stderr, compression=compression, save_raw=False
    )
    if stdout_dropped:
        payload["stdout_middle_dropped"] = True
    if stderr_dropped:
        payload["stderr_middle_dropped"] = True
    compressed = bool(
        payload.get("stdout_compressed") or payload.get("stderr_compressed")
    )
    truncated = bool(payload.get("stdout_truncated") or payload.get("stderr_truncated"))
    middle_note = MIDDLE_DROPPED_NOTE if stdout_dropped or stderr_dropped else None
    if not (compressed or truncated):
        if middle_note:
            payload["notice"] = middle_note
        return payload
    if (status or task.status) == "running":
        notice = (
            "Output compressed or truncated. A raw output file is saved once the "
            "task finishes; read the task output again then."
        )
        payload["notice"] = f"{notice} {middle_note}" if middle_note else notice
        return payload
    if task.raw_output_path is None:
        full_stdout = task.stdout.text()
        full_stderr = task.stderr.text()
        if task.tty:
            full_stdout = clean_tty_text(full_stdout)
        task.raw_output_path = save_raw_output(stdout=full_stdout, stderr=full_stderr)
    if task.raw_output_path is not None:
        payload["raw_output_path"] = str(task.raw_output_path)
        payload["notice"] = raw_output_notice(
            compressed=compressed,
            truncated=truncated,
            extra_note=middle_note,
        )
    elif middle_note:
        payload["notice"] = middle_note
    return payload


def _render_sub_agent_result(task: BackgroundTask) -> str:
    duration = task.summary()["elapsed_seconds"]
    header = f"{task.task_id} {task.status} sub_agent · {duration:.1f}s"
    if task.intent:
        header = f"{header} — {task.intent}"
    lines = [
        f'<{BACKGROUND_RESULT_TAG} task_id="{task.task_id}">',
        header,
        task.stdout.text() or "(no output)",
    ]
    if task.stderr.text():
        lines.append("[error]")
        lines.append(task.stderr.text())
    lines.append(f"</{BACKGROUND_RESULT_TAG}>")
    return "\n".join(lines)
