"""Synchronous display bridge for the Textual chat UI."""

from __future__ import annotations

import logging
import threading
import traceback
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from textual.widgets import Static

from pbi_agent.models.messages import TokenUsage
from pbi_agent.ui.formatting import (
    REDACTED_THINKING_NOTICE,
    compact_json,
    escape_markup_text,
    format_reasoning_title,
    format_session_subtitle,
    format_usage_summary,
    shorten,
    status_markup,
    to_dict,
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
class _PendingToolGroup:
    label: str = ""
    classes: str = ""
    items: list[ToolGroupEntry] = field(default_factory=list)
    function_count: int = 0
    function_names: set[str] = field(default_factory=set)

    def start(self, label: str, *, classes: str = "", function_count: int = 0) -> None:
        self.label = label
        self.classes = classes
        self.items.clear()
        self.function_count = function_count
        self.function_names.clear()

    def add_item(self, text: str, *, classes: str = "") -> None:
        self.items.append(ToolGroupEntry(text=text, classes=classes))

    def update_for_function(self, tool_name: str) -> None:
        normalized = tool_name.strip() or "function"
        self.function_names.add(normalized)
        count = self.function_count or max(1, len(self.items))

        if len(self.function_names) == 1:
            self.label = normalized if count == 1 else f"{normalized} ({count} calls)"
            self.classes = tool_group_class(normalized)
            return

        self.label = f"Tool calls ({count})"
        self.classes = "tool-group-mixed"

    def reset(self) -> None:
        self.label = ""
        self.classes = ""
        self.items.clear()
        self.function_count = 0
        self.function_names.clear()


@dataclass(slots=True)
class _TurnUsageWidget:
    widget_id: str
    elapsed_seconds: float


class Display:
    """Sync bridge between session code and the Textual App."""

    def __init__(self, app: ChatApp, *, verbose: bool = False) -> None:
        self.app = app
        self.verbose = verbose
        self._waiting_widget_id: str | None = None
        self._active_thinking_widget_id: str | None = None
        self._msg_counter = 0
        self._tool_group = _PendingToolGroup()
        self._input_event = threading.Event()
        self._input_value = ""
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
            f"[dim]$[/dim] {escape_markup_text(shorten(command, 96))}  {status}",
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
        lines = [
            f"[bold]{escape_markup_text(dest)}[/bold]  {status}",
        ]
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
                lines = [f"{name_safe}()  {status}", f"[dim]{summary}[/dim]"]
                return "\n".join(lines)
            return f"{name_safe}()  {status}"

        detail_bits: list[str] = []
        if call_id:
            detail_bits.append(f"call_id={escape_markup_text(call_id)}")
        detail_bits.append(
            f"args={escape_markup_text(shorten(compact_json(arguments), 120))}"
        )
        return f"{name_safe}()  {status}  [dim]{' '.join(detail_bits)}[/dim]"

    def request_shutdown(self) -> None:
        self._shutdown.set()
        self._input_event.set()

    def submit_input(self, value: str) -> None:
        self._input_value = value
        self._input_event.set()

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
        self._input_event.clear()
        self._safe_call(self.app.enable_input)
        while True:
            if self._input_event.wait(timeout=0.5):
                break
            if self._shutdown.is_set():
                return "exit"
        if self._shutdown.is_set():
            return "exit"
        return self._input_value

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
        body = text if text is not None else None
        summary = title or ""
        has_body = body is not None and bool(body.strip())
        if not has_body and not summary.strip():
            return None

        widget_title = format_reasoning_title(summary)
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
        self._safe_call(
            self.app.update_session_header, format_session_subtitle(usage.snapshot())
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
        self._refresh_turn_usage_widget(usage)

    def usage_refresh(self, session_usage: TokenUsage, turn_usage: TokenUsage) -> None:
        self.session_usage(session_usage)
        self._refresh_turn_usage_widget(turn_usage)

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
        if self._tool_group.items:
            group_id = self._next_id("tg")
            self._safe_call(
                self.app.mount_tool_group,
                group_id,
                self._tool_group.label,
                list(self._tool_group.items),
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
        wait_display = f"{wait_seconds:.2f}".rstrip("0").rstrip(".")
        self._mount_static_message(
            "notice",
            NoticeMessage,
            f"Rate limit reached. Retrying in {wait_display}s ({attempt}/{max_retries})",
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


__all__ = ["Display"]
