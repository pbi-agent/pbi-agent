from __future__ import annotations

from collections.abc import Iterable
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pbi_agent.config import Settings

_V4A_FILE_EDIT_PROVIDERS = {"openai", "chatgpt"}
_TOOLS_EXCLUDED_FOR_V4A_PROVIDERS = {"replace_in_file", "write_file"}
_TOOLS_EXCLUDED_FOR_NON_V4A_PROVIDERS = {"apply_patch"}
_WEB_FETCH_TOOL = "read_web_url"
_WEB_SEARCH_TOOL = "web_search"
UI_ONLY_TOOL_NAMES = frozenset({"ask_user"})
UI_ONLY_TOOL_CATEGORIES: dict[str, frozenset[str]] = {
    "ask-user": UI_ONLY_TOOL_NAMES,
}
BUILTIN_TOOL_CATEGORIES: dict[str, frozenset[str]] = {
    "read-image": frozenset({"read_image"}),
    "write": frozenset({"apply_patch", "replace_in_file", "write_file"}),
    "web": frozenset({_WEB_FETCH_TOOL, _WEB_SEARCH_TOOL}),
    "sub-agent": frozenset({"sub_agent"}),
    "shell": frozenset({"shell", "background_task"}),
}
BUILTIN_TOOL_NAMES = frozenset().union(*BUILTIN_TOOL_CATEGORIES.values())
# Accepted spellings for built-in tool groups; `read` predates `read-image`.
BUILTIN_TOOL_CATEGORY_ALIASES: dict[str, str] = {
    "read": "read-image",
    "read_image": "read-image",
}


def normalize_tool_categories(
    allowed_tools: Iterable[str] | None,
) -> tuple[str, ...] | None:
    """Map alias tool-group names to canonical names, dropping duplicates."""

    if allowed_tools is None:
        return None
    normalized: list[str] = []
    for category in allowed_tools:
        canonical = BUILTIN_TOOL_CATEGORY_ALIASES.get(category, category)
        if canonical not in normalized:
            normalized.append(canonical)
    return tuple(normalized)


def default_excluded_tool_names(
    excluded_names: Iterable[str] | None = None,
) -> set[str]:
    if excluded_names is None:
        return set(UI_ONLY_TOOL_NAMES)
    return set(excluded_names)


def effective_excluded_tool_names(
    settings: Settings,
    excluded_names: Iterable[str] | None = None,
) -> set[str]:
    """Return session exclusions merged with provider tool policy."""

    effective = default_excluded_tool_names(excluded_names)
    if settings.provider in _V4A_FILE_EDIT_PROVIDERS:
        effective.update(_TOOLS_EXCLUDED_FOR_V4A_PROVIDERS)
    else:
        effective.update(_TOOLS_EXCLUDED_FOR_NON_V4A_PROVIDERS)

    effective.update(disabled_builtin_tool_names(settings))
    if settings.allowed_tools is not None:
        effective.difference_update(enabled_ui_only_tool_names(settings))

    return effective


def enabled_ui_only_tool_names(settings: Settings) -> set[str]:
    allowed_tools = settings.allowed_tools
    if allowed_tools is None:
        return set()
    allowed: set[str] = set()
    for category in allowed_tools:
        allowed.update(UI_ONLY_TOOL_CATEGORIES.get(category, ()))
    return allowed


def enabled_builtin_tool_names(settings: Settings) -> set[str]:
    allowed_tools = settings.allowed_tools
    if allowed_tools is None:
        return set(BUILTIN_TOOL_NAMES)
    allowed: set[str] = set()
    for category in normalize_tool_categories(allowed_tools) or ():
        if category not in BUILTIN_TOOL_CATEGORIES:
            continue
        allowed.update(BUILTIN_TOOL_CATEGORIES[category])
    return allowed


def disabled_builtin_tool_names(settings: Settings) -> set[str]:
    return set(BUILTIN_TOOL_NAMES) - enabled_builtin_tool_names(settings)


def without_ui_only_tool_categories(
    allowed_tools: tuple[str, ...] | None,
) -> tuple[str, ...] | None:
    if allowed_tools is None:
        return None
    return tuple(
        category
        for category in allowed_tools
        if category not in UI_ONLY_TOOL_CATEGORIES
    )
