"""Console-oriented display bridge for single-turn CLI modes."""

from __future__ import annotations

from typing import Any, TextIO

from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.text import Text
from rich.tree import Tree

from pbi_agent.models.messages import TokenUsage
from pbi_agent.ui.display_protocol import DisplayProtocol, PendingToolGroup
from pbi_agent.ui.formatting import (
    REDACTED_THINKING_NOTICE,
    compact_json,
    escape_markup_text,
    format_session_subtitle,
    format_usage_summary,
    resolve_reasoning_panel,
    shorten,
    status_markup,
    to_dict,
    tool_group_class,
    tool_item_class,
)


_TOOL_ICONS: dict[str, str] = {
    "shell": "\u25b6",  # ▶
    "apply-patch": "\u25a0",  # ■
    "skill-knowledge": "\u25c6",  # ◆
    "init-report": "\u2605",  # ★
    "generic": "\u2022",  # •
}


class ConsoleDisplay(DisplayProtocol):
    """Sync stdout/stderr display for headless single-turn execution."""

    def __init__(
        self,
        *,
        verbose: bool = False,
        stdout: TextIO | None = None,
        stderr: TextIO | None = None,
    ) -> None:
        self.verbose = verbose
        self._console = Console(file=stdout)
        self._error_console = Console(file=stderr, stderr=True)
        self._tool_group = PendingToolGroup()
        self._thinking_counter = 0
        self._latest_session_subtitle: str | None = None
        self._usage_section_open = False
        self._turn_count = 0
        self._status: Any = None

    def _stop_spinner(self) -> None:
        """Stop the wait spinner if one is currently active."""
        if self._status is not None:
            self._status.stop()
            self._status = None

    def _append_call_id(self, lines: list[str], call_id: str) -> None:
        if self.verbose and call_id:
            lines.append(f"[dim]call_id:[/dim] {escape_markup_text(call_id)}")

    def _format_shell_tool_item(
        self,
        command: str,
        *,
        status: str,
        call_id: str = "",
        working_directory: str = ".",
        timeout_ms: int | str = "default",
    ) -> str:
        lines = [
            f"[green]$[/green] [bold]{escape_markup_text(shorten(command, 96))}[/bold]  {status}",
            f"[dim]wd:[/dim] {escape_markup_text(str(working_directory))}  "
            f"[dim]timeout_ms:[/dim] {escape_markup_text(str(timeout_ms))}",
        ]
        self._append_call_id(lines, call_id)
        return "\n".join(lines)

    def _format_patch_tool_item(
        self,
        path: str,
        operation: str,
        *,
        status: str,
        call_id: str = "",
        detail: str = "",
        diff: str = "",
        shorten_path: bool = False,
    ) -> str:
        display_path = shorten(path, 96) if shorten_path else path
        lines = [
            f"{escape_markup_text(operation)} "
            f"[bold]{escape_markup_text(display_path)}[/bold]  {status}",
        ]
        if detail:
            lines.append(
                f"[dim]detail:[/dim] {escape_markup_text(shorten(detail, 320))}"
            )
        if diff.strip():
            lines.extend(
                [
                    "[dim]diff:[/dim]",
                    escape_markup_text(shorten(diff.strip(), 600)),
                ]
            )
        self._append_call_id(lines, call_id)
        return "\n".join(lines)

    def _format_skill_knowledge_item(
        self,
        skills: list[str],
        *,
        status: str,
        call_id: str = "",
    ) -> str:
        skill_list = ", ".join(skills) if skills else "<none>"
        lines = [
            f"[dim]skills:[/dim] {escape_markup_text(shorten(skill_list, 120))}  {status}",
        ]
        self._append_call_id(lines, call_id)
        return "\n".join(lines)

    def _format_init_report_item(
        self,
        dest: str,
        *,
        status: str,
        call_id: str = "",
        force: bool = False,
    ) -> str:
        lines = [f"[bold]{escape_markup_text(dest)}[/bold]  {status}"]
        if force:
            lines.append("[dim]force:[/dim] true")
        self._append_call_id(lines, call_id)
        return "\n".join(lines)

    def _format_generic_function_item(
        self,
        name: str,
        *,
        status: str,
        call_id: str = "",
        arguments: Any = None,
    ) -> str:
        name_safe = escape_markup_text(name)
        args = to_dict(arguments)
        if not self.verbose:
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

    def _start_tool_group(
        self,
        label: str,
        *,
        classes: str = "",
        function_count: int = 0,
    ) -> None:
        self._tool_group.start(label, classes=classes, function_count=function_count)

    def _append_tool_line(self, tool_name: str, text: str) -> None:
        self._tool_group.add_item(text, classes=tool_item_class(tool_name))

    def _print_tool_item(self, text: str) -> None:
        lines = text.splitlines() or [text]
        for index, line in enumerate(lines):
            prefix = "  - " if index == 0 else "    "
            self._console.print(f"{prefix}{line}")

    def request_shutdown(self) -> None:
        return None

    def submit_input(self, value: str) -> None:
        del value
        return None

    def welcome(
        self,
        *,
        interactive: bool = True,
        model: str | None = None,
        reasoning_effort: str | None = None,
        single_turn_hint: str | None = None,
    ) -> None:
        mode = "interactive" if interactive else "single-turn"
        detail_parts: list[str] = []
        if model:
            detail_parts.append(f"[dim]model:[/dim] {escape_markup_text(model)}")
        if reasoning_effort:
            detail_parts.append(
                f"[dim]reasoning:[/dim] {escape_markup_text(reasoning_effort)}"
            )
        subtitle = "  ".join(detail_parts) if detail_parts else None
        self._console.print(
            Panel(
                f"[dim]{escape_markup_text(mode)}[/dim]",
                title="[bold cyan]PBI Agent[/bold cyan]",
                subtitle=subtitle,
                border_style="cyan",
                expand=False,
                padding=(0, 2),
            )
        )
        if single_turn_hint:
            self._console.print(f"[dim]{escape_markup_text(single_turn_hint)}[/dim]")

    def user_prompt(self) -> str:
        raise RuntimeError("ConsoleDisplay does not support interactive user input.")

    def assistant_start(self) -> None:
        return None

    def wait_start(self, message: str = "model is processing your request...") -> None:
        self._stop_spinner()
        if self._console.is_terminal:
            from rich.status import Status

            self._status = Status(
                escape_markup_text(message),
                console=self._console,
                spinner="dots",
                spinner_style="cyan",
            )
            self._status.start()
        else:
            self._console.print(f"[dim]... {escape_markup_text(message)}[/dim]")

    def wait_stop(self) -> None:
        self._stop_spinner()

    def render_markdown(self, text: str) -> None:
        self._stop_spinner()
        self._console.print(Markdown(text))

    def render_thinking(
        self,
        text: str | None = None,
        *,
        title: str | None = None,
        replace_existing: bool = False,
        widget_id: str | None = None,
    ) -> str | None:
        self._stop_spinner()
        del replace_existing
        summary = title or ""
        body, display_title = resolve_reasoning_panel(text, summary)
        if body is None and not summary.strip():
            return None

        resolved_widget_id = widget_id
        if resolved_widget_id is None:
            self._thinking_counter += 1
            resolved_widget_id = f"thinking-{self._thinking_counter}"

        content = Markdown(body) if body else Text("...", style="dim")
        self._console.print(
            Panel(
                content,
                title=f"[italic]{escape_markup_text(display_title)}[/italic]",
                title_align="left",
                border_style="dim",
                padding=(0, 1),
            )
        )
        return resolved_widget_id

    def render_redacted_thinking(self) -> None:
        self._stop_spinner()
        self._console.print(REDACTED_THINKING_NOTICE)

    def session_usage(self, usage: TokenUsage) -> None:
        self._latest_session_subtitle = format_session_subtitle(usage.snapshot())
        if (
            self._usage_section_open
            and self._latest_session_subtitle
            and self._turn_count > 1
        ):
            self._console.print(f"[dim]{self._latest_session_subtitle}[/dim]")
            self._usage_section_open = False

    def turn_usage(self, usage: TokenUsage, elapsed_seconds: float) -> None:
        self._stop_spinner()
        self._turn_count += 1
        self._console.print()
        summary = format_usage_summary(
            usage.snapshot(),
            elapsed_seconds=elapsed_seconds,
            label="Turn",
        )
        self._console.print(
            Panel(
                summary,
                title="[bold]Usage[/bold]",
                title_align="left",
                border_style="dim",
                expand=True,
                padding=(0, 1),
            )
        )
        self._usage_section_open = True

    def shell_start(self, commands: list[str]) -> None:
        count = len(commands)
        self._start_tool_group(
            f"Running {count} shell command{'s' if count != 1 else ''}",
            classes=tool_group_class("shell"),
        )

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
        self._append_tool_line(
            "shell",
            self._format_shell_tool_item(
                command,
                status=status_markup(timed_out=timed_out, exit_code=exit_code),
                call_id=call_id,
                working_directory=working_directory,
                timeout_ms=timeout_ms,
            ),
        )

    def patch_start(self, count: int) -> None:
        self._start_tool_group(
            f"Editing {count} file{'s' if count != 1 else ''}",
            classes=tool_group_class("apply_patch"),
        )

    def patch_result(
        self,
        path: str,
        operation: str,
        success: bool,
        *,
        call_id: str = "",
        detail: str = "",
    ) -> None:
        self._append_tool_line(
            "apply_patch",
            self._format_patch_tool_item(
                path,
                operation,
                status=status_markup(success=success),
                call_id=call_id,
                detail=detail,
            ),
        )

    def function_start(self, count: int) -> None:
        self._start_tool_group(
            f"Tool call{'s' if count != 1 else ''}",
            classes="tool-group-generic",
            function_count=count,
        )

    def function_result(
        self,
        name: str,
        success: bool,
        *,
        call_id: str = "",
        arguments: Any = None,
    ) -> None:
        status = status_markup(success=success)
        args = to_dict(arguments)
        self._tool_group.update_for_function(name)

        if name == "shell":
            command = str(args.get("command", "")).strip() or "<missing command>"
            self._append_tool_line(
                name,
                self._format_shell_tool_item(
                    command,
                    status=status,
                    call_id=call_id,
                    working_directory=str(args.get("working_directory", ".")),
                    timeout_ms=args.get("timeout_ms", "default"),
                ),
            )
            return

        if name == "apply_patch":
            raw_diff = args.get("diff")
            self._append_tool_line(
                name,
                self._format_patch_tool_item(
                    str(args.get("path", "<missing path>")),
                    str(args.get("operation_type", "<missing operation_type>")),
                    status=status,
                    call_id=call_id,
                    diff=raw_diff if isinstance(raw_diff, str) else "",
                    shorten_path=True,
                ),
            )
            return

        if name == "skill_knowledge":
            raw_skills = args.get("skills", [])
            skills = raw_skills if isinstance(raw_skills, list) else [str(raw_skills)]
            self._append_tool_line(
                name,
                self._format_skill_knowledge_item(
                    skills,
                    status=status,
                    call_id=call_id,
                ),
            )
            return

        if name == "init_report":
            self._append_tool_line(
                name,
                self._format_init_report_item(
                    str(args.get("dest", ".")),
                    status=status,
                    call_id=call_id,
                    force=bool(args.get("force", False)),
                ),
            )
            return

        self._append_tool_line(
            name,
            self._format_generic_function_item(
                name,
                status=status,
                call_id=call_id,
                arguments=arguments,
            ),
        )

    def tool_group_end(self) -> None:
        self._stop_spinner()
        if not self._tool_group.items:
            self._tool_group.reset()
            return

        label = self._tool_group.label
        style_key = self._tool_group.classes.replace("tool-group-", "")
        icon = _TOOL_ICONS.get(style_key, _TOOL_ICONS["generic"])

        tree = Tree(f"[bold]{icon} {escape_markup_text(label)}[/bold]")
        for item in self._tool_group.items:
            tree.add(item.text)

        self._console.print(
            Panel(tree, border_style="blue", padding=(0, 1), expand=True)
        )
        self._tool_group.reset()

    def retry_notice(self, attempt: int, max_retries: int) -> None:
        self.wait_stop()
        self._console.print(f"[yellow]Retrying... ({attempt}/{max_retries})[/yellow]")

    def rate_limit_notice(
        self,
        *,
        wait_seconds: float,
        attempt: int,
        max_retries: int,
    ) -> None:
        self.wait_stop()
        wait_display = f"{wait_seconds:.2f}".rstrip("0").rstrip(".")
        self._console.print(
            "[yellow]Rate limit reached. "
            f"Retrying in {wait_display}s ({attempt}/{max_retries})[/yellow]"
        )

    def error(self, message: str) -> None:
        self.wait_stop()
        self._tool_group.reset()
        self._error_console.print(f"[red]Error: {escape_markup_text(message)}[/red]")

    def debug(self, message: str) -> None:
        if self.verbose:
            self._console.print(f"[dim]{escape_markup_text(message)}[/dim]")


__all__ = ["ConsoleDisplay"]
