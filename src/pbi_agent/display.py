"""Textual TUI chat interface for PBI Agent.

All user-facing output goes through :class:`Display` so that ``session.py``
never touches widgets directly.  The :class:`ChatApp` is a Textual App that
owns a Display instance and runs the agent session in a background worker
thread.  Display methods use ``call_from_thread`` to bridge synchronous
session code to the async Textual UI.
"""

from __future__ import annotations

import json
import logging
import os
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from textual import events, on, work
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.message import Message
from textual.widget import Widget
from textual.widgets import (
    Button,
    Collapsible,
    Footer,
    Header,
    LoadingIndicator,
    Markdown as MarkdownWidget,
    Static,
    TextArea,
)

from pbi_agent import __version__
from pbi_agent.models.messages import TokenUsage

_log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _shorten(text: str, limit: int = 80) -> str:
    if len(text) <= limit:
        return text
    return text[: limit - 1] + "\u2026"


def _compact_json(value: Any) -> str:
    try:
        return json.dumps(value, separators=(",", ":"), ensure_ascii=False)
    except TypeError:
        return str(value)


def _escape_markup_text(text: str) -> str:
    """Escape literal '[' so dynamic values can't break Rich markup parsing."""
    return text.replace("[", r"\[")


# ---------------------------------------------------------------------------
# Custom widgets
# ---------------------------------------------------------------------------


class WelcomeBanner(Static):
    """Welcome banner with PBI Agent branding."""

    def __init__(
        self,
        *,
        interactive: bool = True,
        model: str | None = None,
        reasoning_effort: str | None = None,
        single_turn_hint: str | None = None,
    ) -> None:
        logo_rows = [
            "              \u2588\u2588\u2588\u2588",
            "              \u2588\u2588\u2588\u2588",
            "        \u2588\u2588\u2588\u2588  \u2588\u2588\u2588\u2588",
            "        \u2588\u2588\u2588\u2588  \u2588\u2588\u2588\u2588",
            "  \u2588\u2588\u2588\u2588  \u2588\u2588\u2588\u2588  \u2588\u2588\u2588\u2588",
            "  \u2588\u2588\u2588\u2588  \u2588\u2588\u2588\u2588  \u2588\u2588\u2588\u2588",
        ]
        lines: list[str] = []
        lines.append(f"[bold #F2C811]{''.join(logo_rows[0])}[/bold #F2C811]")
        for row in logo_rows[1:]:
            lines.append(f"[bold #F2C811]{row}[/bold #F2C811]")
        lines.append("")
        lines.append("[bold #F2C811]PBI AGENT[/bold #F2C811]")
        lines.append("[bold]Transform data into decisions.[/bold]")
        lines.append("")

        if interactive:
            lines.append(
                "[dim]Interactive mode:[/dim] Type [bold]exit[/bold] or "
                "[bold]quit[/bold] to stop."
            )
            lines.append("[dim]Enter[/dim] for newline  ·  [dim]Ctrl+S[/dim] to submit")
        elif single_turn_hint:
            cleaned = single_turn_hint
            for tag in (
                "[dim]",
                "[/dim]",
                "[bold]",
                "[/bold]",
            ):
                cleaned = cleaned.replace(tag, "")
            lines.append(cleaned)
        else:
            lines.append("Single prompt mode: Running one request.")

        if model or reasoning_effort:
            parts: list[str] = []
            if model:
                parts.append(f"Model: [bold]{model}[/bold]")
            if reasoning_effort:
                parts.append(f"Reasoning: [bold]{reasoning_effort}[/bold]")
            lines.append("[dim]\u00b7[/dim]  ".join(parts))

        lines.append(f"[dim]v{__version__}[/dim]")
        super().__init__("\n".join(lines))


class UserMessage(Static):
    """User message bubble."""

    def __init__(self, text: str, **kwargs: Any) -> None:
        super().__init__(text, **kwargs)


class AssistantMarkdown(MarkdownWidget):
    """Markdown widget for assistant responses."""


class WaitingIndicator(Vertical):
    """Loading indicator with contextual message."""

    def __init__(self, message: str = "processing...", **kwargs: Any) -> None:
        clean_message = message.strip() or "processing..."
        super().__init__(
            LoadingIndicator(classes="waiting-spinner"),
            Static(clean_message, classes="waiting-message"),
            **kwargs,
        )


class ToolGroup(Collapsible):
    """Collapsible container for tool execution items."""


class ToolHeader(Static):
    """Header for a tool group."""


class ToolItem(Static):
    """Individual tool execution result."""


class UsageSummary(Static):
    """Token usage summary bar."""


class ErrorMessage(Static):
    """Error message display."""


class ThinkingBlock(Collapsible):
    """Collapsible block for model thinking/reasoning content."""


class ThinkingContent(MarkdownWidget):
    """Markdown widget for thinking content within a collapsible."""


class NoticeMessage(Static):
    """Notice/warning message."""


class ChatInput(TextArea):
    """Multiline input that auto-grows and submits on Ctrl+S."""

    BASE_HEIGHT = 4
    MAX_HEIGHT = 20
    _CHROME_HEIGHT = 2  # TextArea uses a tall border.

    @dataclass
    class Submitted(Message):
        """Message emitted when the user submits the chat input."""

        input: "ChatInput"
        value: str

        @property
        def control(self) -> "ChatInput":
            return self.input

    def on_mount(self) -> None:
        # Keep widget CSS constraints in sync with class-level constants so
        # changing BASE_HEIGHT / MAX_HEIGHT is enough.
        self.styles.min_height = self.BASE_HEIGHT
        self.styles.max_height = self.MAX_HEIGHT
        self.reset_height()

    def reset_height(self) -> None:
        """Reset to the initial compact size."""
        self.styles.height = self.BASE_HEIGHT

    def _resize_to_content(self) -> None:
        """Grow/shrink with content, clamped to a usable max."""
        content_height = max(self.wrapped_document.height, 1)
        target_height = max(
            self.BASE_HEIGHT,
            min(self.MAX_HEIGHT, content_height + self._CHROME_HEIGHT),
        )
        self.styles.height = target_height

    def on_text_area_changed(self, _: TextArea.Changed) -> None:
        self._resize_to_content()

    async def _on_key(self, event: events.Key) -> None:
        self._restart_blink()
        if self.read_only:
            return
        if event.key == "ctrl+s" or "ctrl+s" in event.aliases:
            event.stop()
            event.prevent_default()
            self.post_message(self.Submitted(self, self.text))
            return
        await super()._on_key(event)


# ---------------------------------------------------------------------------
# Display bridge  (synchronous API consumed by session.py)
# ---------------------------------------------------------------------------


class Display:
    """Sync bridge between session code and the Textual App.

    Every public method in this class is safe to call from a non-UI thread.
    Internally each call uses ``app.call_from_thread`` to schedule the
    corresponding widget update on the main Textual thread.
    """

    def __init__(self, app: ChatApp, *, verbose: bool = False) -> None:
        self.app = app
        self.verbose = verbose
        self._stream_parts: list[str] = []
        self._thinking_id: str | None = None
        self._current_msg_id: str | None = None
        self._msg_counter = 0
        self._pending_group_label: str = ""
        self._pending_group_items: list[str] = []
        self._input_event = threading.Event()
        self._input_value = ""
        self._shutdown = threading.Event()

    # -- internal helpers ---------------------------------------------------

    def _next_id(self, prefix: str = "w") -> str:
        self._msg_counter += 1
        return f"{prefix}-{self._msg_counter}"

    def _safe_call(self, callback: Any, *args: Any, **kwargs: Any) -> Any:
        """Call a method on the app from a worker thread, swallowing errors
        that occur when the app has already shut down."""
        try:
            return self.app.call_from_thread(callback, *args, **kwargs)
        except Exception:
            _log.debug(
                "_safe_call failed for %s: %s",
                getattr(callback, "__name__", callback),
                __import__("traceback").format_exc(),
            )
            return None

    def request_shutdown(self) -> None:
        """Signal the Display to unblock any waiting prompt and stop."""
        self._shutdown.set()
        self._input_event.set()

    def submit_input(self, value: str) -> None:
        """Called from the UI thread when user submits input."""
        self._input_value = value
        self._input_event.set()

    # -- lifecycle ----------------------------------------------------------

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
        """Block the worker thread until the user submits input.

        Returns ``"exit"`` if the app is shutting down.
        """
        self._input_event.clear()
        self._safe_call(self.app.enable_input)
        # Wait with periodic checks so Ctrl+Q / app shutdown is honoured.
        while True:
            if self._input_event.wait(timeout=0.5):
                break
            if self._shutdown.is_set():
                return "exit"
        if self._shutdown.is_set():
            return "exit"
        return self._input_value

    # -- assistant streaming ------------------------------------------------

    def assistant_start(self) -> None:
        """Visual separator before the assistant response (no-op in TUI)."""

    def wait_start(self, message: str = "model is processing your request...") -> None:
        """Show a transient loading indicator."""
        if self._thinking_id is not None:
            return
        tid = self._next_id("think")
        self._thinking_id = tid
        self._safe_call(
            self.app.mount_widget,
            WaitingIndicator(message=message, id=tid),
        )

    def wait_stop(self) -> None:
        if self._thinking_id is not None:
            self._safe_call(self.app.remove_widget, self._thinking_id)
            self._thinking_id = None

    def stream_delta(self, delta: str) -> None:
        """Append a streamed token and update the live Markdown widget."""
        self.wait_stop()
        self._stream_parts.append(delta)
        text = "".join(self._stream_parts)

        if self._current_msg_id is None:
            mid = self._next_id("assistant")
            self._current_msg_id = mid
            self._safe_call(
                self.app.mount_widget,
                AssistantMarkdown("", id=mid),
            )

        self._safe_call(self.app.update_markdown, self._current_msg_id, text)

    def stream_end(self) -> None:
        """Finalise the streamed Markdown widget."""
        self.wait_stop()
        text = "".join(self._stream_parts)
        if self._current_msg_id and text.strip():
            self._safe_call(
                self.app.update_markdown,
                self._current_msg_id,
                text,
            )
        self._stream_parts = []
        self._current_msg_id = None

    def stream_abort(self) -> None:
        """Stop active waiting/streaming without printing final text."""
        self.wait_stop()
        if self._current_msg_id:
            self._safe_call(self.app.remove_widget, self._current_msg_id)
        self._stream_parts = []
        self._current_msg_id = None

    def render_markdown(self, text: str) -> None:
        """Render a completed response as Markdown (single-turn mode)."""
        mid = self._next_id("md")
        self._safe_call(
            self.app.mount_widget,
            AssistantMarkdown(text, id=mid),
        )

    def render_thinking(self, text: str) -> None:
        """Render a thinking/reasoning block as a collapsible element."""
        tid = self._next_id("thinking")
        content_widget = ThinkingContent(text, id=f"{tid}-content")
        block = ThinkingBlock(
            content_widget,
            title="Thinking\u2026",
            collapsed=True,
            id=tid,
        )
        self._safe_call(self.app.mount_widget, block)

    def render_redacted_thinking(self) -> None:
        """Render a notice for redacted (encrypted) thinking blocks."""
        nid = self._next_id("redact")
        self._safe_call(
            self.app.mount_widget,
            NoticeMessage(
                "[dim]Some thinking was encrypted for safety reasons.[/dim]",
                id=nid,
            ),
        )

    def session_usage(self, usage: TokenUsage, elapsed_seconds: float) -> None:
        """Show cumulative session usage and estimated cost."""
        total_secs = int(elapsed_seconds)
        hours, remainder = divmod(total_secs, 3600)
        minutes, seconds = divmod(remainder, 60)
        time_str = (
            f"{hours}:{minutes:02d}:{seconds:02d}"
            if hours > 0
            else f"{minutes}:{seconds:02d}"
        )
        total = f"{usage.total_tokens:,}"
        inp = f"{usage.input_tokens:,}"
        cached = f"{usage.cached_input_tokens:,}"
        cache_w = usage.cache_write_tokens + usage.cache_write_1h_tokens
        out = f"{usage.output_tokens:,}"
        cost = f"${usage.estimated_cost_usd:.3f}"
        cache_detail = f"{cached} cached"
        if cache_w:
            cache_detail += f" [dim]\u00b7[/dim] {cache_w:,} cache-write"
        out_detail = f"{out} out"
        if usage.reasoning_tokens:
            out_detail += f" [dim]\u00b7[/dim] {usage.reasoning_tokens:,} reasoning"
        text = (
            f"[dim]{total} tokens[/dim]  "
            f"({inp} in [dim]\u00b7[/dim] {cache_detail} [dim]\u00b7[/dim] {out_detail})"
            f"  [dim]|[/dim]  {cost}"
            f"  [dim]|[/dim]  {time_str}"
        )
        uid = self._next_id("usage")
        self._safe_call(self.app.mount_widget, UsageSummary(text, id=uid))

    # -- tool: shell --------------------------------------------------------

    def shell_start(self, commands: list[str]) -> None:
        n = len(commands)
        self._pending_group_label = f"Running {n} shell command{'s' if n != 1 else ''}"
        self._pending_group_items = []

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
        cmd_short = _escape_markup_text(_shorten(command, 72))
        if timed_out:
            status = "[yellow]timeout[/yellow]"
        elif exit_code == 0:
            status = "[green]done[/green]"
        else:
            status = f"[red]exit {exit_code}[/red]"

        meta = ""
        if self.verbose:
            meta = (
                f"  [dim]({_escape_markup_text(call_id)}) "
                f"wd={_escape_markup_text(str(working_directory))} "
                f"timeout_ms={_escape_markup_text(str(timeout_ms))}[/dim]"
            )
        text = f"[dim]$[/dim] {cmd_short}  {status}{meta}"
        self._pending_group_items.append(text)

    # -- tool: apply_patch --------------------------------------------------

    def patch_start(self, count: int) -> None:
        self._pending_group_label = f"Editing {count} file{'s' if count != 1 else ''}"
        self._pending_group_items = []

    def patch_result(
        self,
        path: str,
        operation: str,
        success: bool,
        *,
        call_id: str = "",
        detail: str = "",
    ) -> None:
        operation_safe = _escape_markup_text(operation)
        path_safe = _escape_markup_text(path)
        icon = "[green]done[/green]" if success else "[red]FAILED[/red]"
        extra = ""
        if self.verbose:
            extra = f"  [dim]({_escape_markup_text(call_id)})[/dim]"
            if detail:
                extra += f"  [dim]{_escape_markup_text(_shorten(detail, 100))}[/dim]"
        elif not success and detail:
            extra = f"  [dim]{_escape_markup_text(_shorten(detail, 60))}[/dim]"
        text = f"{operation_safe} [bold]{path_safe}[/bold]  {icon}{extra}"
        self._pending_group_items.append(text)

    # -- tool: function -----------------------------------------------------

    def function_start(self, count: int) -> None:
        self._pending_group_label = (
            f"Calling {count} function{'s' if count != 1 else ''}"
        )
        self._pending_group_items = []

    def function_result(
        self,
        name: str,
        success: bool,
        *,
        call_id: str = "",
        arguments: Any = None,
    ) -> None:
        name_safe = _escape_markup_text(name)
        icon = "[green]done[/green]" if success else "[red]FAILED[/red]"
        if self.verbose:
            args_str = _escape_markup_text(_shorten(_compact_json(arguments), 120))
            text = (
                f"{name_safe}()  {icon}  [dim]({_escape_markup_text(call_id)}) "
                f"args={args_str}[/dim]"
            )
        else:
            text = f"{name_safe}()  {icon}"
        self._pending_group_items.append(text)

    # -- tool group end (shared) -------------------------------------------

    def tool_group_end(self) -> None:
        """Flush buffered tool items as a complete tool group widget."""
        if self._pending_group_items:
            gid = self._next_id("tg")
            self._safe_call(
                self.app.mount_tool_group,
                gid,
                self._pending_group_label,
                list(self._pending_group_items),
            )
        self._pending_group_label = ""
        self._pending_group_items = []

    # -- retries / errors ---------------------------------------------------

    def retry_notice(self, attempt: int, max_retries: int) -> None:
        self.wait_stop()
        nid = self._next_id("notice")
        self._safe_call(
            self.app.mount_widget,
            NoticeMessage(f"Reconnecting\u2026 ({attempt}/{max_retries})", id=nid),
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
        nid = self._next_id("notice")
        self._safe_call(
            self.app.mount_widget,
            NoticeMessage(
                f"Rate limit reached. Retrying in {wait_display}s "
                f"({attempt}/{max_retries})",
                id=nid,
            ),
        )

    def error(self, message: str) -> None:
        self.stream_abort()
        eid = self._next_id("err")
        self._safe_call(
            self.app.mount_widget,
            ErrorMessage(f"Error: {message}", id=eid),
        )

    def debug(self, message: str) -> None:
        """Print only when ``--verbose`` is active."""
        if self.verbose:
            did = self._next_id("dbg")
            self._safe_call(
                self.app.mount_widget,
                Static(f"[dim]{message}[/dim]", id=did, classes="debug-msg"),
            )


# ---------------------------------------------------------------------------
# Textual App
# ---------------------------------------------------------------------------


class ChatApp(App):
    """Textual TUI for PBI Agent."""

    TITLE = "PBI Agent"
    SUB_TITLE = f"v{__version__}  \u00b7  Power BI Report Assistant"

    CSS = """
    Screen {
        background: $surface;
    }

    /* ---- chat log ---- */
    #chat-log {
        height: 1fr;
        padding: 0 1;
    }

    /* ---- welcome ---- */
    WelcomeBanner {
        text-align: center;
        padding: 1 2;
        margin: 1 6;
        border: tall #F2C811;
        background: $boost;
    }

    /* ---- user message ---- */
    UserMessage {
        margin: 1 1 0 12;
        padding: 1 2;
        background: $primary 15%;
        border-left: thick $success;
    }

    /* ---- assistant response ---- */
    AssistantMarkdown {
        margin: 1 12 0 1;
        padding: 0 2;
    }

    /* ---- waiting ---- */
    WaitingIndicator {
        margin: 0 12 0 1;
        padding: 0 2;
        height: auto;
    }
    WaitingIndicator > .waiting-spinner {
        color: $accent;
    }
    WaitingIndicator > .waiting-message {
        color: $text-muted;
    }

    /* ---- tool groups ---- */
    ToolGroup {
        margin: 1 4;
        padding: 0 2;
        height: auto;
        background: $boost;
    }
    ToolGroup > CollapsibleTitle {
        padding: 1 2;
    }
    ToolGroup > Contents {
        padding: 1 2;
    }
    ToolItem {
        padding-left: 2;
    }

    /* ---- thinking block ---- */
    ThinkingBlock {
        margin: 1 4;
        padding: 0 1;
        height: auto;
        background: $boost;
        border-left: thick $accent;
    }
    ThinkingBlock > CollapsibleTitle {
        padding: 1 2;
        color: $text-muted;
    }
    ThinkingBlock > Contents {
        padding: 0 2;
    }
    ThinkingContent {
        color: $text-muted;
        padding: 0 1;
    }

    /* ---- usage summary ---- */
    UsageSummary {
        text-align: center;
        color: $text-muted;
        padding: 1 0;
        margin: 0 4;
    }

    /* ---- error / notice ---- */
    ErrorMessage {
        color: $error;
        text-style: bold;
        margin: 1 4;
        padding: 1 2;
        border: round $error;
    }
    NoticeMessage {
        color: $warning;
        margin: 0 4;
        padding: 0 2;
    }
    .debug-msg {
        color: $text-muted;
        margin: 0 4;
    }

    /* ---- input ---- */
    #input-row {
        dock: bottom;
        margin: 0 2 1 2;
        height: auto;
        align-vertical: middle;
    }
    #user-input {
        width: 1fr;
        min-width: 0;
        height: 4;
    }
    #user-input:disabled {
        opacity: 0.5;
    }
    #send-button {
        width: auto;
        min-width: 10;
        margin: 1 5 0 0;
    }
    #send-button:disabled {
        opacity: 0.5;
    }
    """

    BINDINGS = [
        Binding("ctrl+q", "quit", "Quit", show=True),
        Binding("ctrl+c", "quit", "Quit", show=False),
    ]

    def __init__(
        self,
        *,
        settings: Any,
        verbose: bool = False,
        mode: str = "chat",
        prompt: str | None = None,
        audit_report_dir: Path | None = None,
        single_turn_hint: str | None = None,
    ) -> None:
        super().__init__()
        self._settings = settings
        self._verbose = verbose
        self._mode = mode
        self._prompt = prompt
        self._audit_report_dir = audit_report_dir
        self._single_turn_hint = single_turn_hint
        self._bridge: Display | None = None
        self.exit_code: int = 0

    # -- compose / mount ----------------------------------------------------

    def compose(self) -> ComposeResult:
        yield Header()
        yield VerticalScroll(id="chat-log")
        yield Horizontal(
            ChatInput(
                placeholder=(
                    "Type your message\u2026  "
                    "(Enter: newline, Ctrl+S: send, Ctrl+Q: quit)"
                ),
                id="user-input",
                disabled=True,
            ),
            Button("Send", id="send-button", variant="primary", disabled=True),
            id="input-row",
        )
        yield Footer()

    def on_mount(self) -> None:
        self._bridge = Display(app=self, verbose=self._verbose)
        self._run_session()

    # -- session worker -----------------------------------------------------

    @work(thread=True, exclusive=True)
    def _run_session(self) -> None:
        # Lazy imports avoid circular dependencies.
        from pbi_agent.agent.session import run_chat_loop, run_single_turn

        display = self._bridge
        assert display is not None

        try:
            if self._mode == "chat":
                rc = run_chat_loop(self._settings, display)
            elif self._mode == "run":
                assert self._prompt is not None
                outcome = run_single_turn(
                    self._prompt,
                    self._settings,
                    display,
                    single_turn_hint=self._single_turn_hint,
                )
                rc = 4 if outcome.tool_errors else 0
            elif self._mode == "audit":
                from pbi_agent.agent.audit_prompt import copy_audit_todo

                assert self._prompt is not None
                if self._audit_report_dir:
                    os.chdir(self._audit_report_dir)
                    copy_audit_todo(self._audit_report_dir)
                outcome = run_single_turn(
                    self._prompt,
                    self._settings,
                    display,
                    single_turn_hint=self._single_turn_hint,
                )
                rc = 4 if outcome.tool_errors else 0
            else:
                rc = 0

            self.exit_code = rc
        except SystemExit:
            pass
        except Exception as exc:
            _log.exception("Session worker crashed")
            if display:
                display.error(str(exc))
            self.exit_code = 1
        finally:
            try:
                self.call_from_thread(self.exit)
            except Exception:
                pass

    # -- UI update helpers (called via call_from_thread) --------------------

    async def mount_widget(self, widget: Widget) -> None:
        """Mount a widget into the chat log and scroll to it."""
        chat_log = self.query_one("#chat-log", VerticalScroll)
        await chat_log.mount(widget)
        chat_log.scroll_end(animate=False)

    def remove_widget(self, widget_id: str) -> None:
        """Remove a widget by its ID (silently ignores missing widgets)."""
        try:
            widget = self.query_one(f"#{widget_id}")
            widget.remove()
        except Exception:
            pass

    async def update_markdown(self, widget_id: str, text: str) -> None:
        """Update the content of a Markdown widget."""
        try:
            widget = self.query_one(f"#{widget_id}", AssistantMarkdown)
            await widget.update(text)
            self.query_one("#chat-log", VerticalScroll).scroll_end(animate=False)
        except Exception:
            pass

    def enable_input(self) -> None:
        """Enable the input field and give it focus."""
        inp = self.query_one("#user-input", ChatInput)
        send_btn = self.query_one("#send-button", Button)
        inp.disabled = False
        send_btn.disabled = False
        inp.focus()

    def disable_input(self) -> None:
        """Disable the input field."""
        inp = self.query_one("#user-input", ChatInput)
        send_btn = self.query_one("#send-button", Button)
        inp.disabled = True
        send_btn.disabled = True

    async def mount_tool_group(
        self, group_id: str, label: str, items: list[str]
    ) -> None:
        """Mount a complete tool group with all items in one DOM operation."""
        children = [ToolItem(text) for text in items]
        group = ToolGroup(*children, title=label, collapsed=True, id=group_id)
        chat_log = self.query_one("#chat-log", VerticalScroll)
        await chat_log.mount(group)
        chat_log.scroll_end(animate=False)

    def add_user_message(self, text: str) -> None:
        """Synchronously add a user message bubble to the chat log."""
        chat_log = self.query_one("#chat-log", VerticalScroll)
        chat_log.mount(UserMessage(text))
        chat_log.scroll_end(animate=False)

    # -- event handlers -----------------------------------------------------

    def _submit_user_message(self, raw_text: str) -> None:
        value = raw_text.strip()
        if not value:
            return
        inp = self.query_one("#user-input", ChatInput)
        inp.clear()
        inp.reset_height()
        self.disable_input()
        self.add_user_message(value)
        if self._bridge is not None:
            self._bridge.submit_input(value)

    @on(ChatInput.Submitted, "#user-input")
    def handle_input_submitted(self, event: ChatInput.Submitted) -> None:
        """Forward user input to the session worker thread."""
        self._submit_user_message(event.value)

    @on(Button.Pressed, "#send-button")
    def handle_send_button_pressed(self, _: Button.Pressed) -> None:
        """Submit the current input when Send is clicked."""
        inp = self.query_one("#user-input", ChatInput)
        self._submit_user_message(inp.text)

    def action_quit(self) -> None:
        """Handle Ctrl+Q / Ctrl+C gracefully."""
        if self._bridge is not None:
            self._bridge.request_shutdown()
        self.exit()
