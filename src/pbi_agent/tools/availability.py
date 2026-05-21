from __future__ import annotations

from collections.abc import Iterable
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pbi_agent.config import Settings

_V4A_FILE_EDIT_PROVIDERS = {"openai", "chatgpt"}
_TOOLS_EXCLUDED_FOR_V4A_PROVIDERS = {"replace_in_file", "write_file"}
_TOOLS_EXCLUDED_FOR_NON_V4A_PROVIDERS = {"apply_patch"}
_WEB_FETCH_TOOL = "read_web_url"
UI_ONLY_TOOL_NAMES = frozenset({"ask_user"})
BUILTIN_TOOL_CATEGORIES: dict[str, frozenset[str]] = {
    "read": frozenset({"read_file", "search_workspace"}),
    "write": frozenset({"apply_patch", "replace_in_file", "write_file"}),
    "web": frozenset({_WEB_FETCH_TOOL}),
    "sub-agent": frozenset({"sub_agent"}),
    "shell": frozenset({"shell"}),
}
BUILTIN_TOOL_NAMES = frozenset().union(*BUILTIN_TOOL_CATEGORIES.values())


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

    return effective


def allowed_builtin_tool_names(settings: Settings) -> set[str]:
    categories = settings.allowed_builtin_tool_categories
    names = settings.allowed_builtin_tool_names
    if categories is None and names is None:
        return set(BUILTIN_TOOL_NAMES)
    allowed: set[str] = set()
    for category in categories or ():
        allowed.update(BUILTIN_TOOL_CATEGORIES[category])
    allowed.update(names or ())
    return allowed


def disabled_builtin_tool_names(settings: Settings) -> set[str]:
    return set(BUILTIN_TOOL_NAMES) - allowed_builtin_tool_names(settings)


def native_web_search_enabled(settings: Settings) -> bool:
    if not settings.web_search:
        return False
    categories = settings.allowed_builtin_tool_categories
    names = settings.allowed_builtin_tool_names
    if categories is None and names is None:
        return True
    return "web" in (categories or ())
