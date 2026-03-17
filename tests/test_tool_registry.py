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


def test_python_exec_tool_description_mentions_installed_analysis_libraries() -> None:
    spec = registry.get_tool_spec("python_exec")

    assert spec is not None
    assert "`polars`" in spec.description
    assert "`pypdf`" in spec.description
    assert "`python-docx`" in spec.description
