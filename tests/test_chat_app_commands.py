from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from pbi_agent.config import Settings
from pbi_agent.ui.app import ChatApp
from pbi_agent.ui.widgets import AssistantMarkdown


@pytest.mark.asyncio
async def test_help_command_is_handled_locally(monkeypatch) -> None:
    monkeypatch.setattr(ChatApp, "_run_session", lambda self: None)
    app = ChatApp(settings=Settings(api_key="test-key", model="gpt-5.4-2026-03-05"))

    async with app.run_test() as pilot:
        bridge = MagicMock()
        app._bridge = bridge

        await app._submit_user_message("/help")
        await pilot.pause()

        widgets = list(app.query(AssistantMarkdown))
        assert widgets
        bridge.submit_input.assert_not_called()


@pytest.mark.asyncio
async def test_clear_command_requests_new_chat(monkeypatch) -> None:
    monkeypatch.setattr(ChatApp, "_run_session", lambda self: None)
    app = ChatApp(settings=Settings(api_key="test-key", model="gpt-5.4-2026-03-05"))

    async with app.run_test() as pilot:
        bridge = MagicMock()
        app._bridge = bridge

        await app._submit_user_message("/clear")
        await pilot.pause()

        bridge.request_new_chat.assert_called_once_with()


@pytest.mark.asyncio
async def test_skills_command_is_forwarded_to_session(monkeypatch) -> None:
    monkeypatch.setattr(ChatApp, "_run_session", lambda self: None)
    app = ChatApp(settings=Settings(api_key="test-key", model="gpt-5.4-2026-03-05"))

    async with app.run_test() as pilot:
        bridge = MagicMock()
        app._bridge = bridge

        await app._submit_user_message("/skills")
        await pilot.pause()

        bridge.submit_input.assert_called_once_with("/skills", image_paths=None)


@pytest.mark.asyncio
async def test_submit_expands_file_mentions_before_bridge_submit(
    monkeypatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(ChatApp, "_run_session", lambda self: None)
    app = ChatApp(settings=Settings(api_key="test-key", model="gpt-5.4-2026-03-05"))
    target = tmp_path / "notes.txt"
    target.write_text("hello from file\n", encoding="utf-8")

    async with app.run_test() as pilot:
        bridge = MagicMock()
        app._bridge = bridge

        monkeypatch.setattr("pbi_agent.ui.app.Path.cwd", lambda: tmp_path)
        await app._submit_user_message("Check @notes.txt")
        await pilot.pause()

        bridge.submit_input.assert_called_once()
        submitted = bridge.submit_input.call_args.args[0]
        assert "@notes.txt" not in submitted
        assert submitted.startswith("Check")
        assert "## Referenced Files" in submitted
        assert "hello from file" in submitted


@pytest.mark.asyncio
async def test_submit_auto_stages_image_mentions_before_bridge_submit(
    monkeypatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(ChatApp, "_run_session", lambda self: None)
    app = ChatApp(settings=Settings(api_key="test-key", model="gpt-5.4-2026-03-05"))
    target = tmp_path / "chart.png"
    target.write_bytes(b"fake-png")

    async with app.run_test() as pilot:
        bridge = MagicMock()
        app._bridge = bridge

        monkeypatch.setattr("pbi_agent.ui.app.Path.cwd", lambda: tmp_path)
        await app._submit_user_message("Check @chart.png extract text")
        await pilot.pause()

        bridge.submit_input.assert_called_once_with(
            "Check extract text",
            image_paths=["chart.png"],
        )
