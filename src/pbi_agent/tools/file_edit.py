"""Shared helpers for file edit tools."""

from __future__ import annotations

import difflib
from dataclasses import dataclass
from pathlib import Path
from collections.abc import Sequence
from typing import Any

from pbi_agent.tools.apply_diff import diff_line_numbers
from pbi_agent.tools.types import ToolContext


@dataclass(frozen=True, slots=True)
class AppliedFileEditResult:
    """Normalized in-memory result for one-file content edits."""

    original_content: str
    new_content: str
    display_diff: str
    diff_line_numbers: list[dict[str, int | None]]
    warnings: tuple[str, ...] = ()


def resolve_safe_path(root: Path, raw_path: str) -> Path:
    candidate = Path(raw_path)
    if candidate.is_absolute():
        return candidate.resolve(strict=False)
    return (root / candidate).resolve(strict=False)


def store_display_metadata(
    context: ToolContext | None,
    operation_type: str,
    path: str,
    applied: AppliedFileEditResult | None,
) -> None:
    if context is None:
        return
    context.display_metadata["operation_type"] = operation_type
    context.display_metadata["path"] = path
    if applied is None:
        return
    context.display_metadata["diff"] = applied.display_diff
    if applied.diff_line_numbers:
        context.display_metadata["diff_line_numbers"] = applied.diff_line_numbers
    if applied.warnings:
        context.display_metadata["diff_warnings"] = list(applied.warnings)


def build_applied_file_edit_result(
    original_content: str,
    new_content: str,
    *,
    operation_type: str,
    warnings: tuple[str, ...] = (),
) -> AppliedFileEditResult:
    display_diff = build_v4a_display_diff(
        original_content,
        new_content,
        operation_type=operation_type,
    )
    mode = "create" if operation_type == "create_file" else "default"
    line_numbers = (
        diff_line_numbers(original_content, display_diff, mode=mode)
        if display_diff
        else []
    )
    return AppliedFileEditResult(
        original_content=original_content,
        new_content=new_content,
        display_diff=display_diff,
        diff_line_numbers=line_numbers,
        warnings=warnings,
    )


def build_v4a_display_diff(
    original_content: str,
    new_content: str,
    *,
    operation_type: str,
) -> str:
    if operation_type == "create_file":
        return "\n".join(f"+{line}" for line in new_content.splitlines())
    if original_content == new_content:
        return ""

    original_lines = original_content.splitlines()
    new_lines = new_content.splitlines()
    unified = difflib.unified_diff(
        original_lines,
        new_lines,
        fromfile="a/file",
        tofile="b/file",
        lineterm="",
        n=3,
    )
    return unified_diff_to_v4a("\n".join(unified), create=False)


def unified_diff_to_v4a(diff: str, *, create: bool) -> str:
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
