"""Textual application for the PBI Agent chat UI."""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any

from textual import on, work
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.widget import Widget
from textual.widgets import Button, Footer, Header

from pbi_agent.models.messages import TokenUsage
from pbi_agent.agent.error_formatting import format_user_facing_error
from pbi_agent.ui.display import Display
from pbi_agent.ui.formatting import format_session_subtitle
from pbi_agent.ui.styles import CHAT_APP_CSS
from pbi_agent.ui.widgets import (
    AssistantMarkdown,
    ChatInput,
    ThinkingBlock,
    ThinkingContent,
    ToolGroup,
    ToolGroupEntry,
    ToolItem,
    UsageSummary,
    UserMessage,
    WaitingIndicator,
)

_log = logging.getLogger(__name__)


class ChatApp(App):
    """Textual TUI for PBI Agent."""

    TITLE = "PBI Agent"
    SUB_TITLE = format_session_subtitle(TokenUsage())
    CSS = CHAT_APP_CSS
    BINDINGS = [
        Binding("ctrl+r", "new_chat", "New Chat", show=True),
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
        self.fatal_error_message: str | None = None

    def compose(self) -> ComposeResult:
        yield Header()
        yield VerticalScroll(id="chat-log")
        yield Vertical(id="status-row")
        yield Horizontal(
            ChatInput(
                placeholder=(
                    "Type your message\u2026  "
                    "(Enter: newline, Ctrl+Enter/Ctrl+S: send, Ctrl+Q: quit)"
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

    def _chat_log(self) -> VerticalScroll:
        return self.query_one("#chat-log", VerticalScroll)

    def _status_row(self) -> Vertical:
        return self.query_one("#status-row", Vertical)

    def _chat_input(self) -> ChatInput:
        return self.query_one("#user-input", ChatInput)

    def _send_button(self) -> Button:
        return self.query_one("#send-button", Button)

    def _scroll_chat_end(self) -> None:
        self._chat_log().scroll_end(animate=False)

    def _query_optional(self, selector: str, widget_type: Any = Widget) -> Any | None:
        try:
            return self.query_one(selector, widget_type)
        except Exception:
            return None

    def _set_input_enabled(self, enabled: bool) -> None:
        inp = self._chat_input()
        send_btn = self._send_button()
        inp.disabled = not enabled
        send_btn.disabled = not enabled
        if enabled:
            inp.focus()

    def _run_single_turn_mode(self, display: Display) -> int:
        from pbi_agent.agent.session import run_single_turn

        assert self._prompt is not None
        outcome = run_single_turn(
            self._prompt,
            self._settings,
            display,
            single_turn_hint=self._single_turn_hint,
        )
        return 4 if outcome.tool_errors else 0

    def _prepare_audit_mode(self) -> None:
        from pbi_agent.agent.audit_prompt import copy_audit_todo

        if self._audit_report_dir:
            os.chdir(self._audit_report_dir)
            copy_audit_todo(self._audit_report_dir)

    def _run_selected_mode(self, display: Display) -> int:
        from pbi_agent.agent.session import run_chat_loop

        if self._mode == "chat":
            return run_chat_loop(self._settings, display)
        if self._mode == "audit":
            self._prepare_audit_mode()
        if self._mode in {"run", "audit"}:
            return self._run_single_turn_mode(display)
        return 0

    @work(thread=True, exclusive=True)
    def _run_session(self) -> None:
        display = self._bridge
        assert display is not None

        try:
            self.exit_code = self._run_selected_mode(display)
        except SystemExit:
            pass
        except Exception as exc:
            _log.exception("Session worker crashed")
            self.fatal_error_message = format_user_facing_error(exc)
            self.exit_code = 1
        finally:
            try:
                self.call_from_thread(self.exit)
            except Exception:
                pass

    async def mount_widget(self, widget: Widget) -> None:
        if isinstance(widget, WaitingIndicator):
            await self._status_row().mount(widget)
            return
        await self._chat_log().mount(widget)
        self._scroll_chat_end()

    def remove_widget(self, widget_id: str) -> None:
        widget = self._query_optional(f"#{widget_id}")
        if widget is not None:
            widget.remove()

    async def update_markdown(self, widget_id: str, text: str) -> None:
        widget = self._query_optional(f"#{widget_id}", AssistantMarkdown)
        if widget is None:
            return
        await widget.update(text)
        self._scroll_chat_end()

    async def mount_thinking_block(
        self,
        block_id: str,
        title: str,
        text: str = "",
    ) -> None:
        block = ThinkingBlock(
            ThinkingContent(text, id=f"{block_id}-content"),
            title=title,
            collapsed=True,
            id=block_id,
        )
        await self._chat_log().mount(block)
        self._scroll_chat_end()

    async def update_thinking_block(
        self,
        block_id: str,
        title: str,
        text: str | None = None,
    ) -> None:
        block = self._query_optional(f"#{block_id}", ThinkingBlock)
        content = self._query_optional(f"#{block_id}-content", ThinkingContent)
        if block is None:
            await self.mount_thinking_block(block_id, title, text or "")
            return
        block.title = title
        if content is None:
            self._scroll_chat_end()
            return
        if text is not None:
            await content.update(text)
        self._scroll_chat_end()

    def update_usage_summary(self, widget_id: str, text: str) -> None:
        widget = self._query_optional(f"#{widget_id}", UsageSummary)
        if widget is None:
            return
        widget.update(text)
        self._scroll_chat_end()

    def update_session_header(self, sub_title: str) -> None:
        self.sub_title = sub_title

    def enable_input(self) -> None:
        self._set_input_enabled(True)

    def disable_input(self) -> None:
        self._set_input_enabled(False)

    async def mount_tool_group(
        self,
        group_id: str,
        label: str,
        items: list[ToolGroupEntry],
        *,
        group_classes: str = "",
    ) -> None:
        group = ToolGroup(
            *[ToolItem(item.text, classes=item.classes) for item in items],
            title=label,
            collapsed=True,
            id=group_id,
            classes=group_classes,
        )
        await self._chat_log().mount(group)
        self._scroll_chat_end()

    def add_user_message(self, text: str) -> None:
        self._chat_log().mount(UserMessage(text))
        self._scroll_chat_end()

    def reset_chat_view(self) -> None:
        self._chat_log().remove_children()
        self._status_row().remove_children()
        inp = self._chat_input()
        inp.clear()
        inp.reset_height()

    def _submit_user_message(self, raw_text: str) -> None:
        value = raw_text.strip()
        if not value:
            return
        inp = self._chat_input()
        inp.clear()
        inp.reset_height()
        self.disable_input()
        self.add_user_message(value)
        if self._bridge is not None:
            self._bridge.submit_input(value)

    @on(ChatInput.Submitted, "#user-input")
    def handle_input_submitted(self, event: ChatInput.Submitted) -> None:
        self._submit_user_message(event.value)

    @on(Button.Pressed, "#send-button")
    def handle_send_button_pressed(self, _: Button.Pressed) -> None:
        self._submit_user_message(self._chat_input().text)

    async def action_new_chat(self) -> None:
        if self._bridge is not None:
            self._bridge.request_new_chat()

    async def action_quit(self) -> None:
        if self._bridge is not None:
            self._bridge.request_shutdown()
        self.exit()


__all__ = ["ChatApp"]
