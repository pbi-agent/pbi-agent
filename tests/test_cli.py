from __future__ import annotations

import sys
import unittest

from pathlib import Path
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from pbi_agent import cli


class DefaultWebCommandTests(unittest.TestCase):
    def test_main_defaults_to_web_for_global_options_only(self) -> None:
        with patch("pbi_agent.cli._handle_web_command", return_value=17) as mock_web:
            rc = cli.main(["--api-key", "test-key"])

        self.assertEqual(rc, 17)
        args, settings = mock_web.call_args.args
        self.assertEqual(args.command, "web")
        self.assertEqual(args.host, "127.0.0.1")
        self.assertEqual(args.port, 8000)
        self.assertEqual(settings.api_key, "test-key")

    def test_main_inserts_web_before_web_specific_flags(self) -> None:
        with patch("pbi_agent.cli._handle_web_command", return_value=23) as mock_web:
            rc = cli.main(
                ["--api-key", "test-key", "--host", "0.0.0.0", "--port", "9001"]
            )

        self.assertEqual(rc, 23)
        args, settings = mock_web.call_args.args
        self.assertEqual(args.command, "web")
        self.assertEqual(args.host, "0.0.0.0")
        self.assertEqual(args.port, 9001)
        self.assertEqual(settings.api_key, "test-key")

    def test_argv_with_default_command_keeps_root_help(self) -> None:
        parser = cli.build_parser()

        self.assertEqual(cli._argv_with_default_command(parser, ["--help"]), ["--help"])

    def test_browser_target_url_uses_loopback_for_wildcard_bind(self) -> None:
        parser = cli.build_parser()
        args = parser.parse_args(["web", "--host", "0.0.0.0", "--port", "9001"])

        self.assertEqual(cli._browser_target_url(args), "http://127.0.0.1:9001")

    def test_browser_target_url_prefers_explicit_public_url(self) -> None:
        parser = cli.build_parser()
        args = parser.parse_args(["web", "--url", "demo.example.com/app"])

        self.assertEqual(cli._browser_target_url(args), "http://demo.example.com/app")

    def test_handle_web_command_opens_browser_by_default(self) -> None:
        parser = cli.build_parser()
        args = parser.parse_args(["web", "--port", "9001"])
        settings = Mock(
            verbose=False,
            provider="openai",
            api_key="test-key",
            responses_url="https://api.openai.com/v1/responses",
            generic_api_url="https://openrouter.ai/api/v1/chat/completions",
            model="gpt-5",
            anthropic_model="claude-sonnet-4-5",
            reasoning_effort="medium",
            max_tool_workers=4,
            max_retries=3,
            compact_threshold=150000,
            anthropic_max_tokens=16384,
        )

        process = Mock()
        process.wait.return_value = 12

        with (
            patch("pbi_agent.cli._wait_for_web_server", return_value=True),
            patch("pbi_agent.cli.subprocess.Popen", return_value=process) as mock_popen,
            patch("pbi_agent.cli.webbrowser.open", return_value=True) as mock_open,
        ):
            rc = cli._handle_web_command(args, settings)

        self.assertEqual(rc, 12)
        mock_popen.assert_called_once()
        mock_open.assert_called_once_with("http://127.0.0.1:9001")
        process.wait.assert_called_once_with()

    def test_handle_web_command_continues_when_browser_open_fails(self) -> None:
        parser = cli.build_parser()
        args = parser.parse_args(["web", "--port", "9001"])
        settings = Mock(
            verbose=False,
            provider="openai",
            api_key="test-key",
            responses_url="https://api.openai.com/v1/responses",
            generic_api_url="https://openrouter.ai/api/v1/chat/completions",
            model="gpt-5",
            anthropic_model="claude-sonnet-4-5",
            reasoning_effort="medium",
            max_tool_workers=4,
            max_retries=3,
            compact_threshold=150000,
            anthropic_max_tokens=16384,
        )

        process = Mock()
        process.wait.return_value = 7

        with (
            patch("pbi_agent.cli._wait_for_web_server", return_value=True),
            patch("pbi_agent.cli.subprocess.Popen", return_value=process) as mock_popen,
            patch("pbi_agent.cli.webbrowser.open", return_value=False) as mock_open,
        ):
            rc = cli._handle_web_command(args, settings)

        self.assertEqual(rc, 7)
        mock_popen.assert_called_once()
        mock_open.assert_called_once_with("http://127.0.0.1:9001")
        process.wait.assert_called_once_with()

    def test_handle_web_command_ctrl_c_exits_cleanly(self) -> None:
        parser = cli.build_parser()
        args = parser.parse_args(["web", "--port", "9001"])
        settings = Mock(
            verbose=False,
            provider="openai",
            api_key="test-key",
            responses_url="https://api.openai.com/v1/responses",
            generic_api_url="https://openrouter.ai/api/v1/chat/completions",
            model="gpt-5",
            anthropic_model="claude-sonnet-4-5",
            reasoning_effort="medium",
            max_tool_workers=4,
            max_retries=3,
            compact_threshold=150000,
            anthropic_max_tokens=16384,
        )

        process = Mock(pid=4321)
        process.poll.return_value = None
        process.wait.side_effect = [KeyboardInterrupt(), 0]

        with (
            patch("pbi_agent.cli._wait_for_web_server", return_value=True),
            patch("pbi_agent.cli.subprocess.Popen", return_value=process),
            patch("pbi_agent.cli.webbrowser.open", return_value=True),
        ):
            rc = cli._handle_web_command(args, settings)

        self.assertEqual(rc, 130)
        process.terminate.assert_called_once_with()
        self.assertEqual(process.wait.call_count, 2)

if __name__ == "__main__":
    unittest.main()
