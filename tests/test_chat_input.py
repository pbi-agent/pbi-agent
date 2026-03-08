"""Tests for the ChatInput widget keyboard shortcuts."""

from __future__ import annotations

import pytest
from textual.app import App, ComposeResult

from pbi_agent.ui.widgets import ChatInput


class ChatInputApp(App):
    """Minimal app that hosts a ChatInput for testing."""

    submitted_values: list[str]

    def __init__(self) -> None:
        super().__init__()
        self.submitted_values = []

    def compose(self) -> ComposeResult:
        yield ChatInput(id="ci")

    def on_chat_input_submitted(self, event: ChatInput.Submitted) -> None:
        self.submitted_values.append(event.value)


@pytest.mark.asyncio
async def test_ctrl_s_submits() -> None:
    """Ctrl+S should emit ChatInput.Submitted."""
    app = ChatInputApp()
    async with app.run_test() as pilot:
        ci = app.query_one("#ci", ChatInput)
        ci.insert("hello from ctrl+s")
        await pilot.press("ctrl+s")
        assert app.submitted_values == ["hello from ctrl+s"]


@pytest.mark.asyncio
async def test_ctrl_enter_submits() -> None:
    """Ctrl+Enter should emit ChatInput.Submitted."""
    app = ChatInputApp()
    async with app.run_test() as pilot:
        ci = app.query_one("#ci", ChatInput)
        ci.insert("hello from ctrl+enter")
        await pilot.press("ctrl+enter")
        assert app.submitted_values == ["hello from ctrl+enter"]


@pytest.mark.asyncio
async def test_plain_enter_does_not_submit() -> None:
    """Plain Enter should NOT emit ChatInput.Submitted (it inserts a newline)."""
    app = ChatInputApp()
    async with app.run_test() as pilot:
        ci = app.query_one("#ci", ChatInput)
        ci.insert("no submit")
        await pilot.press("enter")
        assert app.submitted_values == []
