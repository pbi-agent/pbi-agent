"""Formatting helpers shared by console and browser displays."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from pbi_agent import __version__
from pbi_agent.mcp import display_name_for_mcp_tool
from pbi_agent.mcp.naming import parse_mcp_tool_name
from pbi_agent.models.messages import TokenUsage, context_window_for_model

TOOL_STYLE_MAP = {
    "shell": "shell",
    "apply_patch": "apply-patch",
    "list_files": "list-files",
    "search_files": "search-files",
    "read_file": "read-file",
    "read_image": "read-image",
    "read_web_url": "read-web-url",
    "python_exec": "python-exec",
    "sub_agent": "sub-agent",
    "mcp": "mcp",
    "web_search": "web-search",
}
TOOL_ICONS: dict[str, str] = {
    "shell": "\u25b6",  # ▶
    "apply-patch": "\u25a0",  # ■
    "list-files": "\u2630",  # ☰
    "search-files": "\u2315",  # ⌕
    "read-file": "\u2610",  # ☐
    "read-image": "\U0001f5bc",  # 🖼
    "read-web-url": "\U0001f310",  # 🌐
    "python-exec": "\u2699",  # ⚙
    "sub-agent": "\u25c9",  # ◉
    "mcp": "\u25a7",  # ▧
    "web-search": "\U0001f50d",  # 🔍
    "generic": "\u2022",  # •
}

TOOL_BORDER_STYLES: dict[str, str] = {
    "shell": "blue",
    "apply-patch": "#F97316",
    "list-files": "#818CF8",
    "search-files": "#EC4899",
    "read-file": "#EAB308",
    "read-image": "#FB7185",
    "read-web-url": "#06B6D4",
    "python-exec": "#A855F7",
    "sub-agent": "#F59E0B",
    "mcp": "#14B8A6",
    "web-search": "#0EA5E9",
    "mixed": "#8B5CF6",
    "generic": "blue",
}

REDACTED_THINKING_NOTICE = "[dim]Some thinking was encrypted for safety reasons.[/dim]"
_MARKDOWN_DECORATION_RE = re.compile(r"[*_`~]+")
_ELLIPSIS_ONLY_RE = re.compile(r"^[.\u2026\s]+$")
_PATH_SEPARATOR_RE = re.compile(r"[\\/]+")


def shorten(text: str, limit: int = 80) -> str:
    if len(text) <= limit:
        return text
    return text[: limit - 1] + "\u2026"


def format_informal_path(path: str | Path, *, levels: int = 2) -> str:
    """Return a compact path label using the last ``levels`` segments."""
    raw = str(path).strip()
    if not raw:
        return "."
    if raw in {".", "./", ".\\"}:
        return "."
    if raw in {"/", "\\"}:
        return "/"

    normalized = raw.replace("\\", "/")
    parts = [
        part for part in _PATH_SEPARATOR_RE.split(normalized) if part and part != "."
    ]
    if not parts:
        return "/" if normalized.startswith("/") else "."
    if len(parts) == 1 and parts[0].endswith(":") and normalized.endswith("/"):
        return f"{parts[0]}/"
    return "/".join(parts[-levels:])


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


def resolve_reasoning_body(text: str | None, summary: str | None) -> str | None:
    normalized_body = text.strip() if text is not None else ""
    if normalized_body and not _ELLIPSIS_ONLY_RE.fullmatch(normalized_body):
        return text

    normalized_summary = summary.strip() if summary is not None else ""
    if normalized_summary:
        return normalized_summary

    if normalized_body:
        return text
    return None


def resolve_reasoning_panel(
    text: str | None,
    summary: str | None,
    *,
    fallback_title: str = "Thinking...",
) -> tuple[str | None, str]:
    normalized_summary = summary.strip() if summary is not None else ""
    body = resolve_reasoning_body(text, summary)
    if body is None:
        return None, format_reasoning_title(normalized_summary, fallback=fallback_title)

    using_summary_as_body = bool(normalized_summary) and body == normalized_summary
    title_text = fallback_title if using_summary_as_body else normalized_summary
    return body, format_reasoning_title(title_text, fallback=fallback_title)


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
    if usage.tool_use_tokens:
        out_detail += f" [dim]\u00b7[/dim] {usage.tool_use_tokens:,} tool-use"
    parts = [
        f"[dim]{total} tokens[/dim]  "
        f"({inp} in [dim]\u00b7[/dim] {cache_detail} [dim]\u00b7[/dim] {out_detail})",
        cost,
    ]
    if usage.sub_agent_total_tokens:
        parts.append(
            f"[dim]main:[/dim] {usage.main_agent_total_tokens:,}  "
            f"[dim]sub-agent:[/dim] {usage.sub_agent_total_tokens:,}"
        )
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


def format_session_subtitle(
    usage: TokenUsage,
    *,
    model: str | None = None,
    reasoning_effort: str | None = None,
) -> str:
    main_subtitle, context_label = format_session_subtitle_parts(
        usage,
        model=model,
        reasoning_effort=reasoning_effort,
    )
    if context_label:
        return f"{main_subtitle} \u00b7 {context_label}"
    return main_subtitle


def _context_utilization(
    usage: TokenUsage, model: str | None
) -> tuple[int, float | None]:
    """Return ``(ctx_window, pct)`` for *usage*.

    *pct* is ``None`` when the context window is unknown.
    """
    ctx_model = model or usage.model
    ctx_window = context_window_for_model(ctx_model) if ctx_model else 0
    pct: float | None = None
    if ctx_window:
        pct = min(usage.context_tokens / ctx_window * 100, 100)
    return ctx_window, pct


def format_session_subtitle_parts(
    usage: TokenUsage,
    *,
    model: str | None = None,
    reasoning_effort: str | None = None,
) -> tuple[str, str | None]:
    cwd = Path.cwd()
    session_model = model or usage.model
    parts: list[str] = []
    if session_model:
        model_label = session_model
        if reasoning_effort:
            model_label += f" ({reasoning_effort})"
        parts.append(model_label)
    elif reasoning_effort:
        parts.append(reasoning_effort)
    parts.append(f"v{__version__}")
    parts.append(format_informal_path(cwd))
    tokens = usage.total_tokens
    cost = usage.estimated_cost_usd
    if usage.sub_agent_total_tokens:
        parts.append(
            f"{tokens:,} tok (main {usage.main_agent_total_tokens:,}"
            f" / sub {usage.sub_agent_total_tokens:,})"
        )
    else:
        parts.append(f"{tokens:,} tok")
    context_label: str | None = None
    if usage.context_tokens:
        ctx_window, pct = _context_utilization(usage, session_model)
        if ctx_window and pct is not None:
            context_label = f"ctx {pct:.0f}%"
        else:
            context_label = f"ctx {usage.context_tokens:,}"
    parts.append(f"${cost:.3f}")
    return " \u00b7 ".join(parts), context_label


def format_context_tooltip(
    usage: TokenUsage,
    *,
    model: str | None = None,
) -> str | None:
    """Build a tooltip string showing context token details.

    Returns ``None`` when there is no context information to display.
    """
    if not usage.context_tokens:
        return None
    ctx_window, pct = _context_utilization(usage, model)
    lines = [f"Context tokens: {usage.context_tokens:,}"]
    if ctx_window and pct is not None:
        lines.append(f"Context window: {ctx_window:,}")
        lines.append(f"Utilization: {pct:.1f}%")
    return "\n".join(lines)


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
    if parse_mcp_tool_name(normalized) is not None:
        return "mcp"
    return TOOL_STYLE_MAP.get(normalized, "generic")


def tool_group_class(tool_name: str) -> str:
    return f"tool-group-{tool_style_key(tool_name)}"


def tool_item_class(tool_name: str) -> str:
    return f"tool-call-{tool_style_key(tool_name)}"


# ---------------------------------------------------------------------------
# Tool item formatters (shared free functions)
# ---------------------------------------------------------------------------


def _append_verbose_call_id(lines: list[str], call_id: str, verbose: bool) -> None:
    if verbose and call_id:
        lines.append(f"[dim]call_id:[/dim] {escape_markup_text(call_id)}")


def format_shell_tool_item(
    command: str,
    *,
    verbose: bool = False,
    bold_command: bool = False,
    status: str,
    call_id: str = "",
    working_directory: str = ".",
    timeout_ms: int | str = "default",
) -> str:
    cmd_text = escape_markup_text(shorten(command, 96))
    if bold_command:
        first_line = f"[green]$[/green] [bold]{cmd_text}[/bold]  {status}"
    else:
        first_line = f"[dim]$[/dim] {cmd_text}  {status}"
    lines = [
        first_line,
        f"[dim]wd:[/dim] {escape_markup_text(format_informal_path(working_directory))}  "
        f"[dim]timeout_ms:[/dim] {escape_markup_text(str(timeout_ms))}",
    ]
    _append_verbose_call_id(lines, call_id, verbose)
    return "\n".join(lines)


def format_patch_tool_item(
    path: str,
    operation: str,
    *,
    verbose: bool = False,
    status: str,
    call_id: str = "",
    detail: str = "",
    diff: str = "",
    shorten_path: bool = False,
) -> str:
    display_path = format_informal_path(path)
    if shorten_path:
        display_path = shorten(display_path, 96)
    lines = [
        f"{escape_markup_text(operation)} "
        f"[bold]{escape_markup_text(display_path)}[/bold]  {status}",
    ]
    if detail:
        lines.append(f"[dim]detail:[/dim] {escape_markup_text(shorten(detail, 320))}")
    if diff.strip():
        lines.extend(
            [
                "[dim]diff:[/dim]",
                escape_markup_text(shorten(diff.strip(), 600)),
            ]
        )
    _append_verbose_call_id(lines, call_id, verbose)
    return "\n".join(lines)


def format_python_exec_item(
    code: str,
    *,
    verbose: bool = False,
    status: str,
    call_id: str = "",
    working_directory: str = ".",
    timeout_seconds: int | str = 30,
    capture_result: bool = False,
) -> str:
    first_line = next(
        (line.strip() for line in code.splitlines() if line.strip()), "<empty>"
    )
    flags: list[str] = [
        f"[dim]wd:[/dim] {escape_markup_text(format_informal_path(working_directory))}",
        f"[dim]timeout:[/dim] {escape_markup_text(str(timeout_seconds))}s",
    ]
    if capture_result:
        flags.append("[dim]capture_result[/dim]")
    lines = [
        f"[#A855F7]\u2699[/#A855F7] [bold]{escape_markup_text(shorten(first_line, 96))}[/bold]  {status}",
        "  ".join(flags),
    ]
    _append_verbose_call_id(lines, call_id, verbose)
    return "\n".join(lines)


def format_generic_function_item(
    name: str,
    *,
    verbose: bool = False,
    status: str,
    call_id: str = "",
    arguments: Any = None,
    label: str | None = None,
) -> str:
    name_safe = escape_markup_text(label or name)
    args = to_dict(arguments)
    if not verbose:
        if args:
            summary = escape_markup_text(shorten(compact_json(args), 80))
            return "\n".join([f"{name_safe}()  {status}", f"[dim]{summary}[/dim]"])
        return f"{name_safe}()  {status}"

    detail_bits: list[str] = []
    if call_id:
        detail_bits.append(f"call_id={escape_markup_text(call_id)}")
    detail_bits.append(
        f"args={escape_markup_text(shorten(compact_json(arguments), 120))}"
    )
    return f"{name_safe}()  {status}  [dim]{' '.join(detail_bits)}[/dim]"


def format_list_files_item(
    path: str,
    *,
    verbose: bool = False,
    status: str,
    call_id: str = "",
    recursive: bool = True,
    glob_pattern: str = "",
    entry_type: str = "all",
    max_entries: int | str = 200,
) -> str:
    flags: list[str] = []
    if recursive:
        flags.append("recursive")
    if glob_pattern:
        flags.append(f"glob={escape_markup_text(shorten(glob_pattern, 40))}")
    if entry_type != "all":
        flags.append(f"type={escape_markup_text(entry_type)}")
    flags.append(f"max={max_entries}")
    flag_str = "  ".join(f"[dim]{f}[/dim]" for f in flags)
    lines = [
        f"[#818CF8]\u2630[/#818CF8] [bold]{escape_markup_text(shorten(format_informal_path(path), 96))}[/bold]  {status}",
        flag_str,
    ]
    _append_verbose_call_id(lines, call_id, verbose)
    return "\n".join(lines)


def format_search_files_item(
    pattern: str,
    *,
    verbose: bool = False,
    status: str,
    call_id: str = "",
    path: str = ".",
    glob_pattern: str = "",
    regex: bool = False,
    max_matches: int | str = 100,
) -> str:
    mode = "[dim]regex[/dim]" if regex else "[dim]literal[/dim]"
    lines = [
        f"[#EC4899]\u2315[/#EC4899] [bold]{escape_markup_text(shorten(pattern, 80))}[/bold]  {mode}  {status}",
        f"[dim]path:[/dim] {escape_markup_text(shorten(format_informal_path(path), 60))}  [dim]max:[/dim] {max_matches}",
    ]
    if glob_pattern:
        lines.append(
            f"[dim]glob:[/dim] {escape_markup_text(shorten(glob_pattern, 60))}"
        )
    _append_verbose_call_id(lines, call_id, verbose)
    return "\n".join(lines)


def format_read_file_item(
    path: str,
    *,
    verbose: bool = False,
    status: str,
    call_id: str = "",
    start_line: int | str = 1,
    max_lines: int | str = 200,
    encoding: str = "auto",
) -> str:
    normalized_start = _safe_positive_int(start_line, default=1)
    normalized_max = _safe_positive_int(max_lines, default=200)
    lines = [
        f"[#EAB308]\u2610[/#EAB308] [bold]{escape_markup_text(shorten(format_informal_path(path), 96))}[/bold]  {status}",
        f"[dim]lines:[/dim] {normalized_start}\u2013{normalized_start + normalized_max - 1}"
        f"  [dim]encoding:[/dim] {escape_markup_text(encoding)}",
    ]
    _append_verbose_call_id(lines, call_id, verbose)
    return "\n".join(lines)


def format_read_web_url_item(
    url: str,
    *,
    verbose: bool = False,
    status: str,
    call_id: str = "",
) -> str:
    lines = [
        f"[#06B6D4]\U0001f310[/#06B6D4] [bold]{escape_markup_text(shorten(url, 96))}[/bold]  {status}",
    ]
    _append_verbose_call_id(lines, call_id, verbose)
    return "\n".join(lines)


def format_web_search_sources_item(
    sources: list[dict[str, str]],
    *,
    queries: list[str] | None = None,
    verbose: bool = False,
    status: str = "",
) -> str:
    """Format web search source citations for display."""
    normalized_queries = [query for query in (queries or []) if query]
    query_lines: list[str] = []
    if normalized_queries:
        query_text = escape_markup_text(", ".join(normalized_queries[:3]))
        query_lines.append(f"  [dim]queries:[/dim] {query_text}")
        if len(normalized_queries) > 3:
            query_lines.append(
                f"  [dim]\u2026 and {len(normalized_queries) - 3} more[/dim]"
            )
    if not sources:
        lines = [f"[dim]no sources[/dim]  {status}"]
        lines = query_lines + lines
        return "\n".join(lines)
    count = len(sources)
    header = f"[dim]{count} source{'s' if count != 1 else ''}[/dim]  {status}"
    lines = query_lines + [header]
    if not verbose:
        for src in sources[:5]:
            title = escape_markup_text(shorten(src.get("title", ""), 60))
            url = escape_markup_text(shorten(src.get("url", ""), 60))
            lines.append(f"  [dim]\u2022[/dim] {title}")
            lines.append(f"    [dim]{url}[/dim]")
        if count > 5:
            lines.append(f"  [dim]\u2026 and {count - 5} more[/dim]")
        return "\n".join(lines)
    for src in sources:
        title = escape_markup_text(shorten(src.get("title", ""), 80))
        url = escape_markup_text(src.get("url", ""))
        lines.append(f"  [dim]\u2022[/dim] {title}")
        lines.append(f"    [dim]{url}[/dim]")
        snippet = src.get("snippet", "")
        if snippet:
            lines.append(f"    [dim]{escape_markup_text(shorten(snippet, 200))}[/dim]")
    return "\n".join(lines)


def format_wait_seconds(wait_seconds: float) -> str:
    """Format wait seconds for display: ``1.50`` → ``'1.5'``, ``2.00`` → ``'2'``."""
    return f"{wait_seconds:.2f}".rstrip("0").rstrip(".")


def _safe_positive_int(value: int | str, *, default: int) -> int:
    try:
        normalized = int(value)
    except (TypeError, ValueError):
        return default
    return normalized if normalized > 0 else default


# ---------------------------------------------------------------------------
# Shared function_result routing
# ---------------------------------------------------------------------------


def route_function_result(
    name: str,
    *,
    verbose: bool = False,
    bold_command: bool = False,
    status: str,
    call_id: str = "",
    arguments: Any = None,
) -> tuple[str, str]:
    """Return ``(tool_name, formatted_text)`` for a generic function result.

    This centralises the if/elif routing so that ``WebDisplay``,
    ``ConsoleDisplay``, and their sub-agent variants share a single code-path.
    Callers that have extra tool-specific formatters (e.g. ``list_files``,
    ``search_files``, ``read_file`` on the console) should handle those
    *before* falling through to this function.
    """
    args = to_dict(arguments)

    if name == "shell":
        command = str(args.get("command", "")).strip() or "<missing command>"
        return name, format_shell_tool_item(
            command,
            verbose=verbose,
            bold_command=bold_command,
            status=status,
            call_id=call_id,
            working_directory=str(args.get("working_directory", ".")),
            timeout_ms=args.get("timeout_ms", "default"),
        )

    if name == "apply_patch":
        raw_diff = args.get("diff")
        return name, format_patch_tool_item(
            str(args.get("path", "<missing path>")),
            str(args.get("operation_type", "<missing operation_type>")),
            verbose=verbose,
            status=status,
            call_id=call_id,
            diff=raw_diff if isinstance(raw_diff, str) else "",
            shorten_path=True,
        )

    if name == "python_exec":
        return name, format_python_exec_item(
            str(args.get("code", "")),
            verbose=verbose,
            status=status,
            call_id=call_id,
            working_directory=str(args.get("working_directory", ".")),
            timeout_seconds=args.get("timeout_seconds", 30),
            capture_result=bool(args.get("capture_result", False)),
        )

    if name == "list_files":
        return name, format_list_files_item(
            str(args.get("path", ".")),
            verbose=verbose,
            status=status,
            call_id=call_id,
            recursive=bool(args.get("recursive", True)),
            glob_pattern=str(args.get("glob", "")),
            entry_type=str(args.get("entry_type", "all")),
            max_entries=args.get("max_entries", 200),
        )

    if name == "search_files":
        return name, format_search_files_item(
            str(args.get("pattern", "<missing pattern>")),
            verbose=verbose,
            status=status,
            call_id=call_id,
            path=str(args.get("path", ".")),
            glob_pattern=str(args.get("glob", "")),
            regex=bool(args.get("regex", False)),
            max_matches=args.get("max_matches", 100),
        )

    if name == "read_file":
        return name, format_read_file_item(
            str(args.get("path", "<missing path>")),
            verbose=verbose,
            status=status,
            call_id=call_id,
            start_line=args.get("start_line", 1),
            max_lines=args.get("max_lines", 200),
            encoding=str(args.get("encoding", "auto")),
        )

    if name == "read_web_url":
        return name, format_read_web_url_item(
            str(args.get("url", "<missing url>")),
            verbose=verbose,
            status=status,
            call_id=call_id,
        )

    if name == "web_search":
        raw_sources = args.get("sources", [])
        sources = raw_sources if isinstance(raw_sources, list) else []
        raw_queries = args.get("queries", [])
        queries = raw_queries if isinstance(raw_queries, list) else []
        return name, format_web_search_sources_item(
            sources,
            queries=queries,
            verbose=verbose,
            status=status,
        )

    return name, format_generic_function_item(
        name,
        verbose=verbose,
        status=status,
        call_id=call_id,
        arguments=arguments,
        label=display_name_for_mcp_tool(name),
    )


__all__ = [
    "REDACTED_THINKING_NOTICE",
    "TOOL_BORDER_STYLES",
    "TOOL_ICONS",
    "compact_json",
    "escape_markup_text",
    "format_context_tooltip",
    "format_generic_function_item",
    "format_list_files_item",
    "format_patch_tool_item",
    "format_python_exec_item",
    "format_read_file_item",
    "format_read_web_url_item",
    "format_reasoning_title",
    "format_search_files_item",
    "format_session_subtitle",
    "format_session_subtitle_parts",
    "format_shell_tool_item",
    "format_usage_summary",
    "format_web_search_sources_item",
    "format_wait_seconds",
    "resolve_reasoning_body",
    "resolve_reasoning_panel",
    "route_function_result",
    "shorten",
    "status_markup",
    "to_dict",
    "tool_group_class",
    "tool_item_class",
]
