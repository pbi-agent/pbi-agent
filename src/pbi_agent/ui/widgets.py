"""Custom Textual widgets used by the PBI Agent UI."""

from __future__ import annotations

import contextlib
import time
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any, ClassVar

from textual import events
from textual.binding import Binding
from textual.containers import Vertical, VerticalScroll
from textual.content import Content
from textual.message import Message
from textual.widgets import Header
from textual.widgets import (
    Collapsible,
    LoadingIndicator,
    Markdown as MarkdownWidget,
    Static,
    TextArea,
)
from textual.widgets._header import (
    HeaderClock,
    HeaderClockSpace,
    HeaderIcon,
    HeaderTitle,
)

from pbi_agent.branding import rich_brand_block
from pbi_agent.ui.autocomplete import (
    CompletionResult,
    FuzzyFileController,
    MultiCompletionManager,
    SlashCommandController,
)
from pbi_agent.ui.command_registry import SLASH_COMMANDS

if TYPE_CHECKING:
    from textual.app import ComposeResult
    from textual.events import Click


def _strip_banner_markup(text: str) -> str:
    cleaned = text
    for tag in ("[dim]", "[/dim]", "[bold]", "[/bold]"):
        cleaned = cleaned.replace(tag, "")
    return cleaned


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
        lines = [*rich_brand_block().splitlines(), ""]

        if interactive:
            lines.append(
                "[dim]Interactive mode:[/dim] Type [bold]exit[/bold] or "
                "[bold]quit[/bold] to stop."
            )
            lines.append(
                "[dim]Enter[/dim] to send  "
                "\u00b7  "
                "[dim]Ctrl/Alt/Shift+Enter[/dim] for newline"
            )
        elif single_turn_hint:
            lines.append(_strip_banner_markup(single_turn_hint))
        else:
            lines.append("Single prompt mode: Running one request.")

        if model or reasoning_effort:
            parts: list[str] = []
            if model:
                parts.append(f"Model: [bold]{model}[/bold]")
            if reasoning_effort:
                parts.append(f"Reasoning: [bold]{reasoning_effort}[/bold]")
            lines.append("[dim]\u00b7[/dim]  ".join(parts))

        super().__init__("\n".join(lines))


class SessionHeaderContext(Static):
    """Header badge for the context utilization tooltip target."""

    _cached_label: str | None = None
    _cached_tooltip: str | None = None

    DEFAULT_CSS = """
    SessionHeaderContext {
        dock: right;
        width: auto;
        padding: 0 1;
        color: $text-muted;
        display: none;
    }

    SessionHeaderContext.-active {
        display: block;
    }
    """

    def set_context(self, label: str | None, *, tooltip: str | None = None) -> None:
        if label == self._cached_label and tooltip == self._cached_tooltip:
            return
        self._cached_label = label
        self._cached_tooltip = tooltip
        has_context = bool(label)
        self.update(label or "")
        self.tooltip = tooltip if has_context else None
        self.set_class(has_context, "-active")


class SessionHeader(Header):
    """Header with a dedicated context hover target."""

    DEFAULT_CSS = """
    SessionHeader > HeaderTitle {
        width: 1fr;
        min-width: 0;
    }
    """

    def __init__(
        self,
        *,
        context_label: str | None = None,
        context_tooltip: str | None = None,
    ) -> None:
        super().__init__()
        self._initial_context_label = context_label
        self._initial_context_tooltip = context_tooltip

    def compose(self):
        yield HeaderIcon().data_bind(Header.icon)
        yield HeaderTitle()
        yield (
            HeaderClock().data_bind(Header.time_format)
            if self._show_clock
            else HeaderClockSpace()
        )
        context = SessionHeaderContext(id="session-header-context")
        context.set_context(
            self._initial_context_label,
            tooltip=self._initial_context_tooltip,
        )
        yield context


class UserMessage(Static):
    """User message bubble."""


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


class SubAgentBlock(Collapsible):
    """Collapsible container for nested sub-agent output."""


@dataclass(slots=True)
class ToolGroupEntry:
    """Renderable entry inside a tool group."""

    text: str
    classes: str = ""


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


class SessionListItem(Static):
    """A single session entry in the sidebar."""

    @dataclass
    class Clicked(Message):
        """Emitted when a session item is clicked."""

        session_id: str

    def __init__(self, session_id: str, text: str, **kwargs: Any) -> None:
        super().__init__(text, **kwargs)
        self._session_id = session_id

    def on_click(self) -> None:
        self.post_message(self.Clicked(session_id=self._session_id))


class SessionSidebar(Vertical):
    """Collapsible sidebar listing past sessions."""

    def refresh_sessions(self, items: list[tuple[str, str]]) -> None:
        """Replace sidebar content with new session items."""

        self.remove_children()
        for sid, text in items:
            self.mount(SessionListItem(sid, text, classes="session-list-item"))


class CompletionOption(Static):
    """A clickable completion option in the autocomplete popup."""

    DEFAULT_CSS = """
    CompletionOption {
        height: 1;
        padding: 0 1;
    }

    CompletionOption:hover {
        background: $surface-lighten-1;
    }

    CompletionOption.completion-option-selected {
        background: $primary;
        color: $background;
        text-style: bold;
    }
    """

    class Clicked(Message):
        """Message sent when a completion option is clicked."""

        def __init__(self, index: int) -> None:
            super().__init__()
            self.index = index

    def __init__(
        self,
        label: str,
        description: str,
        index: int,
        *,
        is_selected: bool = False,
        **kwargs: Any,
    ) -> None:
        super().__init__(**kwargs)
        self._label = label
        self._description = description
        self._index = index
        self._is_selected = is_selected

    def on_mount(self) -> None:
        self._update_display()

    def _update_display(self) -> None:
        cursor = "› " if self._is_selected else "  "
        if self._description:
            content = Content.from_markup(
                f"{cursor}[bold]$label[/bold]  [dim]$desc[/dim]",
                label=self._label,
                desc=self._description,
            )
        else:
            content = Content.from_markup(
                f"{cursor}[bold]$label[/bold]",
                label=self._label,
            )
        self.update(content)
        self.set_class(self._is_selected, "completion-option-selected")

    def set_selected(self, *, selected: bool) -> None:
        if self._is_selected == selected:
            return
        self._is_selected = selected
        self._update_display()

    def set_content(
        self, label: str, description: str, index: int, *, is_selected: bool
    ) -> None:
        self._label = label
        self._description = description
        self._index = index
        self._is_selected = is_selected
        self._update_display()

    def on_click(self, event: Click) -> None:
        event.stop()
        self.post_message(self.Clicked(self._index))


class CompletionPopup(VerticalScroll):
    """Popup widget that displays completion suggestions."""

    DEFAULT_CSS = """
    CompletionPopup {
        display: none;
        height: auto;
        max-height: 8;
        border: round $primary;
        background: $surface;
        margin: 0 0 1 0;
    }
    """

    class OptionClicked(Message):
        """Message sent when a completion option is clicked."""

        def __init__(self, index: int) -> None:
            super().__init__()
            self.index = index

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.can_focus = False
        self._options: list[CompletionOption] = []
        self._selected_index = 0

    def update_suggestions(
        self, suggestions: list[tuple[str, str]], selected_index: int
    ) -> None:
        self._selected_index = selected_index
        self.run_worker(
            self._rebuild_options(suggestions, selected_index),
            exclusive=True,
            exit_on_error=False,
        )

    async def _rebuild_options(
        self, suggestions: list[tuple[str, str]], selected_index: int
    ) -> None:
        if not suggestions:
            self.hide()
            return

        existing = len(self._options)
        needed = len(suggestions)
        for index in range(min(existing, needed)):
            label, desc = suggestions[index]
            self._options[index].set_content(
                label,
                desc,
                index,
                is_selected=index == selected_index,
            )

        try:
            if existing > needed:
                for option in self._options[needed:]:
                    await option.remove()
                del self._options[needed:]

            if needed > existing:
                new_widgets: list[CompletionOption] = []
                for index in range(existing, needed):
                    label, desc = suggestions[index]
                    new_widgets.append(
                        CompletionOption(
                            label,
                            desc,
                            index,
                            is_selected=index == selected_index,
                        )
                    )
                self._options.extend(new_widgets)
                await self.mount(*new_widgets)
        except Exception:
            with contextlib.suppress(Exception):
                await self.remove_children()
            self._options = []
            self.hide()
            return

        self.show()
        if 0 <= selected_index < len(self._options):
            self._options[selected_index].scroll_visible()

    def update_selection(self, selected_index: int) -> None:
        if self._selected_index == selected_index:
            return
        if 0 <= self._selected_index < len(self._options):
            self._options[self._selected_index].set_selected(selected=False)
        self._selected_index = selected_index
        if 0 <= selected_index < len(self._options):
            self._options[selected_index].set_selected(selected=True)
            self._options[selected_index].scroll_visible()

    def on_completion_option_clicked(self, event: CompletionOption.Clicked) -> None:
        event.stop()
        self.post_message(self.OptionClicked(event.index))

    def hide(self) -> None:
        self.styles.display = "none"  # type: ignore[assignment]

    def show(self) -> None:
        self.styles.display = "block"


class ChatTextArea(TextArea):
    """Inner text area with chat-specific shortcut behavior."""

    BINDINGS: ClassVar[list[Binding]] = [
        Binding(
            "shift+enter,alt+enter,ctrl+enter",
            "insert_newline",
            "New Line",
            show=False,
            priority=True,
        )
    ]

    _NEWLINE_KEYS: ClassVar[frozenset[str]] = frozenset(
        key
        for binding in BINDINGS
        for key in binding.key.split(",")
        if binding.action == "insert_newline"
    )
    _SUBMIT_KEYS: ClassVar[frozenset[str]] = frozenset({"ctrl+s"})
    _BACKSLASH_ENTER_GAP_SECONDS = 0.15

    class Submitted(Message):
        """Message sent when the input is submitted."""

        def __init__(self, value: str) -> None:
            self.value = value
            super().__init__()

    def __init__(self, **kwargs: Any) -> None:
        kwargs.pop("placeholder", None)
        super().__init__(**kwargs)
        self._completion_active = False
        self._backslash_pending_time: float | None = None

    def set_completion_active(self, *, active: bool) -> None:
        self._completion_active = active

    def action_insert_newline(self) -> None:
        self.insert("\n")

    def _delete_preceding_backslash(self) -> bool:
        row, col = self.cursor_location
        if col > 0:
            start = (row, col - 1)
            if self.document.get_text_range(start, self.cursor_location) == "\\":
                self.delete(start, self.cursor_location)
                return True
        elif row > 0:
            prev_line = self.document.get_line(row - 1)
            start = (row - 1, len(prev_line) - 1)
            end = (row - 1, len(prev_line))
            if self.document.get_text_range(start, end) == "\\":
                self.delete(start, self.cursor_location)
                return True
        return False

    async def _on_key(self, event: events.Key) -> None:
        self._restart_blink()
        if self.read_only:
            return

        now = time.monotonic()
        if (
            event.key == "enter"
            and not self._completion_active
            and self._backslash_pending_time is not None
            and (now - self._backslash_pending_time)
            <= self._BACKSLASH_ENTER_GAP_SECONDS
        ):
            self._backslash_pending_time = None
            if self._delete_preceding_backslash():
                event.prevent_default()
                event.stop()
                self.insert("\n")
                return

        self._backslash_pending_time = None
        if event.key == "backslash" and event.character == "\\":
            self._backslash_pending_time = now

        if event.key in self._NEWLINE_KEYS:
            event.prevent_default()
            event.stop()
            self.insert("\n")
            return

        if self._completion_active and (
            event.key in {"up", "down", "tab", "escape"} or event.key == "enter"
        ):
            event.prevent_default()
            return

        if event.key in self._SUBMIT_KEYS or self._SUBMIT_KEYS & set(event.aliases):
            event.prevent_default()
            event.stop()
            value = self.text.strip()
            if value:
                self.post_message(self.Submitted(value))
            return

        if event.key == "enter":
            event.prevent_default()
            event.stop()
            value = self.text.strip()
            if value:
                self.post_message(self.Submitted(value))
            return

        await super()._on_key(event)


class ChatInput(Vertical):
    """Composite multiline input with autocomplete and chat shortcuts."""

    BASE_HEIGHT = 1
    MAX_HEIGHT = 20
    _CHROME_HEIGHT = 0

    DEFAULT_CSS = """
    ChatInput {
        height: auto;
        min-height: 3;
        max-height: 20;
        border: round $primary;
        background: $surface;
    }

    ChatInput > ChatTextArea {
        width: 1fr;
        min-height: 1;
        border: none;
        background: transparent;
        padding: 0 1;
    }

    ChatInput > ChatTextArea:focus {
        border: none;
    }
    """

    @dataclass
    class Submitted(Message):
        """Message emitted when the user submits the chat input."""

        input: "ChatInput"
        value: str

        @property
        def control(self) -> "ChatInput":
            return self.input

    def __init__(
        self,
        *,
        workspace_root: str | None = None,
        slash_commands: list[tuple[str, str, str]] | None = None,
        placeholder: str | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(**kwargs)
        self._workspace_root = workspace_root
        self._placeholder = placeholder
        self._slash_commands = slash_commands or list(SLASH_COMMANDS)
        self._text_area: ChatTextArea | None = None
        self._popup: CompletionPopup | None = None
        self._completion_manager: MultiCompletionManager | None = None
        self._current_suggestions: list[tuple[str, str]] = []
        self._current_selected_index = 0
        self._file_controller: FuzzyFileController | None = None
        self._slash_controller: SlashCommandController | None = None

    def compose(self) -> ComposeResult:
        yield ChatTextArea(
            placeholder=self._placeholder,
            id="chat-input-editor",
        )
        yield CompletionPopup(id="chat-input-popup")

    def on_mount(self) -> None:
        self._text_area = self.query_one("#chat-input-editor", ChatTextArea)
        self._popup = self.query_one("#chat-input-popup", CompletionPopup)
        root = self._workspace_root
        self._file_controller = FuzzyFileController(
            self,
            root=Path(root).resolve() if root else None,
        )
        self._slash_controller = SlashCommandController(self._slash_commands, self)
        self._completion_manager = MultiCompletionManager(
            [self._slash_controller, self._file_controller]
        )
        self.run_worker(
            self._file_controller.warm_cache(),
            exclusive=False,
            exit_on_error=False,
        )
        self.watch_disabled(self.disabled)
        self.reset_height()
        self.focus_input()

    def reset_height(self) -> None:
        if self._text_area is not None:
            self._text_area.styles.height = self.BASE_HEIGHT

    def _resize_to_content(self) -> None:
        if self._text_area is None:
            return
        content_height = max(self._text_area.wrapped_document.height, 1)
        target_height = max(
            self.BASE_HEIGHT,
            min(self.MAX_HEIGHT, content_height + self._CHROME_HEIGHT),
        )
        self._text_area.styles.height = target_height

    def on_text_area_changed(self, _: TextArea.Changed) -> None:
        self._resize_to_content()
        if self._completion_manager is None or self._text_area is None:
            return
        self._completion_manager.on_text_changed(
            self._text_area.text,
            self._get_cursor_offset(),
        )

    def on_chat_text_area_submitted(self, event: ChatTextArea.Submitted) -> None:
        self._submit_value(event.value)

    async def on_key(self, event: events.Key) -> None:
        if self._completion_manager is None or self._text_area is None:
            return
        result = self._completion_manager.on_key(
            event,
            self._text_area.text,
            self._get_cursor_offset(),
        )
        match result:
            case CompletionResult.HANDLED:
                event.prevent_default()
                event.stop()
            case CompletionResult.SUBMIT:
                event.prevent_default()
                event.stop()
                self._submit_value(self._text_area.text.strip())

    def _submit_value(self, value: str) -> None:
        submitted = value.strip()
        if not submitted:
            return
        if self._completion_manager is not None:
            self._completion_manager.reset()
        self.post_message(self.Submitted(self, submitted))
        self.clear()
        self.reset_height()

    def _get_cursor_offset(self) -> int:
        if self._text_area is None:
            return 0
        text = self._text_area.text
        if not text:
            return 0
        row, col = self._text_area.cursor_location
        lines = text.split("\n")
        row = max(0, min(row, len(lines) - 1))
        col = max(0, min(col, len(lines[row])))
        return sum(len(lines[index]) + 1 for index in range(row)) + col

    def render_completion_suggestions(
        self, suggestions: list[tuple[str, str]], selected_index: int
    ) -> None:
        previous = self._current_suggestions
        self._current_suggestions = suggestions
        self._current_selected_index = selected_index
        if self._popup is None:
            return
        if suggestions == previous:
            self._popup.update_selection(selected_index)
        else:
            self._popup.update_suggestions(suggestions, selected_index)
        if self._text_area is not None:
            self._text_area.set_completion_active(active=bool(suggestions))

    def clear_completion_suggestions(self) -> None:
        self._current_suggestions = []
        self._current_selected_index = 0
        if self._popup is not None:
            self._popup.hide()
        if self._text_area is not None:
            self._text_area.set_completion_active(active=False)

    def on_completion_popup_option_clicked(
        self, event: CompletionPopup.OptionClicked
    ) -> None:
        if not self._current_suggestions or self._text_area is None:
            return
        index = event.index
        if index < 0 or index >= len(self._current_suggestions):
            return
        label, _ = self._current_suggestions[index]
        cursor = self._get_cursor_offset()
        if label.startswith("/"):
            self.replace_completion_range(0, cursor, label)
        elif label.startswith("@"):
            at_index = self._text_area.text[:cursor].rfind("@")
            if at_index >= 0:
                self.replace_completion_range(at_index, cursor, label)
        if self._completion_manager is not None:
            self._completion_manager.reset()
        self.focus_input()

    def replace_completion_range(self, start: int, end: int, replacement: str) -> None:
        if self._text_area is None:
            return
        text = self._text_area.text
        start = max(0, min(start, len(text)))
        end = max(start, min(end, len(text)))
        prefix = text[:start]
        suffix = text[end:]
        insertion = replacement if suffix.startswith(" ") else replacement + " "
        new_text = f"{prefix}{insertion}{suffix}"
        self._text_area.text = new_text

        new_offset = start + len(insertion)
        lines = new_text.split("\n")
        remaining = new_offset
        for row, line in enumerate(lines):
            if remaining <= len(line):
                self._text_area.move_cursor((row, remaining))
                break
            remaining -= len(line) + 1

    def focus_input(self) -> None:
        if self._text_area is not None:
            self._text_area.focus()

    def watch_disabled(self, disabled: bool) -> None:
        if self._text_area is not None:
            self._text_area.disabled = disabled
            if not disabled and self._file_controller is not None:
                self._file_controller.refresh_cache()
            if disabled and self._completion_manager is not None:
                self._completion_manager.reset()

    def update_slash_commands(self, commands: list[tuple[str, str, str]]) -> None:
        self._slash_commands = commands
        if self._slash_controller is not None:
            self._slash_controller.update_commands(commands)

    @property
    def text(self) -> str:
        if self._text_area is None:
            return ""
        return self._text_area.text

    @text.setter
    def text(self, value: str) -> None:
        if self._text_area is not None:
            self._text_area.text = value

    @property
    def input_widget(self) -> ChatTextArea | None:
        return self._text_area

    def insert(self, text: str) -> None:
        if self._text_area is not None:
            self._text_area.insert(text)

    def clear(self) -> None:
        if self._text_area is None:
            return
        self._text_area.text = ""
        self._text_area.move_cursor((0, 0))
        self.clear_completion_suggestions()


__all__ = [
    "AssistantMarkdown",
    "ChatInput",
    "ChatTextArea",
    "CompletionOption",
    "CompletionPopup",
    "ErrorMessage",
    "NoticeMessage",
    "SessionHeader",
    "SessionHeaderContext",
    "SessionListItem",
    "SessionSidebar",
    "SubAgentBlock",
    "ThinkingBlock",
    "ThinkingContent",
    "ToolGroup",
    "ToolGroupEntry",
    "ToolItem",
    "UsageSummary",
    "UserMessage",
    "WaitingIndicator",
    "WelcomeBanner",
]
