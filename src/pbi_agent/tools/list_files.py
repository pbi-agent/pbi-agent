from __future__ import annotations

import fnmatch
from functools import lru_cache
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
        "List files and directories within the workspace, with optional glob and "
        "type filtering for targeted filename or path lookups."
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
            "glob": {
                "type": "string",
                "description": (
                    "Optional glob filter. Match against the entry name unless "
                    "the pattern includes a path separator."
                ),
            },
            "entry_type": {
                "type": "string",
                "description": (
                    "Limit results to files, directories, or both. "
                    "Defaults to 'all'."
                ),
                "enum": ["all", "file", "directory"],
                "default": "all",
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
        glob_pattern = _normalize_glob_pattern(arguments.get("glob"))
        entry_type = _normalize_entry_type(arguments.get("entry_type"))
        if entry_type is None:
            return {
                "error": "'entry_type' must be one of: all, file, directory."
            }
        max_entries = normalize_positive_int(
            arguments.get("max_entries"),
            default=DEFAULT_MAX_ENTRIES,
        )

        if not target_path.exists():
            return {"error": f"path not found: {target_path}"}

        if target_path.is_file():
            entry = _build_entry(root, target_path)
            entries: list[dict[str, Any]] = []
            path_truncated = False
            if _matches_filters(root, target_path, glob_pattern, entry_type):
                entry, path_truncated = _bound_entry_path(entry)
                entries.append(entry)
            return {
                "path": relative_workspace_path(root, target_path),
                "recursive": False,
                "glob": glob_pattern,
                "entry_type": entry_type,
                "entries": entries,
                "returned_entries": len(entries),
                "total_entries": len(entries),
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
            if not _matches_filters(root, resolved_candidate, glob_pattern, entry_type):
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
            "glob": glob_pattern,
            "entry_type": entry_type,
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


def _normalize_glob_pattern(raw_value: Any) -> str | None:
    if not isinstance(raw_value, str):
        return None
    normalized = raw_value.strip()
    return normalized or None


def _normalize_entry_type(raw_value: Any) -> str | None:
    if raw_value is None:
        return "all"
    if not isinstance(raw_value, str):
        return None
    normalized = raw_value.strip().lower()
    if not normalized:
        return "all"
    if normalized in {"all", "file", "directory"}:
        return normalized
    return None


def _matches_filters(
    root: Path,
    path: Path,
    glob_pattern: str | None,
    entry_type: str,
) -> bool:
    if entry_type == "file" and not path.is_file():
        return False
    if entry_type == "directory" and not path.is_dir():
        return False
    if glob_pattern is None:
        return True
    return _matches_glob(root, path, glob_pattern)


def _matches_glob(root: Path, path: Path, glob_pattern: str) -> bool:
    normalized_pattern = glob_pattern.replace("\\", "/")
    if "/" in normalized_pattern:
        return _match_relative_path(relative_workspace_path(root, path), normalized_pattern)
    return fnmatch.fnmatch(path.name, normalized_pattern)


def _match_relative_path(relative_path: str, glob_pattern: str) -> bool:
    path_parts = tuple(part for part in relative_path.split("/") if part)
    pattern_parts = tuple(part for part in glob_pattern.split("/") if part)

    @lru_cache(maxsize=None)
    def _matches(path_index: int, pattern_index: int) -> bool:
        if pattern_index == len(pattern_parts):
            return path_index == len(path_parts)

        pattern_part = pattern_parts[pattern_index]
        if pattern_part == "**":
            return _matches(path_index, pattern_index + 1) or (
                path_index < len(path_parts)
                and _matches(path_index + 1, pattern_index)
            )

        if path_index >= len(path_parts):
            return False

        if not fnmatch.fnmatchcase(path_parts[path_index], pattern_part):
            return False

        return _matches(path_index + 1, pattern_index + 1)

    return _matches(0, 0)
