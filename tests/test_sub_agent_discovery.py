from __future__ import annotations

import os
import stat
from pathlib import Path

import pytest

from pbi_agent.agent.sub_agent_discovery import (
    ProjectSubAgent,
    discover_project_sub_agents,
    format_project_sub_agents_markdown,
    get_project_sub_agent_by_name,
)


def _write_sub_agent(root: Path, filename: str, content: str) -> Path:
    agent_dir = root / ".agents"
    agent_dir.mkdir(parents=True, exist_ok=True)
    path = agent_dir / filename
    path.write_text(content, encoding="utf-8")
    return path


def test_discovers_valid_project_sub_agent(tmp_path: Path) -> None:
    agent_path = _write_sub_agent(
        tmp_path,
        "code-reviewer.md",
        (
            "---\n"
            "name: code-reviewer\n"
            "description: Reviews code changes.\n"
            "---\n\n"
            "You are a code reviewer.\n"
        ),
    )

    agents = discover_project_sub_agents(tmp_path)

    assert agents == [
        ProjectSubAgent(
            name="code-reviewer",
            description="Reviews code changes.",
            model=None,
            reasoning_effort=None,
            system_prompt="You are a code reviewer.",
            location=agent_path.resolve(),
        )
    ]


def test_skips_missing_description(tmp_path: Path, capsys) -> None:
    _write_sub_agent(
        tmp_path,
        "broken.md",
        "---\nname: broken\n---\n\nBody\n",
    )

    agents = discover_project_sub_agents(tmp_path)

    assert agents == []
    assert "missing non-empty 'description'" in capsys.readouterr().err


def test_skips_missing_frontmatter(tmp_path: Path, capsys) -> None:
    _write_sub_agent(tmp_path, "broken.md", "No frontmatter here.\n")

    agents = discover_project_sub_agents(tmp_path)

    assert agents == []
    assert "missing YAML frontmatter" in capsys.readouterr().err


def test_duplicate_names_keep_first_loaded(tmp_path: Path, capsys) -> None:
    first = _write_sub_agent(
        tmp_path,
        "alpha.md",
        ("---\nname: reviewer\ndescription: First reviewer.\n---\n\nFirst prompt.\n"),
    )
    _write_sub_agent(
        tmp_path,
        "beta.md",
        ("---\nname: reviewer\ndescription: Second reviewer.\n---\n\nSecond prompt.\n"),
    )

    agents = discover_project_sub_agents(tmp_path)

    assert agents == [
        ProjectSubAgent(
            name="reviewer",
            description="First reviewer.",
            model=None,
            reasoning_effort=None,
            system_prompt="First prompt.",
            location=first.resolve(),
        )
    ]
    assert "duplicate name 'reviewer'" in capsys.readouterr().err


def test_description_supports_colons_and_block_scalars(tmp_path: Path) -> None:
    _write_sub_agent(
        tmp_path,
        "researcher.md",
        (
            "---\n"
            "name: researcher\n"
            "description: >\n"
            "  Use this sub-agent when: the task needs focused repository research.\n"
            "  Prefer it for broad codebase lookups.\n"
            "---\n\n"
            "Research prompt.\n"
        ),
    )

    agents = discover_project_sub_agents(tmp_path)

    assert [agent.description for agent in agents] == [
        "Use this sub-agent when: the task needs focused repository research. Prefer it for broad codebase lookups."
    ]


def test_description_supports_simple_quoted_scalars(tmp_path: Path) -> None:
    _write_sub_agent(
        tmp_path,
        "reviewer.md",
        (
            "---\n"
            "name: reviewer\n"
            'description: "Reviews code changes before merge."\n'
            "---\n\n"
            "Review prompt.\n"
        ),
    )

    agents = discover_project_sub_agents(tmp_path)

    assert [agent.description for agent in agents] == [
        "Reviews code changes before merge."
    ]


def test_discovers_agent_model_and_reasoning_effort(tmp_path: Path) -> None:
    _write_sub_agent(
        tmp_path,
        "reviewer.md",
        (
            "---\n"
            "name: reviewer\n"
            "description: Reviews code changes.\n"
            "model: gpt-5.4-mini\n"
            "reasoning_effort: high\n"
            "---\n\n"
            "Review prompt.\n"
        ),
    )

    agents = discover_project_sub_agents(tmp_path)

    assert agents == [
        ProjectSubAgent(
            name="reviewer",
            description="Reviews code changes.",
            model="gpt-5.4-mini",
            reasoning_effort="high",
            system_prompt="Review prompt.",
            location=tmp_path.joinpath(".agents", "reviewer.md").resolve(),
        )
    ]


def test_skips_unsupported_nested_yaml_structures(tmp_path: Path, capsys) -> None:
    _write_sub_agent(
        tmp_path,
        "broken.md",
        (
            "---\n"
            "name:\n"
            "  value: reviewer\n"
            "description: Reviews code.\n"
            "---\n\n"
            "Prompt.\n"
        ),
    )

    agents = discover_project_sub_agents(tmp_path)

    assert agents == []
    assert "unsupported yaml structure" in capsys.readouterr().err.lower()


def test_format_project_sub_agents_markdown_includes_default_note(
    tmp_path: Path,
) -> None:
    result = format_project_sub_agents_markdown(tmp_path)

    assert "### Sub-Agents" in result
    assert "Default: use `sub_agent` without `agent_type`" in result
    assert "No project sub-agents discovered under `.agents/*.md`." in result


def test_get_project_sub_agent_by_name_returns_match(tmp_path: Path) -> None:
    _write_sub_agent(
        tmp_path,
        "reviewer.md",
        ("---\nname: reviewer\ndescription: Reviews code.\n---\n\nPrompt.\n"),
    )

    agent = get_project_sub_agent_by_name("reviewer", tmp_path)

    assert agent is not None
    assert agent.name == "reviewer"


@pytest.mark.skipif(os.name == "nt", reason="chmod not effective on Windows")
def test_unreadable_sub_agent_file_is_skipped(tmp_path: Path, capsys) -> None:
    agent_path = _write_sub_agent(
        tmp_path,
        "private.md",
        ("---\nname: private\ndescription: Hidden.\n---\n\nPrompt.\n"),
    )
    agent_path.chmod(0)

    try:
        agents = discover_project_sub_agents(tmp_path)
        assert agents == []
        assert "unreadable" in capsys.readouterr().err.lower()
    finally:
        agent_path.chmod(stat.S_IRUSR | stat.S_IWUSR)
