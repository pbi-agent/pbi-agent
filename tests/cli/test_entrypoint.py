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
from pbi_agent.agents.project_installer import ProjectAgentInstallResult
from pbi_agent.commands.project_installer import (
    ProjectCommandInstallError,
    ProjectCommandInstallResult,
)


def _fake_command_install(
    source: str,
    *,
    command_name: str | None = None,
    force: bool = False,
    workspace: Path | None = None,
) -> ProjectCommandInstallResult:
    assert command_name is not None
    root = (workspace or Path.cwd()).resolve()
    install_path = root / ".agents" / "commands" / f"{command_name}.md"
    if install_path.exists() and not force:
        raise ProjectCommandInstallError(
            f"Command already installed at {install_path}."
        )
    install_path.parent.mkdir(parents=True, exist_ok=True)
    install_path.write_text(
        (
            f"---\nname: {command_name}\ndescription: {command_name} command.\n---\n\n"
            f"# {command_name}\n"
        ),
        encoding="utf-8",
    )
    return ProjectCommandInstallResult(
        command_id=command_name,
        slash_alias=f"/{command_name}",
        install_path=install_path,
        source=source,
        ref=None,
        subpath=f"commands/{command_name}.md",
    )


def _fake_agent_install(
    source: str,
    *,
    agent_name: str | None = None,
    force: bool = False,
    workspace: Path | None = None,
) -> ProjectAgentInstallResult:
    assert agent_name is not None
    root = (workspace or Path.cwd()).resolve()
    install_path = root / ".agents" / "agents" / f"{agent_name}.md"
    if install_path.exists() and not force:
        raise AssertionError("init should pre-skip existing default agents")
    install_path.parent.mkdir(parents=True, exist_ok=True)
    install_path.write_text(
        (
            f"---\nname: {agent_name}\ndescription: Reviews code changes.\n---\n\n"
            "Review code changes.\n"
        ),
        encoding="utf-8",
    )
    return ProjectAgentInstallResult(
        agent_name=agent_name,
        install_path=install_path,
        source=source,
        ref=None,
        subpath=f"agents/{agent_name}.md",
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

    def test_main_defaults_to_web_for_global_options_only(self) -> None:
        with patch(
            "pbi_agent.cli.entrypoint._handle_web_command", return_value=17
        ) as mock_web:
            rc = cli.main([])

        self.assertEqual(rc, 17)
        args, runtime = mock_web.call_args.args
        settings = getattr(runtime, "settings", runtime)
        self.assertEqual(args.command, "web")
        self.assertEqual(args.host, "127.0.0.1")
        self.assertEqual(args.port, cli.DEFAULT_WEB_PORT)
        self.assertEqual(settings.provider, "openai")

    def test_main_inserts_web_before_web_specific_flags(self) -> None:
        with patch(
            "pbi_agent.cli.entrypoint._handle_web_command", return_value=23
        ) as mock_web:
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

        self.assertNotEqual(rc, 0)
        self.assertIn("no longer supported with `pbi-agent web`", stderr.getvalue())

    def test_main_sandbox_routes_without_resolving_settings(self) -> None:
        with (
            patch(
                "pbi_agent.cli.entrypoint._handle_sandbox_command", return_value=33
            ) as mock_handle,
            patch("pbi_agent.cli.entrypoint.resolve_runtime") as mock_resolve_runtime,
            patch(
                "pbi_agent.cli.entrypoint.resolve_web_runtime"
            ) as mock_resolve_web_runtime,
        ):
            rc = cli.main(["sandbox", "run", "--prompt", "hello"])

        self.assertEqual(rc, 33)
        self.assertEqual(mock_handle.call_args.args[0].command, "sandbox")
        self.assertEqual(mock_handle.call_args.args[0].sandbox_command, "run")
        mock_resolve_runtime.assert_not_called()
        mock_resolve_web_runtime.assert_not_called()

    def test_main_agents_list_lists_project_agents_without_settings(self) -> None:
        stdout = io.StringIO()

        with tempfile.TemporaryDirectory() as tmpdir:
            original_cwd = Path.cwd()
            root_dir = Path(tmpdir).resolve()
            agents_dir = root_dir / ".agents" / "agents"
            agents_dir.mkdir(parents=True)
            (agents_dir / "code-reviewer.md").write_text(
                "---\n"
                "name: code-reviewer\n"
                "description: Reviews code changes.\n"
                "---\n\n"
                "You are a code reviewer.\n",
                encoding="utf-8",
            )

            try:
                os.chdir(root_dir)
                with patch("sys.stdout", stdout):
                    rc = cli.main(["agents", "list"])
            finally:
                os.chdir(original_cwd)

        self.assertEqual(rc, 0)
        output = stdout.getvalue()
        self.assertIn("Project Agents", output)
        self.assertIn("code-reviewer", output)

    def test_main_agents_add_routes_without_settings(self) -> None:
        with (
            patch(
                "pbi_agent.cli.entrypoint._handle_agents_command", return_value=41
            ) as mock_handle,
            patch("pbi_agent.cli.entrypoint.resolve_runtime") as mock_resolve_runtime,
            patch(
                "pbi_agent.cli.entrypoint.resolve_web_runtime"
            ) as mock_resolve_web_runtime,
        ):
            rc = cli.main(["agents", "add", "owner/repo"])

        self.assertEqual(rc, 41)
        self.assertEqual(mock_handle.call_args.args[0].command, "agents")
        self.assertEqual(mock_handle.call_args.args[0].agents_action, "add")
        mock_resolve_runtime.assert_not_called()
        mock_resolve_web_runtime.assert_not_called()

    def test_main_init_creates_agents_file_without_settings(self) -> None:
        stdout = io.StringIO()

        with tempfile.TemporaryDirectory() as tmpdir:
            original_cwd = Path.cwd()
            root_dir = Path(tmpdir).resolve()
            try:
                os.chdir(root_dir)
                with (
                    patch("sys.stdout", stdout),
                    patch(
                        "pbi_agent.init_agents.install_project_command",
                        side_effect=_fake_command_install,
                    ),
                    patch(
                        "pbi_agent.init_agents.install_project_agent",
                        side_effect=_fake_agent_install,
                    ),
                    patch(
                        "pbi_agent.cli.entrypoint.resolve_runtime"
                    ) as mock_resolve_runtime,
                    patch(
                        "pbi_agent.cli.entrypoint.resolve_web_runtime"
                    ) as mock_resolve_web_runtime,
                ):
                    rc = cli.main(["init"])
            finally:
                os.chdir(original_cwd)

            agents_path = root_dir / "AGENTS.md"
            content = agents_path.read_text(encoding="utf-8")
            command_created = (
                root_dir / ".agents" / "commands" / "execute.md"
            ).is_file()
            agent_created = (
                root_dir / ".agents" / "agents" / "code-reviewer.md"
            ).is_file()
            generated_agent_created = (
                root_dir / ".agents" / "agents" / "plan.md"
            ).exists()

        self.assertEqual(rc, 0)
        self.assertIn("Created AGENTS.md", stdout.getvalue())
        self.assertIn("Installed command `/execute`", stdout.getvalue())
        self.assertIn("Installed sub-agent `code-reviewer`", stdout.getvalue())
        self.assertTrue(content.startswith("# AGENTS.md"))
        self.assertTrue(command_created)
        self.assertTrue(agent_created)
        self.assertFalse(generated_agent_created)
        mock_resolve_runtime.assert_not_called()
        mock_resolve_web_runtime.assert_not_called()

    def test_main_init_protects_existing_agents_file_by_default(self) -> None:
        stdout = io.StringIO()

        with tempfile.TemporaryDirectory() as tmpdir:
            original_cwd = Path.cwd()
            root_dir = Path(tmpdir).resolve()
            agents_path = root_dir / "AGENTS.md"
            agents_path.write_text("existing", encoding="utf-8")
            try:
                os.chdir(root_dir)
                with (
                    patch("sys.stdout", stdout),
                    patch(
                        "pbi_agent.init_agents.install_project_command",
                        side_effect=_fake_command_install,
                    ),
                    patch(
                        "pbi_agent.init_agents.install_project_agent",
                        side_effect=_fake_agent_install,
                    ),
                ):
                    rc = cli.main(["init"])
            finally:
                os.chdir(original_cwd)
            content = agents_path.read_text(encoding="utf-8")

        self.assertEqual(rc, 0)
        self.assertEqual(content, "existing")
        self.assertIn("Skipped AGENTS.md", stdout.getvalue())
        self.assertIn("already exists", stdout.getvalue())
        self.assertIn("--force", stdout.getvalue())

    def test_main_init_force_overwrites_existing_agents_file(self) -> None:
        stdout = io.StringIO()

        with tempfile.TemporaryDirectory() as tmpdir:
            original_cwd = Path.cwd()
            root_dir = Path(tmpdir).resolve()
            agents_path = root_dir / "AGENTS.md"
            agents_path.write_text("existing", encoding="utf-8")
            command_path = root_dir / ".agents" / "commands" / "execute.md"
            command_path.parent.mkdir(parents=True, exist_ok=True)
            command_path.write_text("old command", encoding="utf-8")
            agent_path = root_dir / ".agents" / "agents" / "code-reviewer.md"
            agent_path.parent.mkdir(parents=True, exist_ok=True)
            agent_path.write_text("old agent", encoding="utf-8")
            try:
                os.chdir(root_dir)
                with (
                    patch("sys.stdout", stdout),
                    patch(
                        "pbi_agent.init_agents.install_project_command",
                        side_effect=_fake_command_install,
                    ),
                    patch(
                        "pbi_agent.init_agents.install_project_agent",
                        side_effect=_fake_agent_install,
                    ),
                ):
                    rc = cli.main(["init", "--force"])
            finally:
                os.chdir(original_cwd)
            content = agents_path.read_text(encoding="utf-8")
            command_content = command_path.read_text(encoding="utf-8")
            agent_content = agent_path.read_text(encoding="utf-8")

        self.assertEqual(rc, 0)
        self.assertIn("Overwrote AGENTS.md", stdout.getvalue())
        self.assertIn("Overwrote command `/execute`", stdout.getvalue())
        self.assertIn("Overwrote sub-agent `code-reviewer`", stdout.getvalue())
        self.assertTrue(content.startswith("# AGENTS.md"))
        self.assertNotEqual(command_content, "old command")
        self.assertNotEqual(agent_content, "old agent")

    def test_main_init_reports_catalog_failure_but_returns_success(self) -> None:
        stdout = io.StringIO()

        def fail_command_install(
            source: str,
            *,
            command_name: str | None = None,
            force: bool = False,
            workspace: Path | None = None,
        ) -> ProjectCommandInstallResult:
            del source, command_name, force, workspace
            raise ProjectCommandInstallError("catalog unavailable")

        with tempfile.TemporaryDirectory() as tmpdir:
            original_cwd = Path.cwd()
            root_dir = Path(tmpdir).resolve()
            try:
                os.chdir(root_dir)
                with (
                    patch("sys.stdout", stdout),
                    patch(
                        "pbi_agent.init_agents.install_project_command",
                        side_effect=fail_command_install,
                    ),
                    patch(
                        "pbi_agent.init_agents.install_project_agent",
                        side_effect=_fake_agent_install,
                    ),
                ):
                    rc = cli.main(["init"])
            finally:
                os.chdir(original_cwd)
            agents_created = (root_dir / "AGENTS.md").is_file()

        self.assertEqual(rc, 0)
        self.assertTrue(agents_created)
        self.assertIn(
            "Failed command `/execute`: catalog unavailable",
            stdout.getvalue(),
        )

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

    def test_service_tier_with_azure_provider_errors(self) -> None:
        stderr = io.StringIO()

        with (
            patch("pbi_agent.config.load_dotenv"),
            patch("sys.stderr", stderr),
        ):
            rc = cli.main(
                [
                    "--provider",
                    "azure",
                    "--responses-url",
                    "https://example-resource.openai.azure.com/openai/v1/responses",
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
                    patch("pbi_agent.cli.entrypoint.configure_logging"),
                    patch(
                        "pbi_agent.cli.entrypoint._handle_web_command", return_value=0
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
        runtime = Mock()
        runtime.settings = self._settings()
        runtime.settings.provider = "xai"
        runtime.settings.model = "grok-4.20"

        with (
            patch("pbi_agent.cli.entrypoint.resolve_runtime", return_value=runtime),
            patch("pbi_agent.cli.entrypoint.configure_logging"),
            patch(
                "pbi_agent.cli.entrypoint._handle_run_command", return_value=0
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
        _args, resolved_runtime = mock_run.call_args.args
        self.assertEqual(resolved_runtime.settings.provider, "xai")
        self.assertEqual(resolved_runtime.settings.model, "grok-4.20")
