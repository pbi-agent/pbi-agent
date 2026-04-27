"""Custom ``shell`` tool – executes shell commands in a subprocess.

This replaces the provider-specific native shell tools (OpenAI ``shell``,
Anthropic ``bash``) with a single, provider-agnostic function tool that goes
through the normal tool registry and execution pipeline.
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any

from pbi_agent.tools.output import MAX_OUTPUT_CHARS as DEFAULT_MAX_OUTPUT_CHARS
from pbi_agent.tools.output import bound_output, decode_output
from pbi_agent.tools.types import ToolContext, ToolSpec

MAX_TIMEOUT_MS = 120_000
MAX_STDOUT_CHARS = 12_000
MAX_STDERR_CHARS = 12_000
MAX_OUTPUT_CHARS = DEFAULT_MAX_OUTPUT_CHARS

SPEC = ToolSpec(
    name="shell",
    description=(
        "Run a shell command in the workspace. Returns stdout, stderr, and "
        "exit code. Use shell for file discovery with bounded commands such as "
        "`rg --files | sed -n '1,200p'`, `find . -maxdepth 2 -type f`, "
        "and content search via `rg -n 'pattern'`."
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
                    "Working directory for the command, relative to the "
                    "workspace root. Defaults to the workspace root."
                ),
            },
            "timeout_ms": {
                "type": "integer",
                "description": (
                    "Timeout in milliseconds (max 120 000). "
                    "Defaults to 120 000 (2 minutes)."
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

    root = Path.cwd().resolve()
    working_directory = _resolve_working_directory(
        root, arguments.get("working_directory")
    )
    timeout_ms = _normalize_timeout_ms(arguments.get("timeout_ms"))

    try:
        completed = subprocess.run(
            command,
            cwd=str(working_directory),
            capture_output=True,
            text=False,
            shell=True,
            timeout=(timeout_ms / 1000.0),
        )
        return {
            **_build_output_payload(
                stdout=decode_output(completed.stdout),
                stderr=decode_output(completed.stderr),
            ),
            "exit_code": completed.returncode,
        }
    except subprocess.TimeoutExpired as exc:
        return {
            **_build_output_payload(
                stdout=decode_output(exc.stdout),
                stderr=decode_output(exc.stderr),
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

    try:
        resolved.relative_to(root)
    except ValueError as exc:
        raise ValueError(
            f"working_directory outside workspace is not allowed: {raw}"
        ) from exc

    if not resolved.exists() or not resolved.is_dir():
        raise FileNotFoundError(f"working_directory does not exist: {resolved}")
    return resolved


def _normalize_timeout_ms(raw_timeout: Any) -> int:
    if raw_timeout is None:
        return MAX_TIMEOUT_MS
    if not isinstance(raw_timeout, int):
        return MAX_TIMEOUT_MS
    if raw_timeout < 1:
        return MAX_TIMEOUT_MS
    return min(raw_timeout, MAX_TIMEOUT_MS)


def _build_output_payload(*, stdout: str, stderr: str) -> dict[str, Any]:
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
