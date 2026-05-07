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
from pbi_agent.cli import catalogs as cli_catalogs
from pbi_agent.config import (
    load_internal_config,
)


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

    def test_main_skills_list_lists_project_skills_without_settings(self) -> None:
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
                    rc = cli.main(["skills", "list"])
            finally:
                os.chdir(original_cwd)

        self.assertEqual(rc, 0)
        output = stdout.getvalue()
        self.assertIn("Project Skills", output)
        self.assertIn("repo-skill", output)

    def test_main_skills_add_routes_without_settings(self) -> None:
        with (
            patch(
                "pbi_agent.cli.entrypoint._handle_skills_command", return_value=41
            ) as mock_handle,
            patch("pbi_agent.cli.entrypoint.resolve_runtime") as mock_resolve_runtime,
            patch(
                "pbi_agent.cli.entrypoint.resolve_web_runtime"
            ) as mock_resolve_web_runtime,
        ):
            rc = cli.main(["skills", "add", "owner/repo"])

        self.assertEqual(rc, 41)
        self.assertEqual(mock_handle.call_args.args[0].command, "skills")
        self.assertEqual(mock_handle.call_args.args[0].skills_action, "add")
        mock_resolve_runtime.assert_not_called()
        mock_resolve_web_runtime.assert_not_called()

    def test_handle_skills_add_without_source_lists_default_catalog(self) -> None:
        args = cli.build_parser().parse_args(["skills", "add"])
        listing = object()

        with (
            patch(
                "pbi_agent.skills.project_installer.list_remote_project_skills",
                return_value=listing,
            ) as mock_list,
            patch(
                "pbi_agent.skills.project_installer.render_remote_skill_listing",
                return_value=17,
            ) as mock_render,
            patch(
                "pbi_agent.skills.project_installer.install_project_skill"
            ) as mock_install,
        ):
            rc = cli_catalogs._handle_skills_add_command(args)

        self.assertEqual(rc, 17)
        mock_list.assert_called_once_with("pbi-agent/skills")
        mock_render.assert_called_once_with(listing)
        mock_install.assert_not_called()

    def test_handle_skills_add_with_skill_and_no_source_installs_default_catalog(
        self,
    ) -> None:
        args = cli.build_parser().parse_args(
            ["skills", "add", "--skill", "workspace-helper"]
        )
        result = Mock(name="result")
        result.name = "workspace-helper"
        result.install_path = Path("/tmp/workspace/.agents/skills/workspace-helper")

        with (
            patch(
                "pbi_agent.skills.project_installer.install_project_skill",
                return_value=result,
            ) as mock_install,
            patch("sys.stdout", new_callable=io.StringIO) as stdout,
        ):
            rc = cli_catalogs._handle_skills_add_command(args)

        self.assertEqual(rc, 0)
        mock_install.assert_called_once()
        self.assertEqual(mock_install.call_args.args[0], "pbi-agent/skills")
        self.assertEqual(
            mock_install.call_args.kwargs["skill_name"], "workspace-helper"
        )
        self.assertIn("Installed skill 'workspace-helper'", stdout.getvalue())

    def test_handle_skills_add_with_explicit_source_and_list_keeps_source(self) -> None:
        args = cli.build_parser().parse_args(
            ["skills", "add", "./skills/local", "--list"]
        )
        listing = object()

        with (
            patch(
                "pbi_agent.skills.project_installer.list_remote_project_skills",
                return_value=listing,
            ) as mock_list,
            patch(
                "pbi_agent.skills.project_installer.render_remote_skill_listing",
                return_value=9,
            ) as mock_render,
        ):
            rc = cli_catalogs._handle_skills_add_command(args)

        self.assertEqual(rc, 9)
        mock_list.assert_called_once_with("./skills/local")
        mock_render.assert_called_once_with(listing)

    def test_main_commands_list_lists_project_commands_without_settings(self) -> None:
        stdout = io.StringIO()

        with tempfile.TemporaryDirectory() as tmpdir:
            original_cwd = Path.cwd()
            root_dir = Path(tmpdir).resolve()
            commands_dir = root_dir / ".agents" / "commands"
            commands_dir.mkdir(parents=True)
            (commands_dir / "execute.md").write_text(
                "# Execute\n\nRun the task end-to-end.\n",
                encoding="utf-8",
            )

            try:
                os.chdir(root_dir)
                with patch("sys.stdout", stdout):
                    rc = cli.main(["commands", "list"])
            finally:
                os.chdir(original_cwd)

        self.assertEqual(rc, 0)
        output = stdout.getvalue()
        self.assertIn("Project Commands", output)
        self.assertIn("/execute", output)

    def test_main_commands_add_routes_without_settings(self) -> None:
        with (
            patch(
                "pbi_agent.cli.entrypoint._handle_commands_command", return_value=37
            ) as mock_handle,
            patch("pbi_agent.cli.entrypoint.resolve_runtime") as mock_resolve_runtime,
            patch(
                "pbi_agent.cli.entrypoint.resolve_web_runtime"
            ) as mock_resolve_web_runtime,
        ):
            rc = cli.main(["commands", "add", "owner/repo"])

        self.assertEqual(rc, 37)
        self.assertEqual(mock_handle.call_args.args[0].command, "commands")
        self.assertEqual(mock_handle.call_args.args[0].commands_action, "add")
        mock_resolve_runtime.assert_not_called()
        mock_resolve_web_runtime.assert_not_called()

    def test_handle_commands_add_without_source_lists_default_catalog(self) -> None:
        args = cli.build_parser().parse_args(["commands", "add"])
        listing = object()

        with (
            patch(
                "pbi_agent.commands.project_installer.list_remote_project_commands",
                return_value=listing,
            ) as mock_list,
            patch(
                "pbi_agent.commands.project_installer.render_remote_command_listing",
                return_value=13,
            ) as mock_render,
            patch(
                "pbi_agent.commands.project_installer.install_project_command"
            ) as mock_install,
        ):
            rc = cli_catalogs._handle_commands_add_command(args)

        self.assertEqual(rc, 13)
        mock_list.assert_called_once_with("pbi-agent/commands")
        mock_render.assert_called_once_with(listing)
        mock_install.assert_not_called()

    def test_handle_commands_add_with_command_and_no_source_installs_default_catalog(
        self,
    ) -> None:
        args = cli.build_parser().parse_args(
            ["commands", "add", "--command", "execute"]
        )
        result = Mock(name="result")
        result.slash_alias = "/execute"
        result.install_path = Path("/tmp/workspace/.agents/commands/execute.md")

        with (
            patch(
                "pbi_agent.commands.project_installer.install_project_command",
                return_value=result,
            ) as mock_install,
            patch("sys.stdout", new_callable=io.StringIO) as stdout,
        ):
            rc = cli_catalogs._handle_commands_add_command(args)

        self.assertEqual(rc, 0)
        mock_install.assert_called_once()
        self.assertEqual(mock_install.call_args.args[0], "pbi-agent/commands")
        self.assertEqual(mock_install.call_args.kwargs["command_name"], "execute")
        self.assertIn("Installed command '/execute'", stdout.getvalue())

    def test_handle_commands_add_with_explicit_source_and_list_keeps_source(
        self,
    ) -> None:
        args = cli.build_parser().parse_args(
            ["commands", "add", "./commands/local", "--list"]
        )
        listing = object()

        with (
            patch(
                "pbi_agent.commands.project_installer.list_remote_project_commands",
                return_value=listing,
            ) as mock_list,
            patch(
                "pbi_agent.commands.project_installer.render_remote_command_listing",
                return_value=11,
            ) as mock_render,
        ):
            rc = cli_catalogs._handle_commands_add_command(args)

        self.assertEqual(rc, 11)
        mock_list.assert_called_once_with("./commands/local")
        mock_render.assert_called_once_with(listing)

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
            agents_dir = root_dir / ".agents" / "agents"
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

    def test_handle_agents_add_without_source_lists_default_catalog(self) -> None:
        args = cli.build_parser().parse_args(["agents", "add"])
        listing = object()

        with (
            patch(
                "pbi_agent.agents.project_installer.list_remote_project_agents",
                return_value=listing,
            ) as mock_list,
            patch(
                "pbi_agent.agents.project_installer.render_remote_agent_listing",
                return_value=15,
            ) as mock_render,
            patch(
                "pbi_agent.agents.project_installer.install_project_agent"
            ) as mock_install,
        ):
            rc = cli_catalogs._handle_agents_add_command(args)

        self.assertEqual(rc, 15)
        mock_list.assert_called_once_with("pbi-agent/agents")
        mock_render.assert_called_once_with(listing)
        mock_install.assert_not_called()

    def test_handle_agents_add_with_agent_and_no_source_installs_default_catalog(
        self,
    ) -> None:
        args = cli.build_parser().parse_args(
            ["agents", "add", "--agent", "code-reviewer"]
        )
        result = Mock(name="result")
        result.agent_name = "code-reviewer"
        result.install_path = Path("/tmp/workspace/.agents/agents/code-reviewer.md")

        with (
            patch(
                "pbi_agent.agents.project_installer.install_project_agent",
                return_value=result,
            ) as mock_install,
            patch("sys.stdout", new_callable=io.StringIO) as stdout,
        ):
            rc = cli_catalogs._handle_agents_add_command(args)

        self.assertEqual(rc, 0)
        mock_install.assert_called_once()
        self.assertEqual(mock_install.call_args.args[0], "pbi-agent/agents")
        self.assertEqual(mock_install.call_args.kwargs["agent_name"], "code-reviewer")
        self.assertIn("Installed agent 'code-reviewer'", stdout.getvalue())

    def test_handle_agents_add_with_explicit_source_and_list_keeps_source(
        self,
    ) -> None:
        args = cli.build_parser().parse_args(
            ["agents", "add", "./agents/local", "--list"]
        )
        listing = object()

        with (
            patch(
                "pbi_agent.agents.project_installer.list_remote_project_agents",
                return_value=listing,
            ) as mock_list,
            patch(
                "pbi_agent.agents.project_installer.render_remote_agent_listing",
                return_value=17,
            ) as mock_render,
        ):
            rc = cli_catalogs._handle_agents_add_command(args)

        self.assertEqual(rc, 17)
        mock_list.assert_called_once_with("./agents/local")
        mock_render.assert_called_once_with(listing)
