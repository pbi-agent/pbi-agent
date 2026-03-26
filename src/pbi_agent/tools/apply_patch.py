"""Custom ``apply_patch`` tool – applies V4A diffs to workspace files.

This replaces the provider-specific native patch/editor tools (OpenAI
``apply_patch``, Anthropic ``str_replace_based_edit_tool``) with a single,
provider-agnostic function tool that goes through the normal tool registry
and execution pipeline.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from pbi_agent.tools.apply_diff import apply_diff
from pbi_agent.tools.output import bound_output
from pbi_agent.tools.types import ToolContext, ToolSpec

SPEC = ToolSpec(
    name="apply_patch",
    description="Create, update, or delete workspace files using V4A diff format.",
    parameters_schema={
        "type": "object",
        "properties": {
            "operation_type": {
                "type": "string",
                "enum": ["create_file", "update_file", "delete_file"],
                "description": "The type of file operation to perform.",
            },
            "path": {
                "type": "string",
                "description": (
                    "File path relative to the workspace root "
                    "(or absolute within workspace)."
                ),
            },
            "diff": {
                "type": "string",
                "description": (
                    "The V4A diff content. Required for create_file and "
                    "update_file operations. For create_file, lines must be "
                    "prefixed with '+'. For update_file, use context lines "
                    "(prefixed ' '), deletion lines ('-'), and insertion "
                    "lines ('+')."
                ),
            },
        },
        "required": ["operation_type", "path"],
        "additionalProperties": False,
    },
    is_destructive=True,
)


def handle(arguments: dict[str, Any], context: ToolContext) -> dict[str, Any]:
    """Execute a single file operation (create, update, or delete)."""
    operation_type = arguments.get("operation_type", "")
    path_value = arguments.get("path", "")
    diff = arguments.get("diff")

    if not isinstance(operation_type, str) or not operation_type:
        return {"error": "'operation_type' must be a non-empty string."}
    if not isinstance(path_value, str) or not path_value.strip():
        return {"error": "'path' must be a non-empty string."}

    root = Path.cwd().resolve()

    try:
        target_path = _resolve_safe_path(root, path_value)

        if operation_type == "create_file":
            _create_file(target_path, diff)
        elif operation_type == "update_file":
            _update_file(target_path, diff)
        elif operation_type == "delete_file":
            _delete_file(target_path)
        else:
            return {"error": f"Unsupported operation_type '{operation_type}'."}

        return {
            "status": "completed",
            "message": f"{operation_type} succeeded for '{path_value}'",
        }
    except Exception as exc:
        return {
            "status": "failed",
            "error": bound_output(str(exc))[0],
        }


# ---------------------------------------------------------------------------
# File operations
# ---------------------------------------------------------------------------


def _create_file(path: Path, diff: str | None) -> None:
    if path.exists():
        raise FileExistsError(f"file already exists: {path}")
    if not isinstance(diff, str) or not diff:
        raise ValueError("'diff' is required for create_file and must be non-empty.")
    content = apply_diff("", diff, mode="create")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _update_file(path: Path, diff: str | None) -> None:
    if not path.exists():
        raise FileNotFoundError(f"file not found: {path}")
    if not isinstance(diff, str) or not diff:
        raise ValueError("'diff' is required for update_file and must be non-empty.")
    current = path.read_text(encoding="utf-8")
    updated = apply_diff(current, diff, mode="default")
    path.write_text(updated, encoding="utf-8")


def _delete_file(path: Path) -> None:
    if not path.exists():
        raise FileNotFoundError(f"file not found: {path}")
    if path.is_dir():
        raise IsADirectoryError(f"path is a directory: {path}")
    path.unlink()


# ---------------------------------------------------------------------------
# Path safety
# ---------------------------------------------------------------------------


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
