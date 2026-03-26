"""Autocomplete helpers for the Textual chat composer."""

from __future__ import annotations

import asyncio
import contextlib
import os
from difflib import SequenceMatcher
from enum import StrEnum
from pathlib import Path
from typing import TYPE_CHECKING, Protocol

from pbi_agent.tools.workspace_filters import should_skip_directory_name

if TYPE_CHECKING:
    from textual import events


class CompletionResult(StrEnum):
    """Result of handling a key event in the completion system."""

    IGNORED = "ignored"
    HANDLED = "handled"
    SUBMIT = "submit"


class CompletionView(Protocol):
    """Protocol for widgets that render completion suggestions."""

    def render_completion_suggestions(
        self, suggestions: list[tuple[str, str]], selected_index: int
    ) -> None: ...

    def clear_completion_suggestions(self) -> None: ...

    def replace_completion_range(
        self, start: int, end: int, replacement: str
    ) -> None: ...


class CompletionController(Protocol):
    """Protocol implemented by completion controllers."""

    def can_handle(self, text: str, cursor_index: int) -> bool: ...

    def on_text_changed(self, text: str, cursor_index: int) -> None: ...

    def on_key(
        self, event: events.Key, text: str, cursor_index: int
    ) -> CompletionResult: ...

    def reset(self) -> None: ...


MAX_SUGGESTIONS = 10
_MAX_WORKSPACE_FILES = 2_000
_MIN_FUZZY_SCORE = 15
_MIN_FUZZY_RATIO = 0.4
_MIN_SLASH_FUZZY_SCORE = 25
_MIN_DESC_SEARCH_LEN = 2


class SlashCommandController:
    """Controller for `/command` autocomplete."""

    def __init__(
        self,
        commands: list[tuple[str, str, str]],
        view: CompletionView,
    ) -> None:
        self._commands = commands
        self._view = view
        self._suggestions: list[tuple[str, str]] = []
        self._selected_index = 0

    @staticmethod
    def can_handle(text: str, cursor_index: int) -> bool:
        return cursor_index > 0 and text.startswith("/")

    def update_commands(self, commands: list[tuple[str, str, str]]) -> None:
        self._commands = commands
        self.reset()

    def reset(self) -> None:
        if self._suggestions:
            self._suggestions.clear()
            self._selected_index = 0
            self._view.clear_completion_suggestions()

    @staticmethod
    def _score_command(search: str, cmd: str, desc: str, keywords: str = "") -> float:
        if not search:
            return 0.0

        name = cmd.lstrip("/").lower()
        lower_desc = desc.lower()
        if name.startswith(search):
            return 200.0
        if search in name:
            return 150.0
        if keywords and len(search) >= _MIN_DESC_SEARCH_LEN:
            for keyword in keywords.lower().split():
                if keyword.startswith(search) or search in keyword:
                    return 120.0
        if len(search) >= _MIN_DESC_SEARCH_LEN and search in lower_desc:
            idx = lower_desc.find(search)
            return 110.0 if idx == 0 or lower_desc[idx - 1] == " " else 90.0
        name_ratio = SequenceMatcher(None, search, name).ratio()
        desc_ratio = SequenceMatcher(None, search, lower_desc).ratio()
        best = max(name_ratio * 60, desc_ratio * 30)
        return best if best >= _MIN_SLASH_FUZZY_SCORE else 0.0

    def on_text_changed(self, text: str, cursor_index: int) -> None:
        if not self.can_handle(text, cursor_index):
            self.reset()
            return

        search = text[1:cursor_index].lower()
        if not search:
            suggestions = [(cmd, desc) for cmd, desc, _ in self._commands][
                :MAX_SUGGESTIONS
            ]
        else:
            scored = [
                (score, cmd, desc)
                for cmd, desc, keywords in self._commands
                if (score := self._score_command(search, cmd, desc, keywords)) > 0
            ]
            scored.sort(key=lambda item: -item[0])
            suggestions = [(cmd, desc) for _, cmd, desc in scored[:MAX_SUGGESTIONS]]

        if suggestions:
            self._suggestions = suggestions
            self._selected_index = 0
            self._view.render_completion_suggestions(
                self._suggestions, self._selected_index
            )
        else:
            self.reset()

    def on_key(
        self, event: events.Key, _text: str, cursor_index: int
    ) -> CompletionResult:
        if not self._suggestions:
            return CompletionResult.IGNORED

        if event.key == "tab":
            return (
                CompletionResult.HANDLED
                if self._apply_selected_completion(cursor_index)
                else CompletionResult.IGNORED
            )
        if event.key == "enter":
            return (
                CompletionResult.SUBMIT
                if self._apply_selected_completion(cursor_index)
                else CompletionResult.HANDLED
            )
        if event.key == "down":
            self._move_selection(1)
            return CompletionResult.HANDLED
        if event.key == "up":
            self._move_selection(-1)
            return CompletionResult.HANDLED
        if event.key == "escape":
            self.reset()
            return CompletionResult.HANDLED
        return CompletionResult.IGNORED

    def _move_selection(self, delta: int) -> None:
        if not self._suggestions:
            return
        count = len(self._suggestions)
        self._selected_index = (self._selected_index + delta) % count
        self._view.render_completion_suggestions(
            self._suggestions, self._selected_index
        )

    def _apply_selected_completion(self, cursor_index: int) -> bool:
        if not self._suggestions:
            return False
        command, _ = self._suggestions[self._selected_index]
        self._view.replace_completion_range(0, cursor_index, command)
        self.reset()
        return True


class FuzzyFileController:
    """Controller for `@file` autocomplete."""

    def __init__(self, view: CompletionView, *, root: Path | None = None) -> None:
        self._view = view
        self._root = (root or Path.cwd()).resolve()
        self._suggestions: list[tuple[str, str]] = []
        self._selected_index = 0
        self._file_cache: list[str] | None = None

    @staticmethod
    def can_handle(text: str, cursor_index: int) -> bool:
        if cursor_index <= 0 or cursor_index > len(text):
            return False
        before_cursor = text[:cursor_index]
        at_index = before_cursor.rfind("@")
        if at_index < 0 or cursor_index <= at_index:
            return False
        if at_index > 0 and before_cursor[at_index - 1].isalnum():
            return False
        fragment = before_cursor[at_index:cursor_index]
        return bool(fragment) and " " not in fragment

    def reset(self) -> None:
        if self._suggestions:
            self._suggestions.clear()
            self._selected_index = 0
            self._view.clear_completion_suggestions()

    def refresh_cache(self) -> None:
        self._file_cache = None

    async def warm_cache(self) -> None:
        if self._file_cache is not None:
            return
        with contextlib.suppress(Exception):
            self._file_cache = await asyncio.to_thread(_get_workspace_files, self._root)

    def on_text_changed(self, text: str, cursor_index: int) -> None:
        if not self.can_handle(text, cursor_index):
            self.reset()
            return

        before_cursor = text[:cursor_index]
        at_index = before_cursor.rfind("@")
        search = before_cursor[at_index + 1 :]
        suggestions = self._get_fuzzy_suggestions(search)
        if suggestions:
            self._suggestions = suggestions
            self._selected_index = 0
            self._view.render_completion_suggestions(
                self._suggestions, self._selected_index
            )
        else:
            self.reset()

    def _get_files(self) -> list[str]:
        if self._file_cache is None:
            self._file_cache = _get_workspace_files(self._root)
        return self._file_cache

    def _get_fuzzy_suggestions(self, search: str) -> list[tuple[str, str]]:
        include_dotfiles = search.startswith(".")
        matches = _fuzzy_search(
            search,
            self._get_files(),
            limit=MAX_SUGGESTIONS,
            include_dotfiles=include_dotfiles,
        )
        suggestions: list[tuple[str, str]] = []
        for path in matches:
            suffix = Path(path).suffix.lower()
            type_hint = suffix[1:] if suffix else "file"
            suggestions.append((f"@{path}", type_hint))
        return suggestions

    def on_key(
        self, event: events.Key, text: str, cursor_index: int
    ) -> CompletionResult:
        if not self._suggestions:
            return CompletionResult.IGNORED

        if event.key == "tab" or event.key == "enter":
            return (
                CompletionResult.HANDLED
                if self._apply_selected_completion(text, cursor_index)
                else CompletionResult.IGNORED
            )
        if event.key == "down":
            self._move_selection(1)
            return CompletionResult.HANDLED
        if event.key == "up":
            self._move_selection(-1)
            return CompletionResult.HANDLED
        if event.key == "escape":
            self.reset()
            return CompletionResult.HANDLED
        return CompletionResult.IGNORED

    def _move_selection(self, delta: int) -> None:
        if not self._suggestions:
            return
        count = len(self._suggestions)
        self._selected_index = (self._selected_index + delta) % count
        self._view.render_completion_suggestions(
            self._suggestions, self._selected_index
        )

    def _apply_selected_completion(self, text: str, cursor_index: int) -> bool:
        if not self._suggestions:
            return False
        before_cursor = text[:cursor_index]
        at_index = before_cursor.rfind("@")
        if at_index < 0:
            return False
        label, _ = self._suggestions[self._selected_index]
        self._view.replace_completion_range(at_index, cursor_index, label)
        self.reset()
        return True


class MultiCompletionManager:
    """Delegates to the first controller that matches the current input."""

    def __init__(self, controllers: list[CompletionController]) -> None:
        self._controllers = controllers
        self._active: CompletionController | None = None

    def on_text_changed(self, text: str, cursor_index: int) -> None:
        candidate = None
        for controller in self._controllers:
            if controller.can_handle(text, cursor_index):
                candidate = controller
                break

        if candidate is None:
            if self._active is not None:
                self._active.reset()
                self._active = None
            return

        if candidate is not self._active:
            if self._active is not None:
                self._active.reset()
            self._active = candidate

        candidate.on_text_changed(text, cursor_index)

    def on_key(
        self, event: events.Key, text: str, cursor_index: int
    ) -> CompletionResult:
        if self._active is None:
            return CompletionResult.IGNORED
        return self._active.on_key(event, text, cursor_index)

    def reset(self) -> None:
        if self._active is not None:
            self._active.reset()
            self._active = None


def _get_workspace_files(root: Path) -> list[str]:
    files: list[str] = []
    for current_root, dirnames, filenames in os.walk(
        root, topdown=True, followlinks=False
    ):
        dirnames[:] = [
            dirname
            for dirname in sorted(dirnames, key=str.casefold)
            if not should_skip_directory_name(dirname)
        ]
        for filename in sorted(filenames, key=str.casefold):
            path = Path(current_root) / filename
            try:
                relative = path.relative_to(root).as_posix()
            except ValueError:
                continue
            files.append(relative)
            if len(files) >= _MAX_WORKSPACE_FILES:
                return files
    return files


def _fuzzy_score(query: str, candidate: str) -> float:
    query_lower = query.lower()
    candidate_normalized = candidate.replace("\\", "/")
    candidate_lower = candidate_normalized.lower()
    filename = candidate_normalized.rsplit("/", 1)[-1].lower()
    filename_start = candidate_lower.rfind("/") + 1

    if query_lower in filename:
        idx = filename.find(query_lower)
        if idx == 0:
            return 150 + (1 / len(candidate))
        if idx > 0 and filename[idx - 1] in "_-.":
            return 120 + (1 / len(candidate))
        return 100 + (1 / len(candidate))

    if query_lower in candidate_lower:
        idx = candidate_lower.find(query_lower)
        if idx == filename_start:
            return 80 + (1 / len(candidate))
        if idx == 0 or candidate[idx - 1] in "/_-.":
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
    limit: int = MAX_SUGGESTIONS,
    *,
    include_dotfiles: bool = False,
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


__all__ = [
    "CompletionController",
    "CompletionResult",
    "CompletionView",
    "FuzzyFileController",
    "MAX_SUGGESTIONS",
    "MultiCompletionManager",
    "SlashCommandController",
]
