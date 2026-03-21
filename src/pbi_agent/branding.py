"""Shared branding helpers for PBI Agent surfaces."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from rich.align import Align

PBI_AGENT_ACCENT = "#F2C811"
PBI_AGENT_NAME = "PBI AGENT"
PBI_AGENT_TAGLINE = "Transform data into decisions."
PBI_AGENT_LOGO_ROWS = (
    "              ████",
    "              ████",
    "        ████  ████",
    "        ████  ████",
    "  ████  ████  ████",
    "  ████  ████  ████",
)


def rich_brand_block(*, accent: str = PBI_AGENT_ACCENT) -> str:
    """Return the Rich markup block used for branded startup banners."""

    lines = [f"[bold {accent}]{row}[/bold {accent}]" for row in PBI_AGENT_LOGO_ROWS]
    lines.extend(
        [
            "",
            f"[bold {accent}]{PBI_AGENT_NAME}[/bold {accent}]",
            f"[bold]{PBI_AGENT_TAGLINE}[/bold]",
        ]
    )
    return "\n".join(lines)


def startup_panel() -> "Align":
    """Return a centered, bordered Rich panel for the CLI startup banner."""
    from rich.align import Align
    from rich.panel import Panel
    from rich.text import Text

    text = Text(justify="center")
    for row in PBI_AGENT_LOGO_ROWS:
        text.append(row + "\n", style=f"bold {PBI_AGENT_ACCENT}")
    text.append("\n")
    text.append(PBI_AGENT_NAME + "\n", style=f"bold {PBI_AGENT_ACCENT}")
    text.append(PBI_AGENT_TAGLINE, style="bold")

    panel = Panel(
        text,
        border_style=PBI_AGENT_ACCENT,
        padding=(1, 4),
        expand=False,
    )
    return Align.center(panel)
