from __future__ import annotations

from pathlib import Path

from pbi_agent.web.skill_mentions import search_skill_mentions


def _write_skill(root: Path, name: str, description: str) -> None:
    skill_dir = root / ".agents" / "skills" / name
    skill_dir.mkdir(parents=True, exist_ok=True)
    (skill_dir / "SKILL.md").write_text(
        f"---\nname: {name}\ndescription: {description}\n---\n\n# {name}\n",
        encoding="utf-8",
    )


def test_search_skill_mentions_returns_empty_query_sorted_by_name(
    tmp_path: Path,
) -> None:
    _write_skill(tmp_path, "zeta", "Last skill")
    _write_skill(tmp_path, "alpha", "First skill")

    results = search_skill_mentions("", root=tmp_path, limit=10)

    assert [(item.name, item.path) for item in results] == [
        ("alpha", ".agents/skills/alpha/SKILL.md"),
        ("zeta", ".agents/skills/zeta/SKILL.md"),
    ]


def test_search_skill_mentions_ranks_name_matches_before_descriptions(
    tmp_path: Path,
) -> None:
    _write_skill(tmp_path, "writer", "Draft release notes")
    _write_skill(tmp_path, "release-writing", "Write pbi-agent release notes")
    _write_skill(tmp_path, "docs", "Release documentation helper")

    results = search_skill_mentions("release", root=tmp_path, limit=10)

    assert [item.name for item in results] == [
        "release-writing",
        "docs",
        "writer",
    ]


def test_search_skill_mentions_skips_invalid_skills(tmp_path: Path) -> None:
    _write_skill(tmp_path, "valid", "Usable skill")
    invalid_dir = tmp_path / ".agents" / "skills" / "broken"
    invalid_dir.mkdir(parents=True, exist_ok=True)
    (invalid_dir / "SKILL.md").write_text("# Missing frontmatter\n", encoding="utf-8")

    results = search_skill_mentions("", root=tmp_path, limit=10)

    assert [item.name for item in results] == ["valid"]
