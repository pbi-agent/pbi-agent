"""Project agent mention search for web composer `@agent (agent)` completions."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from pbi_agent.agent.sub_agent_discovery import discover_all_project_sub_agents
from pbi_agent.agents.state import agent_enabled_map


@dataclass(slots=True, frozen=True)
class AgentMentionItem:
    name: str
    description: str
    path: str
    enabled: bool


def search_agent_mentions(
    query: str,
    *,
    root: Path,
    limit: int = 20,
    directory_key: str | None = None,
) -> list[AgentMentionItem]:
    normalized_query = query.strip().casefold()
    discovered = discover_all_project_sub_agents(workspace=root)
    enabled = agent_enabled_map(
        [agent.name for agent in discovered],
        workspace=root,
        directory_key=directory_key,
    )
    agents = [
        AgentMentionItem(
            name=agent.name,
            description=agent.description,
            path=_display_path(agent.location, root=root),
            enabled=enabled.get(agent.name, True),
        )
        for agent in discovered
    ]
    if not normalized_query:
        return sorted(
            agents, key=lambda item: (item.name.casefold(), item.path.casefold())
        )[:limit]

    ranked: list[tuple[int, str, AgentMentionItem]] = []
    for agent in agents:
        name = agent.name.casefold()
        description = agent.description.casefold()
        haystack = f"{name} {description}"
        if normalized_query not in haystack:
            continue
        if name == normalized_query:
            score = 0
        elif name.startswith(normalized_query):
            score = 1
        elif normalized_query in name:
            score = 2
        else:
            score = 3
        ranked.append((score, name, agent))

    ranked.sort(key=lambda item: (item[0], item[1], item[2].path.casefold()))
    return [item for _score, _name, item in ranked[:limit]]


def _display_path(path: Path, *, root: Path) -> str:
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return str(path)
