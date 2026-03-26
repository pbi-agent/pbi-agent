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
from textual.widgets import Footer

from pbi_agent.models.messages import TokenUsage
from pbi_agent.agent.error_formatting import format_user_facing_error
from pbi_agent.providers.capabilities import provider_supports_images
from pbi_agent.ui.display import Display
from pbi_agent.ui.command_registry import LOCAL_COMMANDS, normalize_command_name
from pbi_agent.ui.formatting import format_session_subtitle_parts
from pbi_agent.ui.input_mentions import expand_input_mentions
from pbi_agent.ui.styles import CHAT_APP_CSS
from pbi_agent.ui.widgets import (
    AssistantMarkdown,
    ChatInput,
    SessionHeader,
    SessionHeaderContext,
    SessionListItem,
    SessionSidebar,
    ThinkingBlock,
    ThinkingContent,
    SubAgentBlock,
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
    SUB_TITLE = format_session_subtitle_parts(TokenUsage())[0]
    CSS = CHAT_APP_CSS
    BINDINGS = [
        Binding("ctrl+r", "new_chat", "New Chat", show=True),
        Binding("ctrl+b", "toggle_sidebar", "Sessions", show=True),
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
        resume_session_id: str | None = None,
    ) -> None:
        super().__init__()
        self._settings = settings
        self.sub_title, self._initial_context_label = format_session_subtitle_parts(
            TokenUsage(model=settings.model),
            model=settings.model,
            reasoning_effort=settings.reasoning_effort,
        )
        self._verbose = verbose
        self._mode = mode
        self._prompt = prompt
        self._audit_report_dir = audit_report_dir
        self._single_turn_hint = single_turn_hint
        self._resume_session_id = resume_session_id
        self._bridge: Display | None = None
        self.exit_code: int = 0
        self.fatal_error_message: str | None = None

    def compose(self) -> ComposeResult:
        yield SessionHeader(context_label=self._initial_context_label)
        yield Horizontal(
            SessionSidebar(id="session-sidebar"),
            Vertical(
                VerticalScroll(id="chat-log"),
                Vertical(id="status-row"),
                id="chat-main",
            ),
            id="chat-body",
        )
        yield ChatInput(
            workspace_root=str(Path.cwd().resolve()),
            placeholder=(
                "Type your message\u2026  "
                "(Enter: send, Ctrl/Alt/Shift+Enter: newline, Ctrl+Q: quit)"
            ),
            id="user-input",
            disabled=True,
        )
        yield Footer()

    def on_mount(self) -> None:
        self._bridge = Display(
            app=self,
            verbose=self._verbose,
            model=self._settings.model,
            reasoning_effort=self._settings.reasoning_effort,
        )
        self._run_session()

    def _chat_log(self) -> VerticalScroll:
        return self.query_one("#chat-log", VerticalScroll)

    def _status_row(self) -> Vertical:
        return self.query_one("#status-row", Vertical)

    def _chat_input(self) -> ChatInput:
        return self.query_one("#user-input", ChatInput)

    def _scroll_chat_end(self) -> None:
        self._chat_log().scroll_end(animate=False)

    def _query_optional(self, selector: str, widget_type: Any = Widget) -> Any | None:
        try:
            return self.query_one(selector, widget_type)
        except Exception:
            return None

    def _set_input_enabled(self, enabled: bool) -> None:
        inp = self._chat_input()
        inp.disabled = not enabled
        if enabled:
            inp.focus_input()

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
            return run_chat_loop(
                self._settings,
                display,
                resume_session_id=self._resume_session_id,
            )
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

    async def mount_widget_in_container(
        self, container_id: str, widget: Widget
    ) -> None:
        container = self._query_optional(f"#{container_id}", Widget)
        if container is None:
            return
        await container.mount(widget)
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

    def update_session_header(
        self,
        sub_title: str,
        *,
        context_label: str | None = None,
        tooltip: str | None = None,
    ) -> None:
        if context_label:
            context_suffix = f" \u00b7 {context_label}"
            if sub_title.endswith(context_suffix):
                sub_title = sub_title[: -len(context_suffix)]
        self.sub_title = sub_title
        self.header_context_label = context_label
        self.header_context_tooltip = tooltip
        context_widget = self._query_optional(
            "#session-header-context",
            SessionHeaderContext,
        )
        if context_widget is not None:
            context_widget.set_context(context_label, tooltip=tooltip)

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

    async def mount_sub_agent_block(
        self,
        block_id: str,
        title: str,
        *,
        body_id: str,
    ) -> None:
        block = SubAgentBlock(
            Vertical(id=body_id),
            title=title,
            collapsed=True,
            id=block_id,
            classes="tool-group-sub-agent",
        )
        await self._chat_log().mount(block)
        self._scroll_chat_end()

    def update_sub_agent_title(self, block_id: str, title: str) -> None:
        block = self._query_optional(f"#{block_id}", SubAgentBlock)
        if block is None:
            return
        block.title = title
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

    async def _submit_user_message(self, raw_text: str) -> None:
        value = raw_text.strip()
        if not value:
            return
        inp = self._chat_input()
        inp.clear()
        inp.reset_height()
        if await self._handle_local_command(value):
            inp.focus_input()
            return

        self.disable_input()
        self.add_user_message(value)
        submitted_value = value
        image_paths: list[str] = []
        if not value.startswith("/"):
            submitted_value, image_paths, warnings = expand_input_mentions(
                value,
                root=Path.cwd().resolve(),
            )
            if image_paths and not provider_supports_images(self._settings.provider):
                warnings.append(
                    "Image mentions are not supported by the current provider."
                )
                image_paths = []
            for warning in warnings:
                self.notify(warning, severity="warning", timeout=4)
        if self._bridge is not None:
            self._bridge.submit_input(submitted_value, image_paths=image_paths or None)

    @on(ChatInput.Submitted, "#user-input")
    async def handle_input_submitted(self, event: ChatInput.Submitted) -> None:
        await self._submit_user_message(event.value)

    async def _handle_local_command(self, value: str) -> bool:
        command = normalize_command_name(value)
        if command not in LOCAL_COMMANDS:
            return False

        if command == "/help":
            self.add_user_message(value)
            await self.mount_widget(AssistantMarkdown(self._help_markdown()))
            return True

        if command == "/clear":
            self.disable_input()
            if self._bridge is not None:
                self._bridge.request_new_chat()
            return True

        if command == "/quit":
            await self.action_quit()
            return True

        return False

    @staticmethod
    def _help_markdown() -> str:
        return (
            "### Commands\n"
            "- `/help` Show this help\n"
            "- `/clear` Clear chat and start a new session\n"
            "- `/skills` Show discovered project skills\n"
            "- `/quit` Quit the app\n\n"
            "### Shortcuts\n"
            "- `Enter` send message\n"
            "- `Ctrl+Enter`, `Alt+Enter`, `Shift+Enter` insert newline\n"
            "- `Ctrl+S` send message\n"
            "- `Ctrl+R` start a new chat\n"
            "- `Ctrl+B` toggle sessions sidebar\n"
            "- `Ctrl+Q` quit\n\n"
            "### Input Features\n"
            "- Type `@` to autocomplete workspace files; text files are inlined and supported image files are attached\n"
            "- Type `/` to autocomplete local slash commands"
        )

    async def action_new_chat(self) -> None:
        if self._bridge is not None:
            self._bridge.request_new_chat()

    async def action_toggle_sidebar(self) -> None:
        sidebar = self.query_one("#session-sidebar", SessionSidebar)
        if sidebar.has_class("visible"):
            sidebar.remove_class("visible")
        else:
            sidebar.add_class("visible")
            self._populate_sidebar(sidebar)

    def _populate_sidebar(self, sidebar: SessionSidebar) -> None:
        try:
            from pbi_agent.session_store import SessionStore

            with SessionStore() as store:
                sessions = store.list_sessions(
                    os.getcwd(),
                    limit=30,
                    provider=self._settings.provider,
                )
            items = []
            for s in sessions:
                title = s.title or "(untitled)"
                if len(title) > 24:
                    title = title[:21] + "..."
                updated = s.updated_at[:10]
                items.append(
                    (s.session_id, f"{title}\n[dim]{s.provider} · {updated}[/dim]")
                )
            sidebar.refresh_sessions(items)
        except Exception:
            _log.debug("Failed to populate session sidebar", exc_info=True)

    @on(SessionListItem.Clicked)
    def handle_session_clicked(self, event: SessionListItem.Clicked) -> None:
        if self._bridge is not None:
            self._bridge.request_resume_session(event.session_id)

    async def action_quit(self) -> None:
        if self._bridge is not None:
            self._bridge.request_shutdown()
        self.exit()


__all__ = ["ChatApp"]
