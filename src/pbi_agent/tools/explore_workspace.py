from __future__ import annotations

import shlex
from collections.abc import Iterable
from pathlib import Path
from typing import Any

from codetool_explore import ExploreError, explore as codetool_explore

from pbi_agent.media import detect_image_mime_type, load_image_bytes
from pbi_agent.tools.output import bound_output
from pbi_agent.tools.types import ToolContext, ToolOutput, ToolSpec
from pbi_agent.tools.workspace_access import normalize_positive_int
from pbi_agent.tools.workspace_access import relative_workspace_path
from pbi_agent.tools.workspace_access import resolve_safe_path

DEFAULT_LIMIT = 50
MAX_CONTEXT_LINES = 20
MAX_LIMIT = 1_000

_SEARCH_TARGETS = {"content", "path"}
_TARGETS = _SEARCH_TARGETS | {"read", "list"}
_IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp"}

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
    name="explore_workspace",
    description=(
        "Explore workspace files: content/path search, text read, or one-level list. "
        "Compact text output."
    ),
    prompt_usage=(
        "Use `explore_workspace` for workspace search/read/list: "
        'content `{pattern:"UserService",regex:false}`, '
        'multi-root `{pattern:"UserService",root:["tests","src/pbi_agent"]}`, '
        'path `{pattern:"service",target:"path",glob:"*.py",regex:false}`, '
        'read `{pattern:"src/app.py",target:"read",start_line:20,limit:80}`, '
        'list `{pattern:"src",target:"list",limit:100}`.'
    ),
    parameters_schema={
        "type": "object",
        "properties": {
            "pattern": {
                "type": "string",
                "description": "Search pattern; for read/list, the file or directory path.",
            },
            "root": {
                **_ROOT_SCHEMA,
                "description": (
                    "Workspace-relative file/dir root, or roots array for search. Defaults to '.'."
                ),
            },
            "target": {
                "type": "string",
                "enum": ["content", "path", "read", "list"],
                "description": "Operation. Defaults to content search.",
            },
            "regex": {
                "type": "boolean",
                "description": "Treat search pattern as regex. Defaults to true; use false for literal.",
            },
            "path_scope": {
                "type": "string",
                "enum": ["path", "basename"],
                "description": "For path search, match full path or basename. Defaults to path.",
            },
            "glob": {
                **_STRING_OR_STRING_ARRAY_SCHEMA,
                "description": "Include only glob(s), e.g. '*.py'.",
            },
            "exclude": {
                **_STRING_OR_STRING_ARRAY_SCHEMA,
                "description": "Exclude glob(s).",
            },
            "mode": {
                "type": "string",
                "enum": ["files", "snippets", "count"],
                "description": (
                    "Search result detail: files, snippets, or count. Defaults to snippets "
                    "when context_lines > 0, otherwise files."
                ),
            },
            "context_lines": {
                "type": "integer",
                "description": "Snippet context lines for content search. Defaults to 0; max 20.",
            },
            "limit": {
                "type": "integer",
                "description": "Max matches/list entries/read lines. Defaults to 50; max 1000.",
            },
            "cursor": {
                "oneOf": [{"type": "integer"}, {"type": "string"}],
                "description": "Cursor from a previous truncated result.",
            },
            "start_line": {
                "type": "integer",
                "description": "First line for target='read'. Defaults to 1.",
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

    try:
        target = _normalize_target(arguments.get("target"))
        workspace_root = Path.cwd().resolve()
        if target in _SEARCH_TARGETS:
            result = _handle_search(pattern, arguments, workspace_root, target=target)
        else:
            result = _handle_read_or_list(
                pattern,
                arguments,
                workspace_root,
                target=target,
            )
    except (ValueError, ExploreError) as exc:
        return _error_output(bound_output(str(exc))[0])
    except Exception as exc:
        return _error_output(bound_output(str(exc))[0])

    if isinstance(result, ToolOutput):
        return result
    if not isinstance(result, str):
        return _error_output("explore returned non-text output")
    return result


def _handle_search(
    pattern: str,
    arguments: dict[str, Any],
    workspace_root: Path,
    *,
    target: str,
) -> str:
    search_root = _resolve_search_root(workspace_root, arguments.get("root", "."))
    context_lines = _normalize_context_lines(arguments.get("context_lines"))
    limit = normalize_positive_int(
        arguments.get("limit"), default=DEFAULT_LIMIT, upper_bound=MAX_LIMIT
    )
    result = codetool_explore(
        pattern,
        root=_codetool_root_argument(search_root),
        target=target,
        regex=_normalize_regex(arguments.get("regex")),
        path_scope=_normalize_path_scope(arguments.get("path_scope")),
        glob=_normalize_glob_argument(arguments.get("glob")),
        exclude=_normalize_glob_argument(arguments.get("exclude")),
        mode=_normalize_mode(arguments.get("mode"), context_lines=context_lines),
        context_lines=context_lines,
        limit=limit,
        cursor=_normalize_cursor(arguments.get("cursor")),
        result_format="text",
    )
    if not isinstance(result, str):
        raise ValueError("explore returned non-text output")
    return result


def _handle_read_or_list(
    pattern: str,
    arguments: dict[str, Any],
    workspace_root: Path,
    *,
    target: str,
) -> str | ToolOutput:
    root = _resolve_single_read_list_root(workspace_root, arguments.get("root", "."))
    target_path = _resolve_read_list_target(
        workspace_root,
        root,
        pattern,
        target=target,
    )
    if not target_path.exists():
        raise ValueError(f"path not found: {target_path}")
    if target == "read" and _is_supported_image_path(target_path):
        return _handle_image_file(workspace_root, target_path)

    limit = normalize_positive_int(
        arguments.get("limit"), default=DEFAULT_LIMIT, upper_bound=MAX_LIMIT
    )
    if target == "read":
        if not target_path.is_file():
            raise ValueError(f"path is not a file: {target_path}")
        result = codetool_explore(
            target_path.name,
            root=str(target_path.parent),
            target="read",
            start_line=_normalize_start_line(arguments.get("start_line")),
            limit=limit,
        )
    else:
        explore_pattern = "." if target_path.is_dir() else target_path.name
        explore_root = target_path if target_path.is_dir() else target_path.parent
        result = codetool_explore(
            explore_pattern,
            root=str(explore_root),
            target="list",
            glob=_normalize_glob_argument(arguments.get("glob")),
            exclude=_normalize_glob_argument(arguments.get("exclude")),
            limit=limit,
            cursor=_normalize_cursor(arguments.get("cursor")),
        )
    if not isinstance(result, str):
        raise ValueError("explore returned non-text output")
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
            roots.append(_resolve_single_workspace_root(workspace_root, item))
        return roots
    if isinstance(raw_root, str):
        split_roots = _resolve_space_separated_search_roots(workspace_root, raw_root)
        if split_roots is not None:
            return split_roots
    return _resolve_single_workspace_root(workspace_root, raw_root)


def _resolve_single_read_list_root(workspace_root: Path, raw_root: Any) -> Path:
    if isinstance(raw_root, (list, tuple)):
        raise ValueError("'root' must be a single path for read/list targets.")
    return _resolve_single_workspace_root(workspace_root, raw_root)


def _resolve_space_separated_search_roots(
    workspace_root: Path,
    raw_root: str,
) -> list[Path] | None:
    if not raw_root.strip() or not any(char.isspace() for char in raw_root):
        return None
    exact_root = resolve_safe_path(workspace_root, raw_root, default=".").resolve(
        strict=False
    )
    _ensure_inside(
        exact_root, workspace_root, message="'root' must resolve inside the workspace."
    )
    if exact_root.exists():
        return None
    try:
        parts = [
            _strip_matching_quotes(part) for part in shlex.split(raw_root, posix=False)
        ]
    except ValueError:
        return None
    if len(parts) < 2 or not all(part.strip() for part in parts):
        return None
    roots: list[Path] = []
    for part in parts:
        try:
            roots.append(_resolve_single_workspace_root(workspace_root, part))
        except ValueError:
            return None
    return roots


def _strip_matching_quotes(value: str) -> str:
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        return value[1:-1]
    return value


def _resolve_single_workspace_root(workspace_root: Path, raw_root: Any) -> Path:
    search_root = resolve_safe_path(workspace_root, raw_root, default=".").resolve(
        strict=False
    )
    _ensure_inside(
        search_root, workspace_root, message="'root' must resolve inside the workspace."
    )

    if not search_root.exists():
        raise ValueError(f"root not found: {search_root}")
    if not (search_root.is_dir() or search_root.is_file()):
        raise ValueError(f"root is not a file or directory: {search_root}")
    return search_root


def _resolve_read_list_target(
    workspace_root: Path,
    root: Path,
    raw_pattern: str,
    *,
    target: str,
) -> Path:
    if root.is_file():
        root_target = root.resolve(strict=False)
        if raw_pattern.strip() == ".":
            target_path = root_target
        else:
            target_path = resolve_safe_path(root_target.parent, raw_pattern).resolve(
                strict=False
            )
        if target_path != root_target:
            raise ValueError(f"{target} root is a file; pattern must target that file.")
    else:
        root_dir = root.resolve(strict=False)
        target_path = resolve_safe_path(root_dir, raw_pattern).resolve(strict=False)
        _ensure_inside(
            target_path, root_dir, message="'pattern' must resolve inside 'root'."
        )
    _ensure_inside(
        target_path,
        workspace_root,
        message="'pattern' must resolve inside the workspace.",
    )
    return target_path


def _ensure_inside(path: Path, root: Path, *, message: str) -> None:
    try:
        path.relative_to(root)
    except ValueError as exc:
        raise ValueError(message) from exc


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
    if type(raw_value) is not int or raw_value < 0:
        return 0
    return min(raw_value, MAX_CONTEXT_LINES)


def _normalize_target(raw_value: Any) -> str:
    if raw_value is None:
        return "content"
    if isinstance(raw_value, str) and raw_value in _TARGETS:
        return raw_value
    allowed = ", ".join(sorted(_TARGETS))
    raise ValueError(f"'target' must be one of: {allowed}.")


def _normalize_regex(raw_value: Any) -> bool:
    return raw_value if isinstance(raw_value, bool) else True


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


def _normalize_start_line(raw_value: Any) -> int:
    if type(raw_value) is int and raw_value >= 1:
        return raw_value
    return 1


def _is_supported_image_path(target_path: Path) -> bool:
    if not target_path.is_file():
        return False
    if target_path.suffix.lower() in _IMAGE_EXTENSIONS:
        return True
    try:
        with target_path.open("rb") as handle:
            return detect_image_mime_type(handle.read(12)) is not None
    except OSError:
        return False


def _handle_image_file(root: Path, target_path: Path) -> ToolOutput:
    image = load_image_bytes(
        relative_workspace_path(root, target_path),
        target_path.read_bytes(),
    )
    summary = {
        "path": image.path,
        "mime_type": image.mime_type,
        "byte_count": image.byte_count,
    }
    return ToolOutput(result=summary, attachments=[image])
