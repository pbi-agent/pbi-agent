from __future__ import annotations

from pbi_agent.tools import registry


def test_registry_exposes_expected_built_in_tools() -> None:
    expected = {
        "shell",
        "apply_patch",
        "replace_in_file",
        "write_file",
        "read_file",
        "read_image",
        "read_web_url",
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
    assert anthropic_tool_names == expected

    chat_tool_names = {
        item["function"]["name"] for item in registry.get_openai_chat_tool_definitions()
    }
    assert chat_tool_names == expected


def test_registry_returns_none_for_unknown_tool() -> None:
    assert registry.get_tool_handler("missing_tool") is None
    assert registry.get_tool_spec("missing_tool") is None


def test_apply_patch_schema_accepts_patch_only() -> None:
    spec = registry.get_tool_spec("apply_patch")

    assert spec is not None
    assert set(spec.parameters_schema["properties"]) == {"patch"}
    assert spec.parameters_schema["required"] == ["patch"]
    assert "Codex" not in spec.description


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
