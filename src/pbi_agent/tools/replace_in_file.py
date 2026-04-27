"""Provider-agnostic old/new-string file edit tool."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from pbi_agent.tools.file_edit import (
    build_applied_file_edit_result,
    resolve_safe_path,
    store_display_metadata,
)
from pbi_agent.tools.output import bound_output
from pbi_agent.tools.text_replace import replace_text
from pbi_agent.tools.types import ToolContext, ToolSpec

SPEC = ToolSpec(
    name="replace_in_file",
    description=(
        "Replace a unique text block in one workspace file. Use after read_file for targeted edits; "
        "include enough old_string context to make the match unique."
    ),
    parameters_schema={
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": (
                    "File path relative to the workspace root "
                    "(or absolute within workspace)."
                ),
            },
            "old_string": {
                "type": "string",
                "description": (
                    "Existing text block to replace. Include enough exact "
                    "surrounding context to match one location."
                ),
            },
            "new_string": {
                "type": "string",
                "description": "Replacement text for the matched block.",
            },
            "replace_all": {
                "type": "boolean",
                "description": (
                    "Replace every matching occurrence instead of requiring a "
                    "unique match. Defaults to false."
                ),
                "default": False,
            },
        },
        "required": ["path", "old_string", "new_string"],
        "additionalProperties": False,
    },
    is_destructive=True,
)


def handle(arguments: dict[str, Any], context: ToolContext) -> dict[str, Any]:
    path_value = arguments.get("path", "")
    old_string = arguments.get("old_string")
    new_string = arguments.get("new_string")
    replace_all = arguments.get("replace_all", False)

    if not isinstance(path_value, str) or not path_value.strip():
        return {"error": "'path' must be a non-empty string."}
    if not isinstance(old_string, str):
        return {"error": "'old_string' must be a string."}
    if not isinstance(new_string, str):
        return {"error": "'new_string' must be a string."}
    if not isinstance(replace_all, bool):
        return {"error": "'replace_all' must be a boolean."}

    root = Path.cwd().resolve()

    try:
        target_path = resolve_safe_path(root, path_value)
        if not target_path.exists():
            raise FileNotFoundError(f"file not found: {target_path}")
        if target_path.is_dir():
            raise IsADirectoryError(f"path is a directory: {target_path}")

        original_content = target_path.read_text(encoding="utf-8")
        replacement = replace_text(
            original_content,
            old_string,
            new_string,
            replace_all=replace_all,
        )
        applied = build_applied_file_edit_result(
            original_content,
            replacement.content,
            operation_type="update_file",
            warnings=replacement.warnings,
        )

        target_path.write_text(applied.new_content, encoding="utf-8")
        store_display_metadata(context, "update_file", path_value, applied)

        result: dict[str, Any] = {
            "status": "completed",
            "message": f"replace_in_file succeeded for '{path_value}'",
            "replacements": replacement.replacements,
        }
        if applied.warnings:
            result["warnings"] = list(applied.warnings)
        return result
    except Exception as exc:
        return {
            "status": "failed",
            "error": bound_output(str(exc))[0],
        }
