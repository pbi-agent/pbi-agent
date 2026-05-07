from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .shared import _workspace_directory_for_args


def _handle_skills_command(args: argparse.Namespace) -> int:
    if args.skills_action == "list":
        return _handle_skills_list_command(args)
    if args.skills_action == "add":
        return _handle_skills_add_command(args)
    print(f"Error: unknown skills action {args.skills_action!r}", file=sys.stderr)
    return 2


def _handle_skills_list_command(args: argparse.Namespace) -> int:
    from pbi_agent.skills.project_catalog import render_installed_project_skills

    return render_installed_project_skills(workspace=Path.cwd().resolve())


def _handle_skills_add_command(args: argparse.Namespace) -> int:
    from pbi_agent.skills.project_installer import (
        DEFAULT_SKILLS_SOURCE,
        ProjectSkillInstallError,
        install_project_skill,
        list_remote_project_skills,
        render_remote_skill_listing,
    )

    effective_source = args.source or DEFAULT_SKILLS_SOURCE

    try:
        if args.source is None and args.skill is None:
            listing = list_remote_project_skills(effective_source)
            return render_remote_skill_listing(listing)

        if args.list:
            listing = list_remote_project_skills(effective_source)
            return render_remote_skill_listing(listing)

        result = install_project_skill(
            effective_source,
            skill_name=args.skill,
            force=args.force,
            workspace=Path.cwd().resolve(),
        )
    except ProjectSkillInstallError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2

    print(f"Installed skill '{result.name}' to {result.install_path}")
    return 0


def _handle_commands_command(args: argparse.Namespace) -> int:
    if args.commands_action == "list":
        return _handle_commands_list_command(args)
    if args.commands_action == "add":
        return _handle_commands_add_command(args)
    print(f"Error: unknown commands action {args.commands_action!r}", file=sys.stderr)
    return 2


def _handle_commands_list_command(args: argparse.Namespace) -> int:
    from pbi_agent.commands.project_catalog import render_installed_project_commands

    return render_installed_project_commands(workspace=Path.cwd().resolve())


def _handle_commands_add_command(args: argparse.Namespace) -> int:
    from pbi_agent.commands.project_installer import (
        DEFAULT_COMMANDS_SOURCE,
        ProjectCommandInstallError,
        install_project_command,
        list_remote_project_commands,
        render_remote_command_listing,
    )

    effective_source = args.source or DEFAULT_COMMANDS_SOURCE

    try:
        if args.source is None and args.command_name is None:
            listing = list_remote_project_commands(effective_source)
            return render_remote_command_listing(listing)

        if args.list:
            listing = list_remote_project_commands(effective_source)
            return render_remote_command_listing(listing)

        result = install_project_command(
            effective_source,
            command_name=args.command_name,
            force=args.force,
            workspace=Path.cwd().resolve(),
        )
    except ProjectCommandInstallError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2

    print(f"Installed command '{result.slash_alias}' to {result.install_path}")
    return 0


def _handle_agents_command(args: argparse.Namespace) -> int:
    if args.agents_action == "list":
        return _handle_agents_list_command(args)
    if args.agents_action == "add":
        return _handle_agents_add_command(args)
    print(f"Error: unknown agents action {args.agents_action!r}", file=sys.stderr)
    return 2


def _handle_agents_list_command(args: argparse.Namespace) -> int:
    from pbi_agent.agents.project_catalog import render_installed_project_agents

    return render_installed_project_agents(workspace=Path.cwd().resolve())


def _handle_agents_add_command(args: argparse.Namespace) -> int:
    from pbi_agent.agents.project_installer import (
        DEFAULT_AGENTS_SOURCE,
        ProjectAgentInstallError,
        install_project_agent,
        list_remote_project_agents,
        render_remote_agent_listing,
    )

    effective_source = args.source or DEFAULT_AGENTS_SOURCE
    try:
        if args.source is None and args.agent_name is None:
            listing = list_remote_project_agents(effective_source)
            return render_remote_agent_listing(listing)

        if args.list:
            listing = list_remote_project_agents(effective_source)
            return render_remote_agent_listing(listing)

        result = install_project_agent(
            effective_source,
            agent_name=args.agent_name,
            force=args.force,
            workspace=Path.cwd().resolve(),
        )
    except ProjectAgentInstallError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2

    print(f"Installed agent '{result.agent_name}' to {result.install_path}")
    return 0


def _handle_mcp_flag(args: argparse.Namespace) -> int:
    from pbi_agent.mcp import discover_mcp_server_configs
    from rich.console import Console
    from rich.table import Table

    target_dir = _workspace_directory_for_args(args)
    servers = discover_mcp_server_configs(workspace=target_dir)
    console = Console()

    if not servers:
        console.print("[dim]No project MCP servers discovered under[/dim] .agents/")
        return 0

    table = Table(title="MCP Servers", title_style="bold cyan")
    table.add_column("Name", style="green")
    table.add_column("Transport", style="yellow")
    table.add_column("Command / URL")
    table.add_column("Config", style="dim")
    for server in servers:
        if server.transport == "http":
            detail = server.url or ""
        else:
            detail = " ".join([server.command or "", *server.args]).strip()
        table.add_row(server.name, server.transport, detail, str(server.location))
    console.print(table)
    return 0


def _handle_agents_flag(args: argparse.Namespace) -> int:
    from pbi_agent.agent.sub_agent_discovery import discover_project_sub_agents
    from rich.console import Console
    from rich.table import Table

    target_dir = _workspace_directory_for_args(args)
    agents = discover_project_sub_agents(workspace=target_dir)
    console = Console()

    if not agents:
        console.print(
            "[dim]No project sub-agents discovered under[/dim] .agents/agents/*.md"
        )
        return 0

    table = Table(title="Sub-Agents", title_style="bold cyan")
    table.add_column("Name", style="green")
    table.add_column("Description")
    for agent in agents:
        table.add_row(agent.name, agent.description)
    console.print(table)
    return 0
