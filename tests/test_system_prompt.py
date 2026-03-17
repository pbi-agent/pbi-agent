"""Tests for AGENTS.md project-rules loading in system_prompt."""

from __future__ import annotations

import os
import stat

import pytest

from pbi_agent.agent.system_prompt import (
    SYSTEM_PROMPT,
    SUB_AGENT_SYSTEM_PROMPT,
    _MAX_PROJECT_RULES_BYTES,
    get_sub_agent_system_prompt,
    get_system_prompt,
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
    content = "A" * (_MAX_PROJECT_RULES_BYTES + 500)
    (tmp_path / "AGENTS.md").write_text(content, encoding="utf-8")
    result = load_project_rules(cwd=tmp_path)
    assert result is not None
    assert len(result) <= _MAX_PROJECT_RULES_BYTES
    assert "truncated" in capsys.readouterr().err.lower()


def test_truncates_large_multibyte_file_by_bytes(tmp_path, capsys):
    chunk = "🙂"
    expected_chars = _MAX_PROJECT_RULES_BYTES // len(chunk.encode("utf-8"))
    content = chunk * (expected_chars + 10)
    (tmp_path / "AGENTS.md").write_text(content, encoding="utf-8")
    result = load_project_rules(cwd=tmp_path)
    assert result is not None
    assert result == chunk * expected_chars
    assert len(result.encode("utf-8")) == _MAX_PROJECT_RULES_BYTES
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
# get_system_prompt / get_sub_agent_system_prompt integration
# ---------------------------------------------------------------------------


def test_get_system_prompt_without_agents_md(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    prompt = get_system_prompt()
    assert prompt == SYSTEM_PROMPT
    assert "<project_rules>" not in prompt


def test_get_system_prompt_with_agents_md(tmp_path, monkeypatch):
    (tmp_path / "AGENTS.md").write_text("Always use pytest.", encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    prompt = get_system_prompt()
    assert prompt.startswith(SYSTEM_PROMPT)
    assert "<project_rules>\nAlways use pytest.\n</project_rules>" in prompt


def test_get_sub_agent_system_prompt_with_agents_md(tmp_path, monkeypatch):
    (tmp_path / "AGENTS.md").write_text("Sub-agent rule.", encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    prompt = get_sub_agent_system_prompt()
    assert prompt.startswith(SUB_AGENT_SYSTEM_PROMPT)
    assert "<project_rules>\nSub-agent rule.\n</project_rules>" in prompt


def test_get_sub_agent_system_prompt_without_agents_md(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    prompt = get_sub_agent_system_prompt()
    assert prompt == SUB_AGENT_SYSTEM_PROMPT
    assert "<project_rules>" not in prompt


def test_system_prompt_mentions_python_exec_data_libraries() -> None:
    assert "`polars`" in SYSTEM_PROMPT
    assert "`pypdf`" in SYSTEM_PROMPT
    assert "`python-docx`" in SYSTEM_PROMPT
