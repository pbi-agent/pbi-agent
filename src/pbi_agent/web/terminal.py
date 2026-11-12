"""Interactive workspace terminals for the web UI.

Each terminal is a shell attached to a pseudo-terminal (POSIX) so interactive
programs (prompts, confirmations, pagers) behave like in a real terminal. The
shell matches the one used by the agent ``shell`` tool: ``PBI_AGENT_SHELL_EXECUTABLE``
when set, otherwise the user's ``$SHELL``; ``PBI_AGENT_SHELL_BOOTSTRAP`` is sourced
on startup.
"""

from __future__ import annotations

import os
import shlex
import shutil
import signal
import subprocess
import threading
import uuid
from collections.abc import Callable
from pathlib import Path

from pbi_agent.tools.shell import SHELL_BOOTSTRAP_ENV, SHELL_EXECUTABLE_ENV

_SCROLLBACK_LIMIT = 256 * 1024
_READ_SIZE = 65536

Listener = Callable[[bytes], None]


def resolve_terminal_shell() -> list[str]:
    """Return argv for the interactive shell used by web terminals."""
    if os.name == "nt":
        configured = os.environ.get(SHELL_EXECUTABLE_ENV)
        return [configured or os.environ.get("COMSPEC") or "cmd.exe"]
    candidates = [
        os.environ.get(SHELL_EXECUTABLE_ENV),
        os.environ.get("SHELL"),
        shutil.which("bash"),
        "/bin/sh",
    ]
    executable = next(c for c in candidates if c)
    name = Path(executable).name
    if name in {"bash", "zsh", "sh", "dash", "fish", "ksh"}:
        return [executable, "-i"]
    return [executable]


class Terminal:
    def __init__(self, terminal_id: str, cwd: Path, *, cols: int = 80, rows: int = 24):
        self.terminal_id = terminal_id
        self._lock = threading.Lock()
        self._listeners: list[Listener] = []
        self._scrollback = bytearray()
        self._exit_listeners: list[Callable[[int | None], None]] = []
        self.exit_code: int | None = None
        self.closed = False
        env = dict(os.environ)
        env.setdefault("TERM", "xterm-256color")
        env["COLORTERM"] = "truecolor"
        argv = resolve_terminal_shell()
        self._master_fd: int | None = None
        if os.name == "nt":  # pragma: no cover - exercised on Windows only
            self._process = subprocess.Popen(
                argv,
                cwd=str(cwd),
                env=env,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
            )
        else:
            import pty

            master_fd, slave_fd = pty.openpty()
            self._master_fd = master_fd
            self._set_size(cols, rows)
            self._process = subprocess.Popen(
                argv,
                cwd=str(cwd),
                env=env,
                stdin=slave_fd,
                stdout=slave_fd,
                stderr=slave_fd,
                start_new_session=True,
                close_fds=True,
            )
            os.close(slave_fd)
        self._reader = threading.Thread(
            target=self._read_loop, daemon=True, name=f"pbi-terminal-{terminal_id}"
        )
        self._reader.start()
        bootstrap = os.environ.get(SHELL_BOOTSTRAP_ENV)
        if bootstrap and os.name != "nt":
            self.write(f". {shlex.quote(bootstrap)}\n".encode())

    # -- IO -----------------------------------------------------------------
    def _read_chunk(self) -> bytes:
        if self._master_fd is not None:
            try:
                return os.read(self._master_fd, _READ_SIZE)
            except OSError:
                return b""
        stdout = self._process.stdout
        if stdout is None:  # pragma: no cover
            return b""
        return stdout.read1(_READ_SIZE)  # pyright: ignore[reportAttributeAccessIssue]

    def _read_loop(self) -> None:
        while True:
            data = self._read_chunk()
            if not data:
                break
            with self._lock:
                self._scrollback.extend(data)
                overflow = len(self._scrollback) - _SCROLLBACK_LIMIT
                if overflow > 0:
                    del self._scrollback[:overflow]
                listeners = list(self._listeners)
            for listener in listeners:
                try:
                    listener(data)
                except Exception:
                    pass
        try:
            self.exit_code = self._process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            self.exit_code = None
        self.closed = True
        with self._lock:
            exit_listeners = list(self._exit_listeners)
        for exit_listener in exit_listeners:
            try:
                exit_listener(self.exit_code)
            except Exception:
                pass

    def write(self, data: bytes) -> None:
        if self.closed:
            return
        if self._master_fd is not None:
            view = memoryview(data)
            while view:
                written = os.write(self._master_fd, view)
                view = view[written:]
            return
        stdin = self._process.stdin  # pragma: no cover - Windows
        if stdin is not None:
            stdin.write(data)
            stdin.flush()

    def _set_size(self, cols: int, rows: int) -> None:
        if self._master_fd is None:
            return
        import fcntl
        import struct
        import termios

        size = struct.pack("HHHH", max(rows, 1), max(cols, 1), 0, 0)
        fcntl.ioctl(self._master_fd, termios.TIOCSWINSZ, size)

    def resize(self, cols: int, rows: int) -> None:
        if self.closed:
            return
        self._set_size(cols, rows)

    # -- listeners ----------------------------------------------------------
    def attach(
        self, listener: Listener, on_exit: Callable[[int | None], None]
    ) -> bytes:
        """Register listeners and return the scrollback to replay."""
        with self._lock:
            self._listeners.append(listener)
            self._exit_listeners.append(on_exit)
            return bytes(self._scrollback)

    @property
    def has_listeners(self) -> bool:
        return bool(self._listeners)

    def detach(self, listener: Listener, on_exit: Callable[[int | None], None]) -> None:
        with self._lock:
            if listener in self._listeners:
                self._listeners.remove(listener)
            if on_exit in self._exit_listeners:
                self._exit_listeners.remove(on_exit)

    def close(self) -> None:
        if self._process.poll() is None:
            try:
                if os.name != "nt":
                    os.killpg(self._process.pid, signal.SIGHUP)
                else:  # pragma: no cover
                    self._process.terminate()
                self._process.wait(timeout=2)
            except (OSError, subprocess.TimeoutExpired):
                try:
                    self._process.kill()
                except OSError:
                    pass
        if self._master_fd is not None:
            try:
                os.close(self._master_fd)
            except OSError:
                pass
            self._master_fd = None
        self.closed = True


class TerminalManager:
    def __init__(self, cwd_provider: Callable[[], Path]):
        self._cwd_provider = cwd_provider
        self._terminals: dict[str, Terminal] = {}
        self._lock = threading.Lock()

    def get_or_create(
        self, terminal_id: str | None, *, cols: int = 80, rows: int = 24
    ) -> Terminal:
        with self._lock:
            self._prune_exited_locked()
            if terminal_id:
                existing = self._terminals.get(terminal_id)
                if existing is not None and not existing.closed:
                    existing.resize(cols, rows)
                    return existing
            new_id = terminal_id or uuid.uuid4().hex
            terminal = Terminal(new_id, self._cwd_provider(), cols=cols, rows=rows)
            self._terminals[new_id] = terminal
            return terminal

    def _prune_exited_locked(self) -> None:
        # Drop shells that exited on their own and have no attached client so
        # their scrollback does not accumulate for the server lifetime.
        for key, terminal in list(self._terminals.items()):
            if terminal.closed and not terminal.has_listeners:
                del self._terminals[key]

    def close(self, terminal_id: str) -> bool:
        with self._lock:
            terminal = self._terminals.pop(terminal_id, None)
        if terminal is None:
            return False
        terminal.close()
        return True

    def shutdown(self) -> None:
        with self._lock:
            terminals = list(self._terminals.values())
            self._terminals.clear()
        for terminal in terminals:
            terminal.close()


__all__ = ["Terminal", "TerminalManager", "resolve_terminal_shell"]
