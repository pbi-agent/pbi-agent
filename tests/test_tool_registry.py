from __future__ import annotations

from typing import Any

from pbi_agent.agent.session.runtime import _open_runtime_provider
from pbi_agent.agents.state import set_agent_enabled
from pbi_agent.config import Settings
from pbi_agent.tools import registry
from pbi_agent.tools.availability import effective_excluded_tool_names
from pbi_agent.tools.catalog import ToolCatalog


class _ProviderContextStub:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def __enter__(self) -> "_ProviderContextStub":
        return self

    def __exit__(self, *_: object) -> None:
        return None


def test_registry_exposes_expected_built_in_tools() -> None:
    expected = {
        "shell",
        "apply_patch",
        "replace_in_file",
        "write_file",
        "explore_workspace",
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
    excluded = effective_excluded_tool_names(Settings(provider="openai"), None)

    assert {"ask_user", "replace_in_file", "write_file"} <= excluded
    assert "apply_patch" not in excluded
    assert "read_web_url" not in excluded


def test_effective_excluded_tool_names_explicit_empty_allows_ui_only_tools() -> None:
    excluded = effective_excluded_tool_names(Settings(provider="openai"), set())

    assert "ask_user" not in excluded


def test_effective_excluded_tool_names_chatgpt_uses_v4a_editing() -> None:
    excluded = effective_excluded_tool_names(Settings(provider="chatgpt"), set())

    assert {"replace_in_file", "write_file"} <= excluded
    assert "apply_patch" not in excluded


def test_effective_excluded_tool_names_non_openai_uses_simple_editing() -> None:
    excluded = effective_excluded_tool_names(Settings(provider="anthropic"), None)

    assert "apply_patch" in excluded
    assert "replace_in_file" not in excluded
    assert "write_file" not in excluded


def test_effective_excluded_tool_names_disables_web_tools_without_web_group() -> None:
    excluded = effective_excluded_tool_names(
        Settings(provider="openai", allowed_tools=("read",))
    )

    assert "read_web_url" in excluded


def test_effective_excluded_tool_names_honors_allowed_tools() -> None:
    excluded = effective_excluded_tool_names(
        Settings(
            provider="openai",
            allowed_tools=("read",),
        )
    )

    assert "explore_workspace" not in excluded
    assert "shell" in excluded
    assert "read_web_url" in excluded


def test_effective_excluded_tool_names_keeps_ask_user_disabled_when_not_allowed() -> (
    None
):
    assert "ask_user" in effective_excluded_tool_names(
        Settings(provider="openai", allowed_tools=())
    )
    assert "ask_user" in effective_excluded_tool_names(
        Settings(provider="openai", allowed_tools=("read",))
    )


def test_effective_excluded_tool_names_allows_command_enabled_ask_user() -> None:
    excluded = effective_excluded_tool_names(
        Settings(provider="openai", allowed_tools=("ask-user",))
    )

    assert "ask_user" not in excluded
    assert "explore_workspace" in excluded
    assert "shell" in excluded


def test_web_allowed_tool_enables_fetch_tool_and_native_web_search() -> None:
    from pbi_agent.tools.availability import native_web_search_enabled

    settings = Settings(
        provider="openai",
        allowed_tools=("web",),
    )

    assert "read_web_url" not in effective_excluded_tool_names(settings)
    assert "explore_workspace" in effective_excluded_tool_names(settings)
    assert native_web_search_enabled(settings) is True


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


def test_builtin_tool_catalog_sub_agent_schema_uses_explicit_workspace(
    tmp_path, monkeypatch
) -> None:
    workspace_a = tmp_path / "workspace-a"
    workspace_b = tmp_path / "workspace-b"
    (workspace_a / ".agents" / "agents").mkdir(parents=True)
    (workspace_b / ".agents" / "agents").mkdir(parents=True)
    (workspace_a / ".agents" / "agents" / "alpha.md").write_text(
        "---\nname: alpha\ndescription: Alpha agent.\n---\n\nAlpha prompt.\n",
        encoding="utf-8",
    )
    (workspace_b / ".agents" / "agents" / "bravo.md").write_text(
        "---\nname: bravo\ndescription: Bravo agent.\n---\n\nBravo prompt.\n",
        encoding="utf-8",
    )
    monkeypatch.chdir(workspace_a)

    catalog = ToolCatalog.from_builtin_registry(workspace_b)
    spec = catalog.get_spec("sub_agent")

    assert spec is not None
    assert spec.parameters_schema["properties"]["agent_type"]["enum"] == [
        "default",
        "bravo",
    ]


def test_builtin_tool_catalog_sub_agent_schema_scopes_visible_agents(
    tmp_path,
) -> None:
    agents_dir = tmp_path / ".agents" / "agents"
    agents_dir.mkdir(parents=True)
    (agents_dir / "reviewer.md").write_text(
        "---\nname: reviewer\ndescription: Reviews code.\n---\n\nReview prompt.\n",
        encoding="utf-8",
    )
    (agents_dir / "fixer.md").write_text(
        "---\nname: fixer\ndescription: Fixes code.\n---\n\nFix prompt.\n",
        encoding="utf-8",
    )

    catalog = ToolCatalog.from_builtin_registry(
        tmp_path,
        visible_sub_agent_names=("reviewer",),
    )
    spec = catalog.get_spec("sub_agent")

    assert spec is not None
    assert spec.parameters_schema["properties"]["agent_type"]["enum"] == ["reviewer"]
    assert catalog.sub_agent_type_values() == ("reviewer",)


def test_runtime_provider_sub_agent_schema_uses_explicit_workspace(
    tmp_path, monkeypatch
) -> None:
    workspace_a = tmp_path / "workspace-a"
    workspace_b = tmp_path / "workspace-b"
    (workspace_a / ".agents" / "agents").mkdir(parents=True)
    (workspace_b / ".agents" / "agents").mkdir(parents=True)
    (workspace_a / ".agents" / "agents" / "alpha.md").write_text(
        "---\nname: alpha\ndescription: Alpha agent.\n---\n\nAlpha prompt.\n",
        encoding="utf-8",
    )
    (workspace_b / ".agents" / "agents" / "bravo.md").write_text(
        "---\nname: bravo\ndescription: Bravo agent.\n---\n\nBravo prompt.\n",
        encoding="utf-8",
    )
    monkeypatch.chdir(workspace_a)
    captured: dict[str, Any] = {}

    def fake_create_provider(
        settings: Settings,
        *,
        system_prompt: str | None = None,
        excluded_tools: set[str] | None = None,
        tool_catalog: ToolCatalog | None = None,
    ) -> _ProviderContextStub:
        del system_prompt, excluded_tools
        assert tool_catalog is not None
        spec = tool_catalog.get_spec("sub_agent")
        assert spec is not None
        captured["enum"] = spec.parameters_schema["properties"]["agent_type"]["enum"]
        captured["visible_agent_types"] = tool_catalog.sub_agent_type_values()
        return _ProviderContextStub(settings)

    monkeypatch.setattr(
        "pbi_agent.agent.session.runtime.create_provider",
        fake_create_provider,
    )

    with _open_runtime_provider(
        Settings(api_key="test-key", provider="openai"),
        workspace_root=workspace_b,
    ):
        pass

    assert captured["enum"] == ["default", "bravo"]
    assert captured["visible_agent_types"] == ("default", "bravo")


def test_runtime_provider_sub_agent_schema_uses_active_workspace_directory_key(
    tmp_path, monkeypatch
) -> None:
    workspace = tmp_path / "workspace"
    (workspace / ".agents" / "agents").mkdir(parents=True)
    (workspace / ".agents" / "agents" / "reviewer.md").write_text(
        "---\nname: reviewer\ndescription: Reviews code.\n---\n\nReview prompt.\n",
        encoding="utf-8",
    )
    monkeypatch.chdir(workspace)
    monkeypatch.setenv("PBI_AGENT_WORKSPACE_KEY", "initial-workspace-key")
    set_agent_enabled(
        "reviewer",
        False,
        workspace=workspace,
        directory_key="active-workspace-key",
    )
    captured: dict[str, Any] = {}

    def fake_create_provider(
        settings: Settings,
        *,
        system_prompt: str | None = None,
        excluded_tools: set[str] | None = None,
        tool_catalog: ToolCatalog | None = None,
    ) -> _ProviderContextStub:
        del system_prompt, excluded_tools
        assert tool_catalog is not None
        spec = tool_catalog.get_spec("sub_agent")
        assert spec is not None
        captured["enum"] = spec.parameters_schema["properties"]["agent_type"]["enum"]
        captured["visible_agent_types"] = tool_catalog.sub_agent_type_values()
        return _ProviderContextStub(settings)

    monkeypatch.setattr(
        "pbi_agent.agent.session.runtime.create_provider",
        fake_create_provider,
    )

    with _open_runtime_provider(
        Settings(api_key="test-key", provider="openai"),
        workspace_root=workspace,
        workspace_directory_key="active-workspace-key",
    ):
        pass

    assert captured["enum"] == ["default"]
    assert captured["visible_agent_types"] == ("default",)


def test_runtime_provider_sub_agent_schema_includes_explicit_disabled_agent(
    tmp_path, monkeypatch
) -> None:
    (tmp_path / ".agents" / "agents").mkdir(parents=True)
    (tmp_path / ".agents" / "agents" / "reviewer.md").write_text(
        "---\nname: reviewer\ndescription: Reviews code.\n---\n\nReview prompt.\n",
        encoding="utf-8",
    )
    set_agent_enabled("reviewer", False, workspace=tmp_path)
    captured: dict[str, Any] = {}

    def fake_create_provider(
        settings: Settings,
        *,
        system_prompt: str | None = None,
        excluded_tools: set[str] | None = None,
        tool_catalog: ToolCatalog | None = None,
    ) -> _ProviderContextStub:
        del system_prompt, excluded_tools
        assert tool_catalog is not None
        spec = tool_catalog.get_spec("sub_agent")
        assert spec is not None
        captured["enum"] = spec.parameters_schema["properties"]["agent_type"]["enum"]
        captured["visible_agent_types"] = tool_catalog.sub_agent_type_values()
        return _ProviderContextStub(settings)

    monkeypatch.setattr(
        "pbi_agent.agent.session.runtime.create_provider",
        fake_create_provider,
    )

    with _open_runtime_provider(
        Settings(api_key="test-key", provider="openai"),
        workspace_root=tmp_path,
        explicit_agent_names={"reviewer"},
    ):
        pass

    assert captured["enum"] == ["default", "reviewer"]
    assert captured["visible_agent_types"] == ("default", "reviewer")


def test_runtime_provider_sub_agent_schema_scopes_visible_agents(
    tmp_path,
    monkeypatch,
) -> None:
    agents_dir = tmp_path / ".agents" / "agents"
    agents_dir.mkdir(parents=True)
    (agents_dir / "reviewer.md").write_text(
        "---\nname: reviewer\ndescription: Reviews code.\n---\n\nReview prompt.\n",
        encoding="utf-8",
    )
    (agents_dir / "fixer.md").write_text(
        "---\nname: fixer\ndescription: Fixes code.\n---\n\nFix prompt.\n",
        encoding="utf-8",
    )
    set_agent_enabled("reviewer", False, workspace=tmp_path)
    captured: dict[str, Any] = {}

    def fake_create_provider(
        settings: Settings,
        *,
        system_prompt: str | None = None,
        excluded_tools: set[str] | None = None,
        tool_catalog: ToolCatalog | None = None,
    ) -> _ProviderContextStub:
        del system_prompt, excluded_tools
        assert tool_catalog is not None
        spec = tool_catalog.get_spec("sub_agent")
        assert spec is not None
        captured["enum"] = spec.parameters_schema["properties"]["agent_type"]["enum"]
        captured["visible_agent_types"] = tool_catalog.sub_agent_type_values()
        return _ProviderContextStub(settings)

    monkeypatch.setattr(
        "pbi_agent.agent.session.runtime.create_provider",
        fake_create_provider,
    )

    with _open_runtime_provider(
        Settings(api_key="test-key", provider="openai"),
        workspace_root=tmp_path,
        visible_sub_agent_names=("reviewer",),
    ):
        pass

    assert captured["enum"] == ["reviewer"]
    assert captured["visible_agent_types"] == ("reviewer",)


def test_runtime_provider_replaces_reused_catalog_sub_agent_schema_when_scoped(
    tmp_path,
    monkeypatch,
) -> None:
    agents_dir = tmp_path / ".agents" / "agents"
    agents_dir.mkdir(parents=True)
    (agents_dir / "reviewer.md").write_text(
        "---\nname: reviewer\ndescription: Reviews code.\n---\n\nReview prompt.\n",
        encoding="utf-8",
    )
    (agents_dir / "fixer.md").write_text(
        "---\nname: fixer\ndescription: Fixes code.\n---\n\nFix prompt.\n",
        encoding="utf-8",
    )
    reused_catalog = ToolCatalog.from_builtin_registry(tmp_path)
    original_spec = reused_catalog.get_spec("sub_agent")
    assert original_spec is not None
    assert original_spec.parameters_schema["properties"]["agent_type"]["enum"] == [
        "default",
        "fixer",
        "reviewer",
    ]
    captured: dict[str, Any] = {}

    def fake_create_provider(
        settings: Settings,
        *,
        system_prompt: str | None = None,
        excluded_tools: set[str] | None = None,
        tool_catalog: ToolCatalog | None = None,
    ) -> _ProviderContextStub:
        del system_prompt, excluded_tools
        assert tool_catalog is not None
        spec = tool_catalog.get_spec("sub_agent")
        assert spec is not None
        captured["enum"] = spec.parameters_schema["properties"]["agent_type"]["enum"]
        captured["visible_agent_types"] = tool_catalog.sub_agent_type_values()
        return _ProviderContextStub(settings)

    monkeypatch.setattr(
        "pbi_agent.agent.session.runtime.create_provider",
        fake_create_provider,
    )

    with _open_runtime_provider(
        Settings(api_key="test-key", provider="openai"),
        tool_catalog=reused_catalog,
        workspace_root=tmp_path,
        visible_sub_agent_names=("reviewer",),
    ):
        pass

    assert captured["enum"] == ["reviewer"]
    assert captured["visible_agent_types"] == ("reviewer",)
    assert original_spec.parameters_schema["properties"]["agent_type"]["enum"] == [
        "default",
        "fixer",
        "reviewer",
    ]
