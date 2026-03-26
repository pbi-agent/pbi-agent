from __future__ import annotations

import os
import stat
from pathlib import Path

import pytest

from pbi_agent.agent.skill_discovery import ProjectSkill, discover_project_skills


def _write_skill(
    root: Path,
    directory_name: str,
    *,
    name: str,
    description: str,
) -> Path:
    skill_dir = root / directory_name
    skill_dir.mkdir(parents=True, exist_ok=True)
    skill_path = skill_dir / "SKILL.md"
    skill_path.write_text(
        f"---\nname: {name}\ndescription: {description}\n---\n\n# {name}\n",
        encoding="utf-8",
    )
    return skill_path


def test_discovers_valid_skill_from_agents_directory(tmp_path: Path) -> None:
    skill_path = _write_skill(
        tmp_path / ".agents" / "skills",
        "code-review",
        name="code-review",
        description="Review code changes.",
    )

    skills = discover_project_skills(tmp_path)

    assert skills == [
        ProjectSkill(
            name="code-review",
            description="Review code changes.",
            location=skill_path.resolve(),
        )
    ]


def test_missing_description_skips_skill(tmp_path: Path, capsys) -> None:
    skill_dir = tmp_path / ".agents" / "skills" / "broken"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text(
        "---\nname: broken\n---\n\n# Broken\n",
        encoding="utf-8",
    )

    skills = discover_project_skills(tmp_path)

    assert skills == []
    assert "missing non-empty 'description'" in capsys.readouterr().err


def test_recovers_malformed_description_line_with_colon(tmp_path: Path) -> None:
    skill_dir = tmp_path / ".agents" / "skills" / "web-research"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text(
        "---\n"
        "name: web-research\n"
        "description: Use this skill when: the user asks for research\n"
        "---\n\n# Web Research\n",
        encoding="utf-8",
    )

    skills = discover_project_skills(tmp_path)

    assert [skill.description for skill in skills] == [
        "Use this skill when: the user asks for research"
    ]


def test_name_directory_mismatch_warns_but_loads(tmp_path: Path, capsys) -> None:
    _write_skill(
        tmp_path / ".agents" / "skills",
        "folder-name",
        name="skill-name",
        description="Mismatch is allowed.",
    )

    skills = discover_project_skills(tmp_path)

    assert [skill.name for skill in skills] == ["skill-name"]
    assert "does not match parent directory" in capsys.readouterr().err


def test_unparseable_frontmatter_is_skipped(tmp_path: Path, capsys) -> None:
    skill_dir = tmp_path / ".agents" / "skills" / "broken"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text(
        "---\nthis has no colon\n---\n",
        encoding="utf-8",
    )

    skills = discover_project_skills(tmp_path)

    assert skills == []
    assert "not a key-value pair" in capsys.readouterr().err


@pytest.mark.skipif(os.name == "nt", reason="chmod not effective on Windows")
def test_unreadable_skill_file_is_skipped(tmp_path: Path, capsys) -> None:
    skill_path = _write_skill(
        tmp_path / ".agents" / "skills",
        "private-skill",
        name="private-skill",
        description="Will become unreadable.",
    )
    skill_path.chmod(0)

    try:
        skills = discover_project_skills(tmp_path)
        assert skills == []
        assert "unreadable" in capsys.readouterr().err.lower()
    finally:
        skill_path.chmod(stat.S_IRUSR | stat.S_IWUSR)
