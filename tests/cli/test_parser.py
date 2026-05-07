from __future__ import annotations

import argparse
import io
import os
import sys
import unittest

from pathlib import Path
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from pbi_agent import __version__
from pbi_agent import cli
from pbi_agent.cli import parser as cli_parser


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

    def test_argv_with_default_command_keeps_root_help(self) -> None:
        parser = cli.build_parser()

        self.assertEqual(
            cli_parser._argv_with_default_command(parser, ["--help"]), ["--help"]
        )

    def test_argv_with_default_command_keeps_root_version_long_flag(self) -> None:
        parser = cli.build_parser()

        self.assertEqual(
            cli_parser._argv_with_default_command(parser, ["--version"]), ["--version"]
        )

    def test_argv_with_default_command_keeps_root_version_short_flag(self) -> None:
        parser = cli.build_parser()

        self.assertEqual(cli_parser._argv_with_default_command(parser, ["-v"]), ["-v"])

    def test_parser_version_long_flag_prints_resolved_version(self) -> None:
        stdout = io.StringIO()

        with patch("sys.stdout", stdout), self.assertRaises(SystemExit) as exc_info:
            cli.build_parser().parse_args(["--version"])

        self.assertEqual(exc_info.exception.code, 0)
        self.assertEqual(stdout.getvalue().strip(), __version__)

    def test_parser_version_short_flag_prints_resolved_version(self) -> None:
        stdout = io.StringIO()

        with patch("sys.stdout", stdout), self.assertRaises(SystemExit) as exc_info:
            cli.build_parser().parse_args(["-v"])

        self.assertEqual(exc_info.exception.code, 0)
        self.assertEqual(stdout.getvalue().strip(), __version__)

    def test_root_help_keeps_long_options_and_descriptions_on_single_rows(self) -> None:
        with patch(
            "pbi_agent.cli.parser.shutil.get_terminal_size",
            return_value=os.terminal_size((120, 40)),
        ):
            parser = cli.build_parser()
            help_text = parser.format_help()

        self.assertIn(
            "--provider PROVIDER                     Provider backend:", help_text
        )
        self.assertNotIn("--provider PROVIDER\n", help_text)
        self.assertIn("--generic-api-url GENERIC_API_URL", help_text)
        self.assertNotIn("--generic-api-url GENERIC_API_URL\n", help_text)
        self.assertIn(
            "--compact-threshold COMPACT_THRESHOLD   Context compaction token threshold",
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

    def test_parser_accepts_skills_list_command(self) -> None:
        parser = cli.build_parser()

        args = parser.parse_args(["skills", "list"])

        self.assertEqual(args.command, "skills")
        self.assertEqual(args.skills_action, "list")

    def test_parser_accepts_skills_add_command(self) -> None:
        parser = cli.build_parser()

        args = parser.parse_args(
            [
                "skills",
                "add",
                "owner/repo",
                "--skill",
                "repo-skill",
                "--list",
                "--force",
            ]
        )

        self.assertEqual(args.command, "skills")
        self.assertEqual(args.skills_action, "add")
        self.assertEqual(args.source, "owner/repo")
        self.assertEqual(args.skill, "repo-skill")
        self.assertTrue(args.list)
        self.assertTrue(args.force)

    def test_parser_accepts_skills_add_without_source(self) -> None:
        parser = cli.build_parser()

        args = parser.parse_args(["skills", "add"])

        self.assertEqual(args.command, "skills")
        self.assertEqual(args.skills_action, "add")
        self.assertIsNone(args.source)
        self.assertIsNone(args.skill)
        self.assertFalse(args.list)
        self.assertFalse(args.force)

    def test_parser_accepts_skills_add_list_without_source(self) -> None:
        parser = cli.build_parser()

        args = parser.parse_args(["skills", "add", "--list"])

        self.assertEqual(args.command, "skills")
        self.assertEqual(args.skills_action, "add")
        self.assertIsNone(args.source)
        self.assertTrue(args.list)

    def test_parser_accepts_skills_add_skill_without_source(self) -> None:
        parser = cli.build_parser()

        args = parser.parse_args(["skills", "add", "--skill", "workspace-helper"])

        self.assertEqual(args.command, "skills")
        self.assertEqual(args.skills_action, "add")
        self.assertIsNone(args.source)
        self.assertEqual(args.skill, "workspace-helper")

    def test_parser_accepts_skills_add_local_path_source(self) -> None:
        parser = cli.build_parser()

        args = parser.parse_args(["skills", "add", "./skills/local"])

        self.assertEqual(args.command, "skills")
        self.assertEqual(args.skills_action, "add")
        self.assertEqual(args.source, "./skills/local")

    def test_parser_accepts_commands_list_command(self) -> None:
        parser = cli.build_parser()

        args = parser.parse_args(["commands", "list"])

        self.assertEqual(args.command, "commands")
        self.assertEqual(args.commands_action, "list")

    def test_parser_accepts_commands_add_command(self) -> None:
        parser = cli.build_parser()

        args = parser.parse_args(
            [
                "commands",
                "add",
                "owner/repo",
                "--command",
                "execute",
                "--list",
                "--force",
            ]
        )

        self.assertEqual(args.command, "commands")
        self.assertEqual(args.commands_action, "add")
        self.assertEqual(args.source, "owner/repo")
        self.assertEqual(args.command_name, "execute")
        self.assertTrue(args.list)
        self.assertTrue(args.force)

    def test_parser_accepts_commands_add_without_source(self) -> None:
        parser = cli.build_parser()

        args = parser.parse_args(["commands", "add"])

        self.assertEqual(args.command, "commands")
        self.assertEqual(args.commands_action, "add")
        self.assertIsNone(args.source)
        self.assertIsNone(args.command_name)
        self.assertFalse(args.list)
        self.assertFalse(args.force)

    def test_parser_accepts_agents_list_command(self) -> None:
        parser = cli.build_parser()

        args = parser.parse_args(["agents", "list"])

        self.assertEqual(args.command, "agents")
        self.assertEqual(args.agents_action, "list")

    def test_parser_accepts_agents_add_command(self) -> None:
        parser = cli.build_parser()

        args = parser.parse_args(
            [
                "agents",
                "add",
                "owner/repo",
                "--agent",
                "code-reviewer",
                "--list",
                "--force",
            ]
        )

        self.assertEqual(args.command, "agents")
        self.assertEqual(args.agents_action, "add")
        self.assertEqual(args.source, "owner/repo")
        self.assertEqual(args.agent_name, "code-reviewer")
        self.assertTrue(args.list)
        self.assertTrue(args.force)

    def test_parser_accepts_agents_add_without_source(self) -> None:
        parser = cli.build_parser()

        args = parser.parse_args(["agents", "add"])

        self.assertEqual(args.command, "agents")
        self.assertEqual(args.agents_action, "add")
        self.assertIsNone(args.source)
        self.assertIsNone(args.agent_name)
        self.assertFalse(args.list)
        self.assertFalse(args.force)

    def test_parser_rejects_removed_skills_flag(self) -> None:
        with self.assertRaises(SystemExit) as exc_info:
            cli.build_parser().parse_args(["--skills"])

        self.assertEqual(exc_info.exception.code, 2)

    def test_parser_accepts_mcp_flag(self) -> None:
        parser = cli.build_parser()

        args = parser.parse_args(["--mcp", "web"])

        self.assertTrue(args.mcp)

    def test_parser_accepts_agents_flag(self) -> None:
        parser = cli.build_parser()

        args = parser.parse_args(["--agents", "web"])

        self.assertTrue(args.agents)

    def test_parser_accepts_sandbox_default_web_command(self) -> None:
        parser = cli.build_parser()

        args = parser.parse_args(["sandbox", "--rebuild", "--read-only-repo", "-d"])

        self.assertEqual(args.command, "sandbox")
        self.assertIsNone(args.sandbox_command)
        self.assertTrue(args.rebuild)
        self.assertTrue(args.read_only_repo)
        self.assertTrue(args.detach)
        self.assertEqual(args.image, cli.DEFAULT_SANDBOX_IMAGE)
        self.assertEqual(args.host, "127.0.0.1")
        self.assertEqual(args.port, cli.DEFAULT_WEB_PORT)

    def test_parser_accepts_sandbox_web_command(self) -> None:
        parser = cli.build_parser()

        args = parser.parse_args(
            [
                "sandbox",
                "--image",
                "custom:dev",
                "--env-file",
                ".env.sandbox",
                "--local-source",
                "--detach",
                "web",
                "--host",
                "127.0.0.1",
                "--port",
                "9001",
                "--title",
                "Sandbox",
            ]
        )

        self.assertEqual(args.command, "sandbox")
        self.assertEqual(args.sandbox_command, "web")
        self.assertEqual(args.image, "custom:dev")
        self.assertEqual(args.env_file, Path(".env.sandbox"))
        self.assertTrue(args.local_source)
        self.assertTrue(args.detach)
        self.assertEqual(args.port, 9001)
        self.assertEqual(args.title, "Sandbox")

    def test_parser_accepts_sandbox_run_command(self) -> None:
        parser = cli.build_parser()

        args = parser.parse_args(
            [
                "sandbox",
                "run",
                "--prompt",
                "Inspect the repo",
                "--image",
                "diagram.png",
                "--project-dir",
                "app",
                "--session-id",
                "session-1",
            ]
        )

        self.assertEqual(args.command, "sandbox")
        self.assertEqual(args.sandbox_command, "run")
        self.assertEqual(args.prompt, "Inspect the repo")
        self.assertEqual(args.images, ["diagram.png"])
        self.assertEqual(args.project_dir, Path("app"))
        self.assertEqual(args.session_id, "session-1")

    def test_parser_accepts_service_tier_flag(self) -> None:
        parser = cli.build_parser()

        args = parser.parse_args(["--service-tier", "flex", "web"])

        self.assertEqual(args.service_tier, "flex")

    def test_parser_rejects_unsupported_service_tier(self) -> None:
        parser = cli.build_parser()

        with self.assertRaises(SystemExit) as exc_info:
            parser.parse_args(["--service-tier", "scale", "web"])

        self.assertEqual(exc_info.exception.code, 2)
