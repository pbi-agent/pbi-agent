"""Textual sub-agent display — renders child-agent output inside a collapsible block."""

from __future__ import annotations

from typing import Any

from textual.widgets import Static

from pbi_agent.models.messages import TokenUsage
from pbi_agent.session_store import MessageRecord
from pbi_agent.ui.display_protocol import DisplayProtocol, PendingToolGroup
from pbi_agent.ui.formatting import (
    REDACTED_THINKING_NOTICE,
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
from pbi_agent.ui.widgets import (
    AssistantMarkdown,
    ErrorMessage,
    NoticeMessage,
    ThinkingBlock,
    ThinkingContent,
    ToolGroup,
    ToolItem,
    UsageSummary,
    WaitingIndicator,
)

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pbi_agent.ui.display import Display


class SubAgentDisplay(DisplayProtocol):
    """Display bridge for sub-agent output rendered inside a Textual container."""

    def __init__(
        self,
        *,
        parent: Display,
        task_instruction: str,
        reasoning_effort: str | None,
    ) -> None:
        self.parent = parent
        self.verbose = parent.verbose
        self._task_instruction = task_instruction
        self._reasoning_effort = reasoning_effort
        self._tool_group = PendingToolGroup()
        self._waiting_widget_id: str | None = None
        self._active_thinking_widget_id: str | None = None
        self._counter = 0
        self._block_id = parent._next_id("subagent")
        self._body_id = f"{self._block_id}-body"
        self.parent._safe_call(
            self.parent.app.mount_sub_agent_block,
            self._block_id,
            self._title("running"),
            body_id=self._body_id,
        )

    def _title(self, status: str) -> str:
        summary = shorten(self._task_instruction.strip() or "sub-agent task", 72)
        title = f"sub_agent \u00b7 {summary} \u00b7 {status}"
        if self._reasoning_effort:
            title += f" \u00b7 {self._reasoning_effort}"
        return title

    def _next_id(self, prefix: str) -> str:
        self._counter += 1
        return f"{self._block_id}-{prefix}-{self._counter}"

    def _mount_widget(self, widget: Static) -> None:
        self.parent._safe_call(
            self.parent.app.mount_widget_in_container,
            self._body_id,
            widget,
        )

    def _query_optional(self, selector: str) -> Any | None:
        return self.parent._safe_call(self.parent.app._query_optional, selector)

    def _mount_static_message(
        self,
        prefix: str,
        widget_cls: type[Static],
        text: str,
        *,
        classes: str = "",
    ) -> str:
        widget_id = self._next_id(prefix)
        kwargs: dict[str, Any] = {"id": widget_id}
        if classes:
            kwargs["classes"] = classes
        self._mount_widget(widget_cls(text, **kwargs))
        return widget_id

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

    # -- protocol stubs (no-ops for sub-agent context) -----------------------

    def request_shutdown(self) -> None:
        return None

    def submit_input(self, value: str) -> None:
        del value

    def request_new_chat(self) -> None:
        raise RuntimeError("Sub-agent display does not support interactive chat.")

    def reset_chat(self) -> None:
        return None

    def begin_sub_agent(
        self,
        *,
        task_instruction: str,
        reasoning_effort: str | None = None,
    ) -> DisplayProtocol:
        del task_instruction, reasoning_effort
        return self

    def finish_sub_agent(self, *, status: str) -> None:
        self.wait_stop()
        self.parent._safe_call(
            self.parent.app.update_sub_agent_title,
            self._block_id,
            self._title(status),
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
        if self._waiting_widget_id is not None:
            return
        self._active_thinking_widget_id = None
        widget_id = self._next_id("wait")
        self._waiting_widget_id = widget_id
        self._mount_widget(WaitingIndicator(message=message, id=widget_id))

    def wait_stop(self) -> None:
        if self._waiting_widget_id is not None:
            self.parent._safe_call(
                self.parent.app.remove_widget, self._waiting_widget_id
            )
            self._waiting_widget_id = None

    def render_markdown(self, text: str) -> None:
        widget_id = self._next_id("md")
        self._mount_widget(AssistantMarkdown(text, id=widget_id))

    def render_thinking(
        self,
        text: str | None = None,
        *,
        title: str | None = None,
        replace_existing: bool = False,
        widget_id: str | None = None,
    ) -> str | None:
        summary = title or ""
        body, widget_title = resolve_reasoning_panel(text, summary)
        if body is None and not summary.strip():
            return None

        resolved_widget_id = widget_id
        if resolved_widget_id is None and replace_existing:
            resolved_widget_id = self._active_thinking_widget_id
        if resolved_widget_id is None:
            resolved_widget_id = self._next_id("thinking")
        if replace_existing:
            self._active_thinking_widget_id = resolved_widget_id

        existing = self._query_optional(f"#{resolved_widget_id}")
        if existing is None:
            self._mount_widget(
                ThinkingBlock(
                    ThinkingContent(body or "", id=f"{resolved_widget_id}-content"),
                    title=widget_title,
                    collapsed=True,
                    id=resolved_widget_id,
                )
            )
            return resolved_widget_id

        self.parent._safe_call(
            self.parent.app.update_thinking_block,
            resolved_widget_id,
            widget_title,
            body,
        )
        return resolved_widget_id

    def render_redacted_thinking(self) -> None:
        self._mount_static_message("redact", NoticeMessage, REDACTED_THINKING_NOTICE)

    def session_usage(self, usage: TokenUsage) -> None:
        del usage

    def turn_usage(self, usage: TokenUsage, elapsed_seconds: float) -> None:
        usage_text = format_usage_summary(
            usage.snapshot(),
            elapsed_seconds=elapsed_seconds,
            label="Sub-agent",
        )
        self._mount_static_message("usage", UsageSummary, usage_text)

    # -- tool display --------------------------------------------------------

    def shell_start(self, commands: list[str]) -> None:
        self._start_tool_group(
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
        self._append_tool_line(
            "shell",
            format_shell_tool_item(
                command,
                verbose=self.verbose,
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
            format_patch_tool_item(
                path,
                operation,
                verbose=self.verbose,
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
        self._tool_group.update_for_function(name)
        tool_name, text = route_function_result(
            name,
            verbose=self.verbose,
            status=status_markup(success=success),
            call_id=call_id,
            arguments=arguments,
        )
        self._append_tool_line(tool_name, text)

    def tool_group_end(self) -> None:
        if not self._tool_group.items:
            self._tool_group.reset()
            return
        group_id = self._next_id("tg")
        group = ToolGroup(
            *[
                ToolItem(item.text, classes=item.classes)
                for item in self._tool_group.items
            ],
            title=self._tool_group.label,
            collapsed=True,
            id=group_id,
            classes=self._tool_group.classes,
        )
        self._mount_widget(group)
        self._tool_group.reset()

    # -- notices -------------------------------------------------------------

    def retry_notice(self, attempt: int, max_retries: int) -> None:
        self.wait_stop()
        self._mount_static_message(
            "notice",
            NoticeMessage,
            f"Retrying\u2026 ({attempt}/{max_retries})",
        )

    def rate_limit_notice(
        self,
        *,
        wait_seconds: float,
        attempt: int,
        max_retries: int,
    ) -> None:
        self.wait_stop()
        self._mount_static_message(
            "notice",
            NoticeMessage,
            f"Rate limit reached. Retrying in {format_wait_seconds(wait_seconds)}s ({attempt}/{max_retries})",
        )

    def overload_notice(
        self,
        *,
        wait_seconds: float,
        attempt: int,
        max_retries: int,
    ) -> None:
        self.wait_stop()
        self._mount_static_message(
            "notice",
            NoticeMessage,
            f"Provider overloaded. Retrying in {format_wait_seconds(wait_seconds)}s ({attempt}/{max_retries})",
        )

    def error(self, message: str) -> None:
        self.wait_stop()
        self._tool_group.reset()
        self._mount_static_message(
            "err",
            ErrorMessage,
            f"Error: {escape_markup_text(message)}",
        )

    def debug(self, message: str) -> None:
        if self.verbose:
            self._mount_static_message(
                "dbg",
                Static,
                f"[dim]{message}[/dim]",
                classes="debug-msg",
            )

    def replay_history(self, messages: list[MessageRecord]) -> None:
        del messages
