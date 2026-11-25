"""Custom ``shell`` tool - executes shell commands in a subprocess.

This replaces the provider-specific native shell tools (OpenAI ``shell``,
Anthropic ``bash``) with a single, provider-agnostic function tool that goes
through the normal tool registry and execution pipeline.
"""

from __future__ import annotations

import os
import re
import shlex
import signal
import subprocess
import time
from contextlib import suppress
from pathlib import Path
from typing import Any

from codetool_shell import compress_text

from pbi_agent.tools.background_tasks import (
    DEFAULT_BACKGROUND_TIMEOUT_MS,
    AttachedProcess,
    spawn_attached_process,
)
from pbi_agent.tools.model_output import render_shell_output
from pbi_agent.tools.output import MAX_OUTPUT_CHARS as DEFAULT_MAX_OUTPUT_CHARS
from pbi_agent.tools.output import bound_output, decode_output
from pbi_agent.tools.raw_output import raw_output_notice, save_raw_output
from pbi_agent.tools.types import ToolContext, ToolSpec

DEFAULT_YIELD_TIME_MS = 30_000
MAX_YIELD_TIME_MS = 300_000
MAX_STDOUT_CHARS = 12_000
MAX_STDERR_CHARS = 12_000
MAX_OUTPUT_CHARS = DEFAULT_MAX_OUTPUT_CHARS
INTERRUPT_POLL_SECONDS = 0.1
PROCESS_STOP_TIMEOUT_SECONDS = 5.0
SHELL_BOOTSTRAP_ENV = "PBI_AGENT_SHELL_BOOTSTRAP"
SHELL_EXECUTABLE_ENV = "PBI_AGENT_SHELL_EXECUTABLE"
_ANSI_ESCAPE_RE = re.compile(r"\x1b\[[0-?]*[ -/]*[@-~]")

SPEC = ToolSpec(
    name="shell",
    description=("Run a shell command. Returns stdout, stderr, and exit code."),
    prompt_usage=(
        "Use `shell` for commands, incl. git; byte-cap commands with unknown "
        "or possibly large output. Commands still running after "
        "`yield_time_ms` move to background; set `run_in_background` to start "
        "there. Background results arrive automatically; do not poll with "
        "sleep. Use `background_task` to list, inspect, or kill them; kill "
        "ones you no longer need before finishing."
    ),
    parameters_schema={
        "type": "object",
        "properties": {
            "intent": {
                "type": "string",
                "description": (
                    "Short 3-8 word summary of what the command does, shown "
                    "to the user (e.g. 'Run backend unit tests')."
                ),
            },
            "command": {
                "type": "string",
                "description": "The shell command to execute.",
            },
            "working_directory": {
                "type": "string",
                "description": (
                    "Working directory for the command. Relative paths resolve "
                    "from the workspace root. Defaults to the workspace root."
                ),
            },
            "yield_time_ms": {
                "type": "integer",
                "description": (
                    "How long to wait for the command, in milliseconds. If it "
                    "is still running then, it moves to the background and keeps "
                    "running; its result is delivered automatically. Defaults to "
                    "30 000 (30 seconds), maximum 300 000 (5 minutes)."
                ),
            },
            "run_in_background": {
                "type": "boolean",
                "description": (
                    "Start the command in the background and return a task_id "
                    "immediately. The result is delivered to you automatically "
                    "when it finishes (even after you end your turn); do not poll. "
                    "Use for long builds/tests, dev servers, watchers."
                ),
            },
            "background_timeout_ms": {
                "type": "integer",
                "description": (
                    "Background-only timeout in milliseconds. Defaults to "
                    "1 800 000 (30 minutes), maximum 7 200 000 (2 hours)."
                ),
            },
            "tty": {
                "type": "boolean",
                "description": (
                    "Run under a pseudo-terminal (stdout+stderr merged) so the "
                    "task can take input via `background_task` `input` "
                    "(REPLs, prompts). Defaults to false: stdin is closed."
                ),
            },
            "compression": {
                "type": "boolean",
                "description": (
                    "Whether to compress stdout/stderr before returning output. "
                    "Defaults to true."
                ),
            },
        },
        "required": ["intent", "command"],
        "additionalProperties": False,
    },
    is_destructive=True,
    render_output=render_shell_output,
)


def _intent_error(arguments: dict[str, Any]) -> str | None:
    intent = arguments.get("intent")
    if not isinstance(intent, str) or not intent.strip():
        return (
            "'intent' must be a non-empty string briefly describing the command "
            "(3-8 words)."
        )
    return None


def handle(arguments: dict[str, Any], context: ToolContext) -> dict[str, Any]:
    """Execute a single shell command and return structured output."""
    run_in_background = arguments.get("run_in_background")
    if run_in_background is not None and run_in_background is not False:
        return _handle_background(arguments, context)
    started = time.monotonic()
    result = _handle_foreground(arguments, context)
    if "stdout" in result or "stderr" in result:
        result["duration_ms"] = int((time.monotonic() - started) * 1000)
    return result


def _handle_foreground(
    arguments: dict[str, Any], context: ToolContext
) -> dict[str, Any]:
    intent_error = _intent_error(arguments)
    if intent_error is not None:
        return {"error": intent_error}
    command = arguments.get("command", "")
    if not isinstance(command, str) or not command.strip():
        return {"error": "'command' must be a non-empty string."}

    try:
        compression = (
            _normalize_compression(arguments["compression"])
            if "compression" in arguments
            else True
        )
    except ValueError as exc:
        return {"error": str(exc)}

    root = (
        context.workspace_root if context.workspace_root is not None else Path.cwd()
    ).resolve()
    working_directory = _resolve_working_directory(
        root, arguments.get("working_directory")
    )
    if "timeout_ms" in arguments:
        return {"error": _TIMEOUT_MS_REPLACED_ERROR}
    tty = arguments.get("tty", False)
    if not isinstance(tty, bool):
        return {"error": "'tty' must be a boolean."}
    try:
        yield_time_ms = _normalize_yield_time_ms(arguments.get("yield_time_ms"))
    except ValueError as exc:
        return {"error": str(exc)}

    effective_command = _bootstrap_command(_tty_command(command) if tty else command)
    shell_executable = os.environ.get(SHELL_EXECUTABLE_ENV) or None

    try:
        if tty or (isinstance(context, ToolContext) and context.display is not None):
            return _run_interruptible(
                effective_command,
                tty=tty,
                display_command=command,
                intent=str(arguments["intent"]).strip(),
                working_directory=working_directory,
                shell_executable=shell_executable,
                yield_time_ms=yield_time_ms,
                compression=compression,
                context=context,
            )
        completed = subprocess.run(
            effective_command,
            cwd=str(working_directory),
            check=False,
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=False,
            shell=True,
            executable=shell_executable,
            timeout=(yield_time_ms / 1000.0),
        )
        return {
            **_build_output_payload(
                stdout=decode_output(completed.stdout),
                stderr=decode_output(completed.stderr),
                compression=compression,
            ),
            "exit_code": completed.returncode,
        }
    except subprocess.TimeoutExpired as exc:
        return _timed_out_payload(
            stdout=decode_output(exc.stdout),
            stderr=decode_output(exc.stderr),
            compression=compression,
            yield_time_ms=yield_time_ms,
        )
    except Exception as exc:
        stderr, stderr_truncated = bound_output(str(exc))
        return {
            "stdout": "",
            "stderr": stderr,
            "exit_code": 1,
            "error": f"Shell execution failed: {exc}",
            **({"stderr_truncated": True} if stderr_truncated else {}),
        }


_TIMEOUT_MS_REPLACED_ERROR = (
    "'timeout_ms' is not supported; use 'yield_time_ms' (commands still running "
    "after it move to the background instead of being killed)."
)


def _timed_out_payload(
    *,
    stdout: str,
    stderr: str,
    compression: bool,
    yield_time_ms: int,
) -> dict[str, Any]:
    return {
        **_build_output_payload(stdout=stdout, stderr=stderr, compression=compression),
        "exit_code": None,
        "timed_out": True,
        "error": (
            f"Command killed after {yield_time_ms}ms; background tasks are not "
            "available here."
        ),
    }


def _background_manager(context: ToolContext) -> Any:
    display = context.display
    return getattr(display, "background_task_manager", None) if display else None


def _handle_background(
    arguments: dict[str, Any], context: ToolContext
) -> dict[str, Any]:
    manager = _background_manager(context)
    if manager is None:
        return {
            "error": (
                "Background shell tasks are not supported in this mode. "
                "Run the command in the foreground."
            )
        }
    if not isinstance(arguments.get("run_in_background"), bool):
        return {"error": "'run_in_background' must be a boolean."}
    intent_error = _intent_error(arguments)
    if intent_error is not None:
        return {"error": intent_error}
    command = arguments.get("command", "")
    if not isinstance(command, str) or not command.strip():
        return {"error": "'command' must be a non-empty string."}
    try:
        compression = (
            _normalize_compression(arguments["compression"])
            if "compression" in arguments
            else True
        )
        timeout_ms = _normalize_background_timeout_ms(
            arguments.get("background_timeout_ms")
        )
    except ValueError as exc:
        return {"error": str(exc)}
    tty = arguments.get("tty", False)
    if not isinstance(tty, bool):
        return {"error": "'tty' must be a boolean."}
    root = (
        context.workspace_root if context.workspace_root is not None else Path.cwd()
    ).resolve()
    try:
        working_directory = _resolve_working_directory(
            root, arguments.get("working_directory")
        )
        task = manager.start(
            _bootstrap_command(_tty_command(command) if tty else command),
            display_command=command,
            intent=str(arguments["intent"]).strip(),
            working_directory=str(working_directory),
            shell_executable=os.environ.get(SHELL_EXECUTABLE_ENV) or None,
            timeout_ms=timeout_ms,
            compression=compression,
            tool_call_id=context.tool_call_id,
            tty=tty,
        )
    except Exception as exc:
        return {"error": f"Failed to start background task: {exc}"}
    return {
        "background": True,
        "task_id": task.task_id,
        "status": "running",
    }


def _normalize_background_timeout_ms(raw: Any) -> int:
    from pbi_agent.tools.background_tasks import (
        DEFAULT_BACKGROUND_TIMEOUT_MS,
        MAX_BACKGROUND_TIMEOUT_MS,
    )

    if raw is None:
        return DEFAULT_BACKGROUND_TIMEOUT_MS
    if isinstance(raw, bool) or not isinstance(raw, int) or raw < 1:
        raise ValueError("'background_timeout_ms' must be a positive integer.")
    return min(raw, MAX_BACKGROUND_TIMEOUT_MS)


def _run_interruptible(
    command: str,
    *,
    display_command: str,
    intent: str,
    working_directory: Path,
    shell_executable: str | None,
    yield_time_ms: int,
    compression: bool,
    context: ToolContext,
    tty: bool = False,
) -> dict[str, Any]:
    if _interrupt_requested(context):
        return _interrupted_payload(stdout="", stderr="", compression=compression)

    attached = spawn_attached_process(
        command,
        working_directory=str(working_directory),
        shell_executable=shell_executable,
        tty=tty,
    )
    process = attached.process
    deadline = time.monotonic() + (yield_time_ms / 1000.0)
    try:
        while True:
            if _interrupt_requested(context):
                _stop_attached(attached)
                return _interrupted_payload(
                    stdout=attached.stdout.text(),
                    stderr=attached.stderr.text(),
                    compression=compression,
                )

            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return _yield_or_kill(
                    attached,
                    display_command=display_command,
                    intent=intent,
                    working_directory=working_directory,
                    yield_time_ms=yield_time_ms,
                    compression=compression,
                    context=context,
                )

            poll = min(INTERRUPT_POLL_SECONDS, remaining)
            if process.poll() is None:
                try:
                    process.wait(timeout=poll)
                except subprocess.TimeoutExpired:
                    continue
            # Descendants may still hold the pipes after the shell exits.
            alive = [reader for reader in attached.readers if reader.is_alive()]
            if alive:
                alive[0].join(timeout=poll)
                continue
            return {
                **_build_output_payload(
                    stdout=attached.stdout.text(),
                    stderr=attached.stderr.text(),
                    compression=compression,
                ),
                "exit_code": process.returncode,
            }
    except BaseException:
        with suppress(Exception):
            _stop_attached(attached)
        raise


def _yield_or_kill(
    attached: AttachedProcess,
    *,
    display_command: str,
    intent: str,
    working_directory: Path,
    yield_time_ms: int,
    compression: bool,
    context: ToolContext,
) -> dict[str, Any]:
    """Hand a still-running command to the background manager, else kill it."""
    manager = _background_manager(context) if context.background_handoff else None
    if manager is not None:
        try:
            task = manager.adopt(
                attached,
                display_command=display_command,
                intent=intent,
                working_directory=str(working_directory),
                timeout_ms=DEFAULT_BACKGROUND_TIMEOUT_MS,
                compression=compression,
                tool_call_id=context.tool_call_id,
            )
        except Exception:
            task = None
        if task is not None:
            stdout = attached.stdout.read_since(0)
            stderr = attached.stderr.read_since(0)
            task.stdout_cursor = stdout.cursor
            task.stderr_cursor = stderr.cursor
            return {
                **_build_output_payload(
                    stdout=stdout.text,
                    stderr=stderr.text,
                    compression=compression,
                    save_raw=False,
                ),
                "background": True,
                "task_id": task.task_id,
                "status": "running",
            }
    _stop_attached(attached)
    return _timed_out_payload(
        stdout=attached.stdout.text(),
        stderr=attached.stderr.text(),
        compression=compression,
        yield_time_ms=yield_time_ms,
    )


def _interrupt_requested(context: ToolContext) -> bool:
    display = context.display
    if display is None:
        return False
    if display.interrupt_requested():
        return True
    call_id = context.tool_call_id
    checker = getattr(display, "tool_interrupt_requested", None)
    return bool(call_id and callable(checker) and checker(call_id))


def _stop_attached(attached: AttachedProcess) -> None:
    process = attached.process
    _kill_process_tree(process)
    try:
        process.wait(timeout=PROCESS_STOP_TIMEOUT_SECONDS)
    except subprocess.TimeoutExpired:
        if process.poll() is None:
            process.kill()
        with suppress(subprocess.TimeoutExpired):
            process.wait(timeout=INTERRUPT_POLL_SECONDS)
    attached.join_readers(timeout=INTERRUPT_POLL_SECONDS * 5)
    _close_process_pipes(process)


def _kill_process_tree(process: subprocess.Popen[bytes]) -> None:
    if os.name == "nt":
        ctrl_break_event = getattr(signal, "CTRL_BREAK_EVENT", None)
        if ctrl_break_event is not None:
            try:
                os.kill(process.pid, ctrl_break_event)
            except OSError:
                pass
        try:
            subprocess.run(
                ["taskkill", "/F", "/T", "/PID", str(process.pid)],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=PROCESS_STOP_TIMEOUT_SECONDS,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired):
            pass
        if process.poll() is None:
            process.kill()
        return

    try:
        os.killpg(process.pid, signal.SIGKILL)
    except ProcessLookupError:
        return
    except OSError:
        if process.poll() is None:
            process.kill()


def _close_process_pipes(process: subprocess.Popen[bytes]) -> None:
    if process.stdout is not None:
        process.stdout.close()
    if process.stderr is not None:
        process.stderr.close()


def _interrupted_payload(
    *,
    stdout: str,
    stderr: str,
    compression: bool,
) -> dict[str, Any]:
    return {
        **_build_output_payload(
            stdout=stdout,
            stderr=stderr,
            compression=compression,
        ),
        "exit_code": 130,
        "interrupted": True,
        "error": "Command interrupted by user.",
    }


_SHELL_SYNTAX_CHARS = frozenset(";&|<>()$`\\\n*?[]{}~!#=")


def _tty_command(command: str) -> str:
    """``exec`` a simple command so it, not the wrapping shell, owns the PTY.

    Ctrl-C then reaches only the command (the shell would otherwise die and
    report its own signal exit code).
    """
    if os.name == "nt" or any(char in _SHELL_SYNTAX_CHARS for char in command):
        return command
    return f"exec {command}"


def _bootstrap_command(command: str) -> str:
    bootstrap = os.environ.get(SHELL_BOOTSTRAP_ENV)
    if not bootstrap:
        return command
    return f". {shlex.quote(bootstrap)}; {command}"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _resolve_working_directory(root: Path, raw: Any) -> Path:
    if raw is None:
        return root
    if not isinstance(raw, str) or not raw.strip():
        return root

    candidate = Path(raw)
    if candidate.is_absolute():
        resolved = candidate.resolve()
    else:
        resolved = (root / candidate).resolve()

    if not resolved.exists() or not resolved.is_dir():
        raise FileNotFoundError(f"working_directory does not exist: {resolved}")
    return resolved


def _normalize_yield_time_ms(raw: Any) -> int:
    if raw is None:
        return DEFAULT_YIELD_TIME_MS
    if isinstance(raw, bool) or not isinstance(raw, int) or raw < 1:
        raise ValueError("'yield_time_ms' must be a positive integer.")
    return min(raw, MAX_YIELD_TIME_MS)


def _normalize_compression(raw_compression: Any) -> bool:
    if not isinstance(raw_compression, bool):
        raise ValueError("'compression' must be a boolean.")
    return raw_compression


def _compress_output(text: str, *, enabled: bool) -> str:
    if not enabled or not text:
        return text
    try:
        return decode_output(compress_text(text, backend="auto"))
    except Exception:
        return text


def _content_signature(text: str) -> str:
    """Return text with cosmetic differences removed.

    Used to tell lossy compression (summarized or omitted content) apart from
    whitespace-only cleanup: ANSI escapes and all whitespace are ignored.
    """
    return "".join(_ANSI_ESCAPE_RE.sub("", text).split())


def _is_lossy_compression(raw: str, compressed: str) -> bool:
    if raw == compressed:
        return False
    return _content_signature(raw) != _content_signature(compressed)


def _build_output_payload(
    *,
    stdout: str,
    stderr: str,
    compression: bool,
    save_raw: bool = True,
) -> dict[str, Any]:
    raw_stdout = stdout
    raw_stderr = stderr
    stdout = _compress_output(stdout, enabled=compression)
    stderr = _compress_output(stderr, enabled=compression)
    stdout_compressed = _is_lossy_compression(raw_stdout, stdout)
    stderr_compressed = _is_lossy_compression(raw_stderr, stderr)
    bounded_stdout, stdout_truncated = bound_output(
        stdout,
        limit=MAX_STDOUT_CHARS,
    )
    bounded_stderr, stderr_truncated = bound_output(
        stderr,
        limit=MAX_STDERR_CHARS,
    )
    payload: dict[str, Any] = {
        "stdout": bounded_stdout,
        "stderr": bounded_stderr,
    }
    if stdout_compressed:
        payload["stdout_compressed"] = True
    if stderr_compressed:
        payload["stderr_compressed"] = True
    if stdout_truncated:
        payload["stdout_truncated"] = True
    if stderr_truncated:
        payload["stderr_truncated"] = True
    compressed = stdout_compressed or stderr_compressed
    truncated = stdout_truncated or stderr_truncated
    if save_raw and (compressed or truncated):
        raw_path = save_raw_output(stdout=raw_stdout, stderr=raw_stderr)
        if raw_path is not None:
            payload["raw_output_path"] = str(raw_path)
            payload["notice"] = raw_output_notice(
                compressed=compressed, truncated=truncated
            )
    return payload
