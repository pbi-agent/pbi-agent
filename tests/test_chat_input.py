"""Tests for the ChatInput widget keyboard shortcuts and autocomplete."""

from __future__ import annotations

from pathlib import Path

import pytest
from textual.app import App, ComposeResult

from pbi_agent.ui.widgets import ChatInput


class ChatInputApp(App[None]):
    """Minimal app that hosts a ChatInput for testing."""

    submitted_values: list[str]

    def __init__(
        self,
        *,
        workspace_root: Path | None = None,
        slash_commands: list[tuple[str, str, str]] | None = None,
    ) -> None:
        super().__init__()
        self.submitted_values = []
        self.workspace_root = workspace_root
        self.slash_commands = slash_commands

    def compose(self) -> ComposeResult:
        yield ChatInput(
            id="ci",
            workspace_root=str(self.workspace_root) if self.workspace_root else None,
            slash_commands=self.slash_commands,
        )

    def on_chat_input_submitted(self, event: ChatInput.Submitted) -> None:
        self.submitted_values.append(event.value)


@pytest.mark.asyncio
async def test_ctrl_s_submits() -> None:
    app = ChatInputApp()
    async with app.run_test() as pilot:
        ci = app.query_one("#ci", ChatInput)
        ci.insert("hello from ctrl+s")
        await pilot.press("ctrl+s")
        assert app.submitted_values == ["hello from ctrl+s"]


@pytest.mark.asyncio
async def test_plain_enter_submits() -> None:
    app = ChatInputApp()
    async with app.run_test() as pilot:
        ci = app.query_one("#ci", ChatInput)
        ci.insert("send on enter")
        await pilot.press("enter")
        assert app.submitted_values == ["send on enter"]


@pytest.mark.asyncio
@pytest.mark.parametrize("key", ["ctrl+enter", "alt+enter", "shift+enter"])
async def test_modified_enter_inserts_newline_without_submit(key: str) -> None:
    app = ChatInputApp()
    async with app.run_test() as pilot:
        ci = app.query_one("#ci", ChatInput)
        ci.insert("line one")
        await pilot.press(key)
        assert app.submitted_values == []
        assert ci.text == "line one\n"


@pytest.mark.asyncio
async def test_slash_command_enter_accepts_completion_and_submits() -> None:
    app = ChatInputApp()
    async with app.run_test() as pilot:
        ci = app.query_one("#ci", ChatInput)
        ci.insert("/he")
        await pilot.pause()

        assert ci._current_suggestions
        assert ci._current_suggestions[0][0] == "/help"

        await pilot.press("enter")
        await pilot.pause()

        assert app.submitted_values == ["/help"]


@pytest.mark.asyncio
async def test_multi_word_slash_command_submits_without_overwriting_args() -> None:
    app = ChatInputApp(
        slash_commands=[
            ("/deploy", "Deploy the current artifact", "release ship"),
        ]
    )
    async with app.run_test() as pilot:
        ci = app.query_one("#ci", ChatInput)
        ci.insert("/deploy run foo")
        await pilot.pause()

        assert ci._current_suggestions == []

        await pilot.press("enter")
        await pilot.pause()

        assert app.submitted_values == ["/deploy run foo"]


@pytest.mark.asyncio
async def test_file_mention_tab_completes_without_submit(tmp_path: Path) -> None:
    (tmp_path / "main.py").write_text("print('hello')\n", encoding="utf-8")
    (tmp_path / "notes.md").write_text("# Notes\n", encoding="utf-8")

    app = ChatInputApp(workspace_root=tmp_path)
    async with app.run_test() as pilot:
        ci = app.query_one("#ci", ChatInput)
        ci.insert("@ma")
        await pilot.pause()

        assert any(label == "@main.py" for label, _ in ci._current_suggestions)

        await pilot.press("tab")
        await pilot.pause()

        assert ci.text == "@main.py "
        assert app.submitted_values == []


@pytest.mark.asyncio
async def test_file_mention_tab_escapes_spaces(tmp_path: Path) -> None:
    (tmp_path / "my notes.txt").write_text("hello\n", encoding="utf-8")

    app = ChatInputApp(workspace_root=tmp_path)
    async with app.run_test() as pilot:
        ci = app.query_one("#ci", ChatInput)
        ci.insert("@my")
        await pilot.pause()

        assert any(label == r"@my\ notes.txt" for label, _ in ci._current_suggestions)

        await pilot.press("tab")
        await pilot.pause()

        assert ci.text == r"@my\ notes.txt "


@pytest.mark.asyncio
async def test_file_completion_cache_refreshes_when_input_reenabled(
    tmp_path: Path,
) -> None:
    (tmp_path / "main.py").write_text("print('hello')\n", encoding="utf-8")

    app = ChatInputApp(workspace_root=tmp_path)
    async with app.run_test() as pilot:
        ci = app.query_one("#ci", ChatInput)
        ci.insert("@ma")
        await pilot.pause()

        assert any(label == "@main.py" for label, _ in ci._current_suggestions)

        (tmp_path / "later.py").write_text("print('later')\n", encoding="utf-8")
        ci.disabled = True
        await pilot.pause()
        ci.disabled = False
        await pilot.pause()

        ci.clear()
        ci.insert("@la")
        await pilot.pause()

        assert any(label == "@later.py" for label, _ in ci._current_suggestions)
