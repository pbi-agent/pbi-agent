"""Centralised CLI display layer.

All user-facing output goes through :class:`Display` so that ``session.py``
never calls ``print()`` directly.
"""

from __future__ import annotations

import json
import sys
from typing import Any

from prompt_toolkit import PromptSession
from prompt_toolkit.formatted_text import HTML
from prompt_toolkit.key_binding import KeyBindings
from textual.app import App

from pbi_agent import __version__
from pbi_agent.models.messages import TokenUsage


def _shorten(text: str, limit: int = 80) -> str:
    if len(text) <= limit:
        return text
    return text[: limit - 1] + "…"


def _compact_json(value: Any) -> str:
    try:
        return json.dumps(value, separators=(",", ":"), ensure_ascii=False)
    except TypeError:
        return str(value)


class _ConsoleApp(App[None]):
    """Minimal Textual app to access Textual's configured console."""


class Display:
    """Single entry-point for every piece of CLI output."""

    def __init__(self, *, verbose: bool = False) -> None:
        self.console = _ConsoleApp().console
        self.verbose = verbose
        self._stream_parts: list[str] = []
        self._prompt_session: PromptSession[str] | None = None
        self._prompt_session_unavailable = False

    def _ensure_prompt_session(self) -> None:
        if self._prompt_session is not None or self._prompt_session_unavailable:
            return

        kb = KeyBindings()
        kb.add("enter")(lambda event: event.current_buffer.validate_and_handle())
        kb.add("escape", "enter")(lambda event: event.current_buffer.insert_text("\n"))

        try:
            self._prompt_session = PromptSession(key_bindings=kb, multiline=True)
        except Exception:
            self._prompt_session_unavailable = True

    def welcome(
        self,
        *,
        interactive: bool = True,
        model: str | None = None,
        reasoning_effort: str | None = None,
        single_turn_hint: str | None = None,
    ) -> None:
        self.console.print()
        self.console.print("[bold yellow]PBI AGENT[/bold yellow]", justify="center")
        self.console.print(
            f"[dim]Power BI Report Assistant · v{__version__}[/dim]", justify="center"
        )
        if interactive:
            self.console.print(
                "[dim]Interactive mode: type exit or quit to stop. Alt+Enter for newline.[/dim]",
                justify="center",
            )
        else:
            self.console.print(
                single_turn_hint
                or "[dim]Single prompt mode: running one request from --prompt.[/dim]",
                justify="center",
            )

        bits: list[str] = []
        if model:
            bits.append(f"Model: {model}")
        if reasoning_effort:
            bits.append(f"Reasoning: {reasoning_effort}")
        if bits:
            self.console.print(f"[dim]{' · '.join(bits)}[/dim]", justify="center")
        self.console.print()

    def user_prompt(self) -> str:
        self._ensure_prompt_session()
        if self._prompt_session is not None:
            return self._prompt_session.prompt(HTML("<ansigreen><b>&gt;</b></ansigreen> "))
        return input("> ")

    def assistant_start(self) -> None:
        self.console.print()

    def wait_start(self, message: str = "model is processing your request...") -> None:
        self.console.print(f"[cyan]Thinking[/cyan] [dim]{message}[/dim]")

    def wait_stop(self) -> None:
        return

    def stream_delta(self, delta: str) -> None:
        self._stream_parts.append(delta)
        sys.stdout.write(delta)
        sys.stdout.flush()

    def stream_end(self) -> None:
        if self._stream_parts:
            self.console.print()
        self._stream_parts = []

    def stream_abort(self) -> None:
        self._stream_parts = []

    def render_markdown(self, text: str) -> None:
        self.console.print()
        self.console.print(text)

    def session_usage(self, usage: TokenUsage, elapsed_seconds: float) -> None:
        total_secs = int(elapsed_seconds)
        hours, remainder = divmod(total_secs, 3600)
        minutes, seconds = divmod(remainder, 60)
        time_str = f"{hours}:{minutes:02d}:{seconds:02d}" if hours > 0 else f"{minutes}:{seconds:02d}"

        total = f"{usage.total_tokens:,}"
        inp = f"{usage.input_tokens:,}"
        cached = f"{usage.cached_input_tokens:,}"
        out = f"{usage.output_tokens:,}"
        cost = f"${usage.estimated_cost_usd:.3f}"
        self.console.print(
            f"[dim]{total} tokens ({inp} in · {cached} cached · {out} out) | {cost} | {time_str}[/dim]"
        )
        self.console.print()

    def shell_start(self, commands: list[str]) -> None:
        n = len(commands)
        self.console.print()
        self.console.print(f"[cyan]Running {n} shell command{'s' if n != 1 else ''}[/cyan]")

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
        if timed_out:
            status = "[yellow]timeout[/yellow]"
        elif exit_code == 0:
            status = "[green]done[/green]"
        else:
            status = f"[red]exit {exit_code}[/red]"

        if self.verbose:
            meta = f" [dim]({call_id}) wd={working_directory} timeout_ms={timeout_ms}[/dim]"
        else:
            meta = ""
        self.console.print(f"  [dim]$[/dim] {cmd_short} {status}{meta}")

    def patch_start(self, count: int) -> None:
        self.console.print()
        self.console.print(f"[cyan]Editing {count} file{'s' if count != 1 else ''}[/cyan]")

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
            extra = f" [dim]({call_id})[/dim]"
            if detail:
                extra += f" [dim]{_shorten(detail, 100)}[/dim]"
        else:
            extra = f" [dim]{_shorten(detail, 60)}[/dim]" if (not success and detail) else ""
        self.console.print(f"  {operation} [bold]{path}[/bold] {icon}{extra}")

    def function_start(self, count: int) -> None:
        self.console.print()
        self.console.print(f"[cyan]Calling {count} function{'s' if count != 1 else ''}[/cyan]")

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
            self.console.print(f"  {name}() {icon} [dim]({call_id}) args={args_str}[/dim]")
        else:
            self.console.print(f"  {name}() {icon}")

    def tool_group_end(self) -> None:
        self.console.print("[dim]----------------------------------------[/dim]")
        self.console.print()

    def retry_notice(self, attempt: int, max_retries: int) -> None:
        self.console.print(f"[yellow]  Reconnecting… ({attempt}/{max_retries})[/yellow]")

    def rate_limit_notice(
        self,
        *,
        wait_seconds: float,
        attempt: int,
        max_retries: int,
    ) -> None:
        wait_display = f"{wait_seconds:.2f}".rstrip("0").rstrip(".")
        self.console.print(
            "[yellow]"
            f"  Rate limit reached. Retrying in {wait_display}s ({attempt}/{max_retries})"
            "[/yellow]"
        )

    def error(self, message: str) -> None:
        self.stream_abort()
        self.console.print(f"[bold red]Error:[/bold red] {message}")

    def debug(self, message: str) -> None:
        if self.verbose:
            self.console.print(f"[dim]{message}[/dim]")
