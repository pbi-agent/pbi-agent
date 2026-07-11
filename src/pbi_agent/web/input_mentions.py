"""Workspace-safe `@file` mention parsing and expansion."""

from __future__ import annotations

import errno
import heapq
import re
import threading
import uuid
from collections.abc import Iterator
from dataclasses import dataclass
from difflib import SequenceMatcher
from pathlib import Path
from typing import Literal

from pbi_agent.web.scan import WorkspaceScanResult, scan_workspace_files

PATH_CHAR_CLASS = r"A-Za-z0-9._~/\\:-"
FILE_MENTION_PATTERN = re.compile(r"@(?P<path>(?:\\.|[" + PATH_CHAR_CLASS + r"])+)")
EMAIL_PREFIX_PATTERN = re.compile(r"[a-zA-Z0-9._%+-]$")
IMAGE_FILE_SUFFIXES = frozenset({".jpeg", ".jpg", ".png", ".webp"})
AGENT_MENTION_PREFIX_PATTERN = re.compile(
    r"^[A-Za-z][A-Za-z0-9_-]*(?:\s+\(agent\))?(?=$|[\s()[\]{}'\"`,;])"
)

_MAX_WORKSPACE_INDEX_FILES = 100_000
_MAX_WORKSPACE_TREE_FILES = 10_000
_MAX_FUZZY_CANDIDATES = 5_000
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


FileMentionRank = tuple[int, float, int, int, str, str]


def _folded_character_mask(value: str) -> int:
    mask = 0
    for character in value:
        mask |= 1 << (ord(character) % 64)
    return mask


@dataclass(frozen=True, slots=True)
class _IndexedWorkspaceFile:
    path: str
    folded_path: str
    filename: str
    character_mask: int
    depth: int
    kind: Literal["file", "image"]

    @classmethod
    def from_path(cls, path: str) -> _IndexedWorkspaceFile:
        normalized_path = path.replace("\\", "/")
        folded_path = normalized_path.casefold()
        filename = folded_path.rsplit("/", 1)[-1]
        return cls(
            path=path,
            folded_path=folded_path,
            filename=filename,
            character_mask=_folded_character_mask(filename),
            depth=normalized_path.count("/"),
            kind=(
                "image"
                if Path(normalized_path).suffix.casefold() in IMAGE_FILE_SUFFIXES
                else "file"
            ),
        )


ScanStatus = Literal["idle", "scanning", "ready", "failed"]


@dataclass(frozen=True, slots=True)
class MentionSearchPayload:
    items: list[MentionSearchResult]
    scan_status: ScanStatus
    is_stale: bool
    file_count: int
    index_generation: str
    index_revision: int
    truncated: bool
    search_approximated: bool
    error: str | None = None


@dataclass(frozen=True, slots=True)
class WorkspaceFileTreePayload:
    items: list[MentionSearchResult]
    scan_status: ScanStatus
    is_stale: bool
    file_count: int
    index_generation: str
    index_revision: int
    truncated: bool
    search_approximated: bool = False
    error: str | None = None


class WorkspaceFileIndex:
    """In-memory workspace file snapshot used by mention autocomplete."""

    def __init__(
        self,
        root: Path,
        *,
        max_files: int = _MAX_WORKSPACE_INDEX_FILES,
        max_tree_files: int = _MAX_WORKSPACE_TREE_FILES,
    ) -> None:
        self._root = root.resolve()
        self._max_files = max(1, max_files)
        self._max_tree_files = max(1, max_tree_files)
        self._lock = threading.Lock()
        self._file_cache: list[_IndexedWorkspaceFile] | None = None
        self._file_lookup: dict[str, _IndexedWorkspaceFile] | None = None
        self._index_generation = uuid.uuid4().hex
        self._index_revision = 0
        self._truncated = False
        self._status: ScanStatus = "idle"
        self._error: str | None = None
        self._scan_thread: threading.Thread | None = None
        self._refresh_pending = False

    def refresh_cache(self) -> None:
        self.start_refresh(queue_if_running=True)

    def warm_cache(self) -> None:
        self.start_refresh()

    def start_refresh(self, *, queue_if_running: bool = False) -> None:
        with self._lock:
            if self._scan_thread is not None:
                if queue_if_running:
                    self._refresh_pending = True
                return
            self._status = "scanning"
            self._error = None
            self._refresh_pending = False
            thread = threading.Thread(
                target=self._refresh_in_background,
                name="pbi-file-mention-scan",
                daemon=True,
            )
            self._scan_thread = thread
            thread.start()

    def search(
        self,
        query: str,
        *,
        limit: int = 20,
        refresh: bool = False,
        exact: bool = False,
    ) -> MentionSearchPayload:
        normalized_query = query.strip().replace("\\ ", " ")
        bounded_limit = max(1, min(limit, 200))
        if refresh:
            self.refresh_cache()
        files, lookup, status, error, is_stale, index_revision, truncated = (
            self._snapshot()
        )
        if files is None and status == "idle":
            self.start_refresh()
            files, lookup, status, error, is_stale, index_revision, truncated = (
                self._snapshot()
            )
        file_list = files or []
        if exact:
            exact_match = (lookup or {}).get(normalized_query)
            matches = [exact_match] if exact_match is not None else []
            search_approximated = False
        else:
            matches, search_approximated = _search_index(
                normalized_query,
                file_list,
                limit=bounded_limit,
            )
        return MentionSearchPayload(
            items=[
                MentionSearchResult(
                    path=item.path,
                    kind=item.kind,
                )
                for item in matches
            ],
            scan_status=status,
            is_stale=is_stale,
            file_count=len(file_list),
            index_generation=self._index_generation,
            index_revision=index_revision,
            truncated=truncated,
            search_approximated=search_approximated,
            error=error,
        )

    def tree_snapshot(self) -> WorkspaceFileTreePayload:
        files, _lookup, status, error, is_stale, index_revision, index_truncated = (
            self._snapshot()
        )
        if files is None and status == "idle":
            self.start_refresh()
            (
                files,
                _lookup,
                status,
                error,
                is_stale,
                index_revision,
                index_truncated,
            ) = self._snapshot()
        file_list = files or []
        tree_files = file_list[: self._max_tree_files]
        return WorkspaceFileTreePayload(
            items=[
                MentionSearchResult(
                    path=item.path,
                    kind=item.kind,
                )
                for item in tree_files
            ],
            scan_status=status,
            is_stale=is_stale,
            file_count=len(file_list),
            index_generation=self._index_generation,
            index_revision=index_revision,
            truncated=index_truncated or len(file_list) > self._max_tree_files,
            search_approximated=False,
            error=error,
        )

    def wait_for_refresh(self, timeout: float | None = None) -> None:
        with self._lock:
            thread = self._scan_thread
        if thread is not None:
            thread.join(timeout=timeout)

    def _snapshot(
        self,
    ) -> tuple[
        list[_IndexedWorkspaceFile] | None,
        dict[str, _IndexedWorkspaceFile] | None,
        ScanStatus,
        str | None,
        bool,
        int,
        bool,
    ]:
        with self._lock:
            files = self._file_cache
            status = self._status
            error = self._error
            is_stale = files is not None and status == "scanning"
            return (
                files,
                self._file_lookup,
                status,
                error,
                is_stale,
                self._index_revision,
                self._truncated,
            )

    def _refresh_in_background(self) -> None:
        while True:
            try:
                result = scan_workspace_files(self._root)
            except Exception as exc:
                result = WorkspaceScanResult(error=str(exc))

            next_files = [
                _IndexedWorkspaceFile.from_path(path)
                for path in result.files[: self._max_files]
            ]
            next_truncated = len(result.files) > self._max_files
            with self._lock:
                if result.error is not None:
                    self._status = "failed"
                    self._error = result.error
                else:
                    if (
                        self._file_cache is None
                        or self._file_cache != next_files
                        or self._truncated != next_truncated
                    ):
                        self._index_revision += 1
                    self._status = "ready"
                    self._error = None
                    self._file_cache = next_files
                    self._file_lookup = {item.path: item for item in next_files}
                    self._truncated = next_truncated

                if self._refresh_pending:
                    self._refresh_pending = False
                    self._status = "scanning"
                    self._error = None
                    continue

                self._scan_thread = None
                self._refresh_pending = False
                return


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
            if AGENT_MENTION_PREFIX_PATTERN.match(raw_segment):
                index = at_index + 1
                continue
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


def _has_token_prefix(query: str, candidate: str) -> bool:
    start = candidate.find(query)
    while start >= 0:
        if start == 0 or candidate[start - 1] in "/_.-":
            return True
        start = candidate.find(query, start + 1)
    return False


def _direct_file_match_tier(
    query: str,
    candidate: _IndexedWorkspaceFile,
) -> int | None:
    if candidate.folded_path == query:
        return 0
    if candidate.filename == query:
        return 1
    if candidate.filename.startswith(query):
        return 2
    if _has_token_prefix(query, candidate.folded_path):
        return 3
    if query in candidate.filename:
        return 4
    if query in candidate.folded_path:
        return 5
    return None


def _fuzzy_similarity(query: str, candidate: _IndexedWorkspaceFile) -> float:
    filename_ratio = SequenceMatcher(None, query, candidate.filename).ratio()
    if filename_ratio > _MIN_FUZZY_RATIO:
        return filename_ratio * 100
    return SequenceMatcher(None, query, candidate.folded_path).ratio() * 50


def _rank_indexed_file(
    query: str,
    candidate: _IndexedWorkspaceFile,
    *,
    include_fuzzy: bool,
) -> FileMentionRank | None:
    if not query:
        tier = 8
        fuzzy_order = 0.0
    elif (direct_tier := _direct_file_match_tier(query, candidate)) is not None:
        tier = direct_tier
        fuzzy_order = 0.0
    elif include_fuzzy:
        fuzzy_score = _fuzzy_similarity(query, candidate)
        if fuzzy_score < _MIN_FUZZY_SCORE:
            return None
        tier = 6
        fuzzy_order = -fuzzy_score
    else:
        return None
    return (
        tier,
        fuzzy_order,
        candidate.depth,
        len(candidate.path),
        candidate.folded_path,
        candidate.path,
    )


def file_mention_rank(query: str, path: str) -> FileMentionRank | None:
    """Return the shared rank tuple for a file mention candidate."""

    return _rank_indexed_file(
        query.strip().replace("\\ ", " ").casefold(),
        _IndexedWorkspaceFile.from_path(path),
        include_fuzzy=True,
    )


def _fuzzy_prefilter_rank(
    query_character_mask: int,
    query_length: int,
    candidate: _IndexedWorkspaceFile,
) -> tuple[int, int, int, int, str, str]:
    return (
        -(query_character_mask & candidate.character_mask).bit_count(),
        abs(len(candidate.filename) - query_length),
        candidate.depth,
        len(candidate.path),
        candidate.folded_path,
        candidate.path,
    )


def _search_index(
    query: str,
    candidates: list[_IndexedWorkspaceFile],
    *,
    limit: int,
) -> tuple[list[_IndexedWorkspaceFile], bool]:
    normalized_query = query.casefold()
    if not normalized_query:
        ranked = heapq.nsmallest(
            limit,
            (
                (rank, candidate)
                for candidate in candidates
                if (
                    rank := _rank_indexed_file(
                        normalized_query,
                        candidate,
                        include_fuzzy=False,
                    )
                )
                is not None
            ),
            key=lambda item: item[0],
        )
        return [candidate for _rank, candidate in ranked], False

    direct_matches = heapq.nsmallest(
        limit,
        (
            (rank, candidate)
            for candidate in candidates
            if (
                rank := _rank_indexed_file(
                    normalized_query,
                    candidate,
                    include_fuzzy=False,
                )
            )
            is not None
        ),
        key=lambda item: item[0],
    )
    if len(direct_matches) >= limit:
        return [candidate for _rank, candidate in direct_matches], False

    fuzzy_candidate_count = 0

    def iter_fuzzy_candidates() -> Iterator[_IndexedWorkspaceFile]:
        nonlocal fuzzy_candidate_count
        for candidate in candidates:
            if _direct_file_match_tier(normalized_query, candidate) is not None:
                continue
            fuzzy_candidate_count += 1
            yield candidate

    query_character_mask = _folded_character_mask(normalized_query)
    fuzzy_candidates = heapq.nsmallest(
        _MAX_FUZZY_CANDIDATES,
        iter_fuzzy_candidates(),
        key=lambda candidate: _fuzzy_prefilter_rank(
            query_character_mask,
            len(normalized_query),
            candidate,
        ),
    )
    fuzzy_matches = heapq.nsmallest(
        limit - len(direct_matches),
        (
            (rank, candidate)
            for candidate in fuzzy_candidates
            if (
                rank := _rank_indexed_file(
                    normalized_query,
                    candidate,
                    include_fuzzy=True,
                )
            )
            is not None
        ),
        key=lambda item: item[0],
    )
    return (
        [candidate for _rank, candidate in [*direct_matches, *fuzzy_matches]],
        fuzzy_candidate_count > _MAX_FUZZY_CANDIDATES,
    )


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
    "file_mention_rank",
    "MentionSearchPayload",
    "MentionSearchResult",
    "ScanStatus",
    "WorkspaceFileTreePayload",
    "search_input_mentions",
]
