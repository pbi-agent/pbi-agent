from __future__ import annotations

import fnmatch
import os
from collections import deque
from functools import lru_cache
from pathlib import Path
from typing import Any

from pbi_agent.tools.output import bound_output
from pbi_agent.tools.types import ToolContext, ToolSpec
from pbi_agent.tools.workspace_access import DEFAULT_MAX_ENTRIES
from pbi_agent.tools.workspace_access import normalize_positive_int
from pbi_agent.tools.workspace_access import relative_workspace_path
from pbi_agent.tools.workspace_access import resolve_safe_path

SPEC = ToolSpec(
    name="find_files",
    description=(
        "Fast file-only glob finder within the workspace. "
        "Use this to locate files by name or path pattern, especially for "
        "lookups like README*, *.md, *.json, or docs/**/*.md. "
        "Use this instead of list_files when you know the file pattern."
    ),
    parameters_schema={
        "type": "object",
        "properties": {
            "glob": {
                "type": "string",
                "description": (
                    "Glob pattern for files. Match against the file name unless "
                    "the pattern includes a path separator."
                ),
            },
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
            "max_results": {
                "type": "integer",
                "description": "Maximum number of files to return. Defaults to 200.",
            },
        },
        "required": ["glob"],
        "additionalProperties": False,
    },
)


def handle(arguments: dict[str, Any], context: ToolContext) -> dict[str, Any]:
    del context
    root = Path.cwd().resolve()
    glob_pattern = arguments.get("glob", "")
    if not isinstance(glob_pattern, str) or not glob_pattern.strip():
        return {"error": "'glob' must be a non-empty string."}

    try:
        target_path = resolve_safe_path(root, arguments.get("path"))
        recursive = bool(arguments.get("recursive", True))
        max_results = normalize_positive_int(
            arguments.get("max_results"),
            default=DEFAULT_MAX_ENTRIES,
        )

        if not target_path.exists():
            return {"error": f"path not found: {target_path}"}

        if target_path.is_file():
            if _matches_file_glob(root, target_path, glob_pattern):
                entry = _build_entry(root, target_path)
                entry, path_truncated = _bound_entry_path(entry)
                result = {
                    "path": relative_workspace_path(root, target_path),
                    "glob": glob_pattern,
                    "recursive": False,
                    "entries": [entry],
                    "returned_entries": 1,
                    "total_entries": 1,
                    "has_more": False,
                }
                if path_truncated:
                    result["path_truncated"] = True
                return result
            return {
                "path": relative_workspace_path(root, target_path),
                "glob": glob_pattern,
                "recursive": False,
                "entries": [],
                "returned_entries": 0,
                "total_entries": 0,
                "has_more": False,
            }

        if not target_path.is_dir():
            return {"error": f"path is not a regular file or directory: {target_path}"}

        matching_entries: list[dict[str, Any]] = []
        entries_truncated = False
        for candidate in _iter_matching_files(
            root,
            target_path,
            glob_pattern,
            recursive=recursive,
        ):
            if len(matching_entries) >= max_results:
                entries_truncated = True
                break
            entry = _build_entry(root, candidate)
            bounded_entry, path_truncated = _bound_entry_path(entry)
            if path_truncated:
                bounded_entry["path_truncated"] = True
            matching_entries.append(bounded_entry)

        result = {
            "path": relative_workspace_path(root, target_path),
            "glob": glob_pattern,
            "recursive": recursive,
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


def _iter_matching_files(
    root: Path,
    target_path: Path,
    glob_pattern: str,
    *,
    recursive: bool,
):
    normalized_pattern = glob_pattern.replace("\\", "/")
    match_relative_path = "/" in normalized_pattern

    queue: deque[Path] = deque([target_path])
    while queue:
        current = queue.popleft()
        files: list[Path] = []
        subdirs: list[Path] = []
        with os.scandir(current) as scan:
            for entry in scan:
                candidate = current / entry.name
                if entry.is_file(follow_symlinks=False):
                    if _matches_entry(
                        root,
                        candidate,
                        entry.name,
                        normalized_pattern,
                        match_relative_path,
                    ):
                        files.append(candidate)
                    continue

                if recursive and entry.is_dir(follow_symlinks=False):
                    subdirs.append(candidate)

        files.sort(key=lambda path: path.name.casefold())
        for path in files:
            yield path

        if recursive:
            subdirs.sort(key=lambda path: path.name.casefold())
            queue.extend(subdirs)


def _matches_file_glob(root: Path, path: Path, glob_pattern: str) -> bool:
    normalized_pattern = glob_pattern.replace("\\", "/")
    return _matches_entry(
        root,
        path,
        path.name,
        normalized_pattern,
        "/" in normalized_pattern,
    )


def _matches_entry(
    root: Path,
    path: Path,
    name: str,
    glob_pattern: str,
    match_relative_path: bool,
) -> bool:
    if match_relative_path:
        return _match_relative_path(relative_workspace_path(root, path), glob_pattern)
    return fnmatch.fnmatch(name, glob_pattern)


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


def _build_entry(root: Path, path: Path) -> dict[str, Any]:
    return {
        "path": relative_workspace_path(root, path),
        "type": "file",
    }


def _bound_entry_path(entry: dict[str, Any]) -> tuple[dict[str, Any], bool]:
    bounded_path, truncated = bound_output(str(entry["path"]))
    return {
        **entry,
        "path": bounded_path,
    }, truncated
