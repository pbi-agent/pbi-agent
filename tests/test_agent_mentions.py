from pathlib import Path

import pbi_agent.web.agent_mentions as agent_mentions
from pbi_agent.agent.sub_agent_discovery import ProjectSubAgent
from pbi_agent.web.agent_mentions import search_agent_mentions


def test_search_agent_mentions_prefers_enabled_agents_for_equal_match_tiers(
    tmp_path: Path,
    monkeypatch,
) -> None:
    discovered = [
        ProjectSubAgent(
            name="review-a",
            description="Review code",
            system_prompt="Review code.",
            location=tmp_path / ".agents" / "agents" / "review-a.md",
        ),
        ProjectSubAgent(
            name="review-z",
            description="Review code",
            system_prompt="Review code.",
            location=tmp_path / ".agents" / "agents" / "review-z.md",
        ),
    ]
    monkeypatch.setattr(
        agent_mentions,
        "discover_all_project_sub_agents",
        lambda *, workspace: discovered,
    )
    monkeypatch.setattr(
        agent_mentions,
        "agent_enabled_map",
        lambda *_args, **_kwargs: {
            "review-a": False,
            "review-z": True,
        },
    )

    results = search_agent_mentions("review", root=tmp_path, limit=2)

    result_names = [item.name for item in results]
    assert result_names == ["review-z", "review-a"]
