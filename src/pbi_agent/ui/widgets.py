"""Custom Textual widgets used by the PBI Agent UI."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from textual import events
from textual.containers import Vertical
from textual.message import Message
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


class ChatInput(TextArea):
    """Multiline input that auto-grows and submits on Ctrl+S or Ctrl+Enter."""

    BASE_HEIGHT = 3
    MAX_HEIGHT = 20
    _CHROME_HEIGHT = 2
    _SUBMIT_KEYS = {"ctrl+s", "ctrl+enter"}

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
