from __future__ import annotations

import json
from pathlib import Path

import pytest

import pbi_agent.config as config_module
from pbi_agent.cli import build_parser
from pbi_agent.config import (
    ConfigConflictError,
    ConfigError,
    InternalConfig,
    ModelProfileConfig,
    ProviderConfig,
    WebConfig,
    create_model_profile_config,
    create_provider_config,
    find_command_config_by_alias,
    delete_provider_config,
    list_command_configs,
    load_internal_config,
    load_internal_config_snapshot,
    normalize_slash_alias,
    resolve_runtime,
    resolve_settings,
    resolve_web_runtime,
    save_internal_config,
    save_internal_config_with_revision,
    select_active_model_profile,
)


def _args(*argv: str):
    return build_parser().parse_args(list(argv))


def _write_command(root: Path, name: str, content: str) -> Path:
    commands_dir = root / ".agents" / "commands"
    commands_dir.mkdir(parents=True, exist_ok=True)
    path = commands_dir / name
    path.write_text(content, encoding="utf-8")
    return path


def test_load_internal_config_treats_old_provider_scoped_shape_as_absent(
    monkeypatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("PBI_AGENT_INTERNAL_CONFIG_PATH", str(tmp_path / "config.json"))
    (tmp_path / "config.json").write_text(
        json.dumps(
            {
                "last_used_provider": "openai",
                "providers": {"openai": {"api_key": "legacy-key"}},
            }
        ),
        encoding="utf-8",
    )

    config = load_internal_config()

    assert config.providers == []
    assert config.model_profiles == []
    assert config.commands == []
    assert config.web.active_profile_id is None


def test_load_internal_config_does_not_seed_default_commands(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.chdir(tmp_path)

    config = load_internal_config()

    assert config.commands == []
    assert find_command_config_by_alias("/plan") is None


def test_list_command_configs_discovers_command_files(tmp_path: Path) -> None:
    path = _write_command(
        tmp_path,
        "fix-issue.md",
        "# Fix GitHub Issue\n\nResolve the linked issue.",
    )

    commands = list_command_configs(tmp_path)

    assert [item.id for item in commands] == ["fix-issue"]
    assert commands[0].name == "Fix Issue"
    assert commands[0].slash_alias == "/fix-issue"
    assert commands[0].description == "Fix GitHub Issue"
    assert commands[0].instructions == "# Fix GitHub Issue\n\nResolve the linked issue."
    assert commands[0].path == str(path.relative_to(tmp_path))


def test_config_store_roundtrip_and_active_profile_selection(monkeypatch) -> None:
    monkeypatch.setattr(config_module, "load_dotenv", lambda: None)

    provider, _ = create_provider_config(
        ProviderConfig(
            id="openai-main",
            name="OpenAI Main",
            kind="openai",
            api_key="saved-openai-key",
            responses_url="https://api.openai.com/v1/responses",
        )
    )
    profile, _ = create_model_profile_config(
        ModelProfileConfig(
            id="analysis",
            name="Analysis",
            provider_id=provider.id,
            model="gpt-5.4-2026-03-05",
            sub_agent_model="gpt-5.4-mini",
            reasoning_effort="xhigh",
            max_tokens=4096,
            service_tier="flex",
            web_search=False,
            max_tool_workers=6,
            max_retries=5,
            compact_threshold=123456,
        )
    )
    select_active_model_profile(profile.id)

    config = load_internal_config()

    assert [item.id for item in config.providers] == ["openai-main"]
    assert [item.id for item in config.model_profiles] == ["analysis"]
    assert config.web.active_profile_id == "analysis"
    assert config.providers[0].api_key == "saved-openai-key"
    assert config.model_profiles[0].service_tier == "flex"


def test_find_command_config_by_alias_reads_command_files(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.chdir(tmp_path)
    _write_command(tmp_path, "plan.md", "Plan carefully before making changes.")

    config = load_internal_config()
    command = find_command_config_by_alias("/plan")

    assert config.commands == []
    assert command is not None
    assert command.instructions == "Plan carefully before making changes."


def test_list_command_configs_skips_reserved_command_alias(tmp_path: Path) -> None:
    _write_command(tmp_path, "skills.md", "List project skills.")

    assert list_command_configs(tmp_path) == []


def test_list_command_configs_skips_empty_files(tmp_path: Path) -> None:
    _write_command(tmp_path, "plan.md", "   \n")

    assert list_command_configs(tmp_path) == []


def test_list_command_configs_skips_duplicate_normalized_names(tmp_path: Path) -> None:
    _write_command(tmp_path, "fix issue.md", "First instructions.")
    _write_command(tmp_path, "fix-issue.md", "Second instructions.")

    commands = list_command_configs(tmp_path)

    assert [item.instructions for item in commands] == ["First instructions."]


def test_normalize_slash_alias_adds_prefix() -> None:
    assert normalize_slash_alias("plan") == "/plan"


def test_config_payload_ignores_commands_from_global_config(
    tmp_path: Path, monkeypatch
) -> None:
    test_workspace = tmp_path / "workspace"
    test_workspace.mkdir()
    monkeypatch.chdir(test_workspace)
    (tmp_path / "internal-config.json").write_text(
        json.dumps(
            {
                "providers": [],
                "model_profiles": [],
                "commands": [
                    {
                        "id": "plan",
                        "name": "Plan",
                        "slash_alias": "/plan",
                        "instructions": "Plan carefully.",
                    }
                ],
                "web": {"active_profile_id": None},
            }
        ),
        encoding="utf-8",
    )

    config = load_internal_config()

    assert config.commands == []
    assert find_command_config_by_alias("/plan") is None


def test_resolve_web_runtime_uses_selected_web_profile(monkeypatch) -> None:
    monkeypatch.setattr(config_module, "load_dotenv", lambda: None)
    monkeypatch.delenv("PBI_AGENT_PROVIDER", raising=False)
    monkeypatch.delenv("PBI_AGENT_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    create_provider_config(
        ProviderConfig(
            id="openai-main",
            name="OpenAI Main",
            kind="openai",
            api_key="saved-openai-key",
        )
    )
    create_model_profile_config(
        ModelProfileConfig(
            id="analysis",
            name="Analysis",
            provider_id="openai-main",
            model="gpt-5.4-2026-03-05",
            reasoning_effort="xhigh",
            max_tool_workers=6,
            max_retries=5,
            compact_threshold=123456,
            web_search=False,
        )
    )
    select_active_model_profile("analysis")

    runtime = resolve_web_runtime()
    settings = runtime.settings

    assert settings.provider == "openai"
    assert settings.api_key == "saved-openai-key"
    assert settings.model == "gpt-5.4-2026-03-05"
    assert settings.sub_agent_model == "gpt-5.4-mini"
    assert settings.max_tool_workers == 6
    assert settings.max_retries == 5
    assert settings.compact_threshold == 123456
    assert settings.web_search is False
    assert runtime.profile_id == "analysis"


def test_resolve_web_runtime_requires_active_profile(monkeypatch) -> None:
    monkeypatch.setattr(config_module, "load_dotenv", lambda: None)

    with pytest.raises(ConfigError, match="No active web model profile configured"):
        resolve_web_runtime()


def test_resolve_settings_prefers_cli_profile_selector_over_env_and_active_profile(
    monkeypatch,
) -> None:
    monkeypatch.setattr(config_module, "load_dotenv", lambda: None)
    monkeypatch.setenv("PBI_AGENT_PROFILE_ID", "env-profile")

    create_provider_config(
        ProviderConfig(id="openai-main", name="OpenAI Main", kind="openai", api_key="k")
    )
    create_model_profile_config(
        ModelProfileConfig(
            id="active-profile",
            name="Active Profile",
            provider_id="openai-main",
            model="gpt-5.4-active",
        )
    )
    create_model_profile_config(
        ModelProfileConfig(
            id="env-profile",
            name="Env Profile",
            provider_id="openai-main",
            model="gpt-5.4-env",
        )
    )
    create_model_profile_config(
        ModelProfileConfig(
            id="cli-profile",
            name="CLI Profile",
            provider_id="openai-main",
            model="gpt-5.4-cli",
        )
    )
    select_active_model_profile("active-profile")

    settings = resolve_settings(_args("--profile-id", "cli-profile", "web"))

    assert settings.model == "gpt-5.4-cli"


def test_resolve_settings_prefers_cli_and_env_over_selected_profile(
    monkeypatch,
) -> None:
    monkeypatch.setattr(config_module, "load_dotenv", lambda: None)
    monkeypatch.setenv("PBI_AGENT_MODEL", "env-model")
    monkeypatch.setenv("PBI_AGENT_MAX_RETRIES", "9")

    create_provider_config(
        ProviderConfig(
            id="openai-main",
            name="OpenAI Main",
            kind="openai",
            api_key="saved-openai-key",
        )
    )
    create_model_profile_config(
        ModelProfileConfig(
            id="analysis",
            name="Analysis",
            provider_id="openai-main",
            model="saved-model",
            max_retries=5,
            max_tool_workers=2,
        )
    )

    settings = resolve_settings(
        _args(
            "--profile-id",
            "analysis",
            "--max-tool-workers",
            "7",
            "web",
        )
    )

    assert settings.model == "env-model"
    assert settings.max_retries == 9
    assert settings.max_tool_workers == 7


def test_provider_specific_api_key_env_fallback_still_applies_after_profile_selection(
    monkeypatch,
) -> None:
    monkeypatch.setattr(config_module, "load_dotenv", lambda: None)
    monkeypatch.delenv("PBI_AGENT_API_KEY", raising=False)
    monkeypatch.setenv("XAI_API_KEY", "xai-env-key")

    create_provider_config(
        ProviderConfig(
            id="xai-main",
            name="xAI Main",
            kind="xai",
            api_key="saved-xai-key",
        )
    )
    create_model_profile_config(
        ModelProfileConfig(
            id="xai-fast",
            name="xAI Fast",
            provider_id="xai-main",
            model="grok-4.20",
        )
    )

    settings = resolve_settings(_args("--profile-id", "xai-fast", "web"))

    assert settings.provider == "xai"
    assert settings.api_key == "xai-env-key"


def test_saved_provider_env_var_reference_beats_saved_plaintext_secret(
    monkeypatch,
) -> None:
    monkeypatch.setattr(config_module, "load_dotenv", lambda: None)
    monkeypatch.delenv("PBI_AGENT_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setenv("OPENAI_PRIMARY_KEY", "env-ref-key")

    create_provider_config(
        ProviderConfig(
            id="openai-main",
            name="OpenAI Main",
            kind="openai",
            api_key="saved-openai-key",
            api_key_env="OPENAI_PRIMARY_KEY",
        )
    )
    create_model_profile_config(
        ModelProfileConfig(
            id="analysis",
            name="Analysis",
            provider_id="openai-main",
            model="gpt-5.4-2026-03-05",
        )
    )

    settings = resolve_settings(_args("--profile-id", "analysis", "web"))

    assert settings.api_key == "env-ref-key"


def test_runtime_overrides_do_not_persist_a_derived_profile(monkeypatch) -> None:
    monkeypatch.setattr(config_module, "load_dotenv", lambda: None)

    create_provider_config(
        ProviderConfig(
            id="openai-main",
            name="OpenAI Main",
            kind="openai",
            api_key="saved-openai-key",
        )
    )
    create_model_profile_config(
        ModelProfileConfig(
            id="analysis",
            name="Analysis",
            provider_id="openai-main",
            model="saved-model",
            max_retries=3,
        )
    )
    before = config_module._internal_config_path().read_text(encoding="utf-8")

    runtime = resolve_runtime(
        _args("--profile-id", "analysis", "--model", "cli-model", "web")
    )
    after = config_module._internal_config_path().read_text(encoding="utf-8")

    assert runtime.settings.model == "cli-model"
    assert runtime.profile_id is None
    assert runtime.provider_id == "openai-main"
    assert before == after
    config = load_internal_config()
    assert [profile.id for profile in config.model_profiles] == ["analysis"]


def test_save_internal_config_rejects_stale_revision() -> None:
    create_provider_config(
        ProviderConfig(
            id="openai-main",
            name="OpenAI Main",
            kind="openai",
            api_key="saved-openai-key",
        )
    )
    config, revision = load_internal_config_snapshot()
    config.providers.append(
        ProviderConfig(
            id="xai-main",
            name="xAI Main",
            kind="xai",
            api_key="saved-xai-key",
        )
    )
    save_internal_config_with_revision(
        InternalConfig(
            providers=[
                ProviderConfig(
                    id="replacement",
                    name="Replacement",
                    kind="openai",
                    api_key="replacement-key",
                )
            ],
            model_profiles=[],
            web=WebConfig(),
        )
    )

    with pytest.raises(ConfigConflictError, match="Config has changed"):
        save_internal_config_with_revision(config, expected_revision=revision)


def test_resolve_settings_rejects_unknown_profile_id(monkeypatch) -> None:
    monkeypatch.setattr(config_module, "load_dotenv", lambda: None)

    with pytest.raises(ConfigError, match="Unknown profile ID 'missing'"):
        resolve_settings(_args("--profile-id", "missing", "web"))


def test_resolve_settings_rejects_profile_pointing_to_missing_provider(
    monkeypatch,
) -> None:
    monkeypatch.setattr(config_module, "load_dotenv", lambda: None)
    save_internal_config(
        InternalConfig(
            providers=[],
            model_profiles=[
                ModelProfileConfig(
                    id="broken-profile",
                    name="Broken Profile",
                    provider_id="missing-provider",
                )
            ],
            web=WebConfig(active_profile_id="broken-profile"),
        )
    )

    with pytest.raises(
        ConfigError,
        match="references missing provider 'missing-provider'",
    ):
        resolve_web_runtime()


def test_invalid_service_tier_on_non_openai_profile_is_rejected(monkeypatch) -> None:
    monkeypatch.setattr(config_module, "load_dotenv", lambda: None)
    create_provider_config(
        ProviderConfig(id="xai-main", name="xAI Main", kind="xai", api_key="x")
    )

    with pytest.raises(ConfigError, match="only supported with the OpenAI provider"):
        create_model_profile_config(
            ModelProfileConfig(
                id="bad-profile",
                name="Bad Profile",
                provider_id="xai-main",
                service_tier="flex",
            )
        )


def test_delete_provider_is_blocked_while_profile_still_references_it(
    monkeypatch,
) -> None:
    monkeypatch.setattr(config_module, "load_dotenv", lambda: None)
    create_provider_config(
        ProviderConfig(
            id="openai-main",
            name="OpenAI Main",
            kind="openai",
            api_key="saved-openai-key",
        )
    )
    create_model_profile_config(
        ModelProfileConfig(
            id="analysis",
            name="Analysis",
            provider_id="openai-main",
        )
    )

    with pytest.raises(ConfigError, match="still references it"):
        delete_provider_config("openai-main")


def test_resolve_settings_falls_back_to_unsaved_runtime_defaults(monkeypatch) -> None:
    monkeypatch.setattr(config_module, "load_dotenv", lambda: None)
    monkeypatch.setenv("PBI_AGENT_PROVIDER", "google")
    monkeypatch.setenv("GEMINI_API_KEY", "google-key")

    settings = resolve_settings(_args("web"))

    assert settings.provider == "google"
    assert settings.model == "gemini-3.1-pro-preview"
    assert settings.sub_agent_model == "gemini-3-flash-preview"
    assert settings.api_key == "google-key"
