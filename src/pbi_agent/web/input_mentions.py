"""Workspace-safe `@file` mention parsing and expansion."""

from __future__ import annotations

import os
import re
import threading
from dataclasses import dataclass
from difflib import SequenceMatcher
from pathlib import Path
from typing import Literal

from pbi_agent.tools.workspace_access import resolve_safe_path
from pbi_agent.tools.workspace_filters import should_skip_directory_name

PATH_CHAR_CLASS = r"A-Za-z0-9._~/\\:-"
FILE_MENTION_PATTERN = re.compile(r"@(?P<path>(?:\\.|[" + PATH_CHAR_CLASS + r"])+)")
EMAIL_PREFIX_PATTERN = re.compile(r"[a-zA-Z0-9._%+-]$")
IMAGE_FILE_SUFFIXES = frozenset({".jpeg", ".jpg", ".png", ".webp"})

_MAX_WORKSPACE_FILES = 2_000
_MIN_FUZZY_SCORE = 15
_MIN_FUZZY_RATIO = 0.4


@dataclass(frozen=True, slots=True)
class _MentionMatch:
    path: Path
    start: int
    end: int


@dataclass(frozen=True, slots=True)
class MentionSearchResult:
    path: str
    kind: Literal["file", "image"]


class WorkspaceFileIndex:
    """In-memory workspace file cache used by mention autocomplete."""

    def __init__(self, root: Path, *, max_files: int = _MAX_WORKSPACE_FILES) -> None:
        self._root = root.resolve()
        self._max_files = max_files
        self._lock = threading.Lock()
        self._file_cache: list[str] | None = None

    def refresh_cache(self) -> None:
        with self._lock:
            self._file_cache = None

    def warm_cache(self) -> None:
        self._get_files()

    def search(self, query: str, *, limit: int = 20) -> list[MentionSearchResult]:
        normalized_query = query.strip().replace("\\ ", " ")
        bounded_limit = max(1, min(limit, 200))
        matches = _fuzzy_search(
            normalized_query,
            self._get_files(),
            limit=bounded_limit,
            include_dotfiles=normalized_query.startswith("."),
        )
        return [
            MentionSearchResult(
                path=path,
                kind="image"
                if Path(path).suffix.lower() in IMAGE_FILE_SUFFIXES
                else "file",
            )
            for path in matches
        ]

    def _get_files(self) -> list[str]:
        with self._lock:
            if self._file_cache is None:
                self._file_cache = _get_workspace_files(
                    self._root,
                    max_files=self._max_files,
                )
            return self._file_cache


def expand_file_mentions(
    text: str,
    *,
    root: Path,
    max_inline_bytes: int = 0,
) -> tuple[str, list[str]]:
    """Return input text with normalized workspace file mentions."""

    expanded, _file_paths, _image_paths, warnings = expand_input_mentions(
        text,
        root=root,
        max_inline_bytes=max_inline_bytes,
    )
    return expanded, warnings


def expand_input_mentions(
    text: str,
    *,
    root: Path,
    max_inline_bytes: int = 0,
) -> tuple[str, list[str], list[str], list[str]]:
    """Return normalized mention text plus image mention paths and warnings."""

    del max_inline_bytes
    warnings: list[str] = []
    mentioned_files = _collect_mentioned_files(text, root=root, warnings=warnings)
    if not mentioned_files:
        return text, [], [], warnings

    root = root.resolve()
    parts: list[str] = []
    cursor = 0
    file_paths: list[str] = []
    seen_file_paths: set[str] = set()
    image_paths: list[str] = []
    seen_image_paths: set[str] = set()
    for match in mentioned_files:
        relative_path = match.path.relative_to(root).as_posix()
        if relative_path not in seen_file_paths:
            seen_file_paths.add(relative_path)
            file_paths.append(relative_path)
        parts.append(text[cursor : match.start])
        parts.append(relative_path)
        cursor = match.end
        if match.path.suffix.lower() in IMAGE_FILE_SUFFIXES:
            if relative_path not in seen_image_paths:
                seen_image_paths.add(relative_path)
                image_paths.append(relative_path)

    parts.append(text[cursor:])
    return "".join(parts), file_paths, image_paths, warnings


def search_input_mentions(
    query: str,
    *,
    root: Path,
    limit: int = 20,
    index: WorkspaceFileIndex | None = None,
) -> list[MentionSearchResult]:
    """Return ranked workspace file suggestions for the browser composer."""

    mention_index = index or WorkspaceFileIndex(root)
    return mention_index.search(query, limit=limit)


def _collect_mentioned_files(
    text: str, *, root: Path, warnings: list[str]
) -> list[_MentionMatch]:
    root = root.resolve()
    files: list[_MentionMatch] = []
    index = 0
    while index < len(text):
        at_index = text.find("@", index)
        if at_index < 0:
            break
        if at_index > 0 and EMAIL_PREFIX_PATTERN.search(text[at_index - 1]):
            index = at_index + 1
            continue

        line_end = text.find("\n", at_index + 1)
        if line_end < 0:
            line_end = len(text)
        raw_segment = text[at_index + 1 : line_end]

        resolved, clean_path, consumed = _resolve_mentioned_file(raw_segment, root=root)
        if resolved is None:
            missing_path = _missing_mention_path(raw_segment)
            if missing_path:
                try:
                    resolve_safe_path(root, missing_path)
                except ValueError:
                    pass
                else:
                    warnings.append(f"Referenced file not found: {missing_path}")
            index = at_index + 1
            continue

        files.append(_MentionMatch(resolved, at_index, at_index + 1 + consumed))
        index = at_index + 1 + consumed

    return files


def _get_workspace_files(
    root: Path, *, max_files: int = _MAX_WORKSPACE_FILES
) -> list[str]:
    files: list[str] = []
    for current_root, dir_names, file_names in os.walk(
        root, topdown=True, followlinks=False
    ):
        dir_names[:] = [
            dir_name
            for dir_name in sorted(dir_names, key=str.casefold)
            if not should_skip_directory_name(dir_name)
        ]
        for file_name in sorted(file_names, key=str.casefold):
            path = Path(current_root) / file_name
            try:
                relative_path = path.relative_to(root).as_posix()
            except ValueError:
                continue
            files.append(relative_path)
            if len(files) >= max_files:
                return files
    return files


def _fuzzy_score(query: str, candidate: str) -> float:
    query_lower = query.lower()
    candidate_normalized = candidate.replace("\\", "/")
    candidate_lower = candidate_normalized.lower()
    filename = candidate_normalized.rsplit("/", 1)[-1].lower()
    filename_start = candidate_lower.rfind("/") + 1

    if query_lower in filename:
        index = filename.find(query_lower)
        if index == 0:
            return 150 + (1 / len(candidate))
        if index > 0 and filename[index - 1] in "_-.":
            return 120 + (1 / len(candidate))
        return 100 + (1 / len(candidate))

    if query_lower in candidate_lower:
        index = candidate_lower.find(query_lower)
        if index == filename_start:
            return 80 + (1 / len(candidate))
        if index == 0 or candidate[index - 1] in "/_-.":
            return 60 + (1 / len(candidate))
        return 40 + (1 / len(candidate))

    filename_ratio = SequenceMatcher(None, query_lower, filename).ratio()
    if filename_ratio > _MIN_FUZZY_RATIO:
        return filename_ratio * 30

    return SequenceMatcher(None, query_lower, candidate_lower).ratio() * 15


def _is_dotpath(path: str) -> bool:
    return any(part.startswith(".") for part in path.split("/"))


def _path_depth(path: str) -> int:
    return path.count("/")


def _fuzzy_search(
    query: str,
    candidates: list[str],
    *,
    limit: int,
    include_dotfiles: bool,
) -> list[str]:
    filtered = (
        candidates
        if include_dotfiles
        else [candidate for candidate in candidates if not _is_dotpath(candidate)]
    )
    if not query:
        return sorted(filtered, key=lambda item: (_path_depth(item), item.lower()))[
            :limit
        ]

    scored = [
        (score, candidate)
        for candidate in filtered
        if (score := _fuzzy_score(query, candidate)) >= _MIN_FUZZY_SCORE
    ]
    scored.sort(key=lambda item: -item[0])
    return [candidate for _, candidate in scored[:limit]]


def _resolve_mentioned_file(
    raw_segment: str, *, root: Path
) -> tuple[Path | None, str, int]:
    if not raw_segment or raw_segment[0].isspace():
        return None, "", 0

    for end in range(len(raw_segment), 0, -1):
        candidate = raw_segment[:end].rstrip()
        if not candidate or candidate[0].isspace():
            continue
        clean_path = candidate.replace("\\ ", " ")
        try:
            resolved = resolve_safe_path(root, clean_path)
        except ValueError:
            continue
        if resolved.exists() and resolved.is_file():
            return resolved, clean_path, len(candidate)

    return None, "", 0


def _missing_mention_path(raw_segment: str) -> str:
    if not raw_segment or raw_segment[0].isspace():
        return ""

    chars: list[str] = []
    index = 0
    while index < len(raw_segment):
        char = raw_segment[index]
        if char == "\\" and index + 1 < len(raw_segment):
            chars.extend([char, raw_segment[index + 1]])
            index += 2
            continue
        if char in " \t\r\n":
            break
        if not re.match(r"[" + PATH_CHAR_CLASS + r"]", char):
            break
        chars.append(char)
        index += 1

    return "".join(chars).replace("\\ ", " ")


__all__ = [
    "EMAIL_PREFIX_PATTERN",
    "FILE_MENTION_PATTERN",
    "IMAGE_FILE_SUFFIXES",
    "WorkspaceFileIndex",
    "expand_input_mentions",
    "expand_file_mentions",
    "MentionSearchResult",
    "search_input_mentions",
]
