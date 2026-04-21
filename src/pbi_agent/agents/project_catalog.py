from __future__ import annotations

from pathlib import Path

from rich.console import Console

from pbi_agent.agent.sub_agent_discovery import (
    discover_project_sub_agents,
    render_installed_project_sub_agents,
)


def discover_installed_project_agents(workspace: Path | None = None):
    return discover_project_sub_agents(workspace)


def render_installed_project_agents(
    workspace: Path | None = None,
    *,
    console: Console | None = None,
) -> int:
    return render_installed_project_sub_agents(workspace=workspace, console=console)
