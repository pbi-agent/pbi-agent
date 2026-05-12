from __future__ import annotations

from collections.abc import Iterable

from pbi_agent.config import Settings

_V4A_FILE_EDIT_PROVIDERS = {"openai", "chatgpt"}
_TOOLS_EXCLUDED_FOR_V4A_PROVIDERS = {"replace_in_file", "write_file"}
_TOOLS_EXCLUDED_FOR_NON_V4A_PROVIDERS = {"apply_patch"}
_WEB_FETCH_TOOL = "read_web_url"


def effective_excluded_tool_names(
    settings: Settings,
    excluded_names: Iterable[str] | None = None,
) -> set[str]:
    """Return session exclusions merged with provider tool policy."""

    effective = set(excluded_names or ())
    if settings.provider in _V4A_FILE_EDIT_PROVIDERS:
        effective.update(_TOOLS_EXCLUDED_FOR_V4A_PROVIDERS)
    else:
        effective.update(_TOOLS_EXCLUDED_FOR_NON_V4A_PROVIDERS)

    if not settings.web_search:
        effective.add(_WEB_FETCH_TOOL)

    return effective
