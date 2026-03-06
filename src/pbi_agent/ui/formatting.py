"""Formatting helpers for the Textual chat UI."""

from __future__ import annotations

import json
import re
from typing import Any

from pbi_agent import __version__
from pbi_agent.models.messages import TokenUsage

TOOL_STYLE_MAP = {
    "shell": "shell",
    "apply_patch": "apply-patch",
    "skill_knowledge": "skill-knowledge",
    "init_report": "init-report",
}
REDACTED_THINKING_NOTICE = "[dim]Some thinking was encrypted for safety reasons.[/dim]"
_MARKDOWN_DECORATION_RE = re.compile(r"[*_`~]+")


def shorten(text: str, limit: int = 80) -> str:
    if len(text) <= limit:
        return text
    return text[: limit - 1] + "\u2026"


def compact_json(value: Any) -> str:
    try:
        return json.dumps(value, separators=(",", ":"), ensure_ascii=False)
    except TypeError:
        return str(value)


def escape_markup_text(text: str) -> str:
    """Escape literal '[' so dynamic values can't break Rich markup parsing."""
    return text.replace("[", r"\[")


def format_reasoning_title(
    summary: str, *, fallback: str = "Thinking...", limit: int = 96
) -> str:
    normalized = summary.strip()
    if not normalized:
        return fallback
    normalized = next(
        (line.strip() for line in normalized.splitlines() if line.strip()),
        "",
    )
    if not normalized:
        return fallback
    normalized = _MARKDOWN_DECORATION_RE.sub("", normalized)
    normalized = normalized.lstrip("#>- ")
    return shorten(normalized, limit)


def format_usage_summary(
    usage: TokenUsage,
    *,
    elapsed_seconds: float | None = None,
    label: str | None = None,
) -> str:
    total = f"{usage.total_tokens:,}"
    inp = f"{usage.input_tokens:,}"
    cached = f"{usage.cached_input_tokens:,}"
    cache_w = usage.cache_write_tokens + usage.cache_write_1h_tokens
    out = f"{usage.output_tokens:,}"
    cost = f"${usage.estimated_cost_usd:.3f}"
    cache_detail = f"{cached} cached"
    if cache_w:
        cache_detail += f" [dim]\u00b7[/dim] {cache_w:,} cache-write"
    out_detail = f"{out} out"
    if usage.reasoning_tokens:
        out_detail += f" [dim]\u00b7[/dim] {usage.reasoning_tokens:,} reasoning"
    parts = [
        f"[dim]{total} tokens[/dim]  "
        f"({inp} in [dim]\u00b7[/dim] {cache_detail} [dim]\u00b7[/dim] {out_detail})",
        cost,
    ]
    if elapsed_seconds is not None:
        total_secs = int(elapsed_seconds)
        hours, remainder = divmod(total_secs, 3600)
        minutes, seconds = divmod(remainder, 60)
        time_str = (
            f"{hours}:{minutes:02d}:{seconds:02d}"
            if hours > 0
            else f"{minutes}:{seconds:02d}"
        )
        parts.append(time_str)
    body = "  [dim]|[/dim]  ".join(parts)
    if label:
        return f"[dim]{label}[/dim]  {body}"
    return body


def format_session_subtitle(usage: TokenUsage) -> str:
    return (
        f"v{__version__} \u00b7 Session {usage.total_tokens:,} tokens "
        f"\u00b7 ${usage.estimated_cost_usd:.3f}"
    )


def status_markup(
    *,
    success: bool | None = None,
    timed_out: bool = False,
    exit_code: int | None = None,
) -> str:
    if timed_out:
        return "[yellow]timeout[/yellow]"
    if success is not None:
        return "[green]done[/green]" if success else "[red]FAILED[/red]"
    if exit_code == 0:
        return "[green]done[/green]"
    return f"[red]exit {exit_code}[/red]"


def to_dict(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if isinstance(value, str) and value.strip():
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            return {}
        if isinstance(parsed, dict):
            return parsed
    return {}


def tool_style_key(tool_name: str) -> str:
    normalized = tool_name.strip().lower()
    return TOOL_STYLE_MAP.get(normalized, "generic")


def tool_group_class(tool_name: str) -> str:
    return f"tool-group-{tool_style_key(tool_name)}"


def tool_item_class(tool_name: str) -> str:
    return f"tool-call-{tool_style_key(tool_name)}"


__all__ = [
    "REDACTED_THINKING_NOTICE",
    "compact_json",
    "escape_markup_text",
    "format_reasoning_title",
    "format_session_subtitle",
    "format_usage_summary",
    "shorten",
    "status_markup",
    "to_dict",
    "tool_group_class",
    "tool_item_class",
]
