from __future__ import annotations

import sys
from pathlib import Path

from pbi_agent.agent.skill_discovery import ProjectSkill, discover_project_skills
from pbi_agent.agent.sub_agent_discovery import (
    ProjectSubAgent,
    discover_project_sub_agents,
)
from pbi_agent.config import CommandConfig, ConfigError, list_command_configs


def resolve_skill_references(
    configured_names: tuple[str, ...] | None,
    workspace: Path | None = None,
    *,
    directory_key: str | None = None,
    source_label: str = "Configuration",
) -> tuple[ProjectSkill, ...] | None:
    """Resolve configured skill names against project skills.

    Configured skill names are explicit references, so disabled project skills are
    included when their on-disk skill definition exists. Missing skills are soft
    references: warn to stderr and omit them. ``None`` preserves absent-field
    behavior and returns ``None``.
    """

    if configured_names is None:
        return None
    skills = discover_project_skills(
        workspace,
        explicit_skill_names=set(configured_names),
        directory_key=directory_key,
    )
    by_name = {skill.name.casefold(): skill for skill in skills}
    resolved: list[ProjectSkill] = []
    for name in configured_names:
        skill = by_name.get(name.casefold())
        if skill is None:
            _warn(
                f"Warning: {source_label} references unknown skill '{name}'; omitting."
            )
            continue
        resolved.append(skill)
    return tuple(resolved)


def resolve_command_references(
    configured_names: tuple[str, ...] | None,
    workspace: Path | None = None,
    *,
    strict: bool = False,
    source_label: str = "Configuration",
) -> tuple[CommandConfig, ...] | None:
    """Resolve configured command names/IDs/aliases against project commands."""

    if configured_names is None:
        return None
    commands = list_command_configs(workspace)
    by_key: dict[str, CommandConfig] = {}
    for command in commands:
        by_key[command.id.casefold()] = command
        by_key[command.name.casefold()] = command
        by_key[command.slash_alias.casefold()] = command

    resolved: list[CommandConfig] = []
    for name in configured_names:
        command = by_key.get(name.casefold())
        if command is None:
            message = f"{source_label} references unknown command '{name}'."
            if strict:
                raise ConfigError(message)
            _warn(f"Warning: {message} Omitting.")
            continue
        resolved.append(command)
    return tuple(resolved)


def resolve_sub_agent_references(
    configured_names: tuple[str, ...] | None,
    workspace: Path | None = None,
    *,
    directory_key: str | None = None,
    strict: bool = False,
    source_label: str = "Configuration",
) -> tuple[ProjectSubAgent, ...] | None:
    """Resolve configured sub-agent names against project sub-agents.

    Configured sub-agent names are explicit references, so disabled project
    sub-agents are included when their on-disk definition exists.
    """

    if configured_names is None:
        return None
    agents = discover_project_sub_agents(
        workspace,
        explicit_agent_names=set(configured_names),
        directory_key=directory_key,
    )
    by_name = {agent.name.casefold(): agent for agent in agents}
    resolved: list[ProjectSubAgent] = []
    for name in configured_names:
        agent = by_name.get(name.casefold())
        if agent is None:
            message = f"{source_label} references unknown sub-agent '{name}'."
            if strict:
                raise ConfigError(message)
            _warn(f"Warning: {message} Omitting.")
            continue
        resolved.append(agent)
    return tuple(resolved)


def _warn(message: str) -> None:
    print(message, file=sys.stderr)
