"""Console sub-agent display — renders child-agent output to the terminal."""

from __future__ import annotations

from typing import Any, TYPE_CHECKING

from rich.markdown import Markdown
from rich.panel import Panel
from rich.text import Text
from rich.tree import Tree

from pbi_agent.models.messages import TokenUsage, WebSearchSource
from pbi_agent.session_store import MessageRecord
from pbi_agent.ui.display_protocol import DisplayProtocol, PendingToolGroup
from pbi_agent.ui.formatting import (
    REDACTED_THINKING_NOTICE,
    TOOL_BORDER_STYLES,
    TOOL_ICONS,
    escape_markup_text,
    format_patch_tool_item,
    format_shell_tool_item,
    format_usage_summary,
    format_wait_seconds,
    resolve_reasoning_panel,
    route_function_result,
    shorten,
    status_markup,
    tool_group_class,
    tool_item_class,
)

if TYPE_CHECKING:
    from pbi_agent.ui.console_display import ConsoleDisplay


class ConsoleSubAgentDisplay(DisplayProtocol):
    """Console display bridge for sub-agent output."""

    def __init__(
        self,
        *,
        parent: ConsoleDisplay,
        task_instruction: str,
        reasoning_effort: str | None,
        name: str = "sub_agent",
    ) -> None:
        self.parent = parent
        self.verbose = parent.verbose
        self._task_instruction = task_instruction
        self._reasoning_effort = reasoning_effort
        self._name = name
        self._tool_group = PendingToolGroup()
        self.parent._stop_spinner()
        self.parent._console.print(
            Panel(
                self._title("running"),
                border_style=TOOL_BORDER_STYLES["sub-agent"],
                expand=True,
                padding=(0, 1),
            )
        )

    def _title(self, status: str) -> str:
        summary = shorten(self._task_instruction.strip() or "task", 72)
        title = f"{self._name} \u00b7 {summary} \u00b7 {status}"
        if self._reasoning_effort:
            title += f" \u00b7 {self._reasoning_effort}"
        return title

    # -- protocol stubs ------------------------------------------------------

    def request_shutdown(self) -> None:
        return None

    def submit_input(self, value: str, *, image_paths: list[str] | None = None) -> None:
        del value, image_paths

    def request_new_chat(self) -> None:
        raise RuntimeError("Sub-agent display does not support interactive chat.")

    def reset_chat(self) -> None:
        return None

    def begin_sub_agent(
        self,
        *,
        task_instruction: str,
        reasoning_effort: str | None = None,
        name: str = "sub_agent",
    ) -> DisplayProtocol:
        del task_instruction, reasoning_effort, name
        return self

    def finish_sub_agent(self, *, status: str) -> None:
        self.parent._console.print(
            f"[bold #F59E0B]{escape_markup_text(self._title(status))}[/bold #F59E0B]"
        )

    def welcome(
        self,
        *,
        interactive: bool = True,
        model: str | None = None,
        reasoning_effort: str | None = None,
        single_turn_hint: str | None = None,
    ) -> None:
        del interactive, model, reasoning_effort, single_turn_hint

    def user_prompt(self) -> str:
        raise RuntimeError("Sub-agent display does not support user input.")

    def assistant_start(self) -> None:
        return None

    # -- rendering -----------------------------------------------------------

    def wait_start(self, message: str = "model is processing your request...") -> None:
        self.parent._console.print(
            f"[dim]{escape_markup_text(self._name)}: {escape_markup_text(message)}[/dim]"
        )

    def wait_stop(self) -> None:
        return None

    def render_markdown(self, text: str) -> None:
        self.parent._console.print(Markdown(text))

    def render_thinking(
        self,
        text: str | None = None,
        *,
        title: str | None = None,
        replace_existing: bool = False,
        widget_id: str | None = None,
    ) -> str | None:
        del replace_existing, widget_id
        body, display_title = resolve_reasoning_panel(text, title or "")
        if body is None and not (title or "").strip():
            return None
        content = Markdown(body) if body else Text("...", style="dim")
        self.parent._console.print(
            Panel(
                content,
                title=f"[italic]{escape_markup_text(display_title)}[/italic]",
                title_align="left",
                border_style="dim",
                padding=(0, 1),
            )
        )
        return "sub-agent-thinking"

    def render_redacted_thinking(self) -> None:
        self.parent._console.print(REDACTED_THINKING_NOTICE)

    def session_usage(self, usage: TokenUsage) -> None:
        del usage

    def turn_usage(self, usage: TokenUsage, elapsed_seconds: float) -> None:
        summary = format_usage_summary(
            usage.snapshot(),
            elapsed_seconds=elapsed_seconds,
            label=self._name,
        )
        self.parent._console.print(
            Panel(
                summary,
                title="[bold]Usage[/bold]",
                title_align="left",
                border_style="dim",
                expand=True,
                padding=(0, 1),
            )
        )

    # -- tool display --------------------------------------------------------

    def shell_start(self, commands: list[str]) -> None:
        self._tool_group.start(
            f"Running {len(commands)} shell command{'s' if len(commands) != 1 else ''}",
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
        self._tool_group.add_item(
            format_shell_tool_item(
                command,
                verbose=self.verbose,
                bold_command=True,
                status=status_markup(timed_out=timed_out, exit_code=exit_code),
                call_id=call_id,
                working_directory=working_directory,
                timeout_ms=timeout_ms,
            ),
            classes=tool_item_class("shell"),
        )

    def patch_start(self, count: int) -> None:
        self._tool_group.start(
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
        self._tool_group.add_item(
            format_patch_tool_item(
                path,
                operation,
                verbose=self.verbose,
                status=status_markup(success=success),
                call_id=call_id,
                detail=detail,
            ),
            classes=tool_item_class("apply_patch"),
        )

    def function_start(self, count: int) -> None:
        self._tool_group.start(
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
        self._tool_group.update_for_function(name)
        tool_name, text = route_function_result(
            name,
            verbose=self.verbose,
            bold_command=True,
            status=status_markup(success=success),
            call_id=call_id,
            arguments=arguments,
        )
        self._tool_group.add_item(text, classes=tool_item_class(tool_name))

    def tool_group_end(self) -> None:
        if not self._tool_group.items:
            self._tool_group.reset()
            return
        label = self._tool_group.label
        style_key = self._tool_group.classes.replace("tool-group-", "")
        icon = TOOL_ICONS.get(style_key, TOOL_ICONS["generic"])
        border = TOOL_BORDER_STYLES.get(style_key, TOOL_BORDER_STYLES["generic"])
        tree = Tree(f"[bold]{icon} {escape_markup_text(label)}[/bold]")
        for item in self._tool_group.items:
            tree.add(item.text)
        self.parent._console.print(
            Panel(tree, border_style=border, padding=(0, 1), expand=True)
        )
        self._tool_group.reset()

    # -- notices -------------------------------------------------------------

    def retry_notice(self, attempt: int, max_retries: int) -> None:
        self.parent._console.print(
            f"[yellow]Retrying... ({attempt}/{max_retries})[/yellow]"
        )

    def rate_limit_notice(
        self,
        *,
        wait_seconds: float,
        attempt: int,
        max_retries: int,
    ) -> None:
        self.parent._console.print(
            "[yellow]Rate limit reached. "
            f"Retrying in {format_wait_seconds(wait_seconds)}s ({attempt}/{max_retries})[/yellow]"
        )

    def overload_notice(
        self,
        *,
        wait_seconds: float,
        attempt: int,
        max_retries: int,
    ) -> None:
        self.parent._console.print(
            "[yellow]Provider overloaded. "
            f"Retrying in {format_wait_seconds(wait_seconds)}s ({attempt}/{max_retries})[/yellow]"
        )

    def error(self, message: str) -> None:
        self.parent._error_console.print(
            f"[red]Error: {escape_markup_text(message)}[/red]"
        )

    def debug(self, message: str) -> None:
        if self.verbose:
            self.parent._console.print(f"[dim]{escape_markup_text(message)}[/dim]")

    def web_search_sources(self, sources: list[WebSearchSource]) -> None:
        del sources

    def replay_history(self, messages: list[MessageRecord]) -> None:
        del messages
