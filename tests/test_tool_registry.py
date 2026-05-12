from __future__ import annotations

from pbi_agent.config import Settings
from pbi_agent.tools import registry
from pbi_agent.tools.availability import effective_excluded_tool_names


def test_registry_exposes_expected_built_in_tools() -> None:
    expected = {
        "shell",
        "apply_patch",
        "replace_in_file",
        "write_file",
        "read_file",
        "read_web_url",
        "ask_user",
        "sub_agent",
    }

    tool_names = {spec.name for spec in registry.get_tool_specs()}
    assert tool_names == expected

    openai_tool_names = {
        item["name"] for item in registry.get_openai_tool_definitions()
    }
    assert openai_tool_names == expected

    anthropic_tool_names = {
        item["name"] for item in registry.get_anthropic_tool_definitions()
    }
    assert anthropic_tool_names == expected - {"apply_patch"}

    chat_tool_names = {
        item["function"]["name"] for item in registry.get_openai_chat_tool_definitions()
    }
    assert chat_tool_names == expected - {"apply_patch"}


def test_registry_returns_none_for_unknown_tool() -> None:
    assert registry.get_tool_handler("missing_tool") is None
    assert registry.get_tool_spec("missing_tool") is None


def test_effective_excluded_tool_names_openai_uses_v4a_editing() -> None:
    excluded = effective_excluded_tool_names(
        Settings(provider="openai", web_search=True), {"ask_user"}
    )

    assert {"ask_user", "replace_in_file", "write_file"} <= excluded
    assert "apply_patch" not in excluded
    assert "read_web_url" not in excluded


def test_effective_excluded_tool_names_chatgpt_uses_v4a_editing() -> None:
    excluded = effective_excluded_tool_names(Settings(provider="chatgpt"), set())

    assert {"replace_in_file", "write_file"} <= excluded
    assert "apply_patch" not in excluded


def test_effective_excluded_tool_names_non_openai_uses_simple_editing() -> None:
    excluded = effective_excluded_tool_names(Settings(provider="anthropic"), None)

    assert "apply_patch" in excluded
    assert "replace_in_file" not in excluded
    assert "write_file" not in excluded


def test_effective_excluded_tool_names_hides_read_web_url_without_web_search() -> None:
    excluded = effective_excluded_tool_names(
        Settings(provider="openai", web_search=False)
    )

    assert "read_web_url" in excluded


def test_apply_patch_uses_codex_freeform_spec() -> None:
    spec = registry.get_tool_spec("apply_patch")

    assert spec is not None
    assert spec.parameters_schema == {}
    assert spec.description == (
        "Use the `apply_patch` tool to edit files. This is a FREEFORM tool, so "
        "do not wrap the patch in JSON."
    )
    assert spec.freeform_format is not None
    assert spec.freeform_format["type"] == "grammar"
    assert spec.freeform_format["syntax"] == "lark"
    assert "start: begin_patch hunk+ end_patch" in spec.freeform_format["definition"]

    openai_tool = next(
        item
        for item in registry.get_openai_tool_definitions()
        if item["name"] == "apply_patch"
    )
    assert openai_tool == {
        "type": "custom",
        "name": "apply_patch",
        "description": spec.description,
        "format": spec.freeform_format,
    }


def test_registry_sub_agent_schema_uses_project_agent_enum(
    tmp_path, monkeypatch
) -> None:
    agents_dir = tmp_path / ".agents" / "agents"
    agents_dir.mkdir(parents=True)
    (agents_dir / "reviewer.md").write_text(
        "---\nname: reviewer\ndescription: Reviews code.\n---\n\nReview prompt.\n",
        encoding="utf-8",
    )

    monkeypatch.chdir(tmp_path)

    spec = registry.get_tool_spec("sub_agent")
    assert spec is not None
    assert "reasoning_effort" not in spec.parameters_schema["properties"]
    assert spec.parameters_schema["properties"]["include_context"]["type"] == "boolean"
    assert spec.parameters_schema["properties"]["agent_type"]["enum"] == [
        "default",
        "reviewer",
    ]

    openai_tool = next(
        item
        for item in registry.get_openai_tool_definitions()
        if item["name"] == "sub_agent"
    )
    assert "reasoning_effort" not in openai_tool["parameters"]["properties"]
    assert (
        openai_tool["parameters"]["properties"]["include_context"]["type"] == "boolean"
    )
    assert openai_tool["parameters"]["properties"]["agent_type"]["enum"] == [
        "default",
        "reviewer",
    ]
