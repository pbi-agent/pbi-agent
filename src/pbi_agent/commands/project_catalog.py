from __future__ import annotations

from pathlib import Path

from rich.console import Console
from rich.table import Table

from pbi_agent.config import list_command_configs


def discover_installed_project_commands(workspace: Path | None = None):
    return list_command_configs(workspace)


def render_installed_project_commands(
    workspace: Path | None = None,
    *,
    console: Console | None = None,
) -> int:
    project_commands = discover_installed_project_commands(workspace=workspace)
    active_console = console or Console()

    if not project_commands:
        active_console.print(
            "[dim]No project commands discovered under[/dim] .agents/commands/"
        )
        return 0

    table = Table(title="Project Commands", title_style="bold cyan")
    table.add_column("Name", style="green")
    table.add_column("Alias", style="green")
    table.add_column("Description")
    table.add_column("Location", style="dim")
    for command in project_commands:
        table.add_row(
            command.name,
            command.slash_alias,
            command.description,
            command.path,
        )
    active_console.print(table)
    return 0
