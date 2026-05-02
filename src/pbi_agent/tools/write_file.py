"""Provider-agnostic full-file write tool."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from pbi_agent.tools.file_edit import (
    build_applied_file_edit_result,
    resolve_safe_path,
    store_display_metadata,
)
from pbi_agent.tools.output import bound_output
from pbi_agent.tools.types import ToolContext, ToolSpec

SPEC = ToolSpec(
    name="write_file",
    description=(
        "Write complete text content to one file, creating parent directories as needed. "
        "Best for new files, generated files, or small full-file rewrites."
    ),
    parameters_schema={
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": (
                    "File path relative to the workspace root (or absolute)."
                ),
            },
            "content": {
                "type": "string",
                "description": "Complete text content to write to the file.",
            },
        },
        "required": ["path", "content"],
        "additionalProperties": False,
    },
    is_destructive=True,
)


def handle(arguments: dict[str, Any], context: ToolContext) -> dict[str, Any]:
    path_value = arguments.get("path", "")
    content = arguments.get("content")

    if not isinstance(path_value, str) or not path_value.strip():
        return {"error": "'path' must be a non-empty string."}
    if not isinstance(content, str):
        return {"error": "'content' must be a string."}

    root = Path.cwd().resolve()

    try:
        target_path = resolve_safe_path(root, path_value)
        if target_path.is_dir():
            raise IsADirectoryError(f"path is a directory: {target_path}")

        original_content = (
            target_path.read_text(encoding="utf-8") if target_path.exists() else ""
        )
        operation_type = "update_file" if target_path.exists() else "create_file"
        applied = build_applied_file_edit_result(
            original_content,
            content,
            operation_type=operation_type,
        )

        target_path.parent.mkdir(parents=True, exist_ok=True)
        target_path.write_text(applied.new_content, encoding="utf-8")
        store_display_metadata(context, operation_type, path_value, applied)

        bytes_written = len(applied.new_content.encode("utf-8"))
        return {
            "status": "completed",
            "message": f"write_file succeeded for '{path_value}'",
            "bytes_written": bytes_written,
            "replaced_existing_file": operation_type == "update_file",
        }
    except Exception as exc:
        return {
            "status": "failed",
            "error": bound_output(str(exc))[0],
        }
