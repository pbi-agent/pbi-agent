"""Shared branding helpers for pbi-agent surfaces."""

from __future__ import annotations

from collections.abc import Iterator
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from rich.align import Align

PBI_AGENT_ACCENT = "#1477E0"
PBI_AGENT_TAGLINE = " >_ work smart"
PBI_AGENT_LOGO_ROWS = (
    "PPPPPP  BBBBBB  IIIII",
    "PP  PP  BB   BB   I  ",
    "PPPPPP  BBBBBB    I  ",
    "PP      BB   BB   I  ",
    "PP      BBBBBB  IIIII",
)

_ACCENT_GLYPHS = frozenset({"P", "B", "I"})
_CUTOUT_GLYPHS = frozenset({">", "_", "/"})


def _logo_span_role(char: str) -> str | None:
    if char in _ACCENT_GLYPHS:
        return "accent"
    if char in _CUTOUT_GLYPHS:
        return "cutout"
    return None


def _iter_logo_spans(row: str) -> Iterator[tuple[str, str | None]]:
    current_role: str | None = None
    current_chars: list[str] = []
    for char in row:
        role = _logo_span_role(char)
        if current_chars and role != current_role:
            yield "".join(current_chars), current_role
            current_chars = []
        current_chars.append(char)
        current_role = role
    if current_chars:
        yield "".join(current_chars), current_role


def rich_brand_block(*, accent: str = PBI_AGENT_ACCENT) -> str:
    """Return the Rich markup block used for branded startup banners."""

    accent_style = f"bold {accent}"
    cutout_style = "bold white"
    lines: list[str] = []
    for row in PBI_AGENT_LOGO_ROWS:
        line = []
        for segment, role in _iter_logo_spans(row):
            if role == "accent":
                line.append(f"[{accent_style}]{segment}[/]")
            elif role == "cutout":
                line.append(f"[{cutout_style}]{segment}[/]")
            else:
                line.append(segment)
        lines.append("".join(line))
    lines.extend(
        [
            "",
            f"[bold]{PBI_AGENT_TAGLINE}[/bold]",
        ]
    )
    return "\n".join(lines)


def startup_panel() -> "Align":
    """Return a centered, bordered Rich panel for the CLI startup banner."""
    from rich.align import Align
    from rich import box
    from rich.panel import Panel
    from rich.text import Text

    text = Text()
    accent_style = f"bold {PBI_AGENT_ACCENT}"
    cutout_style = "bold white"
    if PBI_AGENT_LOGO_ROWS:
        logo_lines = list(PBI_AGENT_LOGO_ROWS)
        content_width = max(
            *[len(line) for line in logo_lines],
            len(PBI_AGENT_TAGLINE.strip()),
        )
        for row in logo_lines:
            for segment, role in _iter_logo_spans(row.center(content_width)):
                style = (
                    accent_style
                    if role == "accent"
                    else cutout_style
                    if role == "cutout"
                    else None
                )
                text.append(segment, style=style)
            text.append("\n")
        text.append("\n")
    text.append(PBI_AGENT_TAGLINE.strip().center(content_width), style="bold")

    panel = Panel(
        text,
        box=box.SQUARE,
        border_style=PBI_AGENT_ACCENT,
        padding=(1, 4),
        expand=False,
    )
    return Align.center(panel)
