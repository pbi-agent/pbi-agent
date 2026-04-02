from __future__ import annotations

import argparse
import io
import os
import sys
import tempfile
import unittest

from pathlib import Path
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from pbi_agent import cli
from pbi_agent.config import load_internal_config
from pbi_agent.session_store import SessionStore


class DefaultWebCommandTests(unittest.TestCase):
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
            compact_threshold=150000,
            service_tier=None,
        )

    def test_main_defaults_to_web_for_global_options_only(self) -> None:
        with patch("pbi_agent.cli._handle_web_command", return_value=17) as mock_web:
            rc = cli.main([])

        self.assertEqual(rc, 17)
        args, runtime = mock_web.call_args.args
        settings = getattr(runtime, "settings", runtime)
        self.assertEqual(args.command, "web")
        self.assertEqual(args.host, "127.0.0.1")
        self.assertEqual(args.port, 8000)
        self.assertEqual(settings.provider, "openai")

    def test_main_inserts_web_before_web_specific_flags(self) -> None:
        with patch("pbi_agent.cli._handle_web_command", return_value=23) as mock_web:
            rc = cli.main(["--host", "0.0.0.0", "--port", "9001"])

        self.assertEqual(rc, 23)
        args, runtime = mock_web.call_args.args
        settings = getattr(runtime, "settings", runtime)
        self.assertEqual(args.command, "web")
        self.assertEqual(args.host, "0.0.0.0")
        self.assertEqual(args.port, 9001)
        self.assertEqual(settings.provider, "openai")

    def test_main_rejects_runtime_provider_flags_for_web(self) -> None:
        stderr = io.StringIO()

        with patch.dict(os.environ, {}, clear=False):
            with patch("sys.stderr", stderr):
                rc = cli.main(["--provider", "google", "web"])

        self.assertEqual(rc, 2)
        self.assertIn("no longer supported with `pbi-agent web`", stderr.getvalue())

    def test_argv_with_default_command_keeps_root_help(self) -> None:
        parser = cli.build_parser()

        self.assertEqual(cli._argv_with_default_command(parser, ["--help"]), ["--help"])

    def test_root_help_keeps_long_options_and_descriptions_on_single_rows(self) -> None:
        with patch(
            "pbi_agent.cli.shutil.get_terminal_size",
            return_value=os.terminal_size((120, 40)),
        ):
            parser = cli.build_parser()
            help_text = parser.format_help()

        self.assertIn(
            "--provider PROVIDER                    Provider backend:", help_text
        )
        self.assertNotIn("--provider PROVIDER\n", help_text)
        self.assertIn("--generic-api-url GENERIC_API_URL", help_text)
        self.assertNotIn("--generic-api-url GENERIC_API_URL\n", help_text)
        self.assertIn(
            "--compact-threshold COMPACT_THRESHOLD  Context compaction token threshold",
            help_text,
        )
        self.assertNotIn("--compact-threshold COMPACT_THRESHOLD\n", help_text)

    def test_subcommand_help_uses_clean_subcommand_prog(self) -> None:
        parser = cli.build_parser()
        subparsers = next(
            action
            for action in parser._actions
            if isinstance(action, argparse._SubParsersAction)
        )
        web_help = subparsers.choices["web"].format_help()

        self.assertIn("usage: pbi-agent web [-h] [--host HOST] [--port PORT]", web_help)
        self.assertNotIn("[GLOBAL OPTIONS] [<command>] [COMMAND OPTIONS] web", web_help)
        self.assertIn("Serve the browser interface.", web_help)

    def test_root_help_omits_removed_console_and_open_commands(self) -> None:
        help_text = cli.build_parser().format_help()

        self.assertNotIn(" console ", help_text)
        self.assertNotIn(" open ", help_text)

    def test_parser_rejects_removed_console_command(self) -> None:
        with self.assertRaises(SystemExit) as exc_info:
            cli.build_parser().parse_args(["console"])

        self.assertEqual(exc_info.exception.code, 2)

    def test_parser_rejects_removed_open_command(self) -> None:
        with self.assertRaises(SystemExit) as exc_info:
            cli.build_parser().parse_args(["open", "--session-id", "session-1"])

        self.assertEqual(exc_info.exception.code, 2)

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

        args = parser.parse_args(["--max-tokens", "2048", "web"])

        self.assertEqual(args.max_tokens, 2048)

    def test_parser_accepts_profile_id_flag(self) -> None:
        parser = cli.build_parser()

        args = parser.parse_args(["--profile-id", "analysis", "web"])

        self.assertEqual(args.profile_id, "analysis")

    def test_parser_accepts_sub_agent_model_flag(self) -> None:
        parser = cli.build_parser()

        args = parser.parse_args(["--sub-agent-model", "gpt-5-mini", "web"])

        self.assertEqual(args.sub_agent_model, "gpt-5-mini")

    def test_parser_accepts_skills_flag(self) -> None:
        parser = cli.build_parser()

        args = parser.parse_args(["--skills", "web"])

        self.assertTrue(args.skills)

    def test_parser_accepts_mcp_flag(self) -> None:
        parser = cli.build_parser()

        args = parser.parse_args(["--mcp", "web"])

        self.assertTrue(args.mcp)

    def test_parser_accepts_agents_flag(self) -> None:
        parser = cli.build_parser()

        args = parser.parse_args(["--agents", "web"])

        self.assertTrue(args.agents)

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
        server_args, runtime = mock_server.call_args.args
        self.assertIs(server_args, args)
        self.assertEqual(runtime.settings, settings)
        self.assertEqual(runtime.provider_id, "")
        self.assertEqual(runtime.profile_id, "")
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
            self.assertEqual(os.environ["PBI_AGENT_SUB_AGENT_MODEL"], "gpt-5-mini")

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
            patch("pbi_agent.cli._is_wsl_environment", return_value=False),
            patch("pbi_agent.cli.webbrowser.open", return_value=True) as mock_open,
        ):
            cli._open_browser_when_ready("127.0.0.1", 9001, "http://127.0.0.1:9001")

        mock_open.assert_called_once_with("http://127.0.0.1:9001")

    def test_open_browser_when_ready_continues_when_browser_open_fails(self) -> None:
        with (
            patch("pbi_agent.cli._wait_for_web_server", return_value=True),
            patch("pbi_agent.cli._is_wsl_environment", return_value=False),
            patch("pbi_agent.cli.webbrowser.open", return_value=False) as mock_open,
        ):
            cli._open_browser_when_ready("127.0.0.1", 9001, "http://127.0.0.1:9001")

        mock_open.assert_called_once_with("http://127.0.0.1:9001")

    def test_open_browser_when_ready_uses_windows_browser_opener_on_wsl(self) -> None:
        with (
            patch("pbi_agent.cli._wait_for_web_server", return_value=True),
            patch("pbi_agent.cli._is_wsl_environment", return_value=True),
            patch.dict(os.environ, {}, clear=False),
            patch(
                "pbi_agent.cli._open_url_in_windows_browser", return_value=True
            ) as mock_windows_open,
            patch("pbi_agent.cli.webbrowser.open", return_value=True) as mock_open,
        ):
            os.environ.pop("BROWSER", None)
            cli._open_browser_when_ready("127.0.0.1", 9001, "http://127.0.0.1:9001")

        mock_windows_open.assert_called_once_with("http://127.0.0.1:9001")
        mock_open.assert_not_called()

    def test_open_browser_when_ready_respects_explicit_browser_env_on_wsl(self) -> None:
        with (
            patch("pbi_agent.cli._wait_for_web_server", return_value=True),
            patch("pbi_agent.cli._is_wsl_environment", return_value=True),
            patch.dict(os.environ, {"BROWSER": "custom-browser"}, clear=False),
            patch(
                "pbi_agent.cli._open_url_in_windows_browser", return_value=True
            ) as mock_windows_open,
            patch("pbi_agent.cli.webbrowser.open", return_value=True) as mock_open,
        ):
            cli._open_browser_when_ready("127.0.0.1", 9001, "http://127.0.0.1:9001")

        mock_windows_open.assert_not_called()
        mock_open.assert_called_once_with("http://127.0.0.1:9001")

    def test_open_browser_when_ready_falls_back_to_standard_open_on_wsl(self) -> None:
        with (
            patch("pbi_agent.cli._wait_for_web_server", return_value=True),
            patch("pbi_agent.cli._is_wsl_environment", return_value=True),
            patch.dict(os.environ, {}, clear=False),
            patch(
                "pbi_agent.cli._open_url_in_windows_browser", return_value=False
            ) as mock_windows_open,
            patch("pbi_agent.cli.webbrowser.open", return_value=True) as mock_open,
        ):
            os.environ.pop("BROWSER", None)
            cli._open_browser_when_ready("127.0.0.1", 9001, "http://127.0.0.1:9001")

        mock_windows_open.assert_called_once_with("http://127.0.0.1:9001")
        mock_open.assert_called_once_with("http://127.0.0.1:9001")

    def test_open_url_in_windows_browser_uses_first_successful_command(self) -> None:
        process = Mock()
        process.poll.return_value = 0

        with patch(
            "pbi_agent.cli.subprocess.Popen", return_value=process
        ) as mock_popen:
            opened = cli._open_url_in_windows_browser("http://127.0.0.1:9001")

        self.assertTrue(opened)
        mock_popen.assert_called_once_with(
            ["explorer.exe", "http://127.0.0.1:9001"],
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
            opened = cli._open_url_in_windows_browser("http://127.0.0.1:9001")

        self.assertTrue(opened)
        self.assertEqual(mock_popen.call_count, 2)
        self.assertEqual(
            mock_popen.call_args_list[1].args[0],
            ["cmd.exe", "/c", "start", "", "http://127.0.0.1:9001"],
        )

    def test_open_url_in_windows_browser_returns_false_when_all_commands_fail(
        self,
    ) -> None:
        with patch(
            "pbi_agent.cli.subprocess.Popen",
            side_effect=[OSError("missing"), OSError("missing")],
        ):
            opened = cli._open_url_in_windows_browser("http://127.0.0.1:9001")

        self.assertFalse(opened)

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

    def test_handle_run_command_uses_single_turn_path(self) -> None:
        parser = cli.build_parser()
        args = parser.parse_args(["run", "--prompt", "Inspect the report"])
        settings = self._settings()
        outcome = Mock(tool_errors=False)

        with (
            patch(
                "pbi_agent.agent.session.run_single_turn", return_value=outcome
            ) as mock_run,
            patch(
                "pbi_agent.display.console_display.ConsoleDisplay"
            ) as mock_display_cls,
        ):
            rc = cli._handle_run_command(args, settings)

        self.assertEqual(rc, 0)
        mock_display_cls.assert_called_once_with(verbose=False)
        prompt, runtime, display = mock_run.call_args.args
        self.assertEqual(prompt, "Inspect the report")
        self.assertIs(display, mock_display_cls.return_value)
        self.assertEqual(runtime.settings, settings)
        self.assertEqual(runtime.provider_id, "")
        self.assertEqual(runtime.profile_id, "")
        self.assertEqual(
            mock_run.call_args.kwargs,
            {
                "single_turn_hint": None,
                "image_paths": [],
                "resume_session_id": None,
            },
        )

    def test_handle_run_command_scopes_to_requested_project_dir(self) -> None:
        parser = cli.build_parser()
        with tempfile.TemporaryDirectory() as tmpdir:
            original_cwd = Path.cwd()
            root_dir = Path(tmpdir).resolve()
            project_dir = root_dir / "report-a"
            project_dir.mkdir()
            args = parser.parse_args(
                [
                    "run",
                    "--prompt",
                    "Inspect the report",
                    "--project-dir",
                    str(project_dir),
                ]
            )
            settings = self._settings()
            seen_cwds: list[Path] = []

            def fake_run_single_turn(
                prompt: str,
                runtime_settings,
                display,
                *,
                single_turn_hint: str | None = None,
                image_paths: list[str] | None = None,
                resume_session_id: str | None = None,
            ) -> object:
                del (
                    prompt,
                    runtime_settings,
                    display,
                    single_turn_hint,
                    image_paths,
                    resume_session_id,
                )
                seen_cwds.append(Path.cwd())
                return Mock(tool_errors=False)

            try:
                os.chdir(root_dir)
                with (
                    patch(
                        "pbi_agent.agent.session.run_single_turn",
                        side_effect=fake_run_single_turn,
                    ) as mock_run,
                    patch(
                        "pbi_agent.display.console_display.ConsoleDisplay"
                    ) as mock_display_cls,
                ):
                    rc = cli._handle_run_command(args, settings)
            finally:
                os.chdir(original_cwd)

        self.assertEqual(rc, 0)
        self.assertEqual(seen_cwds, [project_dir])
        self.assertEqual(Path.cwd(), original_cwd)
        mock_display_cls.assert_called_once_with(verbose=False)
        mock_run.assert_called_once()

    def test_handle_run_command_rejects_missing_project_dir(self) -> None:
        parser = cli.build_parser()
        with tempfile.TemporaryDirectory() as tmpdir:
            original_cwd = Path.cwd()
            root_dir = Path(tmpdir).resolve()
            args = parser.parse_args(
                [
                    "run",
                    "--prompt",
                    "Inspect the report",
                    "--project-dir",
                    "missing-project",
                ]
            )
            settings = self._settings()
            stderr = io.StringIO()

            try:
                os.chdir(root_dir)
                with patch("sys.stderr", stderr):
                    rc = cli._handle_run_command(args, settings)
            finally:
                os.chdir(original_cwd)

        self.assertEqual(rc, 1)
        self.assertIn("Project directory does not exist", stderr.getvalue())

    def test_main_skills_flag_lists_project_skills_without_settings(self) -> None:
        stdout = io.StringIO()

        with tempfile.TemporaryDirectory() as tmpdir:
            original_cwd = Path.cwd()
            root_dir = Path(tmpdir).resolve()
            skill_dir = root_dir / ".agents" / "skills" / "repo-skill"
            skill_dir.mkdir(parents=True)
            (skill_dir / "SKILL.md").write_text(
                "---\n"
                "name: repo-skill\n"
                "description: Repository-specific workflow.\n"
                "---\n\n# Repo Skill\n",
                encoding="utf-8",
            )

            try:
                os.chdir(root_dir)
                with patch("sys.stdout", stdout):
                    rc = cli.main(["--skills"])
            finally:
                os.chdir(original_cwd)

        self.assertEqual(rc, 0)
        output = stdout.getvalue()
        self.assertIn("Project Skills", output)
        self.assertIn("repo-skill", output)

    def test_main_mcp_flag_lists_project_servers_without_settings(self) -> None:
        stdout = io.StringIO()

        with tempfile.TemporaryDirectory() as tmpdir:
            original_cwd = Path.cwd()
            root_dir = Path(tmpdir).resolve()
            config_dir = root_dir / ".agents"
            config_dir.mkdir(parents=True)
            (config_dir / "mcp.json").write_text(
                (
                    "{"
                    '"servers":{'
                    '"echo":{"command":"uv","args":["run","server.py"],"cwd":"."}'
                    "}"
                    "}"
                ),
                encoding="utf-8",
            )

            try:
                os.chdir(root_dir)
                with patch("sys.stdout", stdout):
                    rc = cli.main(["--mcp"])
            finally:
                os.chdir(original_cwd)

        self.assertEqual(rc, 0)
        output = stdout.getvalue()
        self.assertIn("MCP Servers", output)
        self.assertIn("echo", output)
        self.assertIn("uv run server.py", output)

    def test_main_agents_flag_lists_project_sub_agents_without_settings(self) -> None:
        stdout = io.StringIO()

        with tempfile.TemporaryDirectory() as tmpdir:
            original_cwd = Path.cwd()
            root_dir = Path(tmpdir).resolve()
            agents_dir = root_dir / ".agents"
            agents_dir.mkdir(parents=True)
            (agents_dir / "code-reviewer.md").write_text(
                "---\n"
                "name: code-reviewer\n"
                "description: Reviews code for quality.\n"
                "---\n\nYou are a code reviewer.\n",
                encoding="utf-8",
            )

            try:
                os.chdir(root_dir)
                with patch("sys.stdout", stdout):
                    rc = cli.main(["--agents"])
            finally:
                os.chdir(original_cwd)

        self.assertEqual(rc, 0)
        output = stdout.getvalue()
        self.assertIn("Sub-Agents", output)
        self.assertIn("code-reviewer", output)

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
        self.assertEqual(
            mock_run_single_turn.call_args.kwargs["prompt"], "audit prompt"
        )
        runtime = mock_run_single_turn.call_args.kwargs["settings"]
        self.assertEqual(runtime.settings, settings)
        self.assertEqual(runtime.provider_id, "")
        self.assertEqual(runtime.profile_id, "")
        self.assertEqual(
            mock_run_single_turn.call_args.kwargs["single_turn_hint"],
            "Audit mode: Evaluating report and writing "
            "AUDIT-TODO.md progress tracker and "
            "AUDIT-REPORT.md.",
        )

    def test_parser_accepts_service_tier_flag(self) -> None:
        parser = cli.build_parser()

        args = parser.parse_args(["--service-tier", "flex", "web"])

        self.assertEqual(args.service_tier, "flex")

    def test_parser_rejects_unsupported_service_tier(self) -> None:
        parser = cli.build_parser()

        with self.assertRaises(SystemExit) as exc_info:
            parser.parse_args(["--service-tier", "scale", "web"])

        self.assertEqual(exc_info.exception.code, 2)

    def test_service_tier_with_non_openai_provider_errors(self) -> None:
        stderr = io.StringIO()

        with (
            patch("pbi_agent.config.load_dotenv"),
            patch("sys.stderr", stderr),
        ):
            rc = cli.main(
                [
                    "--provider",
                    "xai",
                    "--service-tier",
                    "flex",
                    "--api-key",
                    "k",
                    "run",
                    "--prompt",
                    "hello",
                ]
            )

        self.assertEqual(rc, 2)
        self.assertIn("--service-tier", stderr.getvalue())
        self.assertIn("OpenAI", stderr.getvalue())

    def test_main_run_with_session_id_uses_current_runtime_settings(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            db_path = tmp_path / "sessions.db"
            config_path = tmp_path / "config.json"
            config_path.write_text("{}", encoding="utf-8")
            with SessionStore(db_path=db_path) as store:
                session_id = store.create_session(
                    "/tmp/project", "xai", "grok-4", "saved xai session"
                )

            with (
                patch.dict(
                    os.environ,
                    {
                        "PBI_AGENT_SESSION_DB_PATH": str(db_path),
                        "PBI_AGENT_INTERNAL_CONFIG_PATH": str(config_path),
                        "PBI_AGENT_PROVIDER": "openai",
                        "OPENAI_API_KEY": "openai-key",
                    },
                    clear=False,
                ),
                patch("pbi_agent.config.load_dotenv"),
                patch("pbi_agent.cli.configure_logging"),
                patch("pbi_agent.cli._handle_run_command", return_value=0) as mock_run,
            ):
                rc = cli.main(["run", "--prompt", "hello", "--session-id", session_id])

        self.assertEqual(rc, 0)
        args, runtime = mock_run.call_args.args
        self.assertEqual(args.session_id, session_id)
        self.assertEqual(runtime.settings.provider, "openai")
        self.assertEqual(runtime.settings.model, "gpt-5.4")
        self.assertIsNone(runtime.profile_id)

    def test_main_run_with_session_id_uses_saved_session_directory(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            db_path = tmp_path / "sessions.db"
            config_path = tmp_path / "config.json"
            config_path.write_text("{}", encoding="utf-8")
            saved_project = tmp_path / "saved-project"
            saved_project.mkdir()
            caller_project = tmp_path / "caller-project"
            caller_project.mkdir()
            with SessionStore(db_path=db_path) as store:
                session_id = store.create_session(
                    str(saved_project), "xai", "grok-4", "saved xai session"
                )

            original_cwd = Path.cwd()
            try:
                os.chdir(caller_project)
                with (
                    patch.dict(
                        os.environ,
                        {
                            "PBI_AGENT_SESSION_DB_PATH": str(db_path),
                            "PBI_AGENT_INTERNAL_CONFIG_PATH": str(config_path),
                            "PBI_AGENT_PROVIDER": "openai",
                            "OPENAI_API_KEY": "openai-key",
                        },
                        clear=False,
                    ),
                    patch("pbi_agent.config.load_dotenv"),
                    patch("pbi_agent.cli.configure_logging"),
                    patch(
                        "pbi_agent.cli._handle_run_command", return_value=0
                    ) as mock_run,
                ):
                    rc = cli.main(
                        ["run", "--prompt", "hello", "--session-id", session_id]
                    )
            finally:
                os.chdir(original_cwd)

        self.assertEqual(rc, 0)
        args, runtime = mock_run.call_args.args
        self.assertEqual(args.session_id, session_id)
        self.assertEqual(Path(args.project_dir), saved_project)
        self.assertEqual(runtime.settings.provider, "openai")
        self.assertEqual(runtime.settings.model, "gpt-5.4")

    def test_main_config_providers_crud_commands(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "config.json"

            with patch.dict(
                os.environ,
                {"PBI_AGENT_INTERNAL_CONFIG_PATH": str(config_path)},
                clear=False,
            ):
                rc = cli.main(
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
                )
                self.assertEqual(rc, 0)
                self.assertEqual(load_internal_config().providers[0].id, "openai-main")

                stdout = io.StringIO()
                with patch("sys.stdout", stdout):
                    rc = cli.main(["config", "providers", "list"])
                self.assertEqual(rc, 0)
                self.assertIn("openai-main", stdout.getvalue())

                rc = cli.main(
                    [
                        "config",
                        "providers",
                        "update",
                        "openai-main",
                        "--name",
                        "OpenAI Prod",
                    ]
                )
                self.assertEqual(rc, 0)
                self.assertEqual(
                    load_internal_config().providers[0].name, "OpenAI Prod"
                )

                rc = cli.main(["config", "providers", "delete", "openai-main"])
                self.assertEqual(rc, 0)
                self.assertEqual(load_internal_config().providers, [])

    def test_main_config_profiles_crud_commands(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "config.json"

            with patch.dict(
                os.environ,
                {"PBI_AGENT_INTERNAL_CONFIG_PATH": str(config_path)},
                clear=False,
            ):
                os.environ.pop("PBI_AGENT_API_KEY", None)
                os.environ.pop("OPENAI_API_KEY", None)
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
                            "--model",
                            "gpt-5.4",
                            "--max-retries",
                            "4",
                        ]
                    ),
                    0,
                )

                stdout = io.StringIO()
                with patch("sys.stdout", stdout):
                    rc = cli.main(["config", "profiles", "list"])
                self.assertEqual(rc, 0)
                self.assertIn("analysis", stdout.getvalue())

                self.assertEqual(
                    cli.main(["config", "profiles", "select", "analysis"]), 0
                )
                self.assertEqual(
                    load_internal_config().web.active_profile_id, "analysis"
                )

                self.assertEqual(
                    cli.main(
                        [
                            "config",
                            "profiles",
                            "update",
                            "analysis",
                            "--model",
                            "gpt-5.4-2026-03-05",
                        ]
                    ),
                    0,
                )
                self.assertEqual(
                    load_internal_config().model_profiles[0].model, "gpt-5.4-2026-03-05"
                )

                self.assertEqual(
                    cli.main(["config", "profiles", "delete", "analysis"]), 0
                )
                config = load_internal_config()
                self.assertEqual(config.model_profiles, [])
                self.assertIsNone(config.web.active_profile_id)

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

    def test_main_web_uses_profile_id_and_persists_derived_runtime(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "config.json"

            with patch.dict(
                os.environ,
                {"PBI_AGENT_INTERNAL_CONFIG_PATH": str(config_path)},
                clear=False,
            ):
                os.environ.pop("PBI_AGENT_API_KEY", None)
                os.environ.pop("OPENAI_API_KEY", None)
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
                            "--model",
                            "gpt-5.4-2026-03-05",
                        ]
                    ),
                    0,
                )
                self.assertEqual(
                    cli.main(["config", "profiles", "select", "analysis"]), 0
                )
                before = config_path.read_text(encoding="utf-8")

                with (
                    patch("pbi_agent.config.load_dotenv"),
                    patch("pbi_agent.cli.configure_logging"),
                    patch(
                        "pbi_agent.cli._handle_web_command", return_value=0
                    ) as mock_web,
                ):
                    rc = cli.main(["web"])

                after = config_path.read_text(encoding="utf-8")

        self.assertEqual(rc, 0)
        _args, runtime = mock_web.call_args.args
        self.assertEqual(runtime.settings.provider, "openai")
        self.assertEqual(runtime.settings.model, "gpt-5.4-2026-03-05")
        self.assertEqual(runtime.settings.api_key, "saved-key")
        self.assertEqual(runtime.profile_id, "analysis")
        self.assertEqual(before, after)

    def test_main_run_uses_profile_id_flag(self) -> None:
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
                            "xAI Main",
                            "--kind",
                            "xai",
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
                            "Fast",
                            "--provider-id",
                            "xai-main",
                            "--model",
                            "grok-4.20",
                        ]
                    ),
                    0,
                )

                with (
                    patch("pbi_agent.config.load_dotenv"),
                    patch("pbi_agent.cli.configure_logging"),
                    patch(
                        "pbi_agent.cli._handle_run_command", return_value=0
                    ) as mock_run,
                ):
                    rc = cli.main(
                        [
                            "--profile-id",
                            "fast",
                            "run",
                            "--prompt",
                            "hello",
                        ]
                    )

        self.assertEqual(rc, 0)
        _args, runtime = mock_run.call_args.args
        self.assertEqual(runtime.settings.provider, "xai")
        self.assertEqual(runtime.settings.model, "grok-4.20")

    def test_main_run_with_nonexistent_session_id_exits_with_error(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            db_path = tmp_path / "sessions.db"
            config_path = tmp_path / "config.json"
            config_path.write_text("{}", encoding="utf-8")
            SessionStore(db_path=db_path).close()

            with (
                patch.dict(
                    os.environ,
                    {
                        "PBI_AGENT_SESSION_DB_PATH": str(db_path),
                        "PBI_AGENT_INTERNAL_CONFIG_PATH": str(config_path),
                    },
                    clear=False,
                ),
                patch("pbi_agent.config.load_dotenv"),
            ):
                stderr = io.StringIO()
                with patch("sys.stderr", stderr):
                    rc = cli.main(
                        ["run", "--prompt", "hello", "--session-id", "nonexistent-id"]
                    )

        self.assertEqual(rc, 1)
        self.assertIn("not found", stderr.getvalue())


if __name__ == "__main__":
    unittest.main()
