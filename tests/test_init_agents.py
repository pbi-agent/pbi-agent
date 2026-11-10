from __future__ import annotations

from pathlib import Path

import pbi_agent.init_agents as init_agents


def test_init_agents_file_creates_only_agents_md(tmp_path: Path) -> None:
    result = init_agents.init_agents_file(workspace=tmp_path)
    rendered = init_agents.format_init_agents_result(result)

    agents_path = tmp_path / "AGENTS.md"
    assert result.created is True
    assert result.overwritten is False
    assert agents_path.read_text(encoding="utf-8") == init_agents.AGENTS_TEMPLATE
    assert rendered == f"Created AGENTS.md at {agents_path.resolve()}"
    assert sorted(p.name for p in tmp_path.iterdir()) == ["AGENTS.md"]


def test_init_agents_file_skips_existing_file_without_force(tmp_path: Path) -> None:
    agents_path = tmp_path / "AGENTS.md"
    agents_path.write_text("existing", encoding="utf-8")

    result = init_agents.init_agents_file(workspace=tmp_path)
    rendered = init_agents.format_init_agents_result(result)

    assert result.created is False
    assert result.overwritten is False
    assert agents_path.read_text(encoding="utf-8") == "existing"
    assert rendered.startswith("Skipped AGENTS.md")
    assert "already exists" in rendered
    assert "--force" in rendered


def test_init_agents_file_force_overwrites_existing_file(tmp_path: Path) -> None:
    agents_path = tmp_path / "AGENTS.md"
    agents_path.write_text("existing", encoding="utf-8")

    result = init_agents.init_agents_file(workspace=tmp_path, force=True)
    rendered = init_agents.format_init_agents_result(result)

    assert result.created is False
    assert result.overwritten is True
    assert agents_path.read_text(encoding="utf-8") == init_agents.AGENTS_TEMPLATE
    assert rendered.startswith("Overwrote AGENTS.md")
