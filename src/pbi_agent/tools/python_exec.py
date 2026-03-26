"""Custom ``python_exec`` tool – executes Python snippets in a child process."""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

from pbi_agent.tools.output import bound_output, decode_output
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
        "Run Python code locally in the workspace. "
        "Use for data analysis, file parsing, calculations, and transformations. "
        "Has pandas, pypdf, python-docx, and stdlib. "
        "Can return a top-level `result` variable."
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
                    "Execution timeout in seconds, capped at 120. Defaults to 30."
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
    "result_truncated": False,
    "serialization_error": None,
}

TRUNCATED_DICT_KEY = "__pbi_agent_truncated__"

cwd = os.getcwd()
if cwd not in sys.path:
    sys.path.insert(0, cwd)


def _bound_text(text: str, *, limit: int) -> tuple[str, bool]:
    if len(text) <= limit:
        return text, False
    if limit <= 0:
        return "", True

    omitted_chars = len(text) - limit
    while True:
        marker = f" ... {omitted_chars} chars omitted ... "
        available = limit - len(marker)
        if available <= 0:
            return text[: max(limit - 1, 0)] + ("..." if limit > 0 else ""), True

        head = available // 2 + available % 2
        tail = available // 2
        new_omitted_chars = len(text) - head - tail
        if new_omitted_chars == omitted_chars:
            return f"{text[:head]}{marker}{text[-tail:] if tail else ''}", True
        omitted_chars = new_omitted_chars


def _json_size(value) -> int:
    return len(json.dumps(value))


def _truncate_string(value: str, *, limit: int) -> str:
    if _json_size(value) <= limit:
        return value

    bounded, _ = _bound_text(value, limit=max(limit - 2, 1))
    while _json_size(bounded) > limit and bounded:
        bounded = bounded[:-1]
    return bounded


def _truncate_list(value: list[object], *, limit: int):
    marker_template = "... {count} items omitted ..."
    items: list[object] = []

    for index, item in enumerate(value):
        remaining = len(value) - index - 1
        item_limit = max(64, limit // max(index + 2, 2))
        truncated_item, _ = _truncate_json_value(item, limit=item_limit)
        items.append(truncated_item)

        candidate = list(items)
        if remaining:
            candidate.append(marker_template.format(count=remaining))
        if _json_size(candidate) > limit:
            items.pop()
            break

    omitted = len(value) - len(items)
    candidate = list(items)
    if omitted:
        candidate.append(marker_template.format(count=omitted))

    while _json_size(candidate) > limit and items:
        items.pop()
        omitted = len(value) - len(items)
        candidate = list(items)
        if omitted:
            candidate.append(marker_template.format(count=omitted))

    if _json_size(candidate) <= limit:
        return candidate

    marker_only = [marker_template.format(count=len(value))]
    return marker_only if _json_size(marker_only) <= limit else []


def _truncate_dict(value: dict[str, object], *, limit: int):
    items: dict[str, object] = {}
    marker_key = TRUNCATED_DICT_KEY
    while marker_key in value:
        marker_key = f"_{marker_key}"

    source_items = list(value.items())
    for index, (key, item) in enumerate(source_items):
        remaining = len(source_items) - index - 1
        item_limit = max(96, limit // max(index + 2, 2))
        truncated_item, _ = _truncate_json_value(item, limit=item_limit)
        items[key] = truncated_item

        candidate = dict(items)
        if remaining:
            suffix = "s" if remaining != 1 else ""
            candidate[marker_key] = f"{remaining} item{suffix} omitted"
        if _json_size(candidate) > limit:
            items.pop(key)
            break

    omitted = len(source_items) - len(items)
    candidate = dict(items)
    if omitted:
        suffix = "s" if omitted != 1 else ""
        candidate[marker_key] = f"{omitted} item{suffix} omitted"

    while _json_size(candidate) > limit and items:
        last_key = next(reversed(items))
        items.pop(last_key)
        omitted = len(source_items) - len(items)
        candidate = dict(items)
        if omitted:
            suffix = "s" if omitted != 1 else ""
            candidate[marker_key] = f"{omitted} item{suffix} omitted"

    if _json_size(candidate) <= limit:
        return candidate

    marker_only = {marker_key: f"{len(source_items)} items omitted"}
    return marker_only if _json_size(marker_only) <= limit else {}


def _truncate_json_value(value, *, limit: int):
    if _json_size(value) <= limit:
        return value, False

    if isinstance(value, str):
        return _truncate_string(value, limit=limit), True
    if isinstance(value, list):
        return _truncate_list(value, limit=limit), True
    if isinstance(value, dict):
        return _truncate_dict(value, limit=limit), True

    return value, False


try:
    exec(compile(request["code"], "<python_exec>", "exec"), namespace)
    if request.get("capture_result") and "result" in namespace:
        response["result_present"] = True
        response["result"], response["result_truncated"] = _truncate_json_value(
            namespace["result"],
            limit=max(int(request.get("max_result_chars", 0) or 0), 1),
        )
except SystemExit as exc:
    exit_code = exc.code
    if exit_code in (None, 0):
        response["ok"] = True
        response["error_type"] = None
        response["error_message"] = None
    else:
        response["ok"] = False
        response["error_type"] = "SystemExit"
        response["error_message"] = str(exit_code)
        if isinstance(exit_code, str):
            print(exit_code, file=sys.stderr)
except TypeError as exc:
    response["serialization_error"] = (
        "Failed to serialize `result` as JSON: "
        f"{type(exc).__name__}: {exc}"
    )
    response["result_present"] = False
    response["result"] = None
    response["result_truncated"] = False
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
        working_directory = _resolve_working_directory(
            root, arguments.get("working_directory")
        )
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
                        "max_result_chars": MAX_RESULT_CHARS,
                    }
                ),
                encoding="utf-8",
            )
            runner_path.write_text(_WRAPPER_SCRIPT, encoding="utf-8")

            completed = subprocess.run(
                [
                    sys.executable,
                    str(runner_path),
                    str(request_path),
                    str(response_path),
                ],
                cwd=str(working_directory),
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
    stdout = decode_output(completed.stdout)
    stderr = decode_output(completed.stderr)
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
            result = response.get("result")
            result_truncated = bool(response.get("result_truncated", False))
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
        decode_output(exc.stdout),
        limit=MAX_STDOUT_CHARS,
    )
    bounded_stderr, stderr_truncated = bound_output(
        decode_output(exc.stderr),
        limit=MAX_STDERR_CHARS,
    )
    return {
        "ok": False,
        "stdout": bounded_stdout,
        "stderr": bounded_stderr,
        "result": None,
        "error_type": "TimeoutError",
        "error_message": (
            "Execution exceeded timeout of "
            f"{timeout_seconds} second{'s' if timeout_seconds != 1 else ''}"
        ),
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
    final_stderr = (
        _append_stderr(stderr, error_message)
        if error_message and not stderr
        else stderr
    )
    bounded_stderr, stderr_truncated = bound_output(
        final_stderr, limit=MAX_STDERR_CHARS
    )
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


def _elapsed_ms(started_at: float) -> int:
    return int((time.monotonic() - started_at) * 1000)


def _read_response_payload(response_path: Path) -> dict[str, Any] | None:
    try:
        payload = json.loads(response_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return payload if isinstance(payload, dict) else None


def _append_stderr(stderr: str, message: str) -> str:
    if not stderr:
        return message
    if stderr.endswith("\n"):
        return f"{stderr}{message}"
    return f"{stderr}\n{message}"


def _optional_str(value: Any) -> str | None:
    return value if isinstance(value, str) and value else None
