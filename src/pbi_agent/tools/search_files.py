from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from pbi_agent.tools.output import bound_output
from pbi_agent.tools.types import ToolContext, ToolSpec
from pbi_agent.tools.workspace_access import DEFAULT_MAX_MATCHES
from pbi_agent.tools.workspace_access import iter_directory_entries
from pbi_agent.tools.workspace_access import matches_glob
from pbi_agent.tools.workspace_access import normalize_positive_int
from pbi_agent.tools.workspace_access import open_text_file
from pbi_agent.tools.workspace_access import relative_workspace_path
from pbi_agent.tools.workspace_access import resolve_safe_path

SPEC = ToolSpec(
    name="search_files",
    description=(
        "Search text files in the workspace for a string or regex pattern. "
        "Use this for safe cross-platform content search instead of shell grep."
    ),
    parameters_schema={
        "type": "object",
        "properties": {
            "pattern": {
                "type": "string",
                "description": "String or regex pattern to search for.",
            },
            "path": {
                "type": "string",
                "description": (
                    "Directory or file path relative to the workspace root "
                    "(or absolute within workspace). Defaults to '.'."
                ),
            },
            "glob": {
                "type": "string",
                "description": (
                    "Optional glob filter for candidate files. Match against the "
                    "entry name unless the pattern includes a path separator."
                ),
            },
            "regex": {
                "type": "boolean",
                "description": "Treat pattern as a regular expression.",
                "default": False,
            },
            "max_matches": {
                "type": "integer",
                "description": "Maximum number of matches to return. Defaults to 100.",
            },
        },
        "required": ["pattern"],
        "additionalProperties": False,
    },
)


def handle(arguments: dict[str, Any], context: ToolContext) -> dict[str, Any]:
    del context
    pattern = arguments.get("pattern", "")
    if not isinstance(pattern, str) or not pattern:
        return {"error": "'pattern' must be a non-empty string."}

    root = Path.cwd().resolve()
    regex_enabled = bool(arguments.get("regex", False))
    max_matches = normalize_positive_int(
        arguments.get("max_matches"),
        default=DEFAULT_MAX_MATCHES,
    )
    glob_pattern = arguments.get("glob")

    try:
        target_path = resolve_safe_path(root, arguments.get("path"))
        matcher = _build_matcher(pattern, regex_enabled)
        matches: list[dict[str, Any]] = []
        searched_files = 0
        skipped_binary_files = 0

        for candidate in _iter_candidate_files(root, target_path, glob_pattern):
            searched_files += 1
            try:
                with open_text_file(candidate) as text_handle:
                    for line_number, line in enumerate(text_handle, start=1):
                        line_text = line.rstrip("\r\n")
                        if not matcher(line_text):
                            continue
                        match = {
                            "path": relative_workspace_path(root, candidate),
                            "line_number": line_number,
                            "line": line_text,
                        }
                        bounded_match = _bound_match_fields(match)
                        matches.append(bounded_match)
                        if len(matches) >= max_matches:
                            return {
                                "pattern": pattern,
                                "path": relative_workspace_path(root, target_path),
                                "glob": glob_pattern,
                                "regex": regex_enabled,
                                "matches": matches,
                                "searched_files": searched_files,
                                "skipped_binary_files": skipped_binary_files,
                                "matches_truncated": True,
                            }
            except ValueError as exc:
                if str(exc).startswith("binary file is not supported:"):
                    skipped_binary_files += 1
                    continue
                raise

        return {
            "pattern": pattern,
            "path": relative_workspace_path(root, target_path),
            "glob": glob_pattern,
            "regex": regex_enabled,
            "matches": matches,
            "searched_files": searched_files,
            "skipped_binary_files": skipped_binary_files,
        }
    except Exception as exc:
        return {"error": bound_output(str(exc))[0]}


def _build_matcher(pattern: str, regex_enabled: bool) -> Any:
    if not regex_enabled:
        return lambda line: pattern in line

    compiled = re.compile(pattern)
    return lambda line: compiled.search(line) is not None


def _iter_candidate_files(
    root: Path,
    target_path: Path,
    glob_pattern: str | None,
) -> list[Path]:
    if not target_path.exists():
        raise FileNotFoundError(f"path not found: {target_path}")

    if target_path.is_file():
        if matches_glob(root, target_path, glob_pattern):
            return [target_path]
        return []

    if not target_path.is_dir():
        raise ValueError(f"path is not a regular file or directory: {target_path}")

    files: list[Path] = []
    for candidate in iter_directory_entries(target_path, recursive=True):
        resolved_candidate = candidate.resolve(strict=False)
        try:
            resolved_candidate.relative_to(root)
        except ValueError:
            continue
        if not resolved_candidate.is_file():
            continue
        if not matches_glob(root, resolved_candidate, glob_pattern):
            continue
        files.append(resolved_candidate)
    return files


def _bound_match_fields(match: dict[str, Any]) -> dict[str, Any]:
    bounded_path, path_truncated = bound_output(str(match["path"]))
    bounded_line, line_truncated = bound_output(str(match["line"]))
    payload = {
        **match,
        "path": bounded_path,
        "line": bounded_line,
    }
    if path_truncated:
        payload["path_truncated"] = True
    if line_truncated:
        payload["line_truncated"] = True
    return payload
