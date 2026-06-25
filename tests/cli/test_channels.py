from __future__ import annotations

import argparse
import io
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

import pbi_agent.cli.channels as channels_cli
from pbi_agent import cli
from pbi_agent.channels.telegram import TELEGRAM_PLATFORM
from pbi_agent.session_store import SessionStore


class ChannelsCommandTests(unittest.TestCase):
    def setUp(self) -> None:
        self._workspace_env_patch = patch.dict(
            os.environ,
            {
                "PBI_AGENT_WORKSPACE_KEY": "",
                "PBI_AGENT_WORKSPACE_DISPLAY_PATH": "",
                "PBI_AGENT_SANDBOX": "",
            },
            clear=False,
        )
        self._workspace_env_patch.start()
        self.addCleanup(self._workspace_env_patch.stop)

    def test_parser_exposes_channels_help(self) -> None:
        parser = cli.build_parser()
        subparsers = next(
            action
            for action in parser._actions
            if isinstance(action, argparse._SubParsersAction)
        )
        channels_parser = subparsers.choices["channels"]
        channels_subparsers = next(
            action
            for action in channels_parser._actions
            if isinstance(action, argparse._SubParsersAction)
        )
        telegram_parser = channels_subparsers.choices["telegram"]
        telegram_subparsers = next(
            action
            for action in telegram_parser._actions
            if isinstance(action, argparse._SubParsersAction)
        )

        self.assertIn(
            "usage: pbi-agent channels show",
            channels_subparsers.choices["show"].format_help(),
        )
        self.assertIn(
            "--allowed-users ALLOWED_USERS",
            telegram_subparsers.choices["configure"].format_help(),
        )
        self.assertIn(
            "--web-port WEB_PORT",
            telegram_subparsers.choices["restart"].format_help(),
        )

    def test_show_returns_json_without_provider_settings(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            original_cwd = Path.cwd()
            stdout = io.StringIO()
            try:
                os.chdir(root)
                with (
                    patch.dict(os.environ, {"PBI_AGENT_API_KEY": ""}, clear=False),
                    patch("sys.stdout", stdout),
                ):
                    rc = cli.main(["channels", "show", "--json"])
            finally:
                os.chdir(original_cwd)

            self.assertEqual(rc, 0)
            payload = json.loads(stdout.getvalue())
            self.assertIn("telegram", payload)
            self.assertFalse(payload["telegram"]["enabled"])

    def test_configure_persists_workspace_telegram_settings(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            original_cwd = Path.cwd()
            stdout = io.StringIO()
            try:
                os.chdir(root)
                with (
                    patch.dict(
                        os.environ,
                        {
                            "PBI_AGENT_API_KEY": "",
                            "PBI_AGENT_TELEGRAM_BOT_TOKEN": "123:abc",
                        },
                        clear=False,
                    ),
                    patch("sys.stdout", stdout),
                ):
                    rc = cli.main(
                        [
                            "channels",
                            "telegram",
                            "configure",
                            "--enable",
                            "--token-source",
                            "env",
                            "--allowed-users",
                            "123,456",
                            "--json",
                        ]
                    )
            finally:
                os.chdir(original_cwd)

            self.assertEqual(rc, 0)
            payload = json.loads(stdout.getvalue())
            self.assertTrue(payload["telegram"]["enabled"])
            self.assertEqual(payload["telegram"]["allowed_users"], ["123", "456"])
            with SessionStore() as store:
                record = store.get_channel_config(
                    str(root.resolve()).lower(),
                    TELEGRAM_PLATFORM,
                )
            assert record is not None
            self.assertTrue(record.config["enabled"])
            self.assertEqual(record.config["allowed_users"], ["123", "456"])

    def test_restart_uses_local_web_api_when_available(self) -> None:
        fake_payload = {
            "telegram": {
                "enabled": True,
                "token_source": "env",
                "token_env_var": "PBI_AGENT_TELEGRAM_BOT_TOKEN",
                "has_token_secret": False,
                "allowed_users": ["123"],
                "allowed_chats": [],
                "last_update_id": None,
                "status": {"state": "running", "error": None},
            }
        }
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            original_cwd = Path.cwd()
            stdout = io.StringIO()
            try:
                os.chdir(root)
                with (
                    patch.dict(os.environ, {"PBI_AGENT_API_KEY": ""}, clear=False),
                    patch(
                        "pbi_agent.cli.channels._request_web_telegram_restart",
                        return_value=fake_payload,
                    ),
                    patch("sys.stdout", stdout),
                ):
                    rc = cli.main(
                        [
                            "channels",
                            "telegram",
                            "restart",
                            "--json",
                        ]
                    )
            finally:
                os.chdir(original_cwd)

            self.assertEqual(rc, 0)
            payload = json.loads(stdout.getvalue())
            self.assertEqual(payload["telegram"]["status"]["state"], "running")

    def test_restart_fallback_validates_without_starting_runner(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            directory_key = str(root.resolve()).lower()
            with SessionStore() as store:
                store.set_channel_config(
                    directory_key,
                    TELEGRAM_PLATFORM,
                    {
                        "enabled": True,
                        "token_source": "env",
                        "token_env_var": "PBI_AGENT_TELEGRAM_BOT_TOKEN",
                        "token_secret": None,
                        "allowed_users": ["123"],
                        "allowed_chats": [],
                        "last_update_id": None,
                    },
                    status="running",
                    error=None,
                )

            original_cwd = Path.cwd()
            stdout = io.StringIO()
            try:
                os.chdir(root)
                with (
                    patch.dict(
                        os.environ,
                        {
                            "PBI_AGENT_API_KEY": "",
                            "PBI_AGENT_TELEGRAM_BOT_TOKEN": "123:abc",
                        },
                        clear=False,
                    ),
                    patch(
                        "pbi_agent.cli.channels._request_web_telegram_restart",
                        return_value=None,
                    ),
                    patch(
                        "pbi_agent.channels.manager.WorkspaceChannelManager.restart",
                        side_effect=AssertionError("runner should not start"),
                    ),
                    patch("sys.stdout", stdout),
                ):
                    rc = cli.main(
                        [
                            "channels",
                            "telegram",
                            "restart",
                            "--json",
                        ]
                    )
            finally:
                os.chdir(original_cwd)

            self.assertEqual(rc, 0)
            payload = json.loads(stdout.getvalue())
            self.assertEqual(payload["telegram"]["status"]["state"], "configured")

    def test_restart_web_helper_requires_current_workspace(self) -> None:
        calls: list[tuple[str, str, bytes | None]] = []

        def fake_request_web_json(
            url: str,
            *,
            method: str,
            data: bytes | None = None,
        ) -> dict[str, object]:
            calls.append((url, method, data))
            if url.endswith("/api/bootstrap"):
                return {"workspace_key": "/tmp/other-workspace"}
            return {
                "telegram": {
                    "enabled": True,
                    "status": {"state": "running", "error": None},
                }
            }

        with patch(
            "pbi_agent.cli.channels._request_web_json",
            side_effect=fake_request_web_json,
        ):
            payload = channels_cli._request_web_telegram_restart(
                9999,
                "/tmp/current-workspace",
            )

        self.assertIsNone(payload)
        self.assertEqual(
            calls,
            [("http://127.0.0.1:9999/api/bootstrap", "GET", None)],
        )
