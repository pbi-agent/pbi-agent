"""Custom ``shell`` tool – executes shell commands in a subprocess.

This replaces the provider-specific native shell tools (OpenAI ``shell``,
Anthropic ``bash``) with a single, provider-agnostic function tool that goes
through the normal tool registry and execution pipeline.
"""

from __future__ import annotations

import os
import shlex
import subprocess
from collections.abc import Callable, Mapping
from importlib import import_module
from pathlib import Path
from typing import Any

from pbi_agent.tools.output import MAX_OUTPUT_CHARS as DEFAULT_MAX_OUTPUT_CHARS
from pbi_agent.tools.output import bound_output, decode_output
from pbi_agent.tools.types import ToolContext, ToolSpec

DEFAULT_TIMEOUT_MS = 30_000
MAX_TIMEOUT_MS = 300_000
MAX_STDOUT_CHARS = 12_000
MAX_STDERR_CHARS = 12_000
MAX_OUTPUT_CHARS = DEFAULT_MAX_OUTPUT_CHARS
SHELL_BOOTSTRAP_ENV = "PBI_AGENT_SHELL_BOOTSTRAP"
SHELL_EXECUTABLE_ENV = "PBI_AGENT_SHELL_EXECUTABLE"
_HEADROOM_COMPRESS_CONTENT: Callable[..., Any] | None = None

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
                    "Whether to compress stdout/stderr before returning them. "
                    "Defaults to true. Set false when the full raw output is needed."
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
    try:
        compression = _normalize_compression(arguments.get("compression"))
    except ValueError as exc:
        return {"error": str(exc)}

    effective_command = _bootstrap_command(command)
    shell_executable = os.environ.get(SHELL_EXECUTABLE_ENV) or None

    try:
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
    if raw_compression is None:
        return True
    if isinstance(raw_compression, bool):
        return raw_compression
    raise ValueError("'compression' must be a boolean.")


def _build_output_payload(
    *,
    stdout: str,
    stderr: str,
    compression: bool = True,
) -> dict[str, Any]:
    if compression:
        stdout = _compress_stream(stdout)
        stderr = _compress_stream(stderr)
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


def _compress_stream(text: str) -> str:
    if not text:
        return text

    try:
        result = _compress_content(text)
        compressed = _extract_compressed_text(result)
        if compressed is None or compressed == "":
            raise ValueError("Headroom returned no compressed text.")
    except Exception:
        return text
    return compressed


def _compress_content(text: str) -> Any:
    global _HEADROOM_COMPRESS_CONTENT  # noqa: PLW0603
    if _HEADROOM_COMPRESS_CONTENT is None:
        module = import_module("headroom.compression")
        config_type = getattr(module, "UniversalCompressorConfig")
        compressor_type = getattr(module, "UniversalCompressor")
        config = config_type(use_kompress=False, ccr_enabled=False)
        compressor = compressor_type(config=config)
        compress = getattr(compressor, "compress")
        if not callable(compress):
            raise RuntimeError("headroom local compressor is not callable.")
        _HEADROOM_COMPRESS_CONTENT = compress
    return _HEADROOM_COMPRESS_CONTENT(text)


def _extract_compressed_text(result: Any) -> str | None:
    if isinstance(result, str):
        return result
    compressed = _field_value(result, "compressed")
    if not isinstance(compressed, str):
        return None
    return compressed


def _field_value(value: Any, key: str) -> Any:
    if isinstance(value, Mapping):
        return value.get(key)
    return getattr(value, key, None)
