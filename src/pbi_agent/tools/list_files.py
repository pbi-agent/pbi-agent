from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Callable, Iterator

from pbi_agent.tools.output import bound_output
from pbi_agent.tools.types import ToolContext, ToolSpec
from pbi_agent.tools.workspace_filters import build_glob_matcher
from pbi_agent.tools.workspace_filters import should_skip_directory_name
from pbi_agent.tools.workspace_access import DEFAULT_MAX_ENTRIES
from pbi_agent.tools.workspace_access import normalize_positive_int
from pbi_agent.tools.workspace_access import relative_workspace_path
from pbi_agent.tools.workspace_access import resolve_safe_path

SPEC = ToolSpec(
    name="list_files",
    description="List files and directories in the workspace with optional glob filtering.",
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
                    "Limit results to files, directories, or both. Defaults to 'all'."
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
            return {"error": "'entry_type' must be one of: all, file, directory."}
        matcher = build_glob_matcher(glob_pattern)
        max_entries = normalize_positive_int(
            arguments.get("max_entries"),
            default=DEFAULT_MAX_ENTRIES,
        )

        if not target_path.exists():
            return {"error": f"path not found: {target_path}"}

        if target_path.is_file():
            relative_path = relative_workspace_path(root, target_path)
            entry = _build_entry(relative_path, "file")
            entries: list[dict[str, Any]] = []
            if _matches_filters(
                relative_path, target_path.name, "file", matcher, entry_type
            ):
                entry, path_truncated = _bound_entry_path(entry)
                if path_truncated:
                    entry["path_truncated"] = True
                entries.append(entry)
            return {
                "entries": entries,
                "returned_entries": len(entries),
                "total_entries": len(entries),
                "has_more": False,
            }

        if not target_path.is_dir():
            return {"error": f"path is not a regular file or directory: {target_path}"}

        matching_entries: list[dict[str, Any]] = []
        entries_truncated = False
        for relative_path, name, candidate_type in _iter_entries(
            root,
            target_path,
            recursive=bool(recursive),
        ):
            if not _matches_filters(
                relative_path,
                name,
                candidate_type,
                matcher,
                entry_type,
            ):
                continue
            if len(matching_entries) >= max_entries:
                entries_truncated = True
                break
            entry = _build_entry(relative_path, candidate_type)
            bounded_entry, path_truncated = _bound_entry_path(entry)
            if path_truncated:
                bounded_entry["path_truncated"] = True
            matching_entries.append(bounded_entry)

        result: dict[str, Any] = {
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


def _build_entry(relative_path: str, entry_type: str) -> dict[str, Any]:
    return {
        "path": relative_path,
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
    relative_path: str,
    name: str,
    candidate_type: str,
    matcher: Callable[[str, str], bool],
    entry_type: str,
) -> bool:
    if entry_type == "file" and candidate_type != "file":
        return False
    if entry_type == "directory" and candidate_type != "directory":
        return False
    return matcher(relative_path, name)


def _iter_entries(
    root: Path,
    target_path: Path,
    *,
    recursive: bool,
) -> Iterator[tuple[str, str, str]]:
    if not recursive:
        with os.scandir(target_path) as scan:
            entries = sorted(scan, key=lambda entry: entry.name.casefold())
            for entry in entries:
                candidate_type = _entry_type_from_dir_entry(entry)
                if candidate_type is None:
                    continue
                relative_path = (target_path / entry.name).relative_to(root).as_posix()
                yield relative_path, entry.name, candidate_type
        return

    for current_root, dirnames, filenames in os.walk(
        target_path,
        topdown=True,
        followlinks=False,
    ):
        dirnames[:] = [
            dirname
            for dirname in sorted(dirnames, key=str.casefold)
            if not should_skip_directory_name(dirname)
        ]
        filenames.sort(key=str.casefold)
        current = Path(current_root)

        for dirname in dirnames:
            relative_path = (current / dirname).relative_to(root).as_posix()
            yield relative_path, dirname, "directory"

        for filename in filenames:
            relative_path = (current / filename).relative_to(root).as_posix()
            yield relative_path, filename, "file"


def _entry_type_from_dir_entry(entry: os.DirEntry[str]) -> str | None:
    if entry.is_dir(follow_symlinks=False):
        return "directory"
    if entry.is_file(follow_symlinks=False):
        return "file"
    return None
