"""Project agent mention search for web composer `@agent (agent)` completions."""

from __future__ import annotations

import re
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


AgentMentionRank = tuple[int, bool, int, str, str, str, str]


def agent_mention_rank(
    query: str,
    agent: AgentMentionItem,
) -> AgentMentionRank | None:
    """Return the shared rank tuple for an agent mention candidate."""

    normalized_query = query.strip().casefold()
    name = agent.name.casefold()
    if not normalized_query:
        tier = 8
    elif name == normalized_query:
        tier = 0
    elif name.startswith(normalized_query):
        tier = 2
    elif any(
        token.startswith(normalized_query)
        for token in re.split(r"[-_.]+", name)
        if token
    ):
        tier = 3
    elif normalized_query in name:
        tier = 4
    elif normalized_query in agent.description.casefold():
        tier = 7
    else:
        return None
    return (
        tier,
        not agent.enabled,
        len(agent.name),
        name,
        agent.name,
        agent.path.casefold(),
        agent.path,
    )


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
    ranked: list[tuple[AgentMentionRank, AgentMentionItem]] = []
    for agent in agents:
        rank = agent_mention_rank(normalized_query, agent)
        if rank is not None:
            ranked.append((rank, agent))

    ranked.sort(key=lambda item: item[0])
    return [item for _rank, item in ranked[:limit]]


def _display_path(path: Path, *, root: Path) -> str:
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return str(path)
