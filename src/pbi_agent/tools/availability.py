from __future__ import annotations

from collections.abc import Iterable

from pbi_agent.config import Settings

_OPENAI_V4A_PROVIDERS = {"openai", "chatgpt"}
_OPENAI_ONLY_FILE_EDIT_TOOLS = {"replace_in_file", "write_file"}
_NON_OPENAI_FILE_EDIT_TOOLS = {"apply_patch"}
_WEB_FETCH_TOOL = "read_web_url"


def effective_excluded_tool_names(
    settings: Settings,
    excluded_names: Iterable[str] | None = None,
) -> set[str]:
    """Return session exclusions merged with provider tool policy."""

    effective = set(excluded_names or ())
    if settings.provider in _OPENAI_V4A_PROVIDERS:
        effective.update(_OPENAI_ONLY_FILE_EDIT_TOOLS)
    else:
        effective.update(_NON_OPENAI_FILE_EDIT_TOOLS)

    if not settings.web_search:
        effective.add(_WEB_FETCH_TOOL)

    return effective
