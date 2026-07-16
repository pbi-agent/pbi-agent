"""Custom ``shell`` tool – executes shell commands in a subprocess.

This replaces the provider-specific native shell tools (OpenAI ``shell``,
Anthropic ``bash``) with a single, provider-agnostic function tool that goes
through the normal tool registry and execution pipeline.
"""

from __future__ import annotations

import os
import shlex
import signal
import subprocess
import time
from contextlib import suppress
from pathlib import Path
from typing import Any, cast

from codetool_shell import compress_text

from pbi_agent.tools.output import MAX_OUTPUT_CHARS as DEFAULT_MAX_OUTPUT_CHARS
from pbi_agent.tools.output import bound_output, decode_output
from pbi_agent.tools.types import ToolContext, ToolSpec

DEFAULT_TIMEOUT_MS = 30_000
MAX_TIMEOUT_MS = 300_000
MAX_STDOUT_CHARS = 12_000
MAX_STDERR_CHARS = 12_000
MAX_OUTPUT_CHARS = DEFAULT_MAX_OUTPUT_CHARS
INTERRUPT_POLL_SECONDS = 0.1
PROCESS_STOP_TIMEOUT_SECONDS = 5.0
SHELL_BOOTSTRAP_ENV = "PBI_AGENT_SHELL_BOOTSTRAP"
SHELL_EXECUTABLE_ENV = "PBI_AGENT_SHELL_EXECUTABLE"

SPEC = ToolSpec(
    name="shell",
    description=("Run a shell command. Returns stdout, stderr, and exit code."),
    prompt_usage=(
        "Use `shell` for command execution, including git commands; byte-cap "
        "commands with unknown or potentially large output."
    ),
    parameters_schema={
        "type": "object",
        "properties": {
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
            "timeout_ms": {
                "type": "integer",
                "description": (
                    "Timeout in milliseconds. Defaults to 30 000 (30 seconds), "
                    "maximum 300 000 (5 minutes)."
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
        "required": ["command"],
        "additionalProperties": False,
    },
    is_destructive=True,
)


def handle(arguments: dict[str, Any], context: ToolContext) -> dict[str, Any]:
    """Execute a single shell command and return structured output."""
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
    try:
        timeout_ms = _normalize_timeout_ms(arguments.get("timeout_ms"))
    except ValueError as exc:
        return {"error": str(exc)}

    effective_command = _bootstrap_command(command)
    shell_executable = os.environ.get(SHELL_EXECUTABLE_ENV) or None

    try:
        if isinstance(context, ToolContext) and context.display is not None:
            return _run_interruptible(
                effective_command,
                working_directory=working_directory,
                shell_executable=shell_executable,
                timeout_ms=timeout_ms,
                compression=compression,
                context=context,
            )
        completed = subprocess.run(
            effective_command,
            cwd=str(working_directory),
            capture_output=True,
            text=False,
            shell=True,
            executable=shell_executable,
            timeout=(timeout_ms / 1000.0),
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
        return {
            **_build_output_payload(
                stdout=decode_output(exc.stdout),
                stderr=decode_output(exc.stderr),
                compression=compression,
            ),
            "exit_code": None,
            "timed_out": True,
            "error": f"Command timed out after {timeout_ms}ms.",
        }
    except Exception as exc:
        stderr, stderr_truncated = bound_output(str(exc))
        return {
            "stdout": "",
            "stderr": stderr,
            "exit_code": 1,
            "error": f"Shell execution failed: {exc}",
            **({"stderr_truncated": True} if stderr_truncated else {}),
        }


def _run_interruptible(
    command: str,
    *,
    working_directory: Path,
    shell_executable: str | None,
    timeout_ms: int,
    compression: bool,
    context: ToolContext,
) -> dict[str, Any]:
    if _interrupt_requested(context):
        return _interrupted_payload(stdout=b"", stderr=b"", compression=compression)

    popen_kwargs: dict[str, Any] = {}
    if os.name == "nt":
        popen_kwargs["creationflags"] = getattr(
            subprocess,
            "CREATE_NEW_PROCESS_GROUP",
            0,
        )
    else:
        popen_kwargs["start_new_session"] = True

    process = cast(
        subprocess.Popen[bytes],
        subprocess.Popen(
            command,
            cwd=str(working_directory),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=False,
            shell=True,
            executable=shell_executable,
            **popen_kwargs,
        ),
    )
    deadline = time.monotonic() + (timeout_ms / 1000.0)
    try:
        while True:
            if _interrupt_requested(context):
                stdout, stderr = _stop_process(process)
                return _interrupted_payload(
                    stdout=stdout,
                    stderr=stderr,
                    compression=compression,
                )

            remaining = deadline - time.monotonic()
            if remaining <= 0:
                stdout, stderr = _stop_process(process)
                return {
                    **_build_output_payload(
                        stdout=decode_output(stdout),
                        stderr=decode_output(stderr),
                        compression=compression,
                    ),
                    "exit_code": None,
                    "timed_out": True,
                    "error": f"Command timed out after {timeout_ms}ms.",
                }

            try:
                stdout, stderr = process.communicate(
                    timeout=min(INTERRUPT_POLL_SECONDS, remaining)
                )
            except subprocess.TimeoutExpired:
                continue
            return {
                **_build_output_payload(
                    stdout=decode_output(stdout),
                    stderr=decode_output(stderr),
                    compression=compression,
                ),
                "exit_code": process.returncode,
            }
    except BaseException:
        with suppress(Exception):
            _stop_process(process)
        raise


def _interrupt_requested(context: ToolContext) -> bool:
    display = context.display
    if display is None:
        return False
    if display.interrupt_requested():
        return True
    call_id = context.tool_call_id
    checker = getattr(display, "tool_interrupt_requested", None)
    return bool(call_id and callable(checker) and checker(call_id))


def _stop_process(process: subprocess.Popen[bytes]) -> tuple[bytes, bytes]:
    _kill_process_tree(process)
    try:
        return process.communicate(timeout=PROCESS_STOP_TIMEOUT_SECONDS)
    except subprocess.TimeoutExpired as exc:
        if process.poll() is None:
            process.kill()
        try:
            return process.communicate(timeout=INTERRUPT_POLL_SECONDS)
        except subprocess.TimeoutExpired as final_exc:
            _close_process_pipes(process)
            return (
                _timeout_stream(final_exc.stdout, fallback=exc.stdout),
                _timeout_stream(final_exc.stderr, fallback=exc.stderr),
            )


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


def _timeout_stream(
    value: bytes | str | None, *, fallback: bytes | str | None
) -> bytes:
    selected = value if value is not None else fallback
    if isinstance(selected, bytes):
        return selected
    if isinstance(selected, str):
        return selected.encode()
    return b""


def _interrupted_payload(
    *,
    stdout: bytes,
    stderr: bytes,
    compression: bool,
) -> dict[str, Any]:
    return {
        **_build_output_payload(
            stdout=decode_output(stdout),
            stderr=decode_output(stderr),
            compression=compression,
        ),
        "exit_code": 130,
        "interrupted": True,
        "error": "Command interrupted by user.",
    }


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


def _normalize_timeout_ms(raw_timeout: Any) -> int:
    if raw_timeout is None:
        return DEFAULT_TIMEOUT_MS
    if isinstance(raw_timeout, bool) or not isinstance(raw_timeout, int):
        raise ValueError("'timeout_ms' must be a positive integer.")
    if raw_timeout < 1:
        raise ValueError("'timeout_ms' must be a positive integer.")
    return min(raw_timeout, MAX_TIMEOUT_MS)


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


def _build_output_payload(
    *,
    stdout: str,
    stderr: str,
    compression: bool,
) -> dict[str, Any]:
    stdout = _compress_output(stdout, enabled=compression)
    stderr = _compress_output(stderr, enabled=compression)
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
    if stdout_truncated:
        payload["stdout_truncated"] = True
    if stderr_truncated:
        payload["stderr_truncated"] = True
    return payload
