"""Workspace-safe `@file` mention parsing and expansion."""

from __future__ import annotations

import errno
import re
import threading
from dataclasses import dataclass
from difflib import SequenceMatcher
from pathlib import Path
from typing import Literal

from pbi_agent.web.scan import scan_workspace_files

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
class _MentionResolveResult:
    path: Path | None
    clean_path: str
    consumed: int
    path_too_long: bool = False


@dataclass(frozen=True, slots=True)
class MentionSearchResult:
    path: str
    kind: Literal["file", "image"]


ScanStatus = Literal["idle", "scanning", "ready", "failed"]


@dataclass(frozen=True, slots=True)
class MentionSearchPayload:
    items: list[MentionSearchResult]
    scan_status: ScanStatus
    is_stale: bool
    file_count: int
    error: str | None = None


class WorkspaceFileIndex:
    """In-memory workspace file snapshot used by mention autocomplete."""

    def __init__(self, root: Path, *, max_files: int = _MAX_WORKSPACE_FILES) -> None:
        self._root = root.resolve()
        self._max_files = max_files
        self._lock = threading.Lock()
        self._file_cache: list[str] | None = None
        self._status: ScanStatus = "idle"
        self._error: str | None = None
        self._scan_thread: threading.Thread | None = None

    def refresh_cache(self) -> None:
        self.start_refresh()

    def warm_cache(self) -> None:
        self.start_refresh()

    def start_refresh(self) -> None:
        with self._lock:
            if self._scan_thread is not None and self._scan_thread.is_alive():
                return
            self._status = "scanning"
            self._error = None
            thread = threading.Thread(
                target=self._refresh_in_background,
                name="pbi-file-mention-scan",
                daemon=True,
            )
            self._scan_thread = thread
            thread.start()

    def search(self, query: str, *, limit: int = 20) -> MentionSearchPayload:
        normalized_query = query.strip().replace("\\ ", " ")
        bounded_limit = max(1, min(limit, 200))
        files, status, error, is_stale = self._snapshot()
        if files is None:
            self.start_refresh()
            files, status, error, is_stale = self._snapshot()
        file_list = files or []
        matches = _fuzzy_search(
            normalized_query,
            file_list,
            limit=bounded_limit,
            include_dotfiles=normalized_query.startswith("."),
        )
        return MentionSearchPayload(
            items=[
                MentionSearchResult(
                    path=path,
                    kind="image"
                    if Path(path).suffix.lower() in IMAGE_FILE_SUFFIXES
                    else "file",
                )
                for path in matches
            ],
            scan_status=status,
            is_stale=is_stale,
            file_count=len(file_list),
            error=error,
        )

    def wait_for_refresh(self, timeout: float | None = None) -> None:
        with self._lock:
            thread = self._scan_thread
        if thread is not None:
            thread.join(timeout=timeout)

    def _snapshot(self) -> tuple[list[str] | None, ScanStatus, str | None, bool]:
        with self._lock:
            files = self._file_cache
            status = self._status
            error = self._error
            is_stale = files is not None and status == "scanning"
            return files, status, error, is_stale

    def _refresh_in_background(self) -> None:
        result = scan_workspace_files(self._root)
        next_files = result.files[: self._max_files]
        with self._lock:
            if result.error is not None:
                self._status = "failed"
                self._error = result.error
                if self._file_cache is None:
                    self._file_cache = []
            else:
                self._status = "ready"
                self._error = None
                self._file_cache = next_files


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
    mention_index.warm_cache()
    mention_index.wait_for_refresh(timeout=5)
    return mention_index.search(query, limit=limit).items


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

        result = _resolve_mentioned_file(raw_segment, root=root)
        if result.path is None:
            if result.path_too_long:
                warnings.append("Referenced file path is too long and was ignored.")
            else:
                missing_path = _missing_mention_path(raw_segment)
                if missing_path:
                    try:
                        _resolve_workspace_path(root, missing_path)
                    except (OSError, ValueError):
                        pass
                    else:
                        warnings.append(f"Referenced file not found: {missing_path}")
            index = at_index + 1
            continue

        files.append(
            _MentionMatch(result.path, at_index, at_index + 1 + result.consumed)
        )
        index = at_index + 1 + result.consumed

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


def _resolve_workspace_path(root: Path, raw_path: str) -> Path:
    candidate = Path(raw_path)
    resolved = (
        candidate.resolve(strict=False)
        if candidate.is_absolute()
        else (root / candidate).resolve(strict=False)
    )
    resolved.relative_to(root)
    return resolved


def _resolve_mentioned_file(raw_segment: str, *, root: Path) -> _MentionResolveResult:
    if not raw_segment or raw_segment[0].isspace():
        return _MentionResolveResult(None, "", 0)

    path_too_long = False
    for end in range(len(raw_segment), 0, -1):
        candidate = raw_segment[:end].rstrip()
        if not candidate or candidate[0].isspace():
            continue
        clean_path = candidate.replace("\\ ", " ")
        try:
            resolved = _resolve_workspace_path(root, clean_path)
        except OSError as exc:
            if exc.errno == errno.ENAMETOOLONG:
                path_too_long = True
            continue
        except ValueError:
            continue
        try:
            if resolved.is_file():
                return _MentionResolveResult(resolved, clean_path, len(candidate))
        except OSError as exc:
            if exc.errno == errno.ENAMETOOLONG:
                path_too_long = True
            continue

    return _MentionResolveResult(None, "", 0, path_too_long=path_too_long)


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
    "MentionSearchPayload",
    "MentionSearchResult",
    "ScanStatus",
    "search_input_mentions",
]
