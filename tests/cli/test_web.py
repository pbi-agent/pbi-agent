from __future__ import annotations

import io
import os
import sys
import unittest

from pathlib import Path
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from pbi_agent import cli
from pbi_agent.cli import web as cli_web


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

    def test_browser_target_url_uses_loopback_for_wildcard_bind(self) -> None:
        parser = cli.build_parser()
        args = parser.parse_args(["web", "--host", "0.0.0.0", "--port", "9001"])

        self.assertEqual(cli_web._browser_target_url(args), "http://127.0.0.1:9001")

    def test_browser_target_url_prefers_explicit_public_url(self) -> None:
        parser = cli.build_parser()
        args = parser.parse_args(["web", "--url", "demo.example.com/app"])

        self.assertEqual(
            cli_web._browser_target_url(args), "http://demo.example.com/app"
        )

    def test_handle_web_command_serves_in_process(self) -> None:
        parser = cli.build_parser()
        args = parser.parse_args(["web", "--port", "9001"])
        settings = self._settings()
        server = Mock()

        with (
            patch(
                "pbi_agent.cli.web._current_workspace_has_active_web_manager",
                return_value=False,
            ),
            patch(
                "pbi_agent.cli.web._start_browser_open_thread"
            ) as mock_browser_thread,
            patch(
                "pbi_agent.cli.web._create_web_server", return_value=server
            ) as mock_server,
        ):
            rc = cli_web._handle_web_command(args, settings)

        self.assertEqual(rc, 0)
        mock_browser_thread.assert_called_once_with(
            "127.0.0.1",
            9001,
            "http://127.0.0.1:9001",
        )
        server_args, runtime = mock_server.call_args.args
        self.assertIs(server_args, args)
        self.assertEqual(runtime.settings, settings)
        self.assertEqual(runtime.provider_id, "")
        self.assertEqual(runtime.profile_id, "")
        server.serve.assert_called_once_with(debug=False)

    def test_handle_web_command_uses_default_port_when_available(self) -> None:
        parser = cli.build_parser()
        args = parser.parse_args(["web"])
        settings = self._settings()
        server = Mock()

        with (
            patch(
                "pbi_agent.cli.web._current_workspace_has_active_web_manager",
                return_value=False,
            ),
            patch(
                "pbi_agent.cli.web._is_web_port_available", return_value=True
            ) as mock_available,
            patch("pbi_agent.cli.web._find_free_web_port") as mock_find_port,
            patch(
                "pbi_agent.cli.web._start_browser_open_thread"
            ) as mock_browser_thread,
            patch(
                "pbi_agent.cli.web._create_web_server", return_value=server
            ) as mock_server,
        ):
            rc = cli_web._handle_web_command(args, settings)

        self.assertEqual(rc, 0)
        mock_available.assert_called_once_with("127.0.0.1", cli.DEFAULT_WEB_PORT)
        mock_find_port.assert_not_called()
        mock_browser_thread.assert_called_once_with(
            "127.0.0.1",
            cli.DEFAULT_WEB_PORT,
            f"http://127.0.0.1:{cli.DEFAULT_WEB_PORT}",
        )
        self.assertEqual(mock_server.call_args.args[0].port, cli.DEFAULT_WEB_PORT)

    def test_handle_web_command_auto_selects_free_default_port(self) -> None:
        parser = cli.build_parser()
        args = parser.parse_args(["web"])
        settings = self._settings()
        server = Mock()
        stderr = io.StringIO()

        with (
            patch("sys.stderr", stderr),
            patch(
                "pbi_agent.cli.web._current_workspace_has_active_web_manager",
                return_value=False,
            ),
            patch("pbi_agent.cli.web._is_web_port_available", return_value=False),
            patch("pbi_agent.cli.web._find_free_web_port", return_value=8123),
            patch(
                "pbi_agent.cli.web._start_browser_open_thread"
            ) as mock_browser_thread,
            patch(
                "pbi_agent.cli.web._create_web_server", return_value=server
            ) as mock_server,
        ):
            rc = cli_web._handle_web_command(args, settings)

        self.assertEqual(rc, 0)
        self.assertEqual(args.port, 8123)
        self.assertIn(
            f"Port {cli.DEFAULT_WEB_PORT} is unavailable; using port 8123",
            stderr.getvalue(),
        )
        mock_browser_thread.assert_called_once_with(
            "127.0.0.1",
            8123,
            "http://127.0.0.1:8123",
        )
        self.assertEqual(mock_server.call_args.args[0].port, 8123)

    def test_handle_web_command_explicit_port_does_not_auto_select(self) -> None:
        parser = cli.build_parser()
        args = parser.parse_args(["web", "--port", "8000"])
        settings = self._settings()
        server = Mock()

        with (
            patch(
                "pbi_agent.cli.web._current_workspace_has_active_web_manager",
                return_value=False,
            ),
            patch("pbi_agent.cli.web._is_web_port_available") as mock_available,
            patch("pbi_agent.cli.web._find_free_web_port") as mock_find_port,
            patch(
                "pbi_agent.cli.web._start_browser_open_thread"
            ) as mock_browser_thread,
            patch(
                "pbi_agent.cli.web._create_web_server", return_value=server
            ) as mock_server,
        ):
            rc = cli_web._handle_web_command(args, settings)

        self.assertEqual(rc, 0)
        mock_available.assert_not_called()
        mock_find_port.assert_not_called()
        mock_browser_thread.assert_called_once_with(
            "127.0.0.1",
            8000,
            "http://127.0.0.1:8000",
        )
        self.assertEqual(mock_server.call_args.args[0].port, 8000)

    def test_handle_web_command_rejects_active_same_workspace_lease(self) -> None:
        parser = cli.build_parser()
        args = parser.parse_args(["web"])
        settings = self._settings()
        stderr = io.StringIO()

        with (
            patch("sys.stderr", stderr),
            patch(
                "pbi_agent.cli.web._current_workspace_has_active_web_manager",
                return_value=True,
            ),
            patch("pbi_agent.cli.web._is_web_port_available") as mock_available,
            patch(
                "pbi_agent.cli.web._start_browser_open_thread"
            ) as mock_browser_thread,
            patch("pbi_agent.cli.web._create_web_server") as mock_server,
        ):
            rc = cli_web._handle_web_command(args, settings)

        self.assertEqual(rc, 1)
        self.assertIn("already managing this workspace", stderr.getvalue())
        mock_available.assert_not_called()
        mock_browser_thread.assert_not_called()
        mock_server.assert_not_called()

    def test_handle_web_command_does_not_synthesize_settings_env(self) -> None:
        parser = cli.build_parser()
        args = parser.parse_args(["web", "--port", "9001"])
        settings = self._settings()
        server = Mock()

        original_provider = os.environ.get("PBI_AGENT_PROVIDER")
        original_api_key = os.environ.get("PBI_AGENT_API_KEY")
        original_reasoning_effort = os.environ.get("PBI_AGENT_REASONING_EFFORT")
        os.environ["PBI_AGENT_PROVIDER"] = "original-provider"
        os.environ.pop("PBI_AGENT_API_KEY", None)
        os.environ.pop("PBI_AGENT_REASONING_EFFORT", None)

        def assert_env(*, debug: bool) -> None:
            self.assertFalse(debug)
            self.assertEqual(os.environ["PBI_AGENT_PROVIDER"], "original-provider")
            self.assertNotIn("PBI_AGENT_API_KEY", os.environ)
            self.assertNotIn("PBI_AGENT_REASONING_EFFORT", os.environ)

        server.serve.side_effect = assert_env

        try:
            with (
                patch(
                    "pbi_agent.cli.web._current_workspace_has_active_web_manager",
                    return_value=False,
                ),
                patch("pbi_agent.cli.web._start_browser_open_thread"),
                patch(
                    "pbi_agent.cli.web._create_web_server", return_value=server
                ) as mock_server,
            ):
                rc = cli_web._handle_web_command(args, settings)
        finally:
            if original_provider is None:
                os.environ.pop("PBI_AGENT_PROVIDER", None)
            else:
                os.environ["PBI_AGENT_PROVIDER"] = original_provider
            if original_api_key is None:
                os.environ.pop("PBI_AGENT_API_KEY", None)
            else:
                os.environ["PBI_AGENT_API_KEY"] = original_api_key
            if original_reasoning_effort is None:
                os.environ.pop("PBI_AGENT_REASONING_EFFORT", None)
            else:
                os.environ["PBI_AGENT_REASONING_EFFORT"] = original_reasoning_effort

        self.assertEqual(rc, 0)
        server_args, runtime = mock_server.call_args.args
        self.assertIs(server_args, args)
        self.assertEqual(runtime.settings, settings)
        self.assertEqual(os.environ.get("PBI_AGENT_PROVIDER"), original_provider)
        self.assertEqual(os.environ.get("PBI_AGENT_API_KEY"), original_api_key)
        self.assertEqual(
            os.environ.get("PBI_AGENT_REASONING_EFFORT"),
            original_reasoning_effort,
        )

    def test_handle_web_command_can_skip_browser_open_thread(self) -> None:
        parser = cli.build_parser()
        args = parser.parse_args(["web", "--port", "9001", "--no-open"])
        server = Mock()

        with (
            patch(
                "pbi_agent.cli.web._current_workspace_has_active_web_manager",
                return_value=False,
            ),
            patch(
                "pbi_agent.cli.web._start_browser_open_thread"
            ) as mock_browser_thread,
            patch("pbi_agent.cli.web._create_web_server", return_value=server),
        ):
            rc = cli_web._handle_web_command(args, self._settings())

        self.assertEqual(rc, 0)
        mock_browser_thread.assert_not_called()
        server.serve.assert_called_once_with(debug=False)

    def test_open_browser_when_ready_opens_browser_by_default(self) -> None:
        with (
            patch(
                "pbi_agent.cli.web._wait_for_web_server",
                return_value=cli_web.WebServerWaitResult(
                    ready=True,
                    connect_host="127.0.0.1",
                    port=9001,
                    timeout_seconds=20.0,
                    elapsed_seconds=0.5,
                    attempts=3,
                ),
            ),
            patch("pbi_agent.cli.web._is_wsl_environment", return_value=False),
            patch("pbi_agent.cli.web.webbrowser.open", return_value=True) as mock_open,
        ):
            cli_web._open_browser_when_ready("127.0.0.1", 9001, "http://127.0.0.1:9001")

        mock_open.assert_called_once_with("http://127.0.0.1:9001")

    def test_open_browser_when_ready_continues_when_browser_open_fails(self) -> None:
        with (
            patch(
                "pbi_agent.cli.web._wait_for_web_server",
                return_value=cli_web.WebServerWaitResult(
                    ready=True,
                    connect_host="127.0.0.1",
                    port=9001,
                    timeout_seconds=20.0,
                    elapsed_seconds=0.5,
                    attempts=3,
                ),
            ),
            patch("pbi_agent.cli.web._is_wsl_environment", return_value=False),
            patch("pbi_agent.cli.web.webbrowser.open", return_value=False) as mock_open,
        ):
            cli_web._open_browser_when_ready("127.0.0.1", 9001, "http://127.0.0.1:9001")

        mock_open.assert_called_once_with("http://127.0.0.1:9001")

    def test_open_browser_when_ready_waits_grace_period_before_opening(self) -> None:
        status_message = "Waiting for sandbox web server before opening browser..."
        with (
            patch(
                "pbi_agent.cli.web._wait_for_web_server",
                return_value=cli_web.WebServerWaitResult(
                    ready=True,
                    connect_host="127.0.0.1",
                    port=9001,
                    timeout_seconds=20.0,
                    elapsed_seconds=0.5,
                    attempts=3,
                ),
            ),
            patch("pbi_agent.cli.web._sleep_before_browser_open") as mock_sleep,
            patch("pbi_agent.cli.web._is_wsl_environment", return_value=False),
            patch("pbi_agent.cli.web.webbrowser.open", return_value=True) as mock_open,
        ):
            cli_web._open_browser_when_ready(
                "127.0.0.1",
                9001,
                "http://127.0.0.1:9001",
                ready_grace_seconds=cli.SANDBOX_BROWSER_READY_GRACE_SECONDS,
                status_message=status_message,
            )

        mock_sleep.assert_called_once_with(
            cli.SANDBOX_BROWSER_READY_GRACE_SECONDS,
            status_message,
        )
        mock_open.assert_called_once_with("http://127.0.0.1:9001")

    def test_open_browser_when_ready_uses_windows_browser_opener_on_wsl(self) -> None:
        with (
            patch(
                "pbi_agent.cli.web._wait_for_web_server",
                return_value=cli_web.WebServerWaitResult(
                    ready=True,
                    connect_host="127.0.0.1",
                    port=9001,
                    timeout_seconds=20.0,
                    elapsed_seconds=0.5,
                    attempts=3,
                ),
            ),
            patch("pbi_agent.cli.web._is_wsl_environment", return_value=True),
            patch.dict(os.environ, {}, clear=False),
            patch(
                "pbi_agent.cli.web._open_url_in_windows_browser", return_value=True
            ) as mock_windows_open,
            patch("pbi_agent.cli.web.webbrowser.open", return_value=True) as mock_open,
        ):
            os.environ.pop("BROWSER", None)
            cli_web._open_browser_when_ready("127.0.0.1", 9001, "http://127.0.0.1:9001")

        mock_windows_open.assert_called_once_with("http://127.0.0.1:9001")
        mock_open.assert_not_called()

    def test_open_browser_when_ready_respects_explicit_browser_env_on_wsl(self) -> None:
        with (
            patch(
                "pbi_agent.cli.web._wait_for_web_server",
                return_value=cli_web.WebServerWaitResult(
                    ready=True,
                    connect_host="127.0.0.1",
                    port=9001,
                    timeout_seconds=20.0,
                    elapsed_seconds=0.5,
                    attempts=3,
                ),
            ),
            patch("pbi_agent.cli.web._is_wsl_environment", return_value=True),
            patch.dict(os.environ, {"BROWSER": "custom-browser"}, clear=False),
            patch(
                "pbi_agent.cli.web._open_url_in_windows_browser", return_value=True
            ) as mock_windows_open,
            patch("pbi_agent.cli.web.webbrowser.open", return_value=True) as mock_open,
        ):
            cli_web._open_browser_when_ready("127.0.0.1", 9001, "http://127.0.0.1:9001")

        mock_windows_open.assert_not_called()
        mock_open.assert_called_once_with("http://127.0.0.1:9001")

    def test_open_browser_when_ready_falls_back_to_standard_open_on_wsl(self) -> None:
        with (
            patch(
                "pbi_agent.cli.web._wait_for_web_server",
                return_value=cli_web.WebServerWaitResult(
                    ready=True,
                    connect_host="127.0.0.1",
                    port=9001,
                    timeout_seconds=20.0,
                    elapsed_seconds=0.5,
                    attempts=3,
                ),
            ),
            patch("pbi_agent.cli.web._is_wsl_environment", return_value=True),
            patch.dict(os.environ, {}, clear=False),
            patch(
                "pbi_agent.cli.web._open_url_in_windows_browser", return_value=False
            ) as mock_windows_open,
            patch("pbi_agent.cli.web.webbrowser.open", return_value=True) as mock_open,
        ):
            os.environ.pop("BROWSER", None)
            cli_web._open_browser_when_ready("127.0.0.1", 9001, "http://127.0.0.1:9001")

        mock_windows_open.assert_called_once_with("http://127.0.0.1:9001")
        mock_open.assert_called_once_with("http://127.0.0.1:9001")

    def test_open_browser_when_ready_retries_after_initial_timeout(self) -> None:
        first_result = cli_web.WebServerWaitResult(
            ready=False,
            connect_host="127.0.0.1",
            port=9001,
            timeout_seconds=20.0,
            elapsed_seconds=20.0,
            attempts=100,
            last_error="[Errno 111] Connection refused",
        )
        retry_result = cli_web.WebServerWaitResult(
            ready=True,
            connect_host="127.0.0.1",
            port=9001,
            timeout_seconds=10.0,
            elapsed_seconds=1.2,
            attempts=6,
            last_error="[Errno 111] Connection refused",
        )

        with (
            self.assertLogs("pbi_agent.cli", level="WARNING") as logs,
            patch(
                "pbi_agent.cli.web._wait_for_web_server",
                side_effect=[first_result, retry_result],
            ) as mock_wait,
            patch("pbi_agent.cli.web._is_wsl_environment", return_value=False),
            patch("pbi_agent.cli.web.webbrowser.open", return_value=True) as mock_open,
        ):
            cli_web._open_browser_when_ready("127.0.0.1", 9001, "http://127.0.0.1:9001")

        self.assertEqual(mock_wait.call_count, 2)
        self.assertEqual(
            mock_wait.call_args_list[1].kwargs,
            {"timeout_seconds": cli.WEB_SERVER_BROWSER_WAIT_RETRY_SECONDS},
        )
        mock_open.assert_called_once_with("http://127.0.0.1:9001")
        self.assertIn("Retrying browser launch", "\n".join(logs.output))
        self.assertIn("Connection refused", "\n".join(logs.output))

    def test_open_browser_when_ready_logs_diagnostics_after_retry_failure(self) -> None:
        first_result = cli_web.WebServerWaitResult(
            ready=False,
            connect_host="127.0.0.1",
            port=9001,
            timeout_seconds=20.0,
            elapsed_seconds=20.0,
            attempts=100,
            last_error="[Errno 111] Connection refused",
        )
        retry_result = cli_web.WebServerWaitResult(
            ready=False,
            connect_host="127.0.0.1",
            port=9001,
            timeout_seconds=10.0,
            elapsed_seconds=10.0,
            attempts=50,
            last_error="[Errno 111] Connection refused",
        )

        with (
            self.assertLogs("pbi_agent.cli", level="WARNING") as logs,
            patch(
                "pbi_agent.cli.web._wait_for_web_server",
                side_effect=[first_result, retry_result],
            ),
            patch("pbi_agent.cli.web._is_wsl_environment", return_value=False),
            patch("pbi_agent.cli.web.webbrowser.open", return_value=True) as mock_open,
        ):
            cli_web._open_browser_when_ready("127.0.0.1", 9001, "http://127.0.0.1:9001")

        mock_open.assert_not_called()
        log_output = "\n".join(logs.output)
        self.assertIn("Retrying browser launch", log_output)
        self.assertIn("still was not reachable", log_output)
        self.assertIn("attempts=50", log_output)

    def test_open_url_in_windows_browser_uses_first_successful_command(self) -> None:
        process = Mock()
        process.poll.return_value = 0

        with patch(
            "pbi_agent.cli.subprocess.Popen", return_value=process
        ) as mock_popen:
            opened = cli_web._open_url_in_windows_browser(self._OAUTH_URL)

        self.assertTrue(opened)
        mock_popen.assert_called_once_with(
            [
                "powershell.exe",
                "-NoProfile",
                "-NonInteractive",
                "-Command",
                f"Start-Process -FilePath '{self._OAUTH_URL}'",
            ],
            stdout=cli.subprocess.DEVNULL,
            stderr=cli.subprocess.DEVNULL,
        )

    def test_open_url_in_windows_browser_falls_back_to_cmd(self) -> None:
        process = Mock()
        process.poll.return_value = 0

        with patch(
            "pbi_agent.cli.subprocess.Popen",
            side_effect=[OSError("missing"), process],
        ) as mock_popen:
            opened = cli_web._open_url_in_windows_browser(self._OAUTH_URL)

        self.assertTrue(opened)
        self.assertEqual(mock_popen.call_count, 2)
        self.assertEqual(
            mock_popen.call_args_list[1].args[0],
            [
                "cmd.exe",
                "/c",
                f'start "" "{self._OAUTH_URL}"',
            ],
        )

    def test_open_url_in_windows_browser_returns_false_when_all_commands_fail(
        self,
    ) -> None:
        with patch(
            "pbi_agent.cli.subprocess.Popen",
            side_effect=[OSError("missing"), OSError("missing")],
        ):
            opened = cli_web._open_url_in_windows_browser(self._OAUTH_URL)

        self.assertFalse(opened)

    def test_handle_web_command_ctrl_c_exits_cleanly(self) -> None:
        parser = cli.build_parser()
        args = parser.parse_args(["web", "--port", "9001"])
        settings = self._settings()
        server = Mock()
        server.serve.side_effect = KeyboardInterrupt()

        with (
            patch(
                "pbi_agent.cli.web._current_workspace_has_active_web_manager",
                return_value=False,
            ),
            patch("pbi_agent.cli.web._start_browser_open_thread"),
            patch("pbi_agent.cli.web._create_web_server", return_value=server),
        ):
            rc = cli_web._handle_web_command(args, settings)

        self.assertEqual(rc, 130)
        server.serve.assert_called_once_with(debug=False)
