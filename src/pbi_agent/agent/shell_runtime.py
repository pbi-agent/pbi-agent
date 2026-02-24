from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pbi_agent.models.messages import ShellCall

MAX_TIMEOUT_MS = 120000


@dataclass(slots=True)
class ShellExecutionResult:
    call_id: str
    output_chunks: list[dict[str, Any]]
    max_output_length: int | None
    is_error: bool


def execute_shell_calls(
    calls: list[ShellCall],
    *,
    workspace_root: Path | None = None,
) -> tuple[list[dict[str, Any]], bool]:
    root = (workspace_root or Path.cwd()).resolve()
    results = [_execute_one(call, root=root) for call in calls]

    output_items: list[dict[str, Any]] = []
    for result in results:
        item: dict[str, Any] = {
            "type": "shell_call_output",
            "call_id": result.call_id,
            "output": result.output_chunks,
        }
        if result.max_output_length is not None:
            item["max_output_length"] = result.max_output_length
        output_items.append(item)

    had_errors = any(result.is_error for result in results)
    return output_items, had_errors


def _execute_one(call: ShellCall, *, root: Path) -> ShellExecutionResult:
    try:
        commands = _extract_commands(call.action)
        timeout_ms = _normalize_timeout_ms(call.action.get("timeout_ms"))
        working_directory = _resolve_working_directory(
            root, call.action.get("working_directory")
        )
        env = _build_env(call.action.get("env"))
        max_output_length = _normalize_optional_positive_int(
            call.action.get("max_output_length")
        )

        output_chunks: list[dict[str, Any]] = []
        had_non_zero_exit = False
        for command in commands:
            try:
                completed = subprocess.run(
                    command,
                    cwd=str(working_directory),
                    env=env,
                    capture_output=True,
                    text=False,
                    shell=True,
                    timeout=(timeout_ms / 1000.0),
                )
                stdout = _decode_output(completed.stdout)
                stderr = _decode_output(completed.stderr)
                output_chunks.append(
                    {
                        "stdout": stdout,
                        "stderr": stderr,
                        "outcome": {"type": "exit", "exit_code": completed.returncode},
                    }
                )
                had_non_zero_exit = had_non_zero_exit or (completed.returncode != 0)
            except subprocess.TimeoutExpired as exc:
                output_chunks.append(
                    {
                        "stdout": _decode_output(exc.stdout),  # type: ignore[attr-defined]
                        "stderr": _decode_output(exc.stderr),  # type: ignore[attr-defined]
                        "outcome": {"type": "timeout"},
                    }
                )
                return ShellExecutionResult(
                    call_id=call.call_id,
                    output_chunks=output_chunks,
                    max_output_length=max_output_length,
                    is_error=True,
                )

        return ShellExecutionResult(
            call_id=call.call_id,
            output_chunks=output_chunks,
            max_output_length=max_output_length,
            is_error=had_non_zero_exit,
        )
    except Exception as exc:
        return ShellExecutionResult(
            call_id=call.call_id,
            output_chunks=[
                {
                    "stdout": "",
                    "stderr": f"shell execution failed: {exc}",
                    "outcome": {"type": "exit", "exit_code": 1},
                }
            ],
            max_output_length=_normalize_optional_positive_int(
                call.action.get("max_output_length")
            ),
            is_error=True,
        )


def _extract_commands(action: dict[str, Any]) -> list[str]:
    commands = action.get("commands")
    if not isinstance(commands, list) or not commands:
        raise ValueError("shell action.commands must be a non-empty array of strings")
    for command in commands:
        if not isinstance(command, str) or not command.strip():
            raise ValueError("shell action.commands must contain non-empty strings")
    return commands


def _normalize_timeout_ms(raw_timeout: Any) -> int:
    if raw_timeout is None:
        return MAX_TIMEOUT_MS
    if not isinstance(raw_timeout, int):
        raise ValueError("shell action.timeout_ms must be an integer")
    if raw_timeout < 1:
        raise ValueError("shell action.timeout_ms must be >= 1")
    return min(raw_timeout, MAX_TIMEOUT_MS)


def _resolve_working_directory(root: Path, raw_working_directory: Any) -> Path:
    if raw_working_directory is None:
        return root
    if not isinstance(raw_working_directory, str) or not raw_working_directory.strip():
        raise ValueError(
            "shell action.working_directory must be a non-empty string when provided"
        )

    candidate = Path(raw_working_directory)
    if candidate.is_absolute():
        resolved = candidate.resolve()
    else:
        resolved = (root / candidate).resolve()

    try:
        resolved.relative_to(root)
    except ValueError as exc:
        raise ValueError(
            f"working_directory outside workspace is not allowed: {raw_working_directory}"
        ) from exc

    if not resolved.exists() or not resolved.is_dir():
        raise FileNotFoundError(f"working_directory does not exist: {resolved}")
    return resolved


def _build_env(raw_env: Any) -> dict[str, str]:
    if raw_env is None:
        return dict(os.environ)
    if not isinstance(raw_env, dict):
        raise ValueError("shell action.env must be an object when provided")
    env = dict(os.environ)
    for key, value in raw_env.items():
        if not isinstance(key, str):
            raise ValueError("shell action.env keys must be strings")
        if not isinstance(value, str):
            raise ValueError(f"shell action.env['{key}'] must be a string")
        env[key] = value
    return env


def _normalize_optional_positive_int(value: Any) -> int | None:
    if value is None:
        return None
    if not isinstance(value, int) or value < 1:
        raise ValueError("max_output_length must be a positive integer when provided")
    return value


def _decode_output(value: bytes | str | None) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    # Prefer UTF-8 and never fail on undecodable bytes.
    return value.decode("utf-8", errors="replace")  # type: ignore[union-attr]
