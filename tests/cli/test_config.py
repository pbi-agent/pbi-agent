from __future__ import annotations

import io
import os
import sys
import tempfile
import unittest

from pathlib import Path
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from pbi_agent import cli
from pbi_agent.auth.store import build_auth_session


class DefaultWebCommandTests(unittest.TestCase):
    _OAUTH_URL = (
        "https://auth.openai.com/oauth/authorize?"
        "response_type=code&client_id=app_EMoamEEZ73f0CkXaXp7hrann"
        "&redirect_uri=http%3A%2F%2Flocalhost%3A1455%2Fauth%2Fcallback"
        "&scope=openid+profile+email+offline_access"
        "&state=abc123&originator=opencode"
    )

    def _settings(self, *, verbose: bool = False) -> Mock:
        return Mock(
            verbose=verbose,
            provider="openai",
            api_key="test-key",
            responses_url="https://api.openai.com/v1/responses",
            generic_api_url="https://openrouter.ai/api/v1/chat/completions",
            model="gpt-5",
            sub_agent_model="gpt-5-mini",
            max_tokens=16384,
            reasoning_effort="medium",
            max_tool_workers=4,
            max_retries=3,
            compact_threshold=200000,
            service_tier=None,
        )

    def test_main_config_provider_delete_fails_when_profile_references_it(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "config.json"
            stderr = io.StringIO()

            with patch.dict(
                os.environ,
                {"PBI_AGENT_INTERNAL_CONFIG_PATH": str(config_path)},
                clear=False,
            ):
                os.environ.pop("PBI_AGENT_API_KEY", None)
                os.environ.pop("XAI_API_KEY", None)
                self.assertEqual(
                    cli.main(
                        [
                            "config",
                            "providers",
                            "create",
                            "--name",
                            "OpenAI Main",
                            "--kind",
                            "openai",
                            "--api-key",
                            "saved-key",
                        ]
                    ),
                    0,
                )
                self.assertEqual(
                    cli.main(
                        [
                            "config",
                            "profiles",
                            "create",
                            "--name",
                            "Analysis",
                            "--provider-id",
                            "openai-main",
                        ]
                    ),
                    0,
                )

                with patch("sys.stderr", stderr):
                    rc = cli.main(["config", "providers", "delete", "openai-main"])

        self.assertEqual(rc, 2)
        self.assertIn("still references it", stderr.getvalue())

    def test_main_config_maintenance_show_and_set(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "config.json"
            stdout = io.StringIO()
            with (
                patch.dict(
                    os.environ,
                    {"PBI_AGENT_INTERNAL_CONFIG_PATH": str(config_path)},
                    clear=False,
                ),
                patch("pbi_agent.cli.entrypoint.run_startup_maintenance"),
                patch("sys.stdout", stdout),
            ):
                self.assertEqual(
                    cli.main(
                        [
                            "config",
                            "maintenance",
                            "set",
                            "--retention-days",
                            "14",
                        ]
                    ),
                    0,
                )
                self.assertEqual(cli.main(["config", "maintenance", "show"]), 0)

            output = stdout.getvalue()
            self.assertIn("Updated maintenance retention to 14 days.", output)
            self.assertIn("retention_days: 14", output)

    def test_main_config_maintenance_rejects_invalid_retention(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "config.json"
            stderr = io.StringIO()
            with (
                patch.dict(
                    os.environ,
                    {"PBI_AGENT_INTERNAL_CONFIG_PATH": str(config_path)},
                    clear=False,
                ),
                patch("pbi_agent.cli.entrypoint.run_startup_maintenance"),
                patch("sys.stderr", stderr),
            ):
                self.assertEqual(
                    cli.main(
                        [
                            "config",
                            "maintenance",
                            "set",
                            "--retention-days",
                            "0",
                        ]
                    ),
                    2,
                )

            self.assertIn(
                "Maintenance retention days must be at least 1", stderr.getvalue()
            )

    def test_main_config_providers_auth_login_runs_browser_flow(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "config.json"

            with patch.dict(
                os.environ,
                {"PBI_AGENT_INTERNAL_CONFIG_PATH": str(config_path)},
                clear=False,
            ):
                self.assertEqual(
                    cli.main(
                        [
                            "config",
                            "providers",
                            "create",
                            "--name",
                            "OpenAI ChatGPT",
                            "--kind",
                            "chatgpt",
                        ]
                    ),
                    0,
                )
                session = build_auth_session(
                    provider_id="openai-chatgpt",
                    backend="openai_chatgpt",
                    access_token="access-token",
                    refresh_token="refresh-token",
                    account_id="acct_browser",
                    email="browser@example.com",
                )
                with patch(
                    "pbi_agent.cli.config.run_provider_browser_auth_flow",
                    return_value=Mock(session=session),
                ) as mock_login:
                    rc = cli.main(
                        [
                            "config",
                            "providers",
                            "auth-login",
                            "openai-chatgpt",
                            "--method",
                            "browser",
                        ]
                    )

        self.assertEqual(rc, 0)
        mock_login.assert_called_once()
        self.assertEqual(mock_login.call_args.kwargs["provider_kind"], "chatgpt")
        self.assertEqual(mock_login.call_args.kwargs["provider_id"], "openai-chatgpt")
        self.assertEqual(mock_login.call_args.kwargs["auth_mode"], "chatgpt_account")

    def test_main_config_providers_auth_login_runs_device_flow(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "config.json"

            with patch.dict(
                os.environ,
                {"PBI_AGENT_INTERNAL_CONFIG_PATH": str(config_path)},
                clear=False,
            ):
                self.assertEqual(
                    cli.main(
                        [
                            "config",
                            "providers",
                            "create",
                            "--name",
                            "OpenAI ChatGPT",
                            "--kind",
                            "chatgpt",
                        ]
                    ),
                    0,
                )
                session = build_auth_session(
                    provider_id="openai-chatgpt",
                    backend="openai_chatgpt",
                    access_token="access-token",
                    refresh_token="refresh-token",
                    account_id="acct_device",
                    email="device@example.com",
                )
                with patch(
                    "pbi_agent.cli.config.run_provider_device_auth_flow",
                    return_value=Mock(session=session),
                ) as mock_login:
                    rc = cli.main(
                        [
                            "config",
                            "providers",
                            "auth-login",
                            "openai-chatgpt",
                            "--method",
                            "device",
                        ]
                    )

        self.assertEqual(rc, 0)
        mock_login.assert_called_once()
        self.assertEqual(mock_login.call_args.kwargs["provider_kind"], "chatgpt")
        self.assertEqual(mock_login.call_args.kwargs["provider_id"], "openai-chatgpt")
        self.assertEqual(mock_login.call_args.kwargs["auth_mode"], "chatgpt_account")
