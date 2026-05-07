from __future__ import annotations

import argparse
import hashlib
import os
import subprocess
import sys
from pathlib import Path

from pbi_agent import __version__
from pbi_agent.config import ConfigError
from pbi_agent.workspace_context import (
    SANDBOX_ENV,
    WORKSPACE_DISPLAY_PATH_ENV,
    WORKSPACE_KEY_ENV,
)

from .shared import (
    DEFAULT_SANDBOX_IMAGE,
    SANDBOX_BROWSER_READY_GRACE_SECONDS,
    SANDBOX_CONFIG_VOLUME_PREFIX,
    SANDBOX_HOME,
    SANDBOX_HOME_VOLUME_PREFIX,
    SANDBOX_HOST_GIT_PATHS,
    SANDBOX_WORKSPACE,
)
from .web import (
    _browser_target_url,
    _is_web_port_available,
    _open_browser_when_ready,
    _resolve_web_command_port,
    _start_browser_open_thread,
)


def _handle_sandbox_command(args: argparse.Namespace) -> int:  # pyright: ignore[reportUnusedFunction] - imported by CLI entrypoint
    sandbox_command = args.sandbox_command or "web"
    if sandbox_command == "web" and (args.port < 1 or args.port > 65535):
        print("Error: --port must be between 1 and 65535.", file=sys.stderr)
        return 2
    if sandbox_command == "web":
        if getattr(args, "_explicit_web_port", False):
            if not _is_web_port_available(args.host, args.port):
                print(
                    f"Error: host port {args.port} is unavailable for sandbox web.",
                    file=sys.stderr,
                )
                return 1
        elif not _resolve_web_command_port(args):
            return 1

    docker_check = _check_docker_available()
    if docker_check is not None:
        print(f"Error: {docker_check}", file=sys.stderr)
        return 1

    dockerfile = _sandbox_dockerfile_path()
    if dockerfile is None:
        print(
            "Error: bundled sandbox Dockerfile was not found. Reinstall pbi-agent "
            "or run from a complete source checkout.",
            file=sys.stderr,
        )
        return 1

    image = str(args.image).strip() or DEFAULT_SANDBOX_IMAGE
    if args.rebuild or not _docker_image_exists(image):
        build_command = _build_sandbox_image_command(image, dockerfile)
        build_result = subprocess.run(build_command)
        if build_result.returncode != 0:
            return build_result.returncode

    run_command, container_env = _build_sandbox_run_command(args, image)
    detached = bool(getattr(args, "detach", False))
    if sandbox_command == "web" and not detached:
        print(
            "Waiting for sandbox web server before opening browser...",
            file=sys.stderr,
        )
        _start_browser_open_thread(
            args.host,
            args.port,
            _browser_target_url(args),
            ready_grace_seconds=SANDBOX_BROWSER_READY_GRACE_SECONDS,
            status_message=None,
        )
    try:
        if detached:
            completed = subprocess.run(
                run_command,
                env=container_env,
                capture_output=True,
                text=True,
            )
            if completed.stdout:
                print(completed.stdout.strip())
            if completed.stderr:
                print(completed.stderr.strip(), file=sys.stderr)
            if completed.returncode == 0 and sandbox_command == "web":
                print(
                    "Waiting for detached sandbox web server before opening browser...",
                    file=sys.stderr,
                )
                _open_browser_when_ready(
                    args.host,
                    args.port,
                    _browser_target_url(args),
                    ready_grace_seconds=SANDBOX_BROWSER_READY_GRACE_SECONDS,
                    status_message=None,
                )
        else:
            completed = subprocess.run(run_command, env=container_env)
    except KeyboardInterrupt:
        return 130
    return completed.returncode


def _check_docker_available() -> str | None:
    try:
        completed = subprocess.run(
            ["docker", "version", "--format", "{{.Server.Version}}"],
            capture_output=True,
            text=True,
            timeout=10,
        )
    except FileNotFoundError:
        return "Docker CLI was not found. Install and start Docker Desktop."
    except subprocess.TimeoutExpired:
        return "Docker Desktop did not respond to `docker version`."
    except OSError as exc:
        return f"Unable to run Docker CLI: {exc}"
    if completed.returncode != 0:
        stderr = (completed.stderr or completed.stdout or "").strip()
        detail = f" {stderr}" if stderr else ""
        return f"Docker Desktop is not available or is not running.{detail}"
    return None


def _docker_image_exists(image: str) -> bool:
    completed = subprocess.run(
        ["docker", "image", "inspect", image],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    return completed.returncode == 0


def _sandbox_dockerfile_path() -> Path | None:
    package_dockerfile = (
        Path(__file__).resolve().parent.parent / "sandbox" / "Dockerfile.sandbox"
    )
    if package_dockerfile.is_file():
        return package_dockerfile
    return None


def _build_sandbox_image_command(image: str, dockerfile: Path) -> list[str]:
    context_dir = dockerfile.parent
    return [
        "docker",
        "build",
        "--file",
        str(dockerfile),
        "--build-arg",
        f"PBI_AGENT_VERSION={__version__}",
        "--tag",
        image,
        str(context_dir),
    ]


def _build_sandbox_run_command(
    args: argparse.Namespace,
    image: str,
) -> tuple[list[str], dict[str, str]]:
    workspace = Path.cwd().resolve()
    host_workspace = str(workspace)
    workspace_identity = str(_sandbox_workspace_identity(args, workspace))
    container_workspace = _sandbox_container_workspace(workspace)
    env_names, env_overrides = _sandbox_environment(args)
    env_overrides.update(
        {
            SANDBOX_ENV: "1",
            WORKSPACE_KEY_ENV: workspace_identity,
            WORKSPACE_DISPLAY_PATH_ENV: workspace_identity,
        }
    )
    if getattr(args, "local_source", False):
        env_overrides["PBI_AGENT_LOCAL_SOURCE"] = container_workspace
    env_names = sorted(set(env_names) | set(env_overrides))
    sandbox_command = args.sandbox_command or "web"
    if sandbox_command == "web":
        env_overrides["BROWSER"] = "/bin/true"
        env_names = sorted(set(env_names) | {"BROWSER"})
    command = [
        "docker",
        "run",
        "--rm",
        "--init",
        "--workdir",
        container_workspace,
        "--label",
        "pbi-agent.sandbox=1",
        "--label",
        f"pbi-agent.workspace={host_workspace}",
        "--label",
        f"pbi-agent.workspace-key={workspace_identity}",
        "--mount",
        _sandbox_workspace_mount(
            workspace,
            target=container_workspace,
            read_only=bool(args.read_only_repo),
        ),
        "--mount",
        _sandbox_home_mount(workspace),
        "--mount",
        _sandbox_config_mount(workspace),
        "--cap-drop",
        "ALL",
        "--security-opt",
        "no-new-privileges:true",
        "--pids-limit",
        "512",
        "--memory",
        "4g",
        "--read-only",
        "--tmpfs",
        "/tmp:rw,noexec,nosuid,size=256m",
        "--tmpfs",
        f"{SANDBOX_HOME}/.cache:rw,noexec,nosuid,uid=1000,gid=1000,mode=755,size=512m",
    ]
    for mount in _sandbox_host_git_mounts():
        command.extend(["--mount", mount])
    if getattr(args, "detach", False):
        command.append("--detach")
    elif sys.stdin.isatty() and sys.stdout.isatty():
        command.append("-it")
    if args.env_file is not None:
        command.extend(["--env-file", str(args.env_file.resolve())])
    for env_name in env_names:
        command.extend(["--env", env_name])

    if sandbox_command == "web":
        command.extend(
            [
                "--publish",
                f"{args.host}:{args.port}:{args.port}",
            ]
        )

    inner_command = _sandbox_inner_command(args)
    if getattr(args, "local_source", False):
        command.extend(["--entrypoint", "/bin/bash"])
    command.append(image)
    if getattr(args, "local_source", False):
        command.extend(
            [
                "-lc",
                (
                    "python -m pip install --user --prefer-binary -e "
                    '"$PBI_AGENT_LOCAL_SOURCE" && exec pbi-agent "$@"'
                ),
                "pbi-agent",
                *inner_command,
            ]
        )
    else:
        command.extend(inner_command)

    container_env = os.environ.copy()
    container_env.update(env_overrides)
    return command, container_env


def _sandbox_workspace_id(workspace: Path) -> str:
    return hashlib.sha256(str(workspace).encode("utf-8")).hexdigest()[:16]


def _sandbox_workspace_identity(args: argparse.Namespace, workspace: Path) -> Path:
    if (args.sandbox_command or "web") == "run":
        return (workspace / args.project_dir).resolve()
    return workspace


def _sandbox_container_workspace(workspace: Path) -> str:
    return f"{SANDBOX_WORKSPACE}/{_sandbox_workspace_id(workspace)}"


def _sandbox_config_volume(workspace: Path) -> str:  # pyright: ignore[reportUnusedFunction] - imported by sandbox tests
    return f"{SANDBOX_CONFIG_VOLUME_PREFIX}-{_sandbox_workspace_id(workspace)}"


def _sandbox_home_volume(workspace: Path) -> str:
    return f"{SANDBOX_HOME_VOLUME_PREFIX}-{_sandbox_workspace_id(workspace)}"


def _sandbox_host_home_dir() -> Path:
    return Path.home()


def _sandbox_host_config_dir() -> Path:
    return _sandbox_host_home_dir() / ".pbi-agent"


def _sandbox_home_mount(workspace: Path) -> str:
    return f"type=volume,source={_sandbox_home_volume(workspace)},target={SANDBOX_HOME}"


def _sandbox_config_mount(workspace: Path) -> str:
    del workspace
    host_config_dir = _sandbox_host_config_dir()
    host_config_dir.mkdir(parents=True, exist_ok=True)
    return f"type=bind,source={host_config_dir},target={SANDBOX_HOME}/.pbi-agent"


def _sandbox_host_git_mounts() -> list[str]:
    host_home = _sandbox_host_home_dir()
    mounts: list[str] = []
    for relative_source, container_target in SANDBOX_HOST_GIT_PATHS:
        host_source = host_home / relative_source
        if host_source.is_file() or host_source.is_dir():
            mounts.append(
                f"type=bind,source={host_source.resolve()},"
                f"target={container_target},readonly"
            )
    return mounts


def _sandbox_workspace_mount(
    workspace: Path,
    *,
    target: str,
    read_only: bool,
) -> str:
    mount = f"type=bind,source={workspace},target={target}"
    if read_only:
        mount += ",readonly"
    return mount


def _sandbox_environment(args: argparse.Namespace) -> tuple[list[str], dict[str, str]]:
    inherited = {
        name
        for name in os.environ
        if name.startswith("PBI_AGENT_") or name in _sandbox_passthrough_env_names()
    }
    overrides = _sandbox_cli_env_overrides(args)
    names = sorted(inherited | set(overrides))
    return names, overrides


def _sandbox_passthrough_env_names() -> set[str]:
    return {
        "OPENAI_API_KEY",
        "AZURE_API_KEY",
        "XAI_API_KEY",
        "GEMINI_API_KEY",
        "ANTHROPIC_API_KEY",
        "GENERIC_API_KEY",
        "HTTPS_PROXY",
        "HTTP_PROXY",
        "NO_PROXY",
        "https_proxy",
        "http_proxy",
        "no_proxy",
    }


def _sandbox_cli_env_overrides(args: argparse.Namespace) -> dict[str, str]:
    mapping = {
        "provider": "PBI_AGENT_PROVIDER",
        "api_key": "PBI_AGENT_API_KEY",
        "responses_url": "PBI_AGENT_RESPONSES_URL",
        "generic_api_url": "PBI_AGENT_GENERIC_API_URL",
        "profile_id": "PBI_AGENT_PROFILE_ID",
        "model": "PBI_AGENT_MODEL",
        "sub_agent_model": "PBI_AGENT_SUB_AGENT_MODEL",
        "max_tokens": "PBI_AGENT_MAX_TOKENS",
        "reasoning_effort": "PBI_AGENT_REASONING_EFFORT",
        "service_tier": "PBI_AGENT_SERVICE_TIER",
        "max_tool_workers": "PBI_AGENT_MAX_TOOL_WORKERS",
        "max_retries": "PBI_AGENT_MAX_RETRIES",
        "compact_threshold": "PBI_AGENT_COMPACT_THRESHOLD",
        "compact_tail_turns": "PBI_AGENT_COMPACT_TAIL_TURNS",
        "compact_preserve_recent_tokens": "PBI_AGENT_COMPACT_PRESERVE_RECENT_TOKENS",
        "compact_tool_output_max_chars": "PBI_AGENT_COMPACT_TOOL_OUTPUT_MAX_CHARS",
    }
    overrides: dict[str, str] = {}
    for arg_name, env_name in mapping.items():
        value = getattr(args, arg_name, None)
        if value is None:
            continue
        overrides[env_name] = str(value)
    if getattr(args, "no_web_search", False):
        overrides["PBI_AGENT_WEB_SEARCH"] = "false"
    return overrides


def _sandbox_inner_command(args: argparse.Namespace) -> list[str]:
    command: list[str] = []
    if args.verbose:
        command.append("--verbose")
    sandbox_command = args.sandbox_command or "web"
    if sandbox_command == "web":
        command.extend(["web", "--host", "0.0.0.0", "--port", str(args.port)])
        if args.dev:
            command.append("--dev")
        if args.title:
            command.extend(["--title", args.title])
        if args.url:
            command.extend(["--url", args.url])
        return command
    if sandbox_command == "run":
        command.extend(["run", "--prompt", args.prompt])
        for image_path in args.images or []:
            command.extend(["--image", image_path])
        command.extend(["--project-dir", str(args.project_dir)])
        if args.session_id:
            command.extend(["--session-id", args.session_id])
        return command
    raise ConfigError(f"Unknown sandbox command '{sandbox_command}'.")
