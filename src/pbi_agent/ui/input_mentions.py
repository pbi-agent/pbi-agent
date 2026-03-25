"""Workspace-safe `@file` mention parsing and expansion."""

from __future__ import annotations

import re
from pathlib import Path

from pbi_agent.tools.workspace_access import (
    read_text_file,
    relative_workspace_path,
    resolve_safe_path,
)

PATH_CHAR_CLASS = r"A-Za-z0-9._~/\\:-"
FILE_MENTION_PATTERN = re.compile(r"@(?P<path>(?:\\.|[" + PATH_CHAR_CLASS + r"])+)")
EMAIL_PREFIX_PATTERN = re.compile(r"[a-zA-Z0-9._%+-]$")

_MAX_INLINE_BYTES = 64 * 1024


def expand_file_mentions(
    text: str,
    *,
    root: Path,
    max_inline_bytes: int = _MAX_INLINE_BYTES,
) -> tuple[str, list[str]]:
    """Return input text with referenced workspace files appended inline."""

    warnings: list[str] = []
    mentioned_files = _resolve_mentioned_files(text, root=root, warnings=warnings)
    if not mentioned_files:
        return text, warnings

    parts = [text, "", "## Referenced Files"]
    for path in mentioned_files:
        relative_path = relative_workspace_path(root, path)
        try:
            size = path.stat().st_size
        except OSError as exc:
            parts.append(f"### {relative_path}\n[Could not inspect file: {exc}]")
            continue

        if size > max_inline_bytes:
            parts.append(
                "### "
                + relative_path
                + "\n"
                + f"[File too large to inline ({size} bytes). Use read_file if needed.]"
            )
            continue

        try:
            content, encoding = read_text_file(path)
        except ValueError as exc:
            parts.append(f"### {relative_path}\n[Could not read file: {exc}]")
            continue

        parts.append(
            f"### {relative_path}\n[encoding: {encoding}]\n<file>\n{content}\n</file>"
        )

    return "\n".join(parts), warnings


def _resolve_mentioned_files(
    text: str, *, root: Path, warnings: list[str]
) -> list[Path]:
    root = root.resolve()
    seen: set[Path] = set()
    files: list[Path] = []

    for match in FILE_MENTION_PATTERN.finditer(text):
        text_before = text[: match.start()]
        if text_before and EMAIL_PREFIX_PATTERN.search(text_before):
            continue

        raw_path = match.group("path")
        clean_path = raw_path.replace("\\ ", " ")

        try:
            resolved = resolve_safe_path(root, clean_path)
        except ValueError as exc:
            warnings.append(str(exc))
            continue

        if not resolved.exists() or not resolved.is_file():
            warnings.append(f"Referenced file not found: {clean_path}")
            continue
        if resolved in seen:
            continue
        seen.add(resolved)
        files.append(resolved)

    return files


__all__ = [
    "EMAIL_PREFIX_PATTERN",
    "FILE_MENTION_PATTERN",
    "expand_file_mentions",
]
