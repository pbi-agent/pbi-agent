"""Centralised CLI display layer.

All user-facing output goes through :class:`Display` so that ``session.py``
never calls ``print()`` directly.  Two rendering modes are supported:

* **normal** (default) – concise, colour-coded, spinner-enabled output.
* **verbose** (``--verbose``) – full technical details (call IDs, timeout,
  working directory, raw JSON args) for debugging.
"""

from __future__ import annotations

import json
from typing import Any

from rich.console import Console
from rich.console import Group
from rich.live import Live
from rich.markdown import Markdown
from rich.panel import Panel
from rich.rule import Rule
from rich.text import Text

from pbi_agent import __version__
from pbi_agent.models.messages import TokenUsage


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _shorten(text: str, limit: int = 80) -> str:
    if len(text) <= limit:
        return text
    return text[: limit - 1] + "…"


def _compact_json(value: Any) -> str:
    try:
        return json.dumps(value, separators=(",", ":"), ensure_ascii=False)
    except TypeError:
        return str(value)


# ---------------------------------------------------------------------------
# Display
# ---------------------------------------------------------------------------


class Display:
    """Single entry-point for every piece of CLI output."""

    def __init__(self, *, verbose: bool = False) -> None:
        self.console = Console(highlight=False)
        self.verbose = verbose
        self._stream_parts: list[str] = []
        self._live: Live | None = None

    # -- lifecycle ----------------------------------------------------------

    def welcome(
        self,
        *,
        interactive: bool = True,
        model: str | None = None,
        reasoning_effort: str | None = None,
    ) -> None:
        logo = Text(justify="center")
        bar_1 = "#F6E27A"
        bar_2 = "#F2C811"
        bar_3 = "#D89216"
        empty = "  "
        bar = "████"

        rows = [
            (False, False, True),
            (False, False, True),
            (False, True, True),
            (False, True, True),
            (True, True, True),
            (True, True, True),
        ]

        for index, (show_1, show_2, show_3) in enumerate(rows):
            logo.append((bar if show_1 else " " * len(bar)), style=bar_1)
            logo.append(empty)
            logo.append((bar if show_2 else " " * len(bar)), style=bar_2)
            logo.append(empty)
            logo.append((bar if show_3 else " " * len(bar)), style=bar_3)
            if index < len(rows) - 1:
                logo.append("\n")

        title = Text("PBI AGENT", style="bold #F2C811", justify="center")
        subtitle = Text(
            "Transform data into decisions.", style="bold white", justify="center"
        )
        if interactive:
            tips = Text.from_markup(
                "[dim]Interactive mode:[/dim] Type [bold]exit[/bold] or [bold]quit[/bold] to stop.",
                justify="center",
            )
        else:
            tips = Text.from_markup(
                "[dim]Single prompt mode:[/dim] Running one request from [bold]--prompt[/bold].",
                justify="center",
            )
        model_bits: list[str] = []
        if model:
            model_bits.append(f"[dim]Model:[/dim] [bold]{model}[/bold]")
        if reasoning_effort:
            model_bits.append(
                f"[dim]Reasoning:[/dim] [bold]{reasoning_effort}[/bold]"
            )
        model_line = (
            Text.from_markup("  [dim]·[/dim]  ".join(model_bits), justify="center")
            if model_bits
            else None
        )

        panel_width = min(72, max(54, self.console.size.width - 4))
        self.console.print(
            Panel(
                Group(logo, Text(""), title, subtitle, tips, model_line)
                if model_line
                else Group(logo, Text(""), title, subtitle, tips),
                width=panel_width,
                border_style="#F2C811",
                title=f"[bold #F2C811]Welcome[/bold #F2C811] [dim]v{__version__}[/dim]",
                subtitle="[dim]Power BI Report Assistant[/dim]",
                padding=(1, 2),
            ),
            justify="center",
        )
        self.console.print()

    def user_prompt(self) -> str:
        """Display the prompt and return user input (blocking)."""
        return self.console.input("[bold green]>[/bold green] ")

    # -- assistant streaming ------------------------------------------------

    def assistant_start(self) -> None:
        """Visual separator before the assistant response."""
        self.console.print()

    def stream_delta(self, delta: str) -> None:
        """Append a streaming token and update the live Markdown preview.

        Uses ``transient=True`` so the live preview is removed from the
        terminal when streaming ends.  The default ``vertical_overflow``
        (``"ellipsis"``) keeps the preview clipped to the terminal height,
        which avoids the duplication bug caused by ``"visible"`` overflow
        when content exceeded the viewport.
        """
        self._stream_parts.append(delta)
        if self._live is None:
            self._live = Live(
                Markdown(""),
                console=self.console,
                refresh_per_second=8,
                transient=True,
            )
            self._live.start()
        text = "".join(self._stream_parts)
        self._live.update(Markdown(text))

    def stream_end(self) -> None:
        """Stop the transient live preview and print the final Markdown.

        The ``transient=True`` live display is cleared automatically when
        stopped, then the full accumulated text is rendered once as
        formatted Markdown via ``console.print``.
        """
        text = "".join(self._stream_parts)
        if self._live is not None:
            self._live.stop()
            self._live = None
        if text.strip():
            self.console.print(Markdown(text))
        self._stream_parts = []

    def render_markdown(self, text: str) -> None:
        """Render a completed response as Markdown (single-turn mode)."""
        self.console.print()
        self.console.print(Markdown(text))

    def session_usage(self, usage: TokenUsage) -> None:
        """Show cumulative session usage and estimated cost in a bordered section."""
        self.console.print()
        self.console.print(Rule("Session usage", style="dim"))

        total = f"{usage.total_tokens:,}"
        inp = f"{usage.input_tokens:,}"
        cached = f"{usage.cached_input_tokens:,}"
        out = f"{usage.output_tokens:,}"
        cost = f"${usage.estimated_cost_usd:.6f}"

        self.console.print(
            f"  [dim]Tokens[/dim]  {total} total  "
            f"[dim]([/dim]{inp} in [dim]·[/dim] {cached} cached [dim]·[/dim] {out} out[dim])[/dim]"
        )
        self.console.print(f"  [dim]Cost[/dim]    {cost}")
        self.console.print(Rule(style="dim"))
        self.console.print()

    # -- tool: shell --------------------------------------------------------

    def shell_start(self, commands: list[str]) -> None:
        n = len(commands)
        label = f"Running {n} shell command{'s' if n != 1 else ''}"
        self.console.print()
        self.console.print(Rule(label, style="cyan"))

    def shell_command(
        self,
        command: str,
        exit_code: int | None,
        timed_out: bool,
        *,
        call_id: str = "",
        working_directory: str = ".",
        timeout_ms: int | str = "default",
    ) -> None:
        cmd_short = _shorten(command, 72)

        if self.verbose:
            meta = f"  [dim]({call_id}) wd={working_directory} timeout_ms={timeout_ms}[/dim]"
        else:
            meta = ""

        if timed_out:
            status = "[yellow]timeout[/yellow]"
        elif exit_code == 0:
            status = "[green]done[/green]"
        else:
            status = f"[red]exit {exit_code}[/red]"

        self.console.print(f"  [dim]$[/dim] {cmd_short}  {status}{meta}")

    # -- tool: apply_patch --------------------------------------------------

    def patch_start(self, count: int) -> None:
        label = f"Editing {count} file{'s' if count != 1 else ''}"
        self.console.print()
        self.console.print(Rule(label, style="cyan"))

    def patch_result(
        self,
        path: str,
        operation: str,
        success: bool,
        *,
        call_id: str = "",
        detail: str = "",
    ) -> None:
        icon = "[green]done[/green]" if success else "[red]failed[/red]"

        if self.verbose:
            extra = f"  [dim]({call_id})[/dim]"
            if detail:
                extra += f"  [dim]{_shorten(detail, 100)}[/dim]"
        else:
            extra = ""
            if not success and detail:
                extra = f"  [dim]{_shorten(detail, 60)}[/dim]"

        self.console.print(f"  {operation} [bold]{path}[/bold]  {icon}{extra}")

    # -- tool: function -----------------------------------------------------

    def function_start(self, count: int) -> None:
        label = f"Calling {count} function{'s' if count != 1 else ''}"
        self.console.print()
        self.console.print(Rule(label, style="cyan"))

    def function_result(
        self,
        name: str,
        success: bool,
        *,
        call_id: str = "",
        arguments: Any = None,
    ) -> None:
        icon = "[green]done[/green]" if success else "[red]failed[/red]"

        if self.verbose:
            args_str = _shorten(_compact_json(arguments), 120)
            self.console.print(
                f"  {name}()  {icon}  [dim]({call_id}) args={args_str}[/dim]"
            )
        else:
            self.console.print(f"  {name}()  {icon}")

    # -- tool group end (shared) -------------------------------------------

    def tool_group_end(self) -> None:
        """Print a closing rule and a blank line after a tool group."""
        self.console.print(Rule(style="dim"))
        self.console.print()

    # -- retries / errors ---------------------------------------------------

    def retry_notice(self, attempt: int, max_retries: int) -> None:
        self.console.print(
            f"[yellow]  Reconnecting… ({attempt}/{max_retries})[/yellow]"
        )

    def error(self, message: str) -> None:
        self.console.print(f"[bold red]Error:[/bold red] {message}")

    # -- verbose-only technical dump ----------------------------------------

    def debug(self, message: str) -> None:
        """Print only when ``--verbose`` is active."""
        if self.verbose:
            self.console.print(f"[dim]{message}[/dim]")
