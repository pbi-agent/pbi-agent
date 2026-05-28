from __future__ import annotations

from pathlib import Path

import pytest

from pbi_agent.agent.reference_resolution import (
    resolve_command_references,
    resolve_skill_references,
    resolve_sub_agent_references,
)
from pbi_agent.config import ConfigError
from pbi_agent.skills.state import set_skill_enabled


def _write_skill(
    root: Path,
    name: str,
    *,
    description: str = "Useful skill.",
) -> None:
    skill_dir = root / ".agents" / "skills" / name
    skill_dir.mkdir(parents=True, exist_ok=True)
    (skill_dir / "SKILL.md").write_text(
        f"---\nname: {name}\ndescription: {description}\n---\n\n# {name}\n",
        encoding="utf-8",
    )


def _write_command(
    root: Path,
    name: str,
    *,
    description: str = "Useful command.",
) -> None:
    command_dir = root / ".agents" / "commands"
    command_dir.mkdir(parents=True, exist_ok=True)
    (command_dir / f"{name}.md").write_text(
        f"---\nname: {name}\ndescription: {description}\n---\n\nDo the work.\n",
        encoding="utf-8",
    )


def _write_sub_agent(
    root: Path,
    name: str,
    *,
    description: str = "Useful agent.",
) -> None:
    agent_dir = root / ".agents" / "agents"
    agent_dir.mkdir(parents=True, exist_ok=True)
    (agent_dir / f"{name}.md").write_text(
        f"---\nname: {name}\ndescription: {description}\n---\n\nDo the work.\n",
        encoding="utf-8",
    )


def test_resolve_skill_references_preserves_configured_order(
    tmp_path: Path,
) -> None:
    _write_skill(tmp_path, "fastapi")
    _write_skill(tmp_path, "shadcn")

    skills = resolve_skill_references(("shadcn", "fastapi"), tmp_path)

    assert skills is not None
    assert [skill.name for skill in skills] == ["shadcn", "fastapi"]


def test_resolve_skill_references_warns_and_omits_missing_or_disabled(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _write_skill(tmp_path, "fastapi")
    _write_skill(tmp_path, "disabled")
    set_skill_enabled("disabled", False, workspace=tmp_path)

    skills = resolve_skill_references(
        ("fastapi", "missing", "disabled"),
        tmp_path,
        source_label="Command 'review'",
    )

    assert skills is not None
    assert [skill.name for skill in skills] == ["fastapi"]
    stderr = capsys.readouterr().err
    assert (
        "Command 'review' references unavailable or disabled skill 'missing'" in stderr
    )
    assert (
        "Command 'review' references unavailable or disabled skill 'disabled'" in stderr
    )


def test_resolve_command_references_strict_raises_config_error(
    tmp_path: Path,
) -> None:
    _write_command(tmp_path, "review")

    with pytest.raises(ConfigError, match="unknown command 'missing'"):
        resolve_command_references(
            ("review", "missing"),
            tmp_path,
            strict=True,
            source_label="Sub-agent 'reviewer'",
        )


def test_resolve_sub_agent_references_warns_and_omits_invalid(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _write_sub_agent(tmp_path, "reviewer")

    agents = resolve_sub_agent_references(
        ("reviewer", "missing"),
        tmp_path,
        source_label="Command 'review'",
    )

    assert agents is not None
    assert [agent.name for agent in agents] == ["reviewer"]
    assert (
        "Command 'review' references unavailable or disabled sub-agent 'missing'"
        in capsys.readouterr().err
    )


def test_absent_reference_lists_return_none(tmp_path: Path) -> None:
    assert resolve_skill_references(None, tmp_path) is None
    assert resolve_command_references(None, tmp_path) is None
    assert resolve_sub_agent_references(None, tmp_path) is None
