from __future__ import annotations

from pbi_agent.tools import registry


def test_registry_exposes_expected_built_in_tools() -> None:
    expected = {
        "skill_knowledge",
        "init_report",
        "shell",
        "python_exec",
        "apply_patch",
        "list_files",
        "search_files",
        "read_file",
        "read_web_url",
        "sub_agent",
    }

    assert expected.issubset({spec.name for spec in registry.get_tool_specs()})
    assert expected.issubset(
        {item["name"] for item in registry.get_openai_tool_definitions()}
    )
    assert expected.issubset(
        {item["name"] for item in registry.get_anthropic_tool_definitions()}
    )
    assert expected.issubset(
        {
            item["function"]["name"]
            for item in registry.get_openai_chat_tool_definitions()
        }
    )


def test_registry_returns_none_for_unknown_tool() -> None:
    assert registry.get_tool_handler("missing_tool") is None
    assert registry.get_tool_spec("missing_tool") is None


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
