"""Tests for INSTRUCTIONS.md / AGENTS.md / MEMORY.md loading in system_prompt."""

from __future__ import annotations

import os
from pathlib import Path
import stat

import pytest

from pbi_agent.config import CommandConfig, Settings
from pbi_agent.agent.session.shared import _turn_instructions
from pbi_agent.agent.system_prompt import (
    _MAX_FILE_BYTES,
    get_sub_agent_system_prompt,
    get_system_prompt,
    load_instructions,
    load_project_rules,
    load_workspace_memory,
)


def _assert_builtin_prompt_base(prompt: str) -> None:
    assert prompt.startswith("You are task assistant.")
    assert "<tool_usage_rules>" in prompt
    assert "</tool_usage_rules>" in prompt


def _write_skill(tmp_path: Path, name: str, description: str) -> Path:
    skill_dir = tmp_path / ".agents" / "skills" / name
    skill_dir.mkdir(parents=True)
    skill_path = skill_dir / "SKILL.md"
    skill_path.write_text(
        f"---\nname: {name}\ndescription: {description}\n---\n\n# {name}\n",
        encoding="utf-8",
    )
    return skill_path


def _write_sub_agent(tmp_path: Path, name: str, description: str) -> Path:
    agent_dir = tmp_path / ".agents" / "agents"
    agent_dir.mkdir(parents=True, exist_ok=True)
    agent_path = agent_dir / f"{name}.md"
    agent_path.write_text(
        f"---\nname: {name}\ndescription: {description}\n---\n\n# {name}\n",
        encoding="utf-8",
    )
    return agent_path


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
# load_workspace_memory – unit tests
# ---------------------------------------------------------------------------


def test_workspace_memory_returns_none_when_file_absent(tmp_path):
    assert load_workspace_memory(cwd=tmp_path) is None


def test_workspace_memory_returns_stripped_content_when_file_present(tmp_path):
    (tmp_path / "MEMORY.md").write_text("  Remember pytest.  \n\n", encoding="utf-8")
    result = load_workspace_memory(cwd=tmp_path)
    assert result == "Remember pytest."


def test_workspace_memory_returns_none_for_empty_file(tmp_path):
    (tmp_path / "MEMORY.md").write_text("", encoding="utf-8")
    assert load_workspace_memory(cwd=tmp_path) is None


def test_workspace_memory_returns_none_for_whitespace_only_file(tmp_path):
    (tmp_path / "MEMORY.md").write_text("   \n  \n  ", encoding="utf-8")
    assert load_workspace_memory(cwd=tmp_path) is None


def test_workspace_memory_truncates_large_file(tmp_path, capsys):
    content = "M" * (_MAX_FILE_BYTES + 500)
    (tmp_path / "MEMORY.md").write_text(content, encoding="utf-8")
    result = load_workspace_memory(cwd=tmp_path)
    assert result is not None
    assert len(result) <= _MAX_FILE_BYTES
    assert "MEMORY.md exceeds 1 MB" in capsys.readouterr().err


@pytest.mark.skipif(os.name == "nt", reason="chmod not effective on Windows")
def test_workspace_memory_permission_error(tmp_path, capsys):
    memory_file = tmp_path / "MEMORY.md"
    memory_file.write_text("secret", encoding="utf-8")
    memory_file.chmod(0o000)
    try:
        result = load_workspace_memory(cwd=tmp_path)
        assert result is None
        assert "MEMORY.md found but unreadable" in capsys.readouterr().err
    finally:
        memory_file.chmod(stat.S_IRUSR | stat.S_IWUSR)


def test_workspace_memory_encoding_errors_replaced(tmp_path):
    raw = b"Hello \xff\xfe Memory"
    (tmp_path / "MEMORY.md").write_bytes(raw)
    result = load_workspace_memory(cwd=tmp_path)
    assert result is not None
    assert "Hello" in result
    assert "Memory" in result


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
    _assert_builtin_prompt_base(prompt)
    assert prompt.endswith("</tool_usage_rules>")
    assert "<project_rules>" not in prompt
    assert "<workspace_memory>" not in prompt
    assert "<available_skills>" not in prompt


def test_get_system_prompt_with_agents_md(tmp_path, monkeypatch):
    (tmp_path / "AGENTS.md").write_text("Always use pytest.", encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    prompt = get_system_prompt()
    _assert_builtin_prompt_base(prompt)
    assert "<project_rules>\nAlways use pytest.\n</project_rules>" in prompt


def test_get_system_prompt_with_agents_and_memory_orders_sections(tmp_path):
    (tmp_path / "AGENTS.md").write_text("Always use pytest.", encoding="utf-8")
    (tmp_path / "MEMORY.md").write_text("Remember the release note.", encoding="utf-8")
    _write_skill(tmp_path, "release-notes", "Prepare release notes.")

    prompt = get_system_prompt(
        active_command_instructions="Plan before coding.",
        cwd=tmp_path,
    )

    assert "<project_rules>\nAlways use pytest.\n</project_rules>" in prompt
    assert (
        "<workspace_memory>\nRemember the release note.\n</workspace_memory>" in prompt
    )
    assert prompt.index("</project_rules>") < prompt.index("<skill_loading_rules>")
    assert prompt.index("</available_skills>") < prompt.index("<active_command>")
    assert prompt.index("</active_command>") < prompt.index("<workspace_memory>")
    assert prompt.endswith(
        "<workspace_memory>\nRemember the release note.\n</workspace_memory>"
    )


def test_get_system_prompt_with_memory_md_without_agents_md(tmp_path):
    (tmp_path / "MEMORY.md").write_text("Remember local decisions.", encoding="utf-8")

    prompt = get_system_prompt(cwd=tmp_path)

    assert "<project_rules>" not in prompt
    assert (
        "<workspace_memory>\nRemember local decisions.\n</workspace_memory>" in prompt
    )


def test_get_sub_agent_system_prompt_with_agents_md(tmp_path, monkeypatch):
    (tmp_path / "AGENTS.md").write_text("Sub-agent rule.", encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    prompt = get_sub_agent_system_prompt()
    assert "<project_rules>\nSub-agent rule.\n</project_rules>" in prompt


def test_get_sub_agent_system_prompt_with_memory_md(tmp_path):
    (tmp_path / "MEMORY.md").write_text("Sub-agent memory.", encoding="utf-8")
    _write_skill(tmp_path, "sub-agent-memory", "Exercise sub-agent memory ordering.")

    prompt = get_sub_agent_system_prompt(cwd=tmp_path)

    assert "<project_rules>" not in prompt
    assert "<workspace_memory>\nSub-agent memory.\n</workspace_memory>" in prompt
    assert prompt.index("</available_skills>") < prompt.index("<workspace_memory>")
    assert prompt.endswith("<workspace_memory>\nSub-agent memory.\n</workspace_memory>")


def test_get_sub_agent_system_prompt_without_agents_md(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    prompt = get_sub_agent_system_prompt()
    assert "<project_rules>" not in prompt
    assert "<workspace_memory>" not in prompt
    assert "<available_skills>" not in prompt


def test_get_sub_agent_system_prompt_appends_component_commands_in_order(tmp_path):
    prompt = get_sub_agent_system_prompt(
        agent_prompt_override="Review implementation and tests.",
        cwd=tmp_path,
        component_commands=(
            CommandConfig(
                id="review",
                name="Review",
                slash_alias="/review",
                description="Review command.",
                instructions="First command body.",
                model_profile_id="command-profile",
                allowed_tools=("shell",),
                skills=("fastapi",),
                sub_agents=("fixer",),
            ),
            CommandConfig(
                id="qa",
                name="QA",
                slash_alias="/qa",
                description="QA command.",
                instructions="Second command body.",
            ),
        ),
    )

    assert prompt.index("Review implementation and tests.") < prompt.index(
        "<component_commands>"
    )
    assert prompt.index("First command body.") < prompt.index("Second command body.")
    assert '<component_command name="Review" alias="/review">' in prompt
    assert '<component_command name="QA" alias="/qa">' in prompt
    assert "command-profile" not in prompt
    assert "fastapi" not in prompt
    assert "fixer" not in prompt


def test_get_sub_agent_system_prompt_marks_component_commands_active(tmp_path):
    prompt = get_sub_agent_system_prompt(
        agent_prompt_override="You are the orchestrator.",
        cwd=tmp_path,
        component_commands=(
            CommandConfig(
                id="orchestrate",
                name="orchestrate",
                slash_alias="/orchestrate",
                description="Run orchestration.",
                instructions=(
                    "The main agent orchestrates only and delegates to worker."
                ),
            ),
        ),
    )

    assert "`<component_commands>` active" in prompt
    assert '"main/orchestrating agent" = you' in prompt
    assert "Use nested `sub_agent` when required+available" in prompt
    assert "TODO.md/MEMORY.md ownership only blocks those edits" in prompt


def test_get_sub_agent_system_prompt_appends_component_commands_without_agent_body(
    tmp_path,
):
    prompt = get_sub_agent_system_prompt(
        agent_prompt_override="",
        cwd=tmp_path,
        component_commands=(
            CommandConfig(
                id="review",
                name="Review",
                slash_alias="/review",
                description="Review command.",
                instructions="Review command body.",
            ),
        ),
    )

    assert "<component_commands>" in prompt
    assert "Review command body." in prompt
    assert '<component_command name="Review" alias="/review">' in prompt


def test_get_system_prompt_with_project_skills(tmp_path, monkeypatch):
    skill_path = _write_skill(
        tmp_path,
        "code-review",
        "Review code changes before implementation.",
    )

    monkeypatch.chdir(tmp_path)
    prompt = get_system_prompt()

    _assert_builtin_prompt_base(prompt)
    assert "<available_skills>" in prompt
    assert "<name>code-review</name>" in prompt
    assert (
        "<description>Review code changes before implementation.</description>"
        in prompt
    )
    assert f"<location>{skill_path.resolve()}</location>" in prompt
    assert "Project skills use progressive disclosure" in prompt
    assert "the user explicitly names it" in prompt
    assert "Treat `$<skill-name>` in user input as an explicit request" in prompt
    assert "strip the `$` and match `<skill-name>`" in prompt
    assert (
        'load its SKILL.md with `explore_workspace` target="read" using the listed location'
        in prompt
    )


def test_get_system_prompt_scopes_available_skills_to_command_skill_names(tmp_path):
    _write_skill(tmp_path, "fastapi", "Build FastAPI routes.")
    _write_skill(tmp_path, "shadcn", "Build shadcn UI.")

    prompt = get_system_prompt(
        cwd=tmp_path,
        visible_skill_names=("fastapi",),
        explicit_skill_names={"shadcn"},
    )

    assert "<available_skills>" in prompt
    assert "<name>fastapi</name>" in prompt
    assert "<name>shadcn</name>" not in prompt


def test_get_system_prompt_includes_disabled_command_skill_and_omits_missing(
    tmp_path,
    capsys,
):
    from pbi_agent.skills.state import set_skill_enabled

    _write_skill(tmp_path, "fastapi", "Build FastAPI routes.")
    _write_skill(tmp_path, "hibench-communication", "Draft benchmark updates.")
    set_skill_enabled("hibench-communication", False, workspace=tmp_path)

    prompt = get_system_prompt(
        cwd=tmp_path,
        visible_skill_names=(
            "fastapi",
            "hibench-communication",
            "missing-skill",
        ),
    )

    assert "<name>fastapi</name>" in prompt
    assert "<name>hibench-communication</name>" in prompt
    assert "missing-skill" not in prompt
    stderr = capsys.readouterr().err
    assert "Command frontmatter references unknown skill 'missing-skill'" in stderr
    assert "unavailable or disabled skill 'hibench-communication'" not in stderr


def test_get_sub_agent_system_prompt_scopes_available_skills_to_agent_skill_names(
    tmp_path,
):
    _write_skill(tmp_path, "fastapi", "Build FastAPI routes.")
    _write_skill(tmp_path, "shadcn", "Build shadcn UI.")

    prompt = get_sub_agent_system_prompt(
        cwd=tmp_path,
        visible_skill_names=("fastapi",),
        explicit_skill_names={"shadcn"},
        skill_source_label="Sub-agent 'reviewer' frontmatter",
    )

    assert "<available_skills>" in prompt
    assert "<name>fastapi</name>" in prompt
    assert "<name>shadcn</name>" not in prompt


def test_get_sub_agent_system_prompt_includes_disabled_agent_skill(
    tmp_path,
    capsys,
):
    from pbi_agent.skills.state import set_skill_enabled

    _write_skill(tmp_path, "fastapi", "Build FastAPI routes.")
    _write_skill(tmp_path, "hibench-communication", "Draft benchmark updates.")
    set_skill_enabled("hibench-communication", False, workspace=tmp_path)

    prompt = get_sub_agent_system_prompt(
        cwd=tmp_path,
        visible_skill_names=("fastapi", "hibench-communication", "missing-skill"),
        skill_source_label="Sub-agent 'reviewer' frontmatter",
    )

    assert "<name>fastapi</name>" in prompt
    assert "<name>hibench-communication</name>" in prompt
    assert "missing-skill" not in prompt
    stderr = capsys.readouterr().err
    assert (
        "Sub-agent 'reviewer' frontmatter references unknown skill 'missing-skill'"
        in stderr
    )
    assert "unavailable or disabled skill 'hibench-communication'" not in stderr


def test_get_sub_agent_system_prompt_warns_and_omits_missing_agent_skill(
    tmp_path,
    capsys,
):
    _write_skill(tmp_path, "fastapi", "Build FastAPI routes.")

    prompt = get_sub_agent_system_prompt(
        cwd=tmp_path,
        visible_skill_names=("fastapi", "missing-skill"),
        skill_source_label="Sub-agent 'reviewer' frontmatter",
    )

    assert "<name>fastapi</name>" in prompt
    assert "missing-skill" not in prompt
    assert (
        "Sub-agent 'reviewer' frontmatter references unknown skill "
        "'missing-skill'; omitting." in capsys.readouterr().err
    )


def test_turn_instructions_scope_command_skills_and_ignore_external_mentions(
    tmp_path,
):
    _write_skill(tmp_path, "fastapi", "Build FastAPI routes.")
    _write_skill(tmp_path, "shadcn", "Build shadcn UI.")

    instructions = _turn_instructions(
        "Review implementation.",
        settings=Settings(api_key="test-key", provider="openai"),
        cwd=tmp_path,
        user_input="/review please use $shadcn",
        visible_skill_names=("fastapi",),
    )

    assert instructions is not None
    assert "<active_command>\nReview implementation.\n</active_command>" in instructions
    assert "<name>fastapi</name>" in instructions
    assert "<name>shadcn</name>" not in instructions


def test_disabled_project_skill_is_hidden_unless_explicitly_tagged(
    tmp_path,
):
    from pbi_agent.skills.state import set_skill_enabled

    skill_dir = tmp_path / ".agents" / "skills" / "quiet-skill"
    skill_dir.mkdir(parents=True)
    skill_path = skill_dir / "SKILL.md"
    original_content = (
        "---\n"
        "name: quiet-skill\n"
        "description: Quietly assist when explicitly requested.\n"
        "---\n\n# Quiet Skill\n"
    )
    skill_path.write_text(original_content, encoding="utf-8")
    set_skill_enabled("quiet-skill", False, workspace=tmp_path)

    prompt = get_system_prompt(cwd=tmp_path)
    explicit_prompt = get_system_prompt(
        cwd=tmp_path,
        explicit_skill_names={"quiet-skill"},
    )

    assert "<name>quiet-skill</name>" not in prompt
    assert "<name>quiet-skill</name>" in explicit_prompt
    assert skill_path.read_text(encoding="utf-8") == original_content
    assert not (tmp_path / ".agents" / "skills" / ".skill-state.json").exists()
    assert Path(os.environ["PBI_AGENT_SESSION_DB_PATH"]).is_file()


def test_disabled_project_skill_uses_explicit_workspace_directory_key(
    tmp_path,
    monkeypatch,
):
    from pbi_agent.skills.state import set_skill_enabled

    monkeypatch.setenv("PBI_AGENT_WORKSPACE_KEY", "env-workspace-key")
    skill_dir = tmp_path / ".agents" / "skills" / "active-skill"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text(
        "---\n"
        "name: active-skill\n"
        "description: Active workspace scoped skill.\n"
        "---\n\n# Active Skill\n",
        encoding="utf-8",
    )
    set_skill_enabled(
        "active-skill",
        False,
        workspace=tmp_path,
        directory_key="active-workspace-key",
    )

    prompt = get_system_prompt(
        cwd=tmp_path,
        workspace_directory_key="active-workspace-key",
    )

    assert "<name>active-skill</name>" not in prompt


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


def test_get_system_prompt_scopes_available_sub_agents_to_command_names(tmp_path):
    _write_sub_agent(tmp_path, "reviewer", "Review code changes.")
    _write_sub_agent(tmp_path, "fixer", "Fix code changes.")

    prompt = get_system_prompt(
        cwd=tmp_path,
        visible_agent_names=("reviewer",),
        explicit_agent_names={"fixer"},
    )

    assert "<available_sub_agents>" in prompt
    assert "<name>reviewer</name>" in prompt
    assert "<name>fixer</name>" not in prompt
    assert "without `agent_type` for the default generalist" not in prompt
    assert (
        "with `agent_type` set to one of the available project sub-agent names"
        in prompt
    )


def test_get_system_prompt_includes_disabled_command_sub_agent(tmp_path):
    from pbi_agent.agents.state import set_agent_enabled

    _write_sub_agent(tmp_path, "reviewer", "Review code changes.")
    _write_sub_agent(tmp_path, "fixer", "Fix code changes.")
    set_agent_enabled("fixer", False, workspace=tmp_path)

    prompt = get_system_prompt(
        cwd=tmp_path,
        visible_agent_names=("reviewer", "fixer"),
    )

    assert "<available_sub_agents>" in prompt
    assert "<name>reviewer</name>" in prompt
    assert "<name>fixer</name>" in prompt


def test_get_sub_agent_system_prompt_includes_disabled_nested_sub_agent(tmp_path):
    from pbi_agent.agents.state import set_agent_enabled

    _write_sub_agent(tmp_path, "confidence-checker", "Check confidence.")
    _write_sub_agent(tmp_path, "fixer", "Fix code changes.")
    set_agent_enabled("confidence-checker", False, workspace=tmp_path)
    set_agent_enabled("fixer", False, workspace=tmp_path)

    prompt = get_sub_agent_system_prompt(
        cwd=tmp_path,
        visible_agent_names=("confidence-checker", "fixer"),
        agent_source_label="Sub-agent 'reviewer' frontmatter",
    )

    assert "<available_sub_agents>" in prompt
    assert "<name>confidence-checker</name>" in prompt
    assert "<name>fixer</name>" in prompt


def test_turn_instructions_scope_command_sub_agents_and_ignore_external_mentions(
    tmp_path,
):
    _write_sub_agent(tmp_path, "reviewer", "Review code changes.")
    _write_sub_agent(tmp_path, "fixer", "Fix code changes.")

    instructions = _turn_instructions(
        "Review implementation.",
        settings=Settings(api_key="test-key", provider="openai"),
        cwd=tmp_path,
        user_input="/review please use @fixer",
        visible_agent_names=("reviewer",),
    )

    assert instructions is not None
    assert "<active_command>\nReview implementation.\n</active_command>" in instructions
    assert "<name>reviewer</name>" in instructions
    assert "<name>fixer</name>" not in instructions


def test_disabled_project_sub_agent_is_hidden_unless_explicitly_tagged(tmp_path):
    from pbi_agent.agents.state import set_agent_enabled

    agent_dir = tmp_path / ".agents" / "agents"
    agent_dir.mkdir(parents=True)
    agent_path = agent_dir / "code-reviewer.md"
    agent_path.write_text(
        "---\n"
        "name: code-reviewer\n"
        "description: Review code changes before merging.\n"
        "---\n\n"
        "You are a code reviewer.\n",
        encoding="utf-8",
    )
    set_agent_enabled("code-reviewer", False, workspace=tmp_path)

    prompt = get_system_prompt(cwd=tmp_path)
    explicit_prompt = get_system_prompt(
        cwd=tmp_path,
        explicit_agent_names={"code-reviewer"},
    )

    assert "<name>code-reviewer</name>" not in prompt
    assert "<name>code-reviewer</name>" in explicit_prompt
    assert "Treat `@<agent-name> (agent)`" in explicit_prompt


def test_get_system_prompt_filters_tool_rules_by_active_availability(
    tmp_path, monkeypatch
):
    monkeypatch.chdir(tmp_path)
    settings = Settings(
        api_key="test-key",
        provider="openai",
        allowed_tools=("read",),
    )

    prompt = get_system_prompt(settings=settings, excluded_tools={"ask_user"})

    assert "Use `explore_workspace`" in prompt
    assert "Use `shell`" not in prompt
    assert "Use `apply_patch`" not in prompt
    assert "Use `write_file`" not in prompt
    assert "Use `replace_in_file`" not in prompt
    assert "Use `sub_agent`" not in prompt
    assert "Provider-native web search" not in prompt


def test_get_system_prompt_omits_sub_agent_catalog_when_tool_disabled(
    tmp_path, monkeypatch
):
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
    settings = Settings(
        api_key="test-key",
        provider="openai",
        allowed_tools=("read",),
    )

    prompt = get_system_prompt(settings=settings, excluded_tools={"ask_user"})

    assert "<available_sub_agents>" not in prompt
    assert "<sub_agent_loading_rules>" not in prompt
    assert "code-reviewer" not in prompt


def test_get_system_prompt_mentions_web_search_only_for_web_allowed_tool(
    tmp_path, monkeypatch
):
    monkeypatch.chdir(tmp_path)

    web_allowed_prompt = get_system_prompt(
        settings=Settings(
            api_key="test-key",
            provider="openai",
            allowed_tools=("web",),
        )
    )
    read_allowed_prompt = get_system_prompt(
        settings=Settings(
            api_key="test-key",
            provider="openai",
            allowed_tools=("read",),
        )
    )

    assert "Use `web_search`" in web_allowed_prompt
    assert "Use `web_search`" not in read_allowed_prompt
    assert "Use provider-native web search" not in web_allowed_prompt


def test_get_system_prompt_keeps_ask_user_ui_only(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)

    default_prompt = get_system_prompt()
    ui_prompt = get_system_prompt(excluded_tools=set())

    assert "Use `ask_user`" not in default_prompt
    assert "Use `ask_user`" in ui_prompt


def test_get_sub_agent_system_prompt_uses_agent_override(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)

    prompt = get_sub_agent_system_prompt(agent_prompt_override="You are custom.")

    assert "You are custom." in prompt
    assert "<tool_usage_rules>" in prompt
    assert "<persona>" in prompt
    assert "You are task assistant." not in prompt


# ---------------------------------------------------------------------------
# INSTRUCTIONS.md overrides the default system prompt
# ---------------------------------------------------------------------------


def test_get_system_prompt_uses_instructions_md(tmp_path, monkeypatch):
    (tmp_path / "INSTRUCTIONS.md").write_text(
        "You are a code review bot.", encoding="utf-8"
    )
    monkeypatch.chdir(tmp_path)
    prompt = get_system_prompt()
    assert prompt.startswith("You are a code review bot.")
    assert "<tool_usage_rules>" in prompt
    assert "Use `explore_workspace`" in prompt
    assert "Power BI" not in prompt


def test_get_system_prompt_replaces_instructions_md_tool_rules(tmp_path, monkeypatch):
    (tmp_path / "INSTRUCTIONS.md").write_text(
        "Custom.\n\n"
        "<tool_usage_rules>\n"
        "- Use `shell` for everything.\n"
        "</tool_usage_rules>\n",
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)
    prompt = get_system_prompt(
        settings=Settings(
            api_key="test-key",
            provider="openai",
            allowed_tools=("read",),
        )
    )

    assert prompt.startswith("Custom.")
    assert "Use `explore_workspace`" in prompt
    assert "Use `shell` for everything" not in prompt


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
