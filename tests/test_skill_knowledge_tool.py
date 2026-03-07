from __future__ import annotations

from pbi_agent.tools import skill_knowledge
from pbi_agent.tools.types import ToolContext


def test_build_spec_uses_available_skill_catalog(monkeypatch) -> None:
    monkeypatch.setattr(
        skill_knowledge,
        "list_available_skills",
        lambda: [
            ("card_visual", "Build a KPI card."),
            ("table_visual", "Build a table visual."),
        ],
    )

    spec = skill_knowledge.build_spec()

    assert spec.name == "skill_knowledge"
    assert spec.is_destructive is False
    assert spec.parameters_schema["properties"]["skills"]["items"]["enum"] == [
        "card_visual",
        "table_visual",
    ]
    assert "- card_visual: Build a KPI card." in spec.description
    assert "- table_visual: Build a table visual." in spec.description


def test_skill_knowledge_handle_returns_loaded_skills_and_missing_errors(
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        skill_knowledge,
        "load_skill",
        lambda name: {"card_visual": "# Card\nDetails"}.get(name),
    )
    monkeypatch.setattr(
        skill_knowledge,
        "list_available_skills",
        lambda: [
            ("card_visual", "Build a KPI card."),
            ("table_visual", "Build a table visual."),
        ],
    )

    result = skill_knowledge.handle(
        {"skills": ["card_visual", "table_visual"]},
        ToolContext(),
    )

    assert result == {
        "skills": {"card_visual": "# Card\nDetails"},
        "errors": [
            "Skill 'table_visual' not found. Available: ['card_visual', 'table_visual']"
        ],
    }


def test_skill_knowledge_handle_requires_non_empty_skill_list() -> None:
    result = skill_knowledge.handle({"skills": []}, ToolContext())

    assert result == {"error": "No skill names provided."}
