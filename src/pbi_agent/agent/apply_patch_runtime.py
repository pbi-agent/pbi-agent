from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pbi_agent.models.messages import ApplyPatchCall
from pbi_agent.tools.apply_diff import apply_diff


@dataclass(slots=True)
class ApplyPatchResult:
    call_id: str
    status: str
    output: str
    is_error: bool


def execute_apply_patch_calls(
    calls: list[ApplyPatchCall],
    *,
    workspace_root: Path | None = None,
) -> tuple[list[dict[str, Any]], bool]:
    root = (workspace_root or Path.cwd()).resolve()
    results = [_execute_one(call, root=root) for call in calls]
    output_items = [
        {
            "type": "apply_patch_call_output",
            "call_id": result.call_id,
            "status": result.status,
            "output": result.output,
        }
        for result in results
    ]
    had_errors = any(result.is_error for result in results)
    return output_items, had_errors


def _execute_one(call: ApplyPatchCall, *, root: Path) -> ApplyPatchResult:
    try:
        operation_type = call.operation.get("type")
        path_value = call.operation.get("path")
        if not isinstance(operation_type, str):
            raise ValueError("operation.type must be a string")
        if not isinstance(path_value, str) or not path_value.strip():
            raise ValueError("operation.path must be a non-empty string")

        target_path = _resolve_safe_path(root, path_value)
        if operation_type == "create_file":
            _create_file(target_path, call.operation)
        elif operation_type == "update_file":
            _update_file(target_path, call.operation)
        elif operation_type == "delete_file":
            _delete_file(target_path)
        else:
            raise ValueError(f"unsupported operation.type '{operation_type}'")

        return ApplyPatchResult(
            call_id=call.call_id,
            status="completed",
            output=f"{operation_type} succeeded for '{path_value}'",
            is_error=False,
        )
    except Exception as exc:
        return ApplyPatchResult(
            call_id=call.call_id,
            status="failed",
            output=str(exc),
            is_error=True,
        )


def _create_file(path: Path, operation: dict[str, Any]) -> None:
    if path.exists():
        raise FileExistsError(f"file already exists: {path}")
    diff = _require_diff(operation)
    content = apply_diff("", diff, mode="create")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _update_file(path: Path, operation: dict[str, Any]) -> None:
    if not path.exists():
        raise FileNotFoundError(f"file not found: {path}")
    diff = _require_diff(operation)
    current = path.read_text(encoding="utf-8")
    updated = apply_diff(current, diff, mode="default")
    path.write_text(updated, encoding="utf-8")


def _delete_file(path: Path) -> None:
    if not path.exists():
        raise FileNotFoundError(f"file not found: {path}")
    if path.is_dir():
        raise IsADirectoryError(f"path is a directory: {path}")
    path.unlink()


def _require_diff(operation: dict[str, Any]) -> str:
    diff = operation.get("diff")
    if not isinstance(diff, str) or not diff:
        raise ValueError("operation.diff must be a non-empty string")
    return diff


def _resolve_safe_path(root: Path, raw_path: str) -> Path:
    candidate = Path(raw_path)
    if candidate.is_absolute():
        resolved = candidate.resolve()
    else:
        resolved = (root / candidate).resolve()

    try:
        resolved.relative_to(root)
    except ValueError as exc:
        raise ValueError(f"path outside workspace is not allowed: {raw_path}") from exc

    return resolved
