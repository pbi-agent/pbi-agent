from __future__ import annotations

from pathlib import Path
from typing import Any

from pbi_agent.tools.output import bound_output
from pbi_agent.tools.types import ToolContext, ToolSpec
from pbi_agent.tools.workspace_access import DEFAULT_MAX_ENTRIES
from pbi_agent.tools.workspace_access import iter_directory_entries
from pbi_agent.tools.workspace_access import normalize_positive_int
from pbi_agent.tools.workspace_access import relative_workspace_path
from pbi_agent.tools.workspace_access import resolve_safe_path

SPEC = ToolSpec(
    name="list_files",
    description=(
        "List files and directories within the workspace. "
        "Use this for general directory listing only. "
        "For filename or glob searches, use find_files instead."
    ),
    parameters_schema={
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": (
                    "Directory or file path relative to the workspace root "
                    "(or absolute within workspace). Defaults to '.'."
                ),
            },
            "recursive": {
                "type": "boolean",
                "description": "Whether to traverse subdirectories recursively.",
                "default": True,
            },
            "max_entries": {
                "type": "integer",
                "description": "Maximum number of entries to return. Defaults to 200.",
            },
        },
        "additionalProperties": False,
    },
)


def handle(arguments: dict[str, Any], context: ToolContext) -> dict[str, Any]:
    del context
    root = Path.cwd().resolve()

    try:
        target_path = resolve_safe_path(root, arguments.get("path"))
        recursive = arguments.get("recursive", True)
        max_entries = normalize_positive_int(
            arguments.get("max_entries"),
            default=DEFAULT_MAX_ENTRIES,
        )

        if not target_path.exists():
            return {"error": f"path not found: {target_path}"}

        if target_path.is_file():
            entry = _build_entry(root, target_path)
            entry, path_truncated = _bound_entry_path(entry)
            return {
                "path": relative_workspace_path(root, target_path),
                "recursive": False,
                "entries": [entry],
                "returned_entries": 1,
                "total_entries": 1,
                "has_more": False,
                **({"path_truncated": True} if path_truncated else {}),
            }

        if not target_path.is_dir():
            return {"error": f"path is not a regular file or directory: {target_path}"}

        matching_entries: list[dict[str, Any]] = []
        entries_truncated = False
        for candidate in iter_directory_entries(target_path, recursive=bool(recursive)):
            resolved_candidate = candidate.resolve(strict=False)
            try:
                resolved_candidate.relative_to(root)
            except ValueError:
                continue
            if len(matching_entries) >= max_entries:
                entries_truncated = True
                break
            entry = _build_entry(root, resolved_candidate)
            bounded_entry, path_truncated = _bound_entry_path(entry)
            if path_truncated:
                bounded_entry["path_truncated"] = True
            matching_entries.append(bounded_entry)

        result: dict[str, Any] = {
            "path": relative_workspace_path(root, target_path),
            "recursive": bool(recursive),
            "entries": matching_entries,
            "returned_entries": len(matching_entries),
            "has_more": entries_truncated,
        }
        if entries_truncated:
            result["entries_truncated"] = True
        else:
            result["total_entries"] = len(matching_entries)
        return result
    except Exception as exc:
        return {"error": bound_output(str(exc))[0]}


def _build_entry(root: Path, path: Path) -> dict[str, Any]:
    entry_type = "directory" if path.is_dir() else "file"
    return {
        "path": relative_workspace_path(root, path),
        "type": entry_type,
    }


def _bound_entry_path(entry: dict[str, Any]) -> tuple[dict[str, Any], bool]:
    bounded_path, truncated = bound_output(str(entry["path"]))
    return {
        **entry,
        "path": bounded_path,
    }, truncated
