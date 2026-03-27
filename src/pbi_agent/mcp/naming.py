from __future__ import annotations

import re

_NON_IDENTIFIER_CHARS_RE = re.compile(r"[^a-z0-9]+")


def sanitize_mcp_component(value: str, *, fallback: str) -> str:
    normalized = value.strip().lower()
    normalized = _NON_IDENTIFIER_CHARS_RE.sub("_", normalized).strip("_")
    if not normalized:
        normalized = fallback
    if normalized[0].isdigit():
        normalized = f"_{normalized}"
    return normalized


def make_mcp_tool_name(server_name: str, tool_name: str) -> str:
    server = sanitize_mcp_component(server_name, fallback="server")
    tool = sanitize_mcp_component(tool_name, fallback="tool")
    return f"{server}__{tool}"


def parse_mcp_tool_name(value: str) -> tuple[str, str] | None:
    normalized = value.strip().lower()
    if "__" not in normalized:
        return None
    server, sep, tool = normalized.partition("__")
    if not sep or not server or not tool:
        return None
    return server, tool


def display_name_for_mcp_tool(value: str) -> str:
    parsed = parse_mcp_tool_name(value)
    if parsed is None:
        return value
    server, tool = parsed
    return f"mcp:{server}/{tool}"
