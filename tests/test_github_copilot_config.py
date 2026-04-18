from __future__ import annotations

from pbi_agent.auth.models import AUTH_MODE_COPILOT_ACCOUNT, OAuthSessionAuth
from pbi_agent.auth.providers.github_copilot import GITHUB_COPILOT_RESPONSES_URL
from pbi_agent.auth.service import import_provider_auth_session
from pbi_agent.config import (
    ModelProfileConfig,
    ProviderConfig,
    create_model_profile_config,
    create_provider_config,
    provider_ui_metadata,
    resolve_runtime_for_profile_id,
)


def test_resolve_runtime_for_profile_id_uses_saved_github_copilot_session(
    monkeypatch,
    tmp_path,
) -> None:
    monkeypatch.setenv("PBI_AGENT_INTERNAL_CONFIG_PATH", str(tmp_path / "config.json"))

    provider, _ = create_provider_config(
        ProviderConfig(
            id="copilot-main",
            name="Copilot Main",
            kind="github_copilot",
            auth_mode=AUTH_MODE_COPILOT_ACCOUNT,
            responses_url=GITHUB_COPILOT_RESPONSES_URL,
        )
    )
    create_model_profile_config(
        ModelProfileConfig(
            id="copilot-profile",
            name="Copilot Profile",
            provider_id=provider.id,
            model="gpt-5",
        )
    )
    import_provider_auth_session(
        provider_kind="github_copilot",
        provider_id=provider.id,
        auth_mode=AUTH_MODE_COPILOT_ACCOUNT,
        payload={"access_token": "gho_test_token"},
    )

    runtime = resolve_runtime_for_profile_id("copilot-profile")

    assert isinstance(runtime.settings.auth, OAuthSessionAuth)
    assert runtime.settings.provider == "github_copilot"
    assert runtime.settings.responses_url == GITHUB_COPILOT_RESPONSES_URL
    assert runtime.settings.model == "gpt-5"


def test_provider_ui_metadata_exposes_auth_mode_labels_and_methods() -> None:
    metadata = provider_ui_metadata("github_copilot")

    assert metadata["label"] == "GitHub Copilot (Subscription)"
    assert metadata["description"] == "Uses your GitHub Copilot subscription account."
    assert metadata["default_auth_mode"] == AUTH_MODE_COPILOT_ACCOUNT
    assert metadata["auth_mode_metadata"] == {
        "copilot_account": {
            "label": "GitHub Copilot account",
            "account_label": "GitHub Copilot subscription account",
            "supported_methods": ["device"],
        }
    }
