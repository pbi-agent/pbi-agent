"""Shared ranking for mixed workspace file and project-agent mentions."""

from __future__ import annotations

from dataclasses import dataclass

from pbi_agent.web.agent_mentions import (
    AgentMentionItem,
    agent_mention_rank,
)
from pbi_agent.web.input_mentions import (
    MentionSearchPayload,
    MentionSearchResult,
    ScanStatus,
    file_mention_rank,
)

MentionSuggestion = MentionSearchResult | AgentMentionItem
_UnifiedMentionRank = tuple[int, int, float, int, int, str, str, str, str]


@dataclass(frozen=True, slots=True)
class MentionSuggestionPayload:
    items: list[MentionSuggestion]
    scan_status: ScanStatus
    is_stale: bool
    file_count: int
    index_generation: str
    index_revision: int
    truncated: bool
    search_approximated: bool
    error: str | None = None


def combine_mention_suggestions(
    query: str,
    *,
    files: MentionSearchPayload,
    agents: list[AgentMentionItem],
    limit: int,
) -> MentionSuggestionPayload:
    """Globally rank file and agent candidates before applying the result limit."""

    ranked: list[tuple[_UnifiedMentionRank, MentionSuggestion]] = []
    for agent in agents:
        agent_rank = agent_mention_rank(query, agent)
        if agent_rank is None:
            continue
        ranked.append(
            (
                (
                    agent_rank[0],
                    0 if agent.enabled else 2,
                    0.0,
                    0,
                    len(agent.name),
                    agent.name.casefold(),
                    agent.name,
                    "agent",
                    agent.path,
                ),
                agent,
            )
        )
    for file_item in files.items:
        file_rank = file_mention_rank(query, file_item.path)
        if file_rank is None:
            continue
        ranked.append(
            (
                (
                    file_rank[0],
                    1,
                    file_rank[1],
                    file_rank[2],
                    file_rank[3],
                    file_rank[4],
                    file_rank[5],
                    file_item.kind,
                    file_item.path,
                ),
                file_item,
            )
        )
    ranked.sort(key=lambda item: item[0])
    return MentionSuggestionPayload(
        items=[item for _rank, item in ranked[:limit]],
        scan_status=files.scan_status,
        is_stale=files.is_stale,
        file_count=files.file_count,
        index_generation=files.index_generation,
        index_revision=files.index_revision,
        truncated=files.truncated,
        search_approximated=files.search_approximated,
        error=files.error,
    )


__all__ = [
    "combine_mention_suggestions",
    "MentionSuggestion",
    "MentionSuggestionPayload",
]
