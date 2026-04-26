"""Custom ``apply_patch`` tool – applies V4A diffs to workspace files.

This replaces the provider-specific native patch/editor tools (OpenAI
``apply_patch``, Anthropic ``str_replace_based_edit_tool``) with a single,
provider-agnostic function tool that goes through the normal tool registry
and execution pipeline.
"""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path
from typing import Any

from pbi_agent.tools.apply_diff import ApplyDiffMode, apply_diff, diff_line_numbers
from pbi_agent.tools.output import bound_output
from pbi_agent.tools.types import ToolContext, ToolSpec

SPEC = ToolSpec(
    name="apply_patch",
    description=(
        "Create, update, or delete one workspace file. Prefer V4A diff format; "
        "create/update also accept a standard unified diff for the same single "
        "file as a fallback."
    ),
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
                    "lines ('+'); do not add a leading blank line unless the "
                    "file context really contains one. As a fallback for "
                    "create_file/update_file, a standard unified diff for this "
                    "same single path is also accepted. Full multi-file patch "
                    "envelopes are not accepted."
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

        replaced_existing_file = False
        if operation_type == "create_file":
            replaced_existing_file = _create_file(target_path, diff)
            _store_diff_line_numbers(context, "", diff, mode="create")
        elif operation_type == "update_file":
            current = _read_update_display_input(target_path, diff)
            _update_file(target_path, diff)
            if current is not None:
                _store_diff_line_numbers(context, current, diff, mode="default")
        elif operation_type == "delete_file":
            _delete_file(target_path)
        else:
            return {"error": f"Unsupported operation_type '{operation_type}'."}

        if operation_type == "create_file" and replaced_existing_file:
            message = f"file exists and was replaced: '{path_value}'"
        else:
            message = f"{operation_type} succeeded for '{path_value}'"

        return {
            "status": "completed",
            "message": message,
        }
    except Exception as exc:
        return {
            "status": "failed",
            "error": bound_output(str(exc))[0],
        }


# ---------------------------------------------------------------------------
# File operations
# ---------------------------------------------------------------------------


def _create_file(path: Path, diff: str | None) -> bool:
    if not isinstance(diff, str) or not diff:
        raise ValueError("'diff' is required for create_file and must be non-empty.")
    content, _display_diff = _apply_diff_with_unified_fallback("", diff, mode="create")
    replaced_existing_file = path.exists()
    if path.is_dir():
        raise IsADirectoryError(f"path is a directory: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return replaced_existing_file


def _update_file(path: Path, diff: str | None) -> None:
    if not path.exists():
        raise FileNotFoundError(f"file not found: {path}")
    if not isinstance(diff, str) or not diff:
        raise ValueError("'diff' is required for update_file and must be non-empty.")
    current = path.read_text(encoding="utf-8")
    updated, _display_diff = _apply_diff_with_unified_fallback(
        current, diff, mode="default"
    )
    path.write_text(updated, encoding="utf-8")


def _read_update_display_input(path: Path, diff: Any) -> str | None:
    if not isinstance(diff, str) or not diff:
        return None
    if not path.exists() or path.is_dir():
        return None
    return path.read_text(encoding="utf-8")


def _delete_file(path: Path) -> None:
    if not path.exists():
        raise FileNotFoundError(f"file not found: {path}")
    if path.is_dir():
        raise IsADirectoryError(f"path is a directory: {path}")
    path.unlink()


# ---------------------------------------------------------------------------
# Unified diff compatibility
# ---------------------------------------------------------------------------


def _apply_diff_with_unified_fallback(
    input_text: str,
    diff: str,
    *,
    mode: ApplyDiffMode,
) -> tuple[str, str]:
    try:
        return apply_diff(input_text, diff, mode=mode), diff
    except ValueError as exc:
        if diff.startswith("\n"):
            stripped_diff = diff.lstrip("\n")
            try:
                return apply_diff(input_text, stripped_diff, mode=mode), stripped_diff
            except ValueError as stripped_exc:
                if not _looks_like_unified_diff(diff):
                    raise ValueError(
                        "V4A diff begins with an empty context line; remove the "
                        "leading blank line unless the file actually contains "
                        f"one. Details: {stripped_exc}"
                    ) from exc
        if not _looks_like_unified_diff(diff):
            raise
        try:
            v4a_diff = _unified_diff_to_v4a(diff, create=mode == "create")
            return apply_diff(input_text, v4a_diff, mode=mode), v4a_diff
        except ValueError as fallback_exc:
            raise ValueError(
                "Received unified diff syntax and attempted to convert it to "
                "V4A, but applying the converted diff failed. Use a V4A body "
                f"or a unified diff for this one file. Details: {fallback_exc}"
            ) from exc


def _looks_like_unified_diff(diff: str) -> bool:
    lines = diff.splitlines()
    return any(line.startswith("--- ") for line in lines) and any(
        line.startswith("+++ ") for line in lines
    )


def _store_diff_line_numbers(
    context: ToolContext | None,
    input_text: str,
    diff: Any,
    *,
    mode: ApplyDiffMode,
) -> None:
    if context is None:
        return
    if not isinstance(diff, str) or not diff:
        return
    _content, display_diff = _apply_diff_with_unified_fallback(
        input_text,
        diff,
        mode=mode,
    )
    context.display_metadata["diff"] = display_diff
    line_numbers = diff_line_numbers(
        input_text,
        display_diff,
        mode=mode,
    )
    if line_numbers:
        context.display_metadata["diff_line_numbers"] = line_numbers


def diff_line_numbers_metadata(value: Any) -> list[dict[str, int | None]]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        return []
    line_numbers: list[dict[str, int | None]] = []
    for item in value:
        if not isinstance(item, dict):
            continue
        line_numbers.append(
            {
                "old": _optional_line_number(item.get("old")),
                "new": _optional_line_number(item.get("new")),
            }
        )
    return line_numbers


def _optional_line_number(value: Any) -> int | None:
    return value if isinstance(value, int) and value > 0 else None


def _unified_diff_to_v4a(diff: str, *, create: bool) -> str:
    lines = diff.splitlines()
    v4a_lines: list[str] = []
    in_hunk = False
    saw_hunk = False

    for line in lines:
        if line.startswith("@@ "):
            saw_hunk = True
            in_hunk = True
            if not create:
                v4a_lines.append("@@")
            continue

        if not in_hunk:
            continue

        if line.startswith(("diff --git ", "index ", "--- ", "+++ ")):
            in_hunk = False
            continue
        if line.startswith("\\ No newline at end of file"):
            continue
        if line == "":
            # Unified diffs represent an empty context line as a single space;
            # a truly empty physical line is not a valid hunk line.
            continue

        prefix = line[0]
        if prefix not in {" ", "-", "+"}:
            in_hunk = False
            continue
        if create:
            if prefix == "+":
                v4a_lines.append(line)
        else:
            v4a_lines.append(line)

    if not saw_hunk:
        raise ValueError("unified diff is missing a hunk header ('@@ ... @@').")
    if not v4a_lines:
        raise ValueError("unified diff did not contain applicable hunk lines.")
    return "\n".join(v4a_lines)


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
