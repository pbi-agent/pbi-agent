from pbi_agent.web.agent_mentions import AgentMentionItem
from pbi_agent.web.input_mentions import (
    MentionSearchPayload,
    MentionSearchResult,
)
from pbi_agent.web.mention_suggestions import combine_mention_suggestions


def _file_payload(*paths: str) -> MentionSearchPayload:
    return MentionSearchPayload(
        items=[MentionSearchResult(path=path, kind="file") for path in paths],
        scan_status="ready",
        is_stale=False,
        file_count=len(paths),
        index_generation="test-generation",
        index_revision=1,
        truncated=False,
        search_approximated=False,
    )


def test_combined_mentions_rank_exact_file_before_description_only_agents() -> None:
    agents = [
        AgentMentionItem(
            name=f"reviewer-{index}",
            description="Reviews target.py changes",
            path=f".agents/agents/reviewer-{index}.md",
            enabled=True,
        )
        for index in range(8)
    ]

    payload = combine_mention_suggestions(
        "target.py",
        files=_file_payload("target.py"),
        agents=agents,
        limit=8,
    )

    assert isinstance(payload.items[0], MentionSearchResult)
    assert payload.items[0].path == "target.py"
    assert len(payload.items) == 8


def test_combined_mentions_use_consistent_enabled_file_disabled_order() -> None:
    enabled_agent = AgentMentionItem(
        name="review-enabled",
        description="Review changes",
        path=".agents/agents/review-enabled.md",
        enabled=True,
    )
    disabled_agent = AgentMentionItem(
        name="review-disabled",
        description="Review changes",
        path=".agents/agents/review-disabled.md",
        enabled=False,
    )

    payload = combine_mention_suggestions(
        "review",
        files=_file_payload("review-notes.md"),
        agents=[disabled_agent, enabled_agent],
        limit=8,
    )

    expected = [
        enabled_agent,
        MentionSearchResult(path="review-notes.md", kind="file"),
        disabled_agent,
    ]
    assert payload.items == expected
