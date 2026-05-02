"""Custom ``apply_patch`` tool – applies V4A patches to files.

This replaces the provider-specific native patch/editor tools (OpenAI
``apply_patch``, Anthropic ``str_replace_based_edit_tool``) with a single,
provider-agnostic function tool that goes through the normal tool registry
and execution pipeline.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pbi_agent.tools.apply_diff import (
    ApplyDiffMode,
    apply_diff,
    diff_line_numbers,
)
from pbi_agent.tools.file_edit import (
    AppliedFileEditResult,
    resolve_safe_path,
    store_display_metadata,
)
from pbi_agent.tools.output import bound_output
from pbi_agent.tools.types import ToolContext, ToolSpec

SPEC = ToolSpec(
    name="apply_patch",
    description=(
        "Apply a V4A patch to files. The patch must include "
        "*** Begin Patch, one or more file sections, and *** End Patch."
    ),
    parameters_schema={
        "type": "object",
        "properties": {
            "patch": {
                "type": "string",
                "description": (
                    "Full V4A patch. Grammar: Patch := Begin {FileOp} End. "
                    "Begin := '*** Begin Patch'; End := '*** End Patch'. "
                    "FileOp := AddFile | DeleteFile | UpdateFile. AddFile := "
                    "'*** Add File: <path>' followed by '+' content lines. "
                    "DeleteFile := '*** Delete File: <path>'. UpdateFile := "
                    "'*** Update File: <path>' followed by hunks. Hunk := "
                    "'@@' [anchor] followed by lines prefixed with space for "
                    "context, '-' for removals, or '+' for insertions. Paths "
                    "may be relative to the workspace root or absolute. "
                    "Unified diffs are not accepted."
                ),
            },
        },
        "required": ["patch"],
        "additionalProperties": False,
    },
    is_destructive=True,
)

BEGIN_PATCH = "*** Begin Patch"
END_PATCH = "*** End Patch"
ADD_FILE = "*** Add File: "
UPDATE_FILE = "*** Update File: "
DELETE_FILE = "*** Delete File: "
MOVE_TO = "*** Move to: "


@dataclass(frozen=True, slots=True)
class PatchOperation:
    operation_type: str
    path: str
    diff: str | None = None
    move_to: str | None = None


@dataclass(frozen=True, slots=True)
class AppliedPatchResult:
    original_content: str
    new_content: str
    display_diff: str
    diff_line_numbers: list[dict[str, int | None]]
    warnings: tuple[str, ...] = ()

    def as_file_edit(self) -> AppliedFileEditResult:
        return AppliedFileEditResult(
            original_content=self.original_content,
            new_content=self.new_content,
            display_diff=self.display_diff,
            diff_line_numbers=self.diff_line_numbers,
            warnings=self.warnings,
        )


def handle(arguments: dict[str, Any], context: ToolContext) -> dict[str, Any]:
    """Execute a V4A patch envelope."""
    patch = arguments.get("patch")

    if not isinstance(patch, str) or not patch.strip():
        return {"error": "'patch' must be a non-empty string."}

    root = Path.cwd().resolve()

    try:
        operations = _parse_patch(patch)
        if not operations:
            raise ValueError("patch must contain at least one file operation.")

        summaries: list[dict[str, Any]] = []
        first_applied: tuple[PatchOperation, AppliedPatchResult] | None = None
        for operation in operations:
            target_path = resolve_safe_path(root, operation.path)
            applied: AppliedPatchResult | None = None
            replaced_existing_file = False
            if operation.operation_type == "create_file":
                replaced_existing_file, applied = _create_file(
                    target_path, operation.diff
                )
            elif operation.operation_type == "update_file":
                applied = _update_file(target_path, operation.diff)
            elif operation.operation_type == "delete_file":
                _delete_file(target_path)
            else:
                raise ValueError(
                    f"Unsupported operation_type '{operation.operation_type}'."
                )

            if first_applied is None and applied is not None:
                first_applied = (operation, applied)

            item: dict[str, Any] = {
                "operation_type": operation.operation_type,
                "path": operation.path,
            }
            if replaced_existing_file:
                item["replaced_existing_file"] = True
            if applied is not None and applied.warnings:
                item["warnings"] = list(applied.warnings)
            summaries.append(item)

        if first_applied is not None:
            first_operation, first_result = first_applied
            store_display_metadata(
                context,
                first_operation.operation_type,
                first_operation.path,
                first_result.as_file_edit(),
            )
        elif operations:
            store_display_metadata(
                context,
                operations[0].operation_type,
                operations[0].path,
                None,
            )

        result: dict[str, Any] = {
            "status": "completed",
            "message": f"apply_patch succeeded for {len(operations)} file operation(s)",
            "operations": summaries,
        }
        return result
    except Exception as exc:
        return {
            "status": "failed",
            "error": bound_output(str(exc))[0],
        }


# ---------------------------------------------------------------------------
# Patch parsing
# ---------------------------------------------------------------------------


def _parse_patch(patch: str) -> list[PatchOperation]:
    lines = [line.rstrip("\r") for line in patch.split("\n")]
    if lines and lines[-1] == "":
        lines.pop()
    if lines and lines[0] == "":
        lines = lines[1:]
    if not lines or lines[0] != BEGIN_PATCH:
        raise ValueError("patch must start with '*** Begin Patch'.")
    if lines[-1] != END_PATCH:
        raise ValueError("patch must end with '*** End Patch'.")

    operations: list[PatchOperation] = []
    index = 1
    while index < len(lines) - 1:
        line = lines[index]
        if line.startswith(ADD_FILE):
            operation, index = _parse_add_file(lines, index)
        elif line.startswith(UPDATE_FILE):
            operation, index = _parse_update_file(lines, index)
        elif line.startswith(DELETE_FILE):
            operation, index = _parse_delete_file(lines, index)
        elif not line:
            index += 1
            continue
        else:
            raise ValueError(f"Invalid patch line: {line}")
        operations.append(operation)
    return operations


def _parse_add_file(lines: list[str], index: int) -> tuple[PatchOperation, int]:
    path = _parse_path_header(lines[index], ADD_FILE)
    index += 1
    body: list[str] = []
    while index < len(lines) and not _is_file_operation_header(lines[index]):
        line = lines[index]
        if line == END_PATCH:
            break
        if not line.startswith("+"):
            raise ValueError(f"Invalid Add File line for '{path}': {line}")
        body.append(line)
        index += 1
    if not body:
        raise ValueError(f"Add File '{path}' must include '+' content lines.")
    return PatchOperation("create_file", path, "\n".join(body)), index


def _parse_update_file(lines: list[str], index: int) -> tuple[PatchOperation, int]:
    path = _parse_path_header(lines[index], UPDATE_FILE)
    index += 1
    move_to: str | None = None
    if index < len(lines) and lines[index].startswith(MOVE_TO):
        move_to = _parse_path_header(lines[index], MOVE_TO)
        index += 1
    body: list[str] = []
    while index < len(lines) and not _is_file_operation_header(lines[index]):
        line = lines[index]
        if line == END_PATCH:
            break
        body.append(line)
        index += 1
    if move_to is not None:
        raise ValueError("Move/rename operations are not supported yet.")
    if not body:
        raise ValueError(f"Update File '{path}' must include at least one hunk.")
    return PatchOperation("update_file", path, "\n".join(body), move_to), index


def _parse_delete_file(lines: list[str], index: int) -> tuple[PatchOperation, int]:
    path = _parse_path_header(lines[index], DELETE_FILE)
    return PatchOperation("delete_file", path), index + 1


def _parse_path_header(line: str, prefix: str) -> str:
    path = line[len(prefix) :].strip()
    if not path:
        raise ValueError(f"Missing path in patch header: {line}")
    return path


def _is_file_operation_header(line: str) -> bool:
    return line == END_PATCH or line.startswith((ADD_FILE, UPDATE_FILE, DELETE_FILE))


# ---------------------------------------------------------------------------
# File operations
# ---------------------------------------------------------------------------


def _create_file(path: Path, diff: str | None) -> tuple[bool, AppliedPatchResult]:
    if not isinstance(diff, str) or not diff:
        raise ValueError("'diff' is required for create_file and must be non-empty.")
    replaced_existing_file = path.exists()
    if path.is_dir():
        raise IsADirectoryError(f"path is a directory: {path}")
    applied = _apply_v4a_diff("", diff, mode="create")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(applied.new_content, encoding="utf-8")
    return replaced_existing_file, applied


def _update_file(path: Path, diff: str | None) -> AppliedPatchResult:
    if not path.exists():
        raise FileNotFoundError(f"file not found: {path}")
    if not isinstance(diff, str) or not diff:
        raise ValueError("'diff' is required for update_file and must be non-empty.")
    current = path.read_text(encoding="utf-8")
    applied = _apply_v4a_diff(current, diff, mode="default")
    path.write_text(applied.new_content, encoding="utf-8")
    return applied


def _delete_file(path: Path) -> None:
    if not path.exists():
        raise FileNotFoundError(f"file not found: {path}")
    if path.is_dir():
        raise IsADirectoryError(f"path is a directory: {path}")
    path.unlink()


# ---------------------------------------------------------------------------
# V4A application
# ---------------------------------------------------------------------------


def _apply_v4a_diff(
    input_text: str,
    diff: str,
    *,
    mode: ApplyDiffMode,
) -> AppliedPatchResult:
    try:
        return _apply_normalized_diff(input_text, diff, mode=mode)
    except ValueError as exc:
        if diff.startswith("\n"):
            stripped_diff = diff.lstrip("\n")
            try:
                return _apply_normalized_diff(input_text, stripped_diff, mode=mode)
            except ValueError as stripped_exc:
                raise ValueError(
                    "V4A hunk begins with an empty context line; remove the "
                    "leading blank line unless the file actually contains "
                    f"one. Details: {stripped_exc}"
                ) from exc
        if _looks_like_unified_diff(diff):
            raise ValueError(
                "Unified diff syntax is not supported by apply_patch. Use a V4A "
                "patch, replace_in_file for targeted edits, or write_file for "
                "full-file writes."
            ) from exc
        raise


def _apply_normalized_diff(
    input_text: str,
    display_diff: str,
    *,
    mode: ApplyDiffMode,
) -> AppliedPatchResult:
    result = apply_diff(input_text, display_diff, mode=mode)
    return AppliedPatchResult(
        original_content=input_text,
        new_content=result.content,
        display_diff=display_diff,
        diff_line_numbers=diff_line_numbers(input_text, display_diff, mode=mode),
        warnings=result.warnings,
    )


def _looks_like_unified_diff(diff: str) -> bool:
    lines = diff.splitlines()
    return any(line.startswith("--- ") for line in lines) and any(
        line.startswith("+++ ") for line in lines
    )
