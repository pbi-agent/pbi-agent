"""Custom Textual widgets used by the PBI Agent UI."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from textual import events
from textual.containers import Vertical
from textual.message import Message
from textual.widgets import Header
from textual.widgets._header import (
    HeaderClock,
    HeaderClockSpace,
    HeaderIcon,
    HeaderTitle,
)
from textual.widgets import (
    Collapsible,
    LoadingIndicator,
    Markdown as MarkdownWidget,
    Static,
    TextArea,
)


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
        logo_rows = [
            "              \u2588\u2588\u2588\u2588",
            "              \u2588\u2588\u2588\u2588",
            "        \u2588\u2588\u2588\u2588  \u2588\u2588\u2588\u2588",
            "        \u2588\u2588\u2588\u2588  \u2588\u2588\u2588\u2588",
            "  \u2588\u2588\u2588\u2588  \u2588\u2588\u2588\u2588  \u2588\u2588\u2588\u2588",
            "  \u2588\u2588\u2588\u2588  \u2588\u2588\u2588\u2588  \u2588\u2588\u2588\u2588",
        ]
        lines = [f"[bold #F2C811]{row}[/bold #F2C811]" for row in logo_rows]
        lines.extend(
            [
                "",
                "[bold #F2C811]PBI AGENT[/bold #F2C811]",
                "[bold]Transform data into decisions.[/bold]",
                "",
            ]
        )

        if interactive:
            lines.append(
                "[dim]Interactive mode:[/dim] Type [bold]exit[/bold] or "
                "[bold]quit[/bold] to stop."
            )
            lines.append(
                "[dim]Enter[/dim] for newline  \u00b7  [dim]Ctrl+S[/dim] to submit"
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
        """Replace sidebar content with new session items.

        *items* is a list of ``(session_id, display_text)`` tuples.
        """
        self.remove_children()
        for sid, text in items:
            self.mount(SessionListItem(sid, text, classes="session-list-item"))


class ChatInput(TextArea):
    """Multiline input that auto-grows and submits on Ctrl+S."""

    BASE_HEIGHT = 3
    MAX_HEIGHT = 20
    _CHROME_HEIGHT = 2
    _SUBMIT_KEYS = {"ctrl+s"}

    @dataclass
    class Submitted(Message):
        """Message emitted when the user submits the chat input."""

        input: "ChatInput"
        value: str

        @property
        def control(self) -> "ChatInput":
            return self.input

    def on_mount(self) -> None:
        self.styles.min_height = self.BASE_HEIGHT
        self.styles.max_height = self.MAX_HEIGHT
        self.reset_height()

    def reset_height(self) -> None:
        self.styles.height = self.BASE_HEIGHT

    def _resize_to_content(self) -> None:
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
        if event.key in self._SUBMIT_KEYS or self._SUBMIT_KEYS & set(event.aliases):
            event.stop()
            event.prevent_default()
            self.post_message(self.Submitted(self, self.text))
            return
        await super()._on_key(event)


__all__ = [
    "AssistantMarkdown",
    "ChatInput",
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
