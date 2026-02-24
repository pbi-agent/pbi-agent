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
from rich.live import Live
from rich.markdown import Markdown
from rich.rule import Rule


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

    def welcome(self) -> None:
        self.console.print(
            "Interactive mode.  Type [bold]exit[/bold] or [bold]quit[/bold] to stop.\n",
        )

    def user_prompt(self) -> str:
        """Display the prompt and return user input (blocking)."""
        return self.console.input("[bold green]you>[/bold green] ")

    # -- assistant streaming ------------------------------------------------

    def assistant_start(self) -> None:
        """Visual separator before the assistant response."""
        self.console.print()

    def stream_delta(self, delta: str) -> None:
        """Append a streaming token and update the live Markdown render."""
        self._stream_parts.append(delta)
        if self._live is None:
            self._live = Live(
                Markdown(""),
                console=self.console,
                refresh_per_second=8,
                vertical_overflow="visible",
            )
            self._live.start()
        text = "".join(self._stream_parts)
        self._live.update(Markdown(text))

    def stream_end(self) -> None:
        """Finalise the live render and freeze output on screen."""
        if self._live is not None:
            text = "".join(self._stream_parts)
            self._live.update(Markdown(text))
            self._live.stop()
            self._live = None
        self._stream_parts = []

    def render_markdown(self, text: str) -> None:
        """Render a completed response as Markdown (single-turn mode)."""
        self.console.print()
        self.console.print(Markdown(text))

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
