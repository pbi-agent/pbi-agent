"""Custom ``python_exec`` tool – executes Python snippets in a child process."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

from pbi_agent.tools.output import bound_output
from pbi_agent.tools.types import ToolContext, ToolSpec
from pbi_agent.tools.workspace_access import normalize_positive_int, resolve_safe_path

DEFAULT_TIMEOUT_SECONDS = 30
MAX_TIMEOUT_SECONDS = 120
MAX_STDOUT_CHARS = 12_000
MAX_STDERR_CHARS = 12_000
MAX_RESULT_CHARS = 20_000

SPEC = ToolSpec(
    name="python_exec",
    description=(
        "Execute trusted local Python code in a subprocess using the same "
        "interpreter and environment as the CLI. Commands run inside the "
        "workspace directory by default and can optionally return a structured "
        "top-level `result` value."
    ),
    parameters_schema={
        "type": "object",
        "properties": {
            "code": {
                "type": "string",
                "description": "Python source code to execute.",
            },
            "working_directory": {
                "type": "string",
                "description": (
                    "Working directory for the snippet, relative to the "
                    "workspace root. Defaults to the workspace root."
                ),
            },
            "timeout_seconds": {
                "type": "integer",
                "description": (
                    "Execution timeout in seconds, capped at 120. "
                    "Defaults to 30."
                ),
            },
            "capture_result": {
                "type": "boolean",
                "description": (
                    "When true, return the top-level `result` variable if the "
                    "snippet defines one and it is JSON-serializable."
                ),
            },
        },
        "required": ["code"],
        "additionalProperties": False,
    },
    is_destructive=True,
)

_WRAPPER_SCRIPT = """
from __future__ import annotations

import json
import os
import sys
import traceback
from pathlib import Path

request_path = Path(sys.argv[1])
response_path = Path(sys.argv[2])
request = json.loads(request_path.read_text(encoding="utf-8"))

namespace = {"__name__": "__main__"}
response = {
    "ok": True,
    "error_type": None,
    "error_message": None,
    "result": None,
    "result_present": False,
    "serialization_error": None,
}

cwd = os.getcwd()
if cwd not in sys.path:
    sys.path.insert(0, cwd)

try:
    exec(compile(request["code"], "<python_exec>", "exec"), namespace)
    if request.get("capture_result") and "result" in namespace:
        response["result_present"] = True
        try:
            json.dumps(namespace["result"])
        except TypeError as exc:
            response["serialization_error"] = (
                "Failed to serialize `result` as JSON: "
                f"{type(exc).__name__}: {exc}"
            )
        else:
            response["result"] = namespace["result"]
except BaseException as exc:
    response["ok"] = False
    response["error_type"] = type(exc).__name__
    response["error_message"] = str(exc)
    traceback.print_exc(file=sys.stderr)

response_path.write_text(json.dumps(response), encoding="utf-8")
"""


def handle(arguments: dict[str, Any], context: ToolContext) -> dict[str, Any]:
    """Execute Python code and return bounded structured output."""
    del context

    code = arguments.get("code")
    if not isinstance(code, str) or not code.strip():
        return _failure_result(
            error_type="ValueError",
            error_message="'code' must be a non-empty string.",
        )

    root = Path.cwd().resolve()
    try:
        working_directory = _resolve_working_directory(root, arguments.get("working_directory"))
    except Exception as exc:
        return _failure_result(
            error_type=type(exc).__name__,
            error_message=str(exc),
        )

    timeout_seconds = _normalize_timeout_seconds(arguments.get("timeout_seconds"))
    capture_result = bool(arguments.get("capture_result", False))
    started_at = time.monotonic()

    try:
        with tempfile.TemporaryDirectory(prefix="pbi-agent-python-exec-") as temp_dir:
            temp_path = Path(temp_dir)
            request_path = temp_path / "request.json"
            response_path = temp_path / "response.json"
            runner_path = temp_path / "runner.py"

            request_path.write_text(
                json.dumps(
                    {
                        "code": code,
                        "capture_result": capture_result,
                    }
                ),
                encoding="utf-8",
            )
            runner_path.write_text(_WRAPPER_SCRIPT, encoding="utf-8")

            completed = subprocess.run(
                [sys.executable, str(runner_path), str(request_path), str(response_path)],
                cwd=str(working_directory),
                env=dict(os.environ),
                capture_output=True,
                text=False,
                timeout=float(timeout_seconds),
            )
            return _completed_result(
                completed=completed,
                response_path=response_path,
                capture_result=capture_result,
                execution_time_ms=_elapsed_ms(started_at),
            )
    except subprocess.TimeoutExpired as exc:
        return _timeout_result(
            exc=exc,
            timeout_seconds=timeout_seconds,
            execution_time_ms=_elapsed_ms(started_at),
        )
    except Exception as exc:
        return _failure_result(
            stdout="",
            stderr=str(exc),
            error_type=type(exc).__name__,
            error_message=str(exc),
            execution_time_ms=_elapsed_ms(started_at),
        )


def _resolve_working_directory(root: Path, raw: Any) -> Path:
    resolved = resolve_safe_path(root, raw, default=".")
    if not resolved.exists() or not resolved.is_dir():
        raise FileNotFoundError(f"working_directory does not exist: {resolved}")
    return resolved


def _normalize_timeout_seconds(raw_timeout: Any) -> int:
    return normalize_positive_int(
        raw_timeout,
        default=DEFAULT_TIMEOUT_SECONDS,
        upper_bound=MAX_TIMEOUT_SECONDS,
    )


def _completed_result(
    *,
    completed: subprocess.CompletedProcess[bytes],
    response_path: Path,
    capture_result: bool,
    execution_time_ms: int,
) -> dict[str, Any]:
    stdout = _decode_output(completed.stdout)
    stderr = _decode_output(completed.stderr)
    response = _read_response_payload(response_path)

    ok = completed.returncode == 0
    error_type: str | None = None
    error_message: str | None = None
    result: Any = None
    result_truncated = False

    if response is not None:
        ok = bool(response.get("ok", ok))
        error_type = _optional_str(response.get("error_type"))
        error_message = _optional_str(response.get("error_message"))
        serialization_error = _optional_str(response.get("serialization_error"))
        if serialization_error:
            stderr = _append_stderr(stderr, serialization_error)
        if capture_result and response.get("result_present"):
            result, result_truncated = _bound_result(response.get("result"))
    elif completed.returncode != 0:
        error_type = "RuntimeError"
        error_message = f"Python execution failed with exit code {completed.returncode}"

    bounded_stdout, stdout_truncated = bound_output(stdout, limit=MAX_STDOUT_CHARS)
    bounded_stderr, stderr_truncated = bound_output(stderr, limit=MAX_STDERR_CHARS)

    return {
        "ok": ok,
        "stdout": bounded_stdout,
        "stderr": bounded_stderr,
        "result": result,
        "error_type": error_type,
        "error_message": error_message,
        "timed_out": False,
        "execution_time_ms": execution_time_ms,
        "stdout_truncated": stdout_truncated,
        "stderr_truncated": stderr_truncated,
        "result_truncated": result_truncated,
    }


def _timeout_result(
    *,
    exc: subprocess.TimeoutExpired,
    timeout_seconds: int,
    execution_time_ms: int,
) -> dict[str, Any]:
    bounded_stdout, stdout_truncated = bound_output(
        _decode_output(exc.stdout),
        limit=MAX_STDOUT_CHARS,
    )
    bounded_stderr, stderr_truncated = bound_output(
        _decode_output(exc.stderr),
        limit=MAX_STDERR_CHARS,
    )
    return {
        "ok": False,
        "stdout": bounded_stdout,
        "stderr": bounded_stderr,
        "result": None,
        "error_type": "TimeoutError",
        "error_message": f"Execution exceeded timeout of {timeout_seconds} seconds",
        "timed_out": True,
        "execution_time_ms": execution_time_ms,
        "stdout_truncated": stdout_truncated,
        "stderr_truncated": stderr_truncated,
        "result_truncated": False,
    }


def _failure_result(
    *,
    error_type: str,
    error_message: str,
    stdout: str = "",
    stderr: str = "",
    execution_time_ms: int = 0,
) -> dict[str, Any]:
    bounded_stdout, stdout_truncated = bound_output(stdout, limit=MAX_STDOUT_CHARS)
    final_stderr = _append_stderr(stderr, error_message) if error_message and not stderr else stderr
    bounded_stderr, stderr_truncated = bound_output(final_stderr, limit=MAX_STDERR_CHARS)
    return {
        "ok": False,
        "stdout": bounded_stdout,
        "stderr": bounded_stderr,
        "result": None,
        "error_type": error_type,
        "error_message": error_message,
        "timed_out": False,
        "execution_time_ms": execution_time_ms,
        "stdout_truncated": stdout_truncated,
        "stderr_truncated": stderr_truncated,
        "result_truncated": False,
    }


def _decode_output(value: bytes | str | None) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    return value.decode("utf-8", errors="replace")


def _elapsed_ms(started_at: float) -> int:
    return int((time.monotonic() - started_at) * 1000)


def _read_response_payload(response_path: Path) -> dict[str, Any] | None:
    if not response_path.exists():
        return None
    try:
        payload = json.loads(response_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return payload if isinstance(payload, dict) else None


def _bound_result(value: Any) -> tuple[Any, bool]:
    serialized = json.dumps(value)
    bounded_result, was_truncated = bound_output(serialized, limit=MAX_RESULT_CHARS)
    if not was_truncated:
        return value, False
    return bounded_result, True


def _append_stderr(stderr: str, message: str) -> str:
    if not stderr:
        return message
    if stderr.endswith("\n"):
        return f"{stderr}{message}"
    return f"{stderr}\n{message}"


def _optional_str(value: Any) -> str | None:
    return value if isinstance(value, str) and value else None
