"""Synchronous display bridge for the Textual chat UI."""

from __future__ import annotations

import logging
import queue
import threading
import traceback
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from textual.widgets import Static

from pbi_agent.models.messages import TokenUsage
from pbi_agent.session_store import MessageRecord
from pbi_agent.ui.display_protocol import DisplayProtocol, PendingToolGroup
from pbi_agent.ui.formatting import (
    REDACTED_THINKING_NOTICE,
    escape_markup_text,
    format_context_tooltip,
    format_patch_tool_item,
    format_session_subtitle_parts,
    format_shell_tool_item,
    format_usage_summary,
    format_wait_seconds,
    resolve_reasoning_panel,
    route_function_result,
    status_markup,
    tool_group_class,
    tool_item_class,
)
from pbi_agent.ui.widgets import (
    AssistantMarkdown,
    ErrorMessage,
    NoticeMessage,
    ToolGroupEntry,
    UsageSummary,
    WaitingIndicator,
    WelcomeBanner,
)

if TYPE_CHECKING:
    from pbi_agent.ui.app import ChatApp

_log = logging.getLogger(__name__)


@dataclass(slots=True)
class _TurnUsageWidget:
    widget_id: str
    elapsed_seconds: float


class Display(DisplayProtocol):
    """Sync bridge between session code and the Textual App."""

    def __init__(
        self,
        app: ChatApp,
        *,
        verbose: bool = False,
        model: str | None = None,
        reasoning_effort: str | None = None,
    ) -> None:
        self.app = app
        self.verbose = verbose
        self._model = model
        self._reasoning_effort = reasoning_effort
        self._waiting_widget_id: str | None = None
        self._active_thinking_widget_id: str | None = None
        self._msg_counter = 0
        self._tool_group = PendingToolGroup()
        self._input_event = threading.Event()
        self._input_queue: queue.Queue[str] = queue.Queue()
        self._shutdown = threading.Event()
        self._turn_usage_widgets: dict[int, _TurnUsageWidget] = {}
        self._turn_usage_lock = threading.Lock()

    def _next_id(self, prefix: str = "w") -> str:
        self._msg_counter += 1
        return f"{prefix}-{self._msg_counter}"

    def _safe_call(self, callback: Any, *args: Any, **kwargs: Any) -> Any:
        try:
            return self.app.call_from_thread(callback, *args, **kwargs)
        except Exception:
            _log.debug(
                "_safe_call failed for %s: %s",
                getattr(callback, "__name__", callback),
                traceback.format_exc(),
            )
            return None

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
        self._safe_call(self.app.mount_widget, widget_cls(text, **kwargs))
        return widget_id

    def _mount_markdown(self, prefix: str, text: str) -> str:
        widget_id = self._next_id(prefix)
        self._safe_call(self.app.mount_widget, AssistantMarkdown(text, id=widget_id))
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

    def request_shutdown(self) -> None:
        self._shutdown.set()
        self._input_event.set()

    def submit_input(self, value: str) -> None:
        self._input_queue.put(value)
        self._input_event.set()

    def request_new_chat(self) -> None:
        from pbi_agent.agent.session import NEW_CHAT_SENTINEL

        self._input_queue.put(NEW_CHAT_SENTINEL)
        self._input_event.set()

    def request_resume_session(self, session_id: str) -> None:
        from pbi_agent.agent.session import RESUME_SESSION_PREFIX

        self._input_queue.put(f"{RESUME_SESSION_PREFIX}{session_id}")
        self._input_event.set()

    def reset_chat(self) -> None:
        self._waiting_widget_id = None
        self._active_thinking_widget_id = None
        self._tool_group.reset()
        with self._turn_usage_lock:
            self._turn_usage_widgets.clear()
        self._safe_call(self.app.reset_chat_view)

    def begin_sub_agent(
        self,
        *,
        task_instruction: str,
        reasoning_effort: str | None = None,
    ) -> DisplayProtocol:
        from pbi_agent.ui.sub_agent_display import SubAgentDisplay

        return SubAgentDisplay(
            parent=self,
            task_instruction=task_instruction,
            reasoning_effort=reasoning_effort,
        )

    def finish_sub_agent(self, *, status: str) -> None:
        del status

    def welcome(
        self,
        *,
        interactive: bool = True,
        model: str | None = None,
        reasoning_effort: str | None = None,
        single_turn_hint: str | None = None,
    ) -> None:
        self._safe_call(
            self.app.mount_widget,
            WelcomeBanner(
                interactive=interactive,
                model=model,
                reasoning_effort=reasoning_effort,
                single_turn_hint=single_turn_hint,
            ),
        )

    def user_prompt(self) -> str:
        while True:
            if self._shutdown.is_set():
                return "exit"
            try:
                value = self._input_queue.get_nowait()
            except queue.Empty:
                self._safe_call(self.app.enable_input)
                self._input_event.wait(timeout=0.5)
                self._input_event.clear()
                continue
            if self._input_queue.empty():
                self._input_event.clear()
            return value

    def assistant_start(self) -> None:
        """Compatibility hook kept for the session/provider interface."""

    def wait_start(self, message: str = "model is processing your request...") -> None:
        if self._waiting_widget_id is not None:
            return
        self._active_thinking_widget_id = None
        widget_id = self._next_id("think")
        self._waiting_widget_id = widget_id
        self._safe_call(
            self.app.mount_widget,
            WaitingIndicator(message=message, id=widget_id),
        )

    def wait_stop(self) -> None:
        if self._waiting_widget_id is not None:
            self._safe_call(self.app.remove_widget, self._waiting_widget_id)
            self._waiting_widget_id = None

    def render_markdown(self, text: str) -> None:
        self._mount_markdown("md", text)

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

        self._safe_call(
            self.app.update_thinking_block,
            resolved_widget_id,
            widget_title,
            body,
        )
        return resolved_widget_id

    def render_redacted_thinking(self) -> None:
        self._mount_static_message(
            "redact",
            NoticeMessage,
            REDACTED_THINKING_NOTICE,
        )

    def session_usage(self, usage: TokenUsage) -> None:
        snapshot = usage.snapshot()
        sub_title, context_label = format_session_subtitle_parts(
            snapshot,
            model=self._model,
            reasoning_effort=self._reasoning_effort,
        )
        self._safe_call(
            self.app.update_session_header,
            sub_title,
            context_label=context_label,
            tooltip=format_context_tooltip(snapshot, model=self._model),
        )

    def turn_usage(self, usage: TokenUsage, elapsed_seconds: float) -> None:
        usage_text = format_usage_summary(
            usage.snapshot(),
            elapsed_seconds=elapsed_seconds,
            label="Turn",
        )
        widget_id = self._mount_static_message("usage", UsageSummary, usage_text)
        with self._turn_usage_lock:
            self._turn_usage_widgets[id(usage)] = _TurnUsageWidget(
                widget_id=widget_id,
                elapsed_seconds=elapsed_seconds,
            )

    def _refresh_turn_usage_widget(self, usage: TokenUsage) -> None:
        with self._turn_usage_lock:
            target = self._turn_usage_widgets.get(id(usage))
        if target is None:
            return
        text = format_usage_summary(
            usage.snapshot(),
            elapsed_seconds=target.elapsed_seconds,
            label="Turn",
        )
        self._safe_call(self.app.update_usage_summary, target.widget_id, text)

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
        if self._tool_group.items:
            group_id = self._next_id("tg")
            self._safe_call(
                self.app.mount_tool_group,
                group_id,
                self._tool_group.label,
                [
                    ToolGroupEntry(text=item.text, classes=item.classes)
                    for item in self._tool_group.items
                ],
                group_classes=self._tool_group.classes,
            )
        self._tool_group.reset()

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
        if self._active_thinking_widget_id:
            self._safe_call(self.app.remove_widget, self._active_thinking_widget_id)
            self._active_thinking_widget_id = None
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
        for msg in messages:
            if msg.role == "user":
                self._safe_call(self.app.add_user_message, msg.content)
            elif msg.role == "assistant":
                self._mount_markdown("history", msg.content)


__all__ = ["Display"]
