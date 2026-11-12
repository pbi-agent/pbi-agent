"""Interactive workspace terminals for the web UI.

Each terminal is a shell attached to a pseudo-terminal (a POSIX pty, or ConPTY
through ``pywinpty`` on Windows) so interactive programs (prompts, confirmations,
pagers) behave like in a real terminal. Without a pseudo-terminal the shell does
not echo keystrokes or accept xterm's ``\r`` as Enter, so there is no pipe
fallback: a missing ``pywinpty`` is reported to the client as an error. The
shell matches the one used by the agent ``shell`` tool: ``PBI_AGENT_SHELL_EXECUTABLE``
when set, otherwise the user's ``$SHELL`` (``COMSPEC`` on Windows);
``PBI_AGENT_SHELL_BOOTSTRAP`` is sourced on startup when the shell is POSIX-like.
"""

from __future__ import annotations

import os
import shlex
import shutil
import signal
import subprocess
import threading
import time
import uuid
from collections.abc import Callable
from pathlib import Path
from typing import Any

from pbi_agent.tools.shell import SHELL_BOOTSTRAP_ENV, SHELL_EXECUTABLE_ENV

_SCROLLBACK_LIMIT = 256 * 1024
_READ_SIZE = 65536

Listener = Callable[[bytes], None]


_POSIX_SHELLS = {"bash", "zsh", "sh", "dash", "fish", "ksh"}
# Terminal queries ConPTY emits at startup. Replaying them from scrollback makes
# every reattached xterm answer again, typing the reply into the shell.
_CONPTY_QUERIES = (b"\x1b[c", b"\x1b[6n")


def _is_posix_shell(executable: str) -> bool:
    name = Path(executable.replace("\\", "/")).name.lower()
    return name.removesuffix(".exe") in _POSIX_SHELLS


class _ConPty:  # pragma: no cover - exercised on Windows only
    """A process attached to a Windows pseudo-console (ConPTY via pywinpty).

    Uses pywinpty's low-level ``PTY`` rather than ``PtyProcess``: the latter
    relays output through a loopback socket with an in-band keep-alive marker
    that can leak into the output.
    """

    def __init__(
        self, argv: list[str], cwd: Path, env: dict[str, str], cols: int, rows: int
    ) -> None:
        try:
            from winpty import PTY  # pyright: ignore[reportMissingImports]
        except ImportError as exc:
            raise OSError(
                "pywinpty is required for web terminals on Windows; "
                "reinstall pbi-agent to restore it."
            ) from exc
        executable = shutil.which(argv[0], path=env.get("PATH"))
        if executable is None:
            raise FileNotFoundError(f"Shell not found: {argv[0]}")
        cmdline = " " + subprocess.list2cmdline(argv[1:]) if argv[1:] else None
        env_block = "\0".join(f"{key}={value}" for key, value in env.items()) + "\0"
        try:
            self._pty: Any = PTY(max(cols, 1), max(rows, 1))
            self._pty.spawn(executable, cmdline=cmdline, cwd=str(cwd), env=env_block)
        except OSError:
            raise
        except Exception as exc:  # pywinpty raises its own non-OSError type
            raise OSError(f"Could not start {executable}: {exc}") from exc

    @property
    def pid(self) -> int | None:
        return self._pty.pid

    def read(self) -> bytes:
        try:
            while True:
                text = self._pty.read(blocking=True)
                if text:
                    return text.encode("utf-8", errors="replace")
                if self._pty.iseof() or not self._pty.isalive():
                    return b""
                time.sleep(0.01)
        except Exception:
            return b""

    def write(self, data: bytes) -> None:
        try:
            self._pty.write(data.decode("utf-8", errors="replace"))
        except Exception:
            pass

    def resize(self, cols: int, rows: int) -> None:
        try:
            self._pty.set_size(max(cols, 1), max(rows, 1))
        except Exception:
            pass

    def wait(self, timeout: float) -> int | None:
        deadline = time.monotonic() + timeout
        while self._pty.isalive() and time.monotonic() < deadline:
            time.sleep(0.05)
        return None if self._pty.isalive() else self._pty.get_exitstatus()

    def close(self) -> None:
        try:
            pid = self._pty.pid
            if pid is not None and self._pty.isalive():
                # Kill the shell together with whatever it started.
                subprocess.run(
                    ["taskkill", "/F", "/T", "/PID", str(pid)],
                    capture_output=True,
                    check=False,
                    timeout=10,
                )
            self._pty.cancel_io()  # unblock the reader thread
        except Exception:
            pass


def resolve_terminal_shell() -> list[str]:
    """Return argv for the interactive shell used by web terminals."""
    if os.name == "nt":
        executable = (
            os.environ.get(SHELL_EXECUTABLE_ENV)
            or os.environ.get("COMSPEC")
            or "cmd.exe"
        )
        return [executable, "-i"] if _is_posix_shell(executable) else [executable]
    candidates = [
        os.environ.get(SHELL_EXECUTABLE_ENV),
        os.environ.get("SHELL"),
        shutil.which("bash"),
        "/bin/sh",
    ]
    executable = next(c for c in candidates if c)
    return [executable, "-i"] if _is_posix_shell(executable) else [executable]


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
        self._conpty: _ConPty | None = None
        self._process: subprocess.Popen[bytes] | None = None
        if os.name == "nt":  # pragma: no cover - exercised on Windows only
            self._conpty = _ConPty(argv, cwd, env, cols, rows)
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
        if bootstrap and self._conpty is None:
            self.write(f". {shlex.quote(bootstrap)}\n".encode())
        elif bootstrap and _is_posix_shell(argv[0]):  # pragma: no cover - Windows
            # cmd.exe/PowerShell cannot source a POSIX bootstrap file.
            self.write(f". {shlex.quote(Path(bootstrap).as_posix())}\r".encode())

    # -- IO -----------------------------------------------------------------
    def _read_chunk(self) -> bytes:
        if self._master_fd is not None:
            try:
                return os.read(self._master_fd, _READ_SIZE)
            except OSError:
                return b""
        if self._conpty is not None:  # pragma: no cover - Windows
            return self._conpty.read()
        return b""

    def _read_loop(self) -> None:
        while True:
            data = self._read_chunk()
            if not data:
                break
            stored = data
            if self._conpty is not None:  # pragma: no cover - Windows
                for query in _CONPTY_QUERIES:
                    stored = stored.replace(query, b"")
            with self._lock:
                self._scrollback.extend(stored)
                overflow = len(self._scrollback) - _SCROLLBACK_LIMIT
                if overflow > 0:
                    del self._scrollback[:overflow]
                listeners = list(self._listeners)
            for listener in listeners:
                try:
                    listener(data)
                except Exception:
                    pass
        self.exit_code = self._wait_exit_code()
        self.closed = True
        with self._lock:
            exit_listeners = list(self._exit_listeners)
        for exit_listener in exit_listeners:
            try:
                exit_listener(self.exit_code)
            except Exception:
                pass

    def _wait_exit_code(self) -> int | None:
        if self._conpty is not None:  # pragma: no cover - Windows
            return self._conpty.wait(5)
        if self._process is None:  # pragma: no cover
            return None
        try:
            return self._process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            return None

    def write(self, data: bytes) -> None:
        if self.closed:
            return
        if self._master_fd is not None:
            view = memoryview(data)
            while view:
                written = os.write(self._master_fd, view)
                view = view[written:]
            return
        if self._conpty is not None:  # pragma: no cover - Windows
            self._conpty.write(data)

    def _set_size(self, cols: int, rows: int) -> None:
        if self._conpty is not None:  # pragma: no cover - Windows
            self._conpty.resize(cols, rows)
            return
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
        process = self._process
        if self._conpty is not None:  # pragma: no cover - Windows
            self._conpty.close()
        elif process is not None and process.poll() is None:
            try:
                os.killpg(process.pid, signal.SIGHUP)
                process.wait(timeout=2)
            except (OSError, subprocess.TimeoutExpired):
                try:
                    process.kill()
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
