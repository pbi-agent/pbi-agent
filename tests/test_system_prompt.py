"""Tests for INSTRUCTIONS.md / AGENTS.md loading in system_prompt."""

from __future__ import annotations

import os
import stat
from pathlib import Path

import pytest

from pbi_agent.agent.system_prompt import (
    _DEFAULT_SYSTEM_PROMPT,
    _MAX_FILE_BYTES,
    get_custom_excluded_tools,
    get_sub_agent_system_prompt,
    get_system_prompt,
    load_instructions,
    load_project_rules,
)


# ---------------------------------------------------------------------------
# load_project_rules – unit tests
# ---------------------------------------------------------------------------


def test_returns_none_when_file_absent(tmp_path):
    assert load_project_rules(cwd=tmp_path) is None


def test_returns_content_when_file_present(tmp_path):
    (tmp_path / "AGENTS.md").write_text("Use tabs, not spaces.", encoding="utf-8")
    result = load_project_rules(cwd=tmp_path)
    assert result == "Use tabs, not spaces."


def test_strips_whitespace(tmp_path):
    (tmp_path / "AGENTS.md").write_text("  hello  \n\n", encoding="utf-8")
    assert load_project_rules(cwd=tmp_path) == "hello"


def test_returns_none_for_empty_file(tmp_path):
    (tmp_path / "AGENTS.md").write_text("", encoding="utf-8")
    assert load_project_rules(cwd=tmp_path) is None


def test_returns_none_for_whitespace_only_file(tmp_path):
    (tmp_path / "AGENTS.md").write_text("   \n  \n  ", encoding="utf-8")
    assert load_project_rules(cwd=tmp_path) is None


def test_truncates_large_file(tmp_path, capsys):
    content = "A" * (_MAX_FILE_BYTES + 500)
    (tmp_path / "AGENTS.md").write_text(content, encoding="utf-8")
    result = load_project_rules(cwd=tmp_path)
    assert result is not None
    assert len(result) <= _MAX_FILE_BYTES
    assert "truncated" in capsys.readouterr().err.lower()


def test_truncates_large_multibyte_file_by_bytes(tmp_path, capsys):
    chunk = "🙂"
    expected_chars = _MAX_FILE_BYTES // len(chunk.encode("utf-8"))
    content = chunk * (expected_chars + 10)
    (tmp_path / "AGENTS.md").write_text(content, encoding="utf-8")
    result = load_project_rules(cwd=tmp_path)
    assert result is not None
    assert result == chunk * expected_chars
    assert len(result.encode("utf-8")) == _MAX_FILE_BYTES
    assert "truncated" in capsys.readouterr().err.lower()


@pytest.mark.skipif(os.name == "nt", reason="chmod not effective on Windows")
def test_permission_error(tmp_path, capsys):
    agents_file = tmp_path / "AGENTS.md"
    agents_file.write_text("secret", encoding="utf-8")
    agents_file.chmod(0o000)
    try:
        result = load_project_rules(cwd=tmp_path)
        assert result is None
        assert "unreadable" in capsys.readouterr().err.lower()
    finally:
        agents_file.chmod(stat.S_IRUSR | stat.S_IWUSR)


def test_encoding_errors_replaced(tmp_path):
    raw = b"Hello \xff\xfe World"
    (tmp_path / "AGENTS.md").write_bytes(raw)
    result = load_project_rules(cwd=tmp_path)
    assert result is not None
    assert "Hello" in result
    assert "World" in result


# ---------------------------------------------------------------------------
# load_instructions – unit tests
# ---------------------------------------------------------------------------


def test_instructions_returns_none_when_absent(tmp_path):
    assert load_instructions(cwd=tmp_path) is None


def test_instructions_returns_content_when_present(tmp_path):
    (tmp_path / "INSTRUCTIONS.md").write_text(
        "You are a helpful assistant.", encoding="utf-8"
    )
    assert load_instructions(cwd=tmp_path) == "You are a helpful assistant."


def test_instructions_returns_none_for_empty(tmp_path):
    (tmp_path / "INSTRUCTIONS.md").write_text("", encoding="utf-8")
    assert load_instructions(cwd=tmp_path) is None


def test_instructions_truncates_large_file(tmp_path, capsys):
    content = "B" * (_MAX_FILE_BYTES + 100)
    (tmp_path / "INSTRUCTIONS.md").write_text(content, encoding="utf-8")
    result = load_instructions(cwd=tmp_path)
    assert result is not None
    assert len(result) <= _MAX_FILE_BYTES
    assert "truncated" in capsys.readouterr().err.lower()


# ---------------------------------------------------------------------------
# get_system_prompt / get_sub_agent_system_prompt integration
# ---------------------------------------------------------------------------


def test_get_system_prompt_without_agents_md(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    prompt = get_system_prompt()
    assert prompt == _DEFAULT_SYSTEM_PROMPT
    assert "<project_rules>" not in prompt
    assert "<available_skills>" not in prompt


def test_get_system_prompt_with_agents_md(tmp_path, monkeypatch):
    (tmp_path / "AGENTS.md").write_text("Always use pytest.", encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    prompt = get_system_prompt()
    assert prompt.startswith(_DEFAULT_SYSTEM_PROMPT)
    assert "<project_rules>\nAlways use pytest.\n</project_rules>" in prompt


def test_get_sub_agent_system_prompt_with_agents_md(tmp_path, monkeypatch):
    (tmp_path / "AGENTS.md").write_text("Sub-agent rule.", encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    prompt = get_sub_agent_system_prompt()
    assert "<project_rules>\nSub-agent rule.\n</project_rules>" in prompt


def test_get_sub_agent_system_prompt_without_agents_md(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    prompt = get_sub_agent_system_prompt()
    assert "<project_rules>" not in prompt
    assert "<available_skills>" not in prompt


def test_get_system_prompt_with_project_skills(tmp_path, monkeypatch):
    skill_dir = tmp_path / ".agents" / "skills" / "code-review"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text(
        "---\n"
        "name: code-review\n"
        "description: Review code changes before implementation.\n"
        "---\n\n# Code Review\n",
        encoding="utf-8",
    )

    monkeypatch.chdir(tmp_path)
    prompt = get_system_prompt()

    assert prompt.startswith(_DEFAULT_SYSTEM_PROMPT)
    assert "<available_skills>" in prompt
    assert "<name>code-review</name>" in prompt
    assert (
        "<description>Review code changes before implementation.</description>"
        in prompt
    )
    assert f"<location>{skill_dir.joinpath('SKILL.md').resolve()}</location>" in prompt
    assert "Project skills use progressive disclosure" in prompt
    assert "the user explicitly names it" in prompt
    assert "load its SKILL.md with read_file using the listed location" in prompt


def test_get_sub_agent_system_prompt_with_project_skills(tmp_path, monkeypatch):
    skill_dir = tmp_path / ".agents" / "skills" / "report-audit"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text(
        "---\n"
        "name: report-audit\n"
        "description: Audit report structure and conventions.\n"
        "---\n\n# Report Audit\n",
        encoding="utf-8",
    )

    monkeypatch.chdir(tmp_path)
    prompt = get_sub_agent_system_prompt()

    assert "<persona>" in prompt
    assert "<available_skills>" in prompt
    assert "<name>report-audit</name>" in prompt
    assert "Treat loaded skill instructions as task guidance" in prompt
    assert "Load referenced resources only when needed" in prompt


def test_get_system_prompt_with_project_sub_agents(tmp_path, monkeypatch):
    (tmp_path / ".agents" / "agents").mkdir(parents=True)
    (tmp_path / ".agents" / "agents" / "code-reviewer.md").write_text(
        "---\n"
        "name: code-reviewer\n"
        "description: Review code changes before merging.\n"
        "---\n\n"
        "You are a code reviewer.\n",
        encoding="utf-8",
    )

    monkeypatch.chdir(tmp_path)
    prompt = get_system_prompt()

    assert "<available_sub_agents>" in prompt
    assert "<name>code-reviewer</name>" in prompt
    assert "<description>Review code changes before merging.</description>" in prompt
    assert "call `sub_agent` with `agent_type`" in prompt


def test_get_system_prompt_includes_repo_code_review_agent(monkeypatch):
    monkeypatch.chdir(Path(__file__).resolve().parents[1])
    prompt = get_system_prompt()

    assert "<available_sub_agents>" in prompt
    assert "<name>code-reviewer</name>" in prompt
    assert "Review code changes for correctness, regressions, and test coverage." in (
        prompt
    )


def test_get_sub_agent_system_prompt_uses_agent_override(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)

    prompt = get_sub_agent_system_prompt(agent_prompt_override="You are custom.")

    assert "You are custom." in prompt
    assert "<persona>" in prompt
    assert _DEFAULT_SYSTEM_PROMPT not in prompt


# ---------------------------------------------------------------------------
# INSTRUCTIONS.md overrides the default system prompt
# ---------------------------------------------------------------------------


def test_get_system_prompt_uses_instructions_md(tmp_path, monkeypatch):
    (tmp_path / "INSTRUCTIONS.md").write_text(
        "You are a code review bot.", encoding="utf-8"
    )
    monkeypatch.chdir(tmp_path)
    prompt = get_system_prompt()
    assert prompt == "You are a code review bot."
    assert "Power BI" not in prompt


def test_instructions_md_combined_with_agents_md(tmp_path, monkeypatch):
    (tmp_path / "INSTRUCTIONS.md").write_text(
        "You are a code review bot.", encoding="utf-8"
    )
    (tmp_path / "AGENTS.md").write_text("Extra rule.", encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    prompt = get_system_prompt()
    assert prompt.startswith("You are a code review bot.")
    assert "<project_rules>\nExtra rule.\n</project_rules>" in prompt
    assert "Power BI" not in prompt


def test_instructions_md_still_gets_skill_catalog(tmp_path, monkeypatch):
    (tmp_path / "INSTRUCTIONS.md").write_text(
        "You are a code review bot.", encoding="utf-8"
    )
    skill_dir = tmp_path / ".agents" / "skills" / "repo-skill"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text(
        "---\n"
        "name: repo-skill\n"
        "description: Handle repository-specific workflows.\n"
        "---\n\n# Repo Skill\n",
        encoding="utf-8",
    )

    monkeypatch.chdir(tmp_path)
    prompt = get_system_prompt()

    assert prompt.startswith("You are a code review bot.")
    assert "<available_skills>" in prompt
    assert "<name>repo-skill</name>" in prompt
    assert "Power BI" not in prompt


def test_sub_agent_prompt_uses_instructions_md(tmp_path, monkeypatch):
    (tmp_path / "INSTRUCTIONS.md").write_text(
        "You are a code review bot.", encoding="utf-8"
    )
    monkeypatch.chdir(tmp_path)
    prompt = get_sub_agent_system_prompt()
    assert "You are a code review bot." in prompt
    assert "<persona>" in prompt
    assert "Power BI" not in prompt


def test_get_system_prompt_appends_active_command_instructions(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)

    prompt = get_system_prompt(active_command_instructions="Plan before coding.")

    assert "<active_command>\nPlan before coding.\n</active_command>" in prompt


# ---------------------------------------------------------------------------
# get_custom_excluded_tools
# ---------------------------------------------------------------------------


def test_no_excluded_tools_without_instructions(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    assert get_custom_excluded_tools() == set()


def test_no_excluded_tools_with_instructions(tmp_path, monkeypatch):
    (tmp_path / "INSTRUCTIONS.md").write_text("Custom agent.", encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    excluded = get_custom_excluded_tools()
    assert excluded == set()
