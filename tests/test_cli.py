from __future__ import annotations

import io
import os
import sys
import tempfile
import unittest

from pathlib import Path
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from pbi_agent import cli


class DefaultWebCommandTests(unittest.TestCase):
    def _settings(self, *, verbose: bool = False) -> Mock:
        return Mock(
            verbose=verbose,
            provider="openai",
            api_key="test-key",
            responses_url="https://api.openai.com/v1/responses",
            generic_api_url="https://openrouter.ai/api/v1/chat/completions",
            model="gpt-5",
            max_tokens=16384,
            reasoning_effort="medium",
            max_tool_workers=4,
            max_retries=3,
            compact_threshold=150000,
        )

    def test_main_defaults_to_web_for_global_options_only(self) -> None:
        with (
            patch("pbi_agent.cli._handle_web_command", return_value=17) as mock_web,
            patch("pbi_agent.cli.save_internal_config") as mock_save,
        ):
            rc = cli.main(["--api-key", "test-key"])

        self.assertEqual(rc, 17)
        args, settings = mock_web.call_args.args
        self.assertEqual(args.command, "web")
        self.assertEqual(args.host, "127.0.0.1")
        self.assertEqual(args.port, 8000)
        self.assertEqual(settings.api_key, "test-key")
        mock_save.assert_called_once_with(settings)

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

    def test_main_reports_google_specific_api_key_guidance(self) -> None:
        stderr = io.StringIO()

        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("PBI_AGENT_API_KEY", None)
            os.environ.pop("GEMINI_API_KEY", None)

            with (
                patch("pbi_agent.config.load_dotenv"),
                patch("sys.stderr", stderr),
            ):
                rc = cli.main(["--provider", "google", "console"])

        self.assertEqual(rc, 2)
        self.assertIn("Missing API key for provider 'google'", stderr.getvalue())
        self.assertIn("GEMINI_API_KEY", stderr.getvalue())
        self.assertIn("--google-api-key", stderr.getvalue())

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

    def test_parser_accepts_max_tokens_flag(self) -> None:
        parser = cli.build_parser()

        args = parser.parse_args(["--max-tokens", "2048", "console"])

        self.assertEqual(args.max_tokens, 2048)

    def test_web_chat_command_uses_parent_pid_wrapper(self) -> None:
        command = cli._web_chat_command(self._settings(verbose=True), parent_pid=4321)

        self.assertIn("pbi_agent.web.chat_entry", command)
        self.assertIn("--parent-pid 4321", command)
        self.assertIn("--verbose", command)

    def test_handle_web_command_serves_in_process(self) -> None:
        parser = cli.build_parser()
        args = parser.parse_args(["web", "--port", "9001"])
        settings = self._settings()
        server = Mock()

        with (
            patch("pbi_agent.cli._start_browser_open_thread") as mock_browser_thread,
            patch(
                "pbi_agent.cli._create_web_server", return_value=server
            ) as mock_server,
        ):
            rc = cli._handle_web_command(args, settings)

        self.assertEqual(rc, 0)
        mock_browser_thread.assert_called_once_with(
            "127.0.0.1",
            9001,
            "http://127.0.0.1:9001",
        )
        mock_server.assert_called_once()
        self.assertIn("pbi_agent.web.chat_entry", mock_server.call_args.args[1])
        server.serve.assert_called_once_with(debug=False)

    def test_handle_web_command_sets_and_restores_settings_env(self) -> None:
        parser = cli.build_parser()
        args = parser.parse_args(["web", "--port", "9001"])
        settings = self._settings()
        server = Mock()

        original_provider = os.environ.get("PBI_AGENT_PROVIDER")
        original_api_key = os.environ.get("PBI_AGENT_API_KEY")
        os.environ["PBI_AGENT_PROVIDER"] = "original-provider"
        os.environ.pop("PBI_AGENT_API_KEY", None)

        def assert_env(*, debug: bool) -> None:
            self.assertFalse(debug)
            self.assertEqual(os.environ["PBI_AGENT_PROVIDER"], "openai")
            self.assertEqual(os.environ["PBI_AGENT_API_KEY"], "test-key")

        server.serve.side_effect = assert_env

        try:
            with (
                patch("pbi_agent.cli._start_browser_open_thread"),
                patch("pbi_agent.cli._create_web_server", return_value=server),
            ):
                rc = cli._handle_web_command(args, settings)
        finally:
            if original_provider is None:
                os.environ.pop("PBI_AGENT_PROVIDER", None)
            else:
                os.environ["PBI_AGENT_PROVIDER"] = original_provider
            if original_api_key is None:
                os.environ.pop("PBI_AGENT_API_KEY", None)
            else:
                os.environ["PBI_AGENT_API_KEY"] = original_api_key

        self.assertEqual(rc, 0)
        self.assertEqual(os.environ.get("PBI_AGENT_PROVIDER"), original_provider)
        self.assertEqual(os.environ.get("PBI_AGENT_API_KEY"), original_api_key)

    def test_open_browser_when_ready_opens_browser_by_default(self) -> None:
        with (
            patch("pbi_agent.cli._wait_for_web_server", return_value=True),
            patch("pbi_agent.cli.webbrowser.open", return_value=True) as mock_open,
        ):
            cli._open_browser_when_ready("127.0.0.1", 9001, "http://127.0.0.1:9001")

        mock_open.assert_called_once_with("http://127.0.0.1:9001")

    def test_open_browser_when_ready_continues_when_browser_open_fails(self) -> None:
        with (
            patch("pbi_agent.cli._wait_for_web_server", return_value=True),
            patch("pbi_agent.cli.webbrowser.open", return_value=False) as mock_open,
        ):
            cli._open_browser_when_ready("127.0.0.1", 9001, "http://127.0.0.1:9001")

        mock_open.assert_called_once_with("http://127.0.0.1:9001")

    def test_handle_web_command_ctrl_c_exits_cleanly(self) -> None:
        parser = cli.build_parser()
        args = parser.parse_args(["web", "--port", "9001"])
        settings = self._settings()
        server = Mock()
        server.serve.side_effect = KeyboardInterrupt()

        with (
            patch("pbi_agent.cli._start_browser_open_thread"),
            patch("pbi_agent.cli._create_web_server", return_value=server),
        ):
            rc = cli._handle_web_command(args, settings)

        self.assertEqual(rc, 130)
        server.serve.assert_called_once_with(debug=False)

    def test_handle_run_command_uses_console_single_turn_path(self) -> None:
        parser = cli.build_parser()
        args = parser.parse_args(["run", "--prompt", "Inspect the report"])
        settings = self._settings()
        outcome = Mock(tool_errors=False)

        with (
            patch(
                "pbi_agent.agent.session.run_single_turn", return_value=outcome
            ) as mock_run,
            patch("pbi_agent.ui.console_display.ConsoleDisplay") as mock_display_cls,
        ):
            rc = cli._handle_run_command(args, settings)

        self.assertEqual(rc, 0)
        mock_display_cls.assert_called_once_with(verbose=False)
        mock_run.assert_called_once_with(
            "Inspect the report",
            settings,
            mock_display_cls.return_value,
            single_turn_hint=None,
        )

    def test_handle_audit_command_uses_direct_single_turn_path(self) -> None:
        parser = cli.build_parser()
        with tempfile.TemporaryDirectory() as tmpdir:
            report_dir = Path(tmpdir).resolve()
            args = parser.parse_args(["audit", "--report-dir", str(report_dir)])
            settings = self._settings()
            (report_dir / "AUDIT-REPORT.md").write_text("# Audit\n", encoding="utf-8")

            with (
                patch(
                    "pbi_agent.agent.audit_prompt.copy_audit_todo",
                    return_value=report_dir / "AUDIT-TODO.md",
                ) as mock_copy,
                patch(
                    "pbi_agent.agent.audit_prompt.build_audit_prompt",
                    return_value="audit prompt",
                ),
                patch(
                    "pbi_agent.cli._run_single_turn_command",
                    return_value=0,
                ) as mock_run_single_turn,
            ):
                rc = cli._handle_audit_command(args, settings)

        self.assertEqual(rc, 0)
        mock_copy.assert_called_once_with(report_dir)
        mock_run_single_turn.assert_called_once_with(
            prompt="audit prompt",
            settings=settings,
            single_turn_hint=(
                "Audit mode: Evaluating report and writing "
                "AUDIT-TODO.md progress tracker and "
                "AUDIT-REPORT.md."
            ),
        )


if __name__ == "__main__":
    unittest.main()
