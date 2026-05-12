from __future__ import annotations

import os
import sys
import tempfile
import unittest

from pathlib import Path
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from pbi_agent import __version__
from pbi_agent import cli
from pbi_agent.cli import sandbox as cli_sandbox
from pbi_agent.cli import shared as cli_shared


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

    def test_sandbox_default_image_is_versioned(self) -> None:
        self.assertEqual(
            cli.DEFAULT_SANDBOX_IMAGE,
            f"pbi-agent-sandbox:{cli_shared._docker_tag_safe(__version__)}",
        )
        self.assertNotEqual(cli.DEFAULT_SANDBOX_IMAGE, "pbi-agent-sandbox:local")

    def test_build_sandbox_run_command_hardens_container_and_mounts_workspace(
        self,
    ) -> None:
        parser = cli.build_parser()
        args = parser.parse_args(
            [
                "--provider",
                "openai",
                "--api-key",
                "secret-key",
                "sandbox",
                "--env-file",
                ".env.sandbox",
                "--read-only-repo",
                "web",
                "--port",
                "9001",
            ]
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            original_cwd = Path.cwd()
            host_config_dir = Path(tmpdir) / "missing-config"
            try:
                os.chdir(tmpdir)
                with patch(
                    "pbi_agent.cli.sandbox._sandbox_host_config_dir",
                    return_value=host_config_dir,
                ):
                    command, container_env = cli_sandbox._build_sandbox_run_command(
                        args,
                        "sandbox:test",
                    )
            finally:
                os.chdir(original_cwd)

        workspace = Path(tmpdir).resolve()

        self.assertEqual(command[:2], ["docker", "run"])
        self.assertIn("--rm", command)
        self.assertIn("--init", command)
        self.assertIn("--read-only", command)
        self.assertNotIn("--detach", command)
        self.assertIn("--cap-drop", command)
        self.assertIn("ALL", command)
        self.assertIn("--security-opt", command)
        self.assertIn("no-new-privileges:true", command)
        self.assertIn("--pids-limit", command)
        self.assertIn("512", command)
        self.assertIn("--memory", command)
        self.assertIn("4g", command)
        self.assertIn("--label", command)
        self.assertIn("pbi-agent.sandbox=1", command)
        self.assertIn(f"pbi-agent.workspace={workspace}", command)
        self.assertIn(f"pbi-agent.workspace-key={workspace}", command)
        self.assertIn("--tmpfs", command)
        self.assertIn("/tmp:rw,noexec,nosuid,size=256m", command)
        self.assertNotIn(f"{cli.SANDBOX_HOME}/.cache:rw", command)
        self.assertIn("--env-file", command)
        self.assertIn(str((Path(tmpdir) / ".env.sandbox").resolve()), command)
        self.assertIn("--publish", command)
        self.assertIn("127.0.0.1:9001:9001", command)
        self.assertIn("sandbox:test", command)
        self.assertNotIn("/var/run/docker.sock", " ".join(command))

        container_workspace = cli_sandbox._sandbox_container_workspace(workspace)
        mounts = [
            command[index + 1]
            for index, value in enumerate(command)
            if value == "--mount"
        ]
        self.assertIn(
            f"type=bind,source={workspace},target={container_workspace},readonly",
            mounts,
        )
        self.assertIn(
            f"type=volume,source={cli_sandbox._sandbox_home_volume(workspace)},"
            f"target={cli.SANDBOX_HOME}",
            mounts,
        )
        self.assertIn(
            f"type=bind,source={host_config_dir},target={cli.SANDBOX_HOME}/.pbi-agent",
            mounts,
        )
        self.assertNotIn(f"{cli.SANDBOX_HOME}:rw", command)
        self.assertNotIn(f"{cli.SANDBOX_HOME}/.config:rw", command)
        self.assertNotIn(f"{cli.SANDBOX_HOME}/.local:rw", command)
        self.assertNotIn(f"{cli.SANDBOX_HOME}/.bun:rw", command)
        workdir_index = command.index("--workdir")
        self.assertEqual(command[workdir_index + 1], container_workspace)
        self.assertIn("--env", command)
        self.assertIn("BROWSER", command)
        self.assertIn("PBI_AGENT_SANDBOX", command)
        self.assertIn("PBI_AGENT_WORKSPACE_KEY", command)
        self.assertIn("PBI_AGENT_WORKSPACE_DISPLAY_PATH", command)
        self.assertIn("PBI_AGENT_PROVIDER", command)
        self.assertIn("PBI_AGENT_API_KEY", command)
        self.assertEqual(container_env["BROWSER"], "/bin/true")
        self.assertEqual(container_env["PBI_AGENT_SANDBOX"], "1")
        self.assertEqual(container_env["PBI_AGENT_WORKSPACE_KEY"], str(workspace))
        self.assertEqual(
            container_env["PBI_AGENT_WORKSPACE_DISPLAY_PATH"],
            str(workspace),
        )
        self.assertEqual(container_env["PBI_AGENT_PROVIDER"], "openai")
        self.assertEqual(container_env["PBI_AGENT_API_KEY"], "secret-key")
        self.assertNotIn("secret-key", command)

        image_index = command.index("sandbox:test")
        self.assertEqual(
            command[image_index + 1 :],
            ["web", "--host", "0.0.0.0", "--port", "9001"],
        )

    def test_build_sandbox_run_command_can_detach_without_tty(self) -> None:
        parser = cli.build_parser()
        args = parser.parse_args(["sandbox", "--detach", "web", "--port", "9001"])

        with tempfile.TemporaryDirectory() as tmpdir:
            original_cwd = Path.cwd()
            try:
                os.chdir(tmpdir)
                with patch(
                    "pbi_agent.cli.sandbox._sandbox_host_config_dir",
                    return_value=Path(tmpdir) / "missing-config",
                ):
                    command, _container_env = cli_sandbox._build_sandbox_run_command(
                        args,
                        "sandbox:test",
                    )
            finally:
                os.chdir(original_cwd)

        self.assertIn("--detach", command)
        self.assertNotIn("-it", command)

    def test_build_sandbox_run_command_mounts_existing_host_config(
        self,
    ) -> None:
        parser = cli.build_parser()
        args = parser.parse_args(["sandbox", "run", "--prompt", "hello"])

        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir) / "repo"
            workspace.mkdir()
            host_config_dir = Path(tmpdir) / ".pbi-agent"
            host_config_dir.mkdir()
            original_cwd = Path.cwd()
            try:
                os.chdir(workspace)
                with patch(
                    "pbi_agent.cli.sandbox._sandbox_host_config_dir",
                    return_value=host_config_dir,
                ):
                    command, _container_env = cli_sandbox._build_sandbox_run_command(
                        args,
                        "sandbox:test",
                    )
            finally:
                os.chdir(original_cwd)

        mounts = [
            command[index + 1]
            for index, value in enumerate(command)
            if value == "--mount"
        ]
        self.assertIn(
            f"type=bind,source={host_config_dir},target={cli.SANDBOX_HOME}/.pbi-agent",
            mounts,
        )
        self.assertNotIn(
            cli_sandbox._sandbox_config_volume(workspace.resolve()), " ".join(mounts)
        )

    def test_build_sandbox_run_command_creates_and_mounts_host_config(
        self,
    ) -> None:
        parser = cli.build_parser()
        args = parser.parse_args(["sandbox", "run", "--prompt", "hello"])

        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir) / "repo"
            workspace.mkdir()
            host_config_dir = Path(tmpdir) / ".pbi-agent"
            original_cwd = Path.cwd()
            try:
                os.chdir(workspace)
                with patch(
                    "pbi_agent.cli.sandbox._sandbox_host_config_dir",
                    return_value=host_config_dir,
                ):
                    command, _container_env = cli_sandbox._build_sandbox_run_command(
                        args,
                        "sandbox:test",
                    )
            finally:
                os.chdir(original_cwd)

            mounts = [
                command[index + 1]
                for index, value in enumerate(command)
                if value == "--mount"
            ]
            self.assertIn(
                f"type=bind,source={host_config_dir},"
                f"target={cli.SANDBOX_HOME}/.pbi-agent",
                mounts,
            )
            self.assertTrue(host_config_dir.is_dir())

    def test_build_sandbox_run_command_mounts_host_git_account_files(
        self,
    ) -> None:
        parser = cli.build_parser()
        args = parser.parse_args(["sandbox", "run", "--prompt", "hello"])

        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir) / "repo"
            workspace.mkdir()
            host_home = Path(tmpdir) / "home"
            host_home.mkdir()
            (host_home / ".gitconfig").write_text("[user]\n", encoding="utf-8")
            (host_home / ".git-credentials").write_text(
                "https://token@example.invalid\n",
                encoding="utf-8",
            )
            git_config_dir = host_home / ".config" / "git"
            git_config_dir.mkdir(parents=True)
            (git_config_dir / "config").write_text("[credential]\n", encoding="utf-8")
            gh_config_dir = host_home / ".config" / "gh"
            gh_config_dir.mkdir()
            (gh_config_dir / "hosts.yml").write_text("github.com:\n", encoding="utf-8")
            ssh_dir = host_home / ".ssh"
            ssh_dir.mkdir()
            (ssh_dir / "config").write_text("Host github.com\n", encoding="utf-8")
            original_cwd = Path.cwd()
            try:
                os.chdir(workspace)
                with patch(
                    "pbi_agent.cli.sandbox._sandbox_host_home_dir",
                    return_value=host_home,
                ):
                    command, _container_env = cli_sandbox._build_sandbox_run_command(
                        args,
                        "sandbox:test",
                    )
            finally:
                os.chdir(original_cwd)

        mounts = [
            command[index + 1]
            for index, value in enumerate(command)
            if value == "--mount"
        ]
        self.assertIn(
            f"type=bind,source={(host_home / '.gitconfig').resolve()},"
            f"target={cli.SANDBOX_HOME}/.gitconfig,readonly",
            mounts,
        )
        self.assertIn(
            f"type=bind,source={(host_home / '.git-credentials').resolve()},"
            f"target={cli.SANDBOX_HOME}/.git-credentials,readonly",
            mounts,
        )
        self.assertIn(
            f"type=bind,source={git_config_dir.resolve()},"
            f"target={cli.SANDBOX_HOME}/.config/git,readonly",
            mounts,
        )
        self.assertIn(
            f"type=bind,source={gh_config_dir.resolve()},"
            f"target={cli.SANDBOX_HOME}/.config/gh,readonly",
            mounts,
        )
        self.assertIn(
            f"type=bind,source={ssh_dir.resolve()},"
            f"target={cli.SANDBOX_HOME}/.ssh,readonly",
            mounts,
        )

    def test_build_sandbox_run_command_skips_missing_host_git_account_files(
        self,
    ) -> None:
        parser = cli.build_parser()
        args = parser.parse_args(["sandbox", "run", "--prompt", "hello"])

        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir) / "repo"
            workspace.mkdir()
            host_home = Path(tmpdir) / "home"
            host_home.mkdir()
            original_cwd = Path.cwd()
            try:
                os.chdir(workspace)
                with patch(
                    "pbi_agent.cli.sandbox._sandbox_host_home_dir",
                    return_value=host_home,
                ):
                    command, _container_env = cli_sandbox._build_sandbox_run_command(
                        args,
                        "sandbox:test",
                    )
            finally:
                os.chdir(original_cwd)

        mounts = [
            command[index + 1]
            for index, value in enumerate(command)
            if value == "--mount"
        ]
        mount_text = " ".join(mounts)
        self.assertNotIn(f"{cli.SANDBOX_HOME}/.gitconfig", mount_text)
        self.assertNotIn(f"{cli.SANDBOX_HOME}/.git-credentials", mount_text)
        self.assertNotIn(f"{cli.SANDBOX_HOME}/.config/git", mount_text)
        self.assertNotIn(f"{cli.SANDBOX_HOME}/.config/gh", mount_text)
        self.assertNotIn(f"{cli.SANDBOX_HOME}/.ssh", mount_text)

    def test_handle_sandbox_web_opens_browser_from_host(self) -> None:
        parser = cli.build_parser()
        args = parser.parse_args(["sandbox", "web", "--port", "9001"])
        completed = Mock(returncode=0)

        with (
            patch("pbi_agent.cli.sandbox._check_docker_available", return_value=None),
            patch("pbi_agent.cli.sandbox._is_web_port_available", return_value=True),
            patch(
                "pbi_agent.cli.sandbox._sandbox_dockerfile_path",
                return_value=Path("Dockerfile"),
            ),
            patch("pbi_agent.cli.sandbox._docker_image_exists", return_value=True),
            patch(
                "pbi_agent.cli.sandbox._build_sandbox_run_command",
                return_value=(["docker", "run"], {"ENV": "value"}),
            ) as mock_build_run,
            patch(
                "pbi_agent.cli.sandbox.subprocess.run", return_value=completed
            ) as mock_run,
            patch(
                "pbi_agent.cli.sandbox._start_browser_open_thread"
            ) as mock_browser_thread,
        ):
            rc = cli_sandbox._handle_sandbox_command(args)

        self.assertEqual(rc, 0)
        mock_build_run.assert_called_once()
        mock_run.assert_called_once_with(["docker", "run"], env={"ENV": "value"})
        mock_browser_thread.assert_called_once_with(
            "127.0.0.1",
            9001,
            "http://127.0.0.1:9001",
            ready_grace_seconds=cli.SANDBOX_BROWSER_READY_GRACE_SECONDS,
            status_message=None,
        )

    def test_handle_sandbox_web_detached_waits_after_container_starts(self) -> None:
        parser = cli.build_parser()
        args = parser.parse_args(["sandbox", "--detach", "web", "--port", "9001"])
        completed = Mock(returncode=0, stdout="container-id\n", stderr="")

        with (
            patch("pbi_agent.cli.sandbox._check_docker_available", return_value=None),
            patch("pbi_agent.cli.sandbox._is_web_port_available", return_value=True),
            patch(
                "pbi_agent.cli.sandbox._sandbox_dockerfile_path",
                return_value=Path("Dockerfile"),
            ),
            patch("pbi_agent.cli.sandbox._docker_image_exists", return_value=True),
            patch(
                "pbi_agent.cli.sandbox._build_sandbox_run_command",
                return_value=(["docker", "run", "--detach"], {"ENV": "value"}),
            ) as mock_build_run,
            patch(
                "pbi_agent.cli.sandbox.subprocess.run", return_value=completed
            ) as mock_run,
            patch(
                "pbi_agent.cli.sandbox._start_browser_open_thread"
            ) as mock_browser_thread,
            patch(
                "pbi_agent.cli.sandbox._open_browser_when_ready"
            ) as mock_open_when_ready,
        ):
            rc = cli_sandbox._handle_sandbox_command(args)

        self.assertEqual(rc, 0)
        mock_build_run.assert_called_once()
        mock_run.assert_called_once_with(
            ["docker", "run", "--detach"],
            env={"ENV": "value"},
            capture_output=True,
            text=True,
        )
        mock_browser_thread.assert_not_called()
        mock_open_when_ready.assert_called_once_with(
            "127.0.0.1",
            9001,
            "http://127.0.0.1:9001",
            ready_grace_seconds=cli.SANDBOX_BROWSER_READY_GRACE_SECONDS,
            status_message=None,
        )

    def test_handle_sandbox_web_rejects_unavailable_explicit_host_port(self) -> None:
        parser = cli.build_parser()
        args = parser.parse_args(["sandbox", "web", "--port", "9001"])

        with (
            patch("pbi_agent.cli.sandbox._is_web_port_available", return_value=False),
            patch("pbi_agent.cli.sandbox._check_docker_available") as mock_docker_check,
            patch(
                "pbi_agent.cli.sandbox._start_browser_open_thread"
            ) as mock_browser_thread,
        ):
            rc = cli_sandbox._handle_sandbox_command(args)

        self.assertEqual(rc, 1)
        mock_docker_check.assert_not_called()
        mock_browser_thread.assert_not_called()

    def test_sandbox_workspace_state_is_namespaced_by_host_workspace(self) -> None:
        workspace_a = Path("/tmp/repo-a").resolve()
        workspace_b = Path("/tmp/repo-b").resolve()

        self.assertNotEqual(
            cli_sandbox._sandbox_container_workspace(workspace_a),
            cli_sandbox._sandbox_container_workspace(workspace_b),
        )
        self.assertNotEqual(
            cli_sandbox._sandbox_home_volume(workspace_a),
            cli_sandbox._sandbox_home_volume(workspace_b),
        )

    def test_build_sandbox_run_command_can_install_local_source(self) -> None:
        parser = cli.build_parser()
        args = parser.parse_args(
            [
                "sandbox",
                "--local-source",
                "run",
                "--prompt",
                "Inspect",
            ]
        )

        command, container_env = cli_sandbox._build_sandbox_run_command(
            args,
            "sandbox:test",
        )

        workspace = Path.cwd().resolve()
        container_workspace = cli_sandbox._sandbox_container_workspace(workspace)
        self.assertIn("--env", command)
        local_env_index = command.index("PBI_AGENT_LOCAL_SOURCE")
        self.assertEqual(command[local_env_index - 1], "--env")
        entrypoint_index = command.index("--entrypoint")
        image_index = command.index("sandbox:test")
        self.assertLess(entrypoint_index, image_index)
        self.assertEqual(command[entrypoint_index + 1], "/bin/bash")
        self.assertEqual(
            command[image_index + 1 :],
            [
                "-lc",
                (
                    'if [ -r "${PBI_AGENT_SHELL_BOOTSTRAP:-/usr/local/share/pbi-agent/sandbox-shell-env}" ]; '
                    'then . "${PBI_AGENT_SHELL_BOOTSTRAP:-/usr/local/share/pbi-agent/sandbox-shell-env}"; fi; '
                    "python -m pip install --user --prefer-binary -e "
                    '"$PBI_AGENT_LOCAL_SOURCE" && exec pbi-agent "$@"'
                ),
                "pbi-agent",
                "run",
                "--prompt",
                "Inspect",
                "--project-dir",
                ".",
            ],
        )
        self.assertEqual(
            container_env["PBI_AGENT_LOCAL_SOURCE"],
            container_workspace,
        )

    def test_build_sandbox_run_command_for_one_shot_run(self) -> None:
        parser = cli.build_parser()
        args = parser.parse_args(
            [
                "sandbox",
                "run",
                "--prompt",
                "Inspect",
                "--image",
                "diagram.png",
                "--project-dir",
                "pkg",
            ]
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)
            project_dir = workspace / "pkg"
            project_dir.mkdir()
            original_cwd = Path.cwd()
            try:
                os.chdir(workspace)
                command, container_env = cli_sandbox._build_sandbox_run_command(
                    args,
                    "sandbox:test",
                )
            finally:
                os.chdir(original_cwd)

        self.assertNotIn("--publish", command)
        self.assertEqual(
            container_env["PBI_AGENT_WORKSPACE_KEY"],
            str(project_dir.resolve()),
        )
        self.assertEqual(
            container_env["PBI_AGENT_WORKSPACE_DISPLAY_PATH"],
            str(project_dir.resolve()),
        )
        self.assertIn(f"pbi-agent.workspace-key={project_dir.resolve()}", command)
        image_index = command.index("sandbox:test")
        self.assertEqual(
            command[image_index + 1 :],
            [
                "run",
                "--prompt",
                "Inspect",
                "--image",
                "diagram.png",
                "--project-dir",
                "pkg",
            ],
        )

    def test_sandbox_dockerfile_path_ignores_workspace_dockerfile(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace_dockerfile = Path(tmpdir) / "docker" / "Dockerfile.sandbox"
            workspace_dockerfile.parent.mkdir()
            workspace_dockerfile.write_text("FROM scratch\n", encoding="utf-8")
            original_cwd = Path.cwd()
            try:
                os.chdir(tmpdir)
                dockerfile = cli_sandbox._sandbox_dockerfile_path()
            finally:
                os.chdir(original_cwd)

        self.assertIsNotNone(dockerfile)
        assert dockerfile is not None
        self.assertNotEqual(dockerfile, workspace_dockerfile)
        self.assertEqual(dockerfile.name, "Dockerfile.sandbox")

    def test_sandbox_dockerfile_allows_pure_python_sdists(self) -> None:
        dockerfile = cli_sandbox._sandbox_dockerfile_path()

        self.assertIsNotNone(dockerfile)
        assert dockerfile is not None
        content = dockerfile.read_text(encoding="utf-8")
        self.assertIn("--prefer-binary", content)
        self.assertIn("--only-binary=pbi-agent", content)
        self.assertIn("--no-compile", content)
        self.assertNotIn("--only-binary=:all:", content)

    def test_sandbox_dockerfile_uses_alpine_with_minimal_apk_packages(self) -> None:
        dockerfile = cli_sandbox._sandbox_dockerfile_path()

        self.assertIsNotNone(dockerfile)
        assert dockerfile is not None
        content = dockerfile.read_text(encoding="utf-8")
        self.assertIn("FROM python:${PYTHON_VERSION}-alpine3.22", content)
        self.assertIn(
            'ARG RUNTIME_APK="bash build-base ca-certificates curl git github-cli libstdc++ patch ripgrep unzip nodejs npm"',
            content,
        )
        self.assertIn('ARG EXTRA_APK=""', content)
        self.assertIn("ARG FLEXIBLE_SYSTEM_INSTALL=0", content)
        self.assertIn('ARG FLEX_APK="doas"', content)
        self.assertIn("apk add --no-cache ${RUNTIME_APK} ${EXTRA_APK}", content)
        self.assertIn('if [ "${FLEXIBLE_SYSTEM_INSTALL}" = "1" ]; then', content)
        self.assertIn("apk add --no-cache ${FLEX_APK}", content)
        self.assertIn("permit nopass pbi as root", content)
        self.assertIn(
            'PATH="/home/pbi/.local/bin:/home/pbi/bin:/home/pbi/.bun/bin:/home/pbi/.cargo/bin:/home/pbi/.local/share/pnpm:${PATH}"',
            content,
        )
        self.assertIn(
            'PBI_AGENT_SHELL_EXECUTABLE="/usr/local/bin/pbi-agent-shell"',
            content,
        )
        self.assertIn(
            'PBI_AGENT_SHELL_BOOTSTRAP="/usr/local/share/pbi-agent/sandbox-shell-env"',
            content,
        )
        self.assertIn('HOME="/home/pbi"', content)
        self.assertIn('XDG_CONFIG_HOME="/home/pbi/.config"', content)
        self.assertIn('XDG_DATA_HOME="/home/pbi/.local/share"', content)
        self.assertIn('XDG_STATE_HOME="/home/pbi/.local/state"', content)
        self.assertIn('XDG_CACHE_HOME="/home/pbi/.cache"', content)
        self.assertIn(
            'if [ "${_PBI_AGENT_SHELL_BOOTSTRAPPED:-}" = "1" ]; then', content
        )
        self.assertIn("_PBI_AGENT_SHELL_BOOTSTRAPPED=1", content)
        self.assertIn('[ -n "${BASH_VERSION:-}" ]', content)
        self.assertIn('pbi_path_prepend "$HOME/.bun/bin"', content)
        self.assertIn('pbi_path_prepend "$HOME/.cargo/bin"', content)
        self.assertIn('pbi_path_prepend "$HOME/.local/share/pnpm"', content)
        self.assertIn('pbi_path_prepend "$PWD/.venv/bin"', content)
        self.assertIn('pbi_path_prepend "$PWD/node_modules/.bin"', content)
        self.assertIn('find "$root"', content)
        self.assertIn('-path "$HOME/.cache"', content)
        self.assertIn('-o -path "*/.git"', content)
        self.assertIn('-o -path "*/node_modules"', content)
        self.assertIn(") -prune", content)
        self.assertIn("-name bin -o -name .bin", content)
        self.assertIn("command_not_found_handle()", content)
        self.assertIn('pbi_discover_bin_paths "$HOME" "$PWD"', content)
        self.assertIn('"$HOME/.profile"', content)
        self.assertIn('"$HOME/.bashrc"', content)
        self.assertIn("pbi-agent-sandbox-entrypoint", content)
        self.assertIn('exec /usr/local/bin/pbi-agent "$@"', content)
        self.assertIn("pbi-agent-shell", content)
        self.assertIn('PBI_AGENT_ORIGINAL_COMMAND="$command"', content)
        self.assertIn('eval "$PBI_AGENT_ORIGINAL_COMMAND"', content)
        self.assertIn('\' "$@"', content)
        self.assertIn('exec /bin/bash "$@"', content)
        self.assertNotIn("#!/bin/busybox sh", content)
        self.assertNotIn("rm /bin/sh", content)
        self.assertNotIn('exec /bin/busybox sh "$@"', content)
        self.assertIn('"$HOME/.profile"', content)
        self.assertIn('"$HOME/.bashrc"', content)
        self.assertIn("install -d -o pbi -g pbi", content)
        self.assertIn("/workspace", content)
        self.assertIn("/home/pbi", content)
        self.assertIn("/home/pbi/.cache", content)
        self.assertIn("/home/pbi/.config", content)
        self.assertIn("/home/pbi/.local/bin", content)
        self.assertIn("/home/pbi/.local/share", content)
        self.assertIn("/home/pbi/.local/state", content)
        self.assertIn("/home/pbi/bin", content)
        self.assertNotIn("mkdir -p /workspace /home/pbi/.pbi-agent", content)
        self.assertIn('chown -R pbi:pbi /workspace "${HOME}"', content)
        self.assertIn(
            "export HOME=/root XDG_CACHE_HOME=/root/.cache PIP_CACHE_DIR=/root/.cache/pip",
            content,
        )
        self.assertIn("/home/pbi/.cache/*", content)
        self.assertIn("chown -R pbi:pbi /home/pbi /workspace", content)
        self.assertIn("site.getsitepackages()[0]", content)
        self.assertIn("-name tests -o -name test -o -name __pycache__", content)
        self.assertIn("-name '*.pyc' -o -name '*.pyo'", content)
        self.assertIn("${site_packages}/pyarrow/include", content)
        self.assertNotIn("slim-bookworm", content)
        self.assertNotIn("apt-get", content)
        self.assertIn(
            'ENTRYPOINT ["/usr/local/bin/pbi-agent-sandbox-entrypoint"]', content
        )
        self.assertIn("curl", content)
        self.assertIn("github-cli", content)
        self.assertIn("libstdc++", content)
        self.assertIn("ripgrep", content)
        self.assertIn("unzip", content)
        for removed_package in ("procps",):
            self.assertNotIn(removed_package, content)
