from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path
from typing import Any

from codetool_search import search as codetool_search

from pbi_agent.tools.output import bound_output
from pbi_agent.tools.types import ToolContext, ToolOutput, ToolSpec
from pbi_agent.tools.workspace_access import normalize_positive_int, resolve_safe_path

DEFAULT_LIMIT = 50
MAX_CONTEXT_LINES = 20
MAX_LIMIT = 1_000

_STRING_OR_STRING_ARRAY_SCHEMA: dict[str, Any] = {
    "oneOf": [
        {"type": "string"},
        {"type": "array", "items": {"type": "string"}},
    ]
}

_ROOT_SCHEMA: dict[str, Any] = {
    "oneOf": [
        {"type": "string"},
        {
            "type": "array",
            "items": {"type": "string", "minLength": 1},
            "minItems": 1,
        },
    ]
}

SPEC = ToolSpec(
    name="search_workspace",
    description=(
        "Search workspace content/paths. drop-in replacement for `find`/`grep`/`ls` for exploration and file finding."
    ),
    prompt_usage=(
        "Use `search_workspace` to find files, paths, or text in the workspace "
        "when exploring."
    ),
    parameters_schema={
        "type": "object",
        "properties": {
            "pattern": {
                "type": "string",
                "description": "Text or regex pattern to find.",
            },
            "root": {
                **_ROOT_SCHEMA,
                "description": (
                    "Directory/file path, or list of paths, relative to the workspace root. Defaults to '.'."
                ),
            },
            "regex": {
                "type": "boolean",
                "description": "Treat pattern as a regular expression. Defaults to false; set true for regex search.",
            },
            "target": {
                "type": "string",
                "enum": ["content", "path", "both"],
                "description": (
                    "Search file contents, relative paths, or both. Defaults to content."
                ),
            },
            "path_scope": {
                "type": "string",
                "enum": ["path", "basename"],
                "description": "For path search, match the full relative path or only the basename. Defaults to path.",
            },
            "glob": {
                **_STRING_OR_STRING_ARRAY_SCHEMA,
                "description": "Include only files matching this glob or list of globs, e.g. '*.py'.",
            },
            "exclude": {
                **_STRING_OR_STRING_ARRAY_SCHEMA,
                "description": "Exclude files matching this glob or list of globs.",
            },
            "mode": {
                "type": "string",
                "enum": ["files", "snippets", "count"],
                "description": (
                    "Result detail level: files lists matching files/paths, "
                    "snippets includes per-match context, and count reports per-file "
                    "match counts. Defaults to snippets when context_lines > 0; "
                    "otherwise files."
                ),
            },
            "context_lines": {
                "type": "integer",
                "description": "Nearby lines to include before and after each snippet match. Defaults to 0; capped at 20.",
            },
            "limit": {
                "type": "integer",
                "description": "Maximum matches to return. Defaults to 50; capped at 1000.",
            },
            "cursor": {
                "oneOf": [{"type": "integer"}, {"type": "string"}],
                "description": "Cursor or result offset from a previous search response for the next page.",
            },
        },
        "required": ["pattern"],
        "additionalProperties": False,
    },
)


def handle(arguments: dict[str, Any], context: ToolContext) -> ToolOutput | str:
    del context
    pattern = arguments.get("pattern")
    if not isinstance(pattern, str) or not pattern:
        return _error_output("'pattern' must be a non-empty string.")

    workspace_root = Path.cwd().resolve()
    try:
        search_root = _resolve_search_root(workspace_root, arguments.get("root", "."))
    except ValueError as exc:
        return _error_output(str(exc))

    context_lines = _normalize_context_lines(arguments.get("context_lines"))
    limit = normalize_positive_int(
        arguments.get("limit"), default=DEFAULT_LIMIT, upper_bound=MAX_LIMIT
    )

    try:
        result = codetool_search(
            pattern,
            root=_codetool_root_argument(search_root),
            target=_normalize_target(arguments.get("target")),
            regex=_normalize_regex(arguments.get("regex")),
            path_scope=_normalize_path_scope(arguments.get("path_scope")),
            glob=_normalize_glob_argument(arguments.get("glob")),
            exclude=_normalize_glob_argument(arguments.get("exclude")),
            mode=_normalize_mode(arguments.get("mode"), context_lines=context_lines),
            context_lines=context_lines,
            limit=limit,
            cursor=_normalize_cursor(arguments.get("cursor")),
            result_format="raw",
        )
    except Exception as exc:
        return _error_output(bound_output(str(exc))[0])
    if not isinstance(result, str):
        return _error_output("search returned non-text output")
    return result


def _error_output(message: str) -> ToolOutput:
    return ToolOutput(result={"error": message}, is_error=True)


def _resolve_search_root(workspace_root: Path, raw_root: Any) -> Path | list[Path]:
    if isinstance(raw_root, (list, tuple)):
        if not raw_root:
            raise ValueError("'root' must contain at least one path.")
        roots: list[Path] = []
        for item in raw_root:
            if not isinstance(item, str) or not item.strip():
                raise ValueError("'root' array items must be non-empty strings.")
            roots.append(_resolve_single_search_root(workspace_root, item))
        return roots
    return _resolve_single_search_root(workspace_root, raw_root)


def _resolve_single_search_root(workspace_root: Path, raw_root: Any) -> Path:
    search_root = resolve_safe_path(workspace_root, raw_root, default=".").resolve(
        strict=False
    )
    try:
        search_root.relative_to(workspace_root)
    except ValueError as exc:
        raise ValueError("'root' must resolve inside the workspace.") from exc

    if not search_root.exists():
        raise ValueError(f"root not found: {search_root}")
    if not (search_root.is_dir() or search_root.is_file()):
        raise ValueError(f"root is not a file or directory: {search_root}")
    return search_root


def _codetool_root_argument(search_root: Path | list[Path]) -> str | list[str]:
    if isinstance(search_root, list):
        return [str(root) for root in search_root]
    return str(search_root)


def _normalize_glob_argument(raw_value: Any) -> str | list[str] | None:
    if raw_value is None:
        return None
    if isinstance(raw_value, str):
        return raw_value if raw_value.strip() else None
    if isinstance(raw_value, Iterable):
        values = [item for item in raw_value if isinstance(item, str) and item.strip()]
        return values or None
    return None


def _normalize_context_lines(raw_value: Any) -> int:
    if not isinstance(raw_value, int) or raw_value < 0:
        return 0
    return min(raw_value, MAX_CONTEXT_LINES)


def _normalize_target(raw_value: Any) -> str:
    if isinstance(raw_value, str) and raw_value in {"content", "path", "both"}:
        return raw_value
    return "content"


def _normalize_regex(raw_value: Any) -> bool:
    return raw_value if isinstance(raw_value, bool) else False


def _normalize_path_scope(raw_value: Any) -> str:
    if isinstance(raw_value, str) and raw_value in {"path", "basename"}:
        return raw_value
    return "path"


def _normalize_mode(raw_value: Any, *, context_lines: int) -> str:
    if isinstance(raw_value, str) and raw_value in {"files", "snippets", "count"}:
        return raw_value
    if context_lines > 0:
        return "snippets"
    return "files"


def _normalize_cursor(raw_value: Any) -> str | int | None:
    if isinstance(raw_value, bool):
        return None
    if isinstance(raw_value, int):
        return raw_value
    if isinstance(raw_value, str):
        normalized = raw_value.strip()
        return normalized or None
    return None
