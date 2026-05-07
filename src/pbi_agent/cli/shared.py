from __future__ import annotations

import argparse
import logging
import sys

from pathlib import Path

from pbi_agent import __version__
from pbi_agent.config import (
    ResolvedRuntime,
    Settings,
)

LOGGER = logging.getLogger(__name__)
DEFAULT_COMMAND = "web"


def _docker_tag_safe(text: str) -> str:
    tag = "".join(
        character if character.isalnum() or character in "_.-" else "-"
        for character in text
    ).strip(".-")
    return tag or "local"


DEFAULT_SANDBOX_IMAGE = f"pbi-agent-sandbox:{_docker_tag_safe(__version__)}"
SANDBOX_WORKSPACE = "/workspace"
SANDBOX_HOME = "/home/pbi"
SANDBOX_CONFIG_VOLUME_PREFIX = "pbi-agent-sandbox-config"
SANDBOX_HOME_VOLUME_PREFIX = "pbi-agent-sandbox-home"
SANDBOX_HOST_GIT_PATHS = (
    (Path(".gitconfig"), f"{SANDBOX_HOME}/.gitconfig"),
    (Path(".git-credentials"), f"{SANDBOX_HOME}/.git-credentials"),
    (Path(".config/git"), f"{SANDBOX_HOME}/.config/git"),
    (Path(".config/gh"), f"{SANDBOX_HOME}/.config/gh"),
    (Path(".ssh"), f"{SANDBOX_HOME}/.ssh"),
)
WEB_SERVER_BROWSER_WAIT_TIMEOUT_SECONDS = 20.0
WEB_SERVER_BROWSER_WAIT_RETRY_SECONDS = 10.0
WEB_SERVER_BROWSER_POLL_INTERVAL_SECONDS = 0.1
WEB_SERVER_BROWSER_CONNECT_TIMEOUT_SECONDS = 0.2
SANDBOX_BROWSER_READY_GRACE_SECONDS = 2.0
WEB_MANAGER_LEASE_STALE_SECONDS = 30.0


def _workspace_directory_for_args(args: argparse.Namespace) -> Path:
    if getattr(args, "command", None) == "run" and getattr(args, "project_dir", None):
        return (Path.cwd() / args.project_dir).resolve()
    return Path.cwd().resolve()


def _coerce_runtime(settings: Settings | ResolvedRuntime) -> ResolvedRuntime:
    if isinstance(settings, ResolvedRuntime):
        return settings
    return ResolvedRuntime(settings=settings, provider_id="", profile_id="")


def _print_error(message: str) -> None:
    lines = [line for line in message.splitlines() if line.strip()]
    if not lines:
        print("Error.", file=sys.stderr)
        return
    print(f"Error: {lines[0]}", file=sys.stderr)
    for line in lines[1:]:
        print(line, file=sys.stderr)
