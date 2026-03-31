from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import tempfile
from dataclasses import asdict, dataclass, field, replace
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

DEFAULT_RESPONSES_URL = "https://api.openai.com/v1/responses"
DEFAULT_XAI_RESPONSES_URL = "https://api.x.ai/v1/responses"
DEFAULT_GOOGLE_INTERACTIONS_URL = (
    "https://generativelanguage.googleapis.com/v1beta/interactions"
)
DEFAULT_GENERIC_API_URL = "https://openrouter.ai/api/v1/chat/completions"
DEFAULT_MODEL = "gpt-5.4"
DEFAULT_XAI_MODEL = "grok-4.20"
DEFAULT_GOOGLE_MODEL = "gemini-3.1-pro-preview"
DEFAULT_ANTHROPIC_MODEL = "claude-opus-4-6"
DEFAULT_SUB_AGENT_MODEL = "gpt-5.4-mini"
DEFAULT_XAI_SUB_AGENT_MODEL = "grok-4-1-fast"
DEFAULT_GOOGLE_SUB_AGENT_MODEL = "gemini-3-flash-preview"
DEFAULT_ANTHROPIC_SUB_AGENT_MODEL = "claude-sonnet-4-6"
DEFAULT_MAX_TOKENS = 16384
OPENAI_SERVICE_TIERS = ("auto", "default", "flex", "priority")
PROVIDER_API_KEY_ENVS = {
    "openai": "OPENAI_API_KEY",
    "xai": "XAI_API_KEY",
    "google": "GEMINI_API_KEY",
    "anthropic": "ANTHROPIC_API_KEY",
    "generic": "GENERIC_API_KEY",
}
PROVIDER_KINDS = tuple(PROVIDER_API_KEY_ENVS)
INTERNAL_CONFIG_PATH_ENV = "PBI_AGENT_INTERNAL_CONFIG_PATH"
MODEL_PROFILE_ENV = "PBI_AGENT_MODEL_PROFILE"
DEFAULT_INTERNAL_CONFIG_PATH = Path.home() / ".pbi-agent" / "config.json"
SLUG_RE = re.compile(r"[^a-z0-9]+")


class ConfigError(ValueError):
    """Raised when required runtime configuration is invalid."""


class ConfigConflictError(ConfigError):
    """Raised when a config write loses an optimistic concurrency check."""


def missing_api_key_message(provider: str) -> str:
    if provider == "google":
        return (
            "Missing API key for provider 'google'. Set GEMINI_API_KEY (or "
            "PBI_AGENT_API_KEY) in environment, or pass --google-api-key "
            "(or --api-key)."
        )
    return (
        f"Missing API key for provider '{provider}'. Set PBI_AGENT_API_KEY in "
        "environment or pass --api-key."
    )


@dataclass(slots=True)
class Settings:
    api_key: str
    responses_url: str = DEFAULT_RESPONSES_URL
    model: str = DEFAULT_MODEL
    sub_agent_model: str | None = None
    max_tokens: int = DEFAULT_MAX_TOKENS
    verbose: bool = False
    max_tool_workers: int = 4
    max_retries: int = 3
    reasoning_effort: str = "xhigh"
    compact_threshold: int = 200000
    provider: str = "openai"
    generic_api_url: str = DEFAULT_GENERIC_API_URL
    service_tier: str | None = None
    web_search: bool = True

    def validate(self) -> None:
        if self.provider not in PROVIDER_KINDS:
            allowed = ", ".join(PROVIDER_KINDS)
            raise ConfigError(f"--provider must be one of: {allowed}.")
        if not self.api_key:
            raise ConfigError(missing_api_key_message(self.provider))
        if self.max_tool_workers < 1:
            raise ConfigError("--max-tool-workers must be >= 1.")
        if self.max_retries < 0:
            raise ConfigError("--max-retries must be >= 0.")
        if self.reasoning_effort not in {"low", "medium", "high", "xhigh"}:
            raise ConfigError(
                "--reasoning-effort must be one of: low, medium, high, xhigh."
            )
        if self.compact_threshold < 1:
            raise ConfigError("--compact-threshold must be >= 1.")
        if self.max_tokens < 1:
            raise ConfigError("--max-tokens must be >= 1.")
        if self.service_tier is not None and self.provider != "openai":
            raise ConfigError(
                "--service-tier is only supported with the OpenAI provider."
            )
        if (
            self.service_tier is not None
            and self.service_tier not in OPENAI_SERVICE_TIERS
        ):
            allowed = ", ".join(OPENAI_SERVICE_TIERS)
            raise ConfigError(f"--service-tier must be one of: {allowed}.")

    def redacted(self) -> dict[str, str | int | bool | None]:
        return {
            "provider": self.provider,
            "api_key": redact_secret(self.api_key),
            "responses_url": self.responses_url,
            "model": self.model,
            "sub_agent_model": self.sub_agent_model,
            "max_tokens": self.max_tokens,
            "verbose": self.verbose,
            "max_tool_workers": self.max_tool_workers,
            "max_retries": self.max_retries,
            "reasoning_effort": self.reasoning_effort,
            "compact_threshold": self.compact_threshold,
            "generic_api_url": self.generic_api_url,
            "service_tier": self.service_tier,
            "web_search": self.web_search,
        }


@dataclass(slots=True)
class ProviderConfig:
    id: str
    name: str
    kind: str
    api_key: str = ""
    api_key_env: str | None = None
    responses_url: str | None = None
    generic_api_url: str | None = None

    def validate(self) -> None:
        self.id = slugify(self.id)
        self.name = self.name.strip()
        if not self.name:
            raise ConfigError("Provider name cannot be empty.")
        if self.kind not in PROVIDER_KINDS:
            allowed = ", ".join(PROVIDER_KINDS)
            raise ConfigError(f"Provider kind must be one of: {allowed}.")
        if self.api_key_env is not None:
            self.api_key_env = self.api_key_env.strip() or None


@dataclass(slots=True)
class ModelProfileConfig:
    id: str
    name: str
    provider_id: str
    model: str | None = None
    sub_agent_model: str | None = None
    reasoning_effort: str | None = None
    max_tokens: int | None = None
    service_tier: str | None = None
    web_search: bool | None = None
    max_tool_workers: int | None = None
    max_retries: int | None = None
    compact_threshold: int | None = None

    def validate(self, *, provider_kind: str | None = None) -> None:
        self.id = slugify(self.id)
        self.provider_id = slugify(self.provider_id)
        self.name = self.name.strip()
        if not self.name:
            raise ConfigError("Model profile name cannot be empty.")
        if self.reasoning_effort is not None and self.reasoning_effort not in {
            "low",
            "medium",
            "high",
            "xhigh",
        }:
            raise ConfigError(
                "--reasoning-effort must be one of: low, medium, high, xhigh."
            )
        if self.max_tokens is not None and self.max_tokens < 1:
            raise ConfigError("--max-tokens must be >= 1.")
        if self.max_tool_workers is not None and self.max_tool_workers < 1:
            raise ConfigError("--max-tool-workers must be >= 1.")
        if self.max_retries is not None and self.max_retries < 0:
            raise ConfigError("--max-retries must be >= 0.")
        if self.compact_threshold is not None and self.compact_threshold < 1:
            raise ConfigError("--compact-threshold must be >= 1.")
        if self.service_tier is not None and provider_kind not in {None, "openai"}:
            raise ConfigError(
                "--service-tier is only supported with the OpenAI provider."
            )
        if (
            self.service_tier is not None
            and provider_kind is not None
            and self.service_tier not in OPENAI_SERVICE_TIERS
        ):
            allowed = ", ".join(OPENAI_SERVICE_TIERS)
            raise ConfigError(f"--service-tier must be one of: {allowed}.")


@dataclass(slots=True)
class InternalConfig:
    providers: list[ProviderConfig] = field(default_factory=list)
    model_profiles: list[ModelProfileConfig] = field(default_factory=list)
    active_model_profile: str | None = None


def redact_secret(value: str) -> str:
    if not value:
        return ""
    if len(value) <= 8:
        return "***"
    return f"{value[:4]}...{value[-4:]}"


def slugify(value: str) -> str:
    slug = SLUG_RE.sub("-", value.strip().lower()).strip("-")
    if not slug:
        raise ConfigError("IDs must contain at least one letter or number.")
    return slug


def _config_sort_key(item: ProviderConfig | ModelProfileConfig) -> tuple[str, str]:
    return (item.name.lower(), item.id)


def _default_responses_url(provider: str) -> str:
    if provider == "xai":
        return DEFAULT_XAI_RESPONSES_URL
    if provider == "google":
        return DEFAULT_GOOGLE_INTERACTIONS_URL
    return DEFAULT_RESPONSES_URL


def _default_model(provider: str) -> str:
    if provider == "generic":
        return ""
    if provider == "xai":
        return DEFAULT_XAI_MODEL
    if provider == "google":
        return DEFAULT_GOOGLE_MODEL
    if provider == "anthropic":
        return DEFAULT_ANTHROPIC_MODEL
    return DEFAULT_MODEL


def _default_sub_agent_model(provider: str) -> str | None:
    if provider == "generic":
        return None
    if provider == "xai":
        return DEFAULT_XAI_SUB_AGENT_MODEL
    if provider == "google":
        return DEFAULT_GOOGLE_SUB_AGENT_MODEL
    if provider == "anthropic":
        return DEFAULT_ANTHROPIC_SUB_AGENT_MODEL
    return DEFAULT_SUB_AGENT_MODEL


def provider_secret_source(provider: ProviderConfig) -> str:
    if provider.api_key_env:
        return "env_var"
    if provider.api_key:
        return "plaintext"
    return "none"


def provider_has_secret(provider: ProviderConfig) -> bool:
    if provider.api_key_env:
        return bool(os.getenv(provider.api_key_env, ""))
    return bool(provider.api_key)


def provider_ui_metadata(provider_kind: str) -> dict[str, Any]:
    return {
        "default_model": _default_model(provider_kind),
        "default_sub_agent_model": _default_sub_agent_model(provider_kind),
        "default_responses_url": (
            _default_responses_url(provider_kind)
            if provider_kind != "generic"
            else None
        ),
        "default_generic_api_url": (
            DEFAULT_GENERIC_API_URL if provider_kind == "generic" else None
        ),
        "supports_responses_url": provider_kind != "generic",
        "supports_generic_api_url": provider_kind == "generic",
        "supports_service_tier": provider_kind == "openai",
        "supports_native_web_search": provider_kind != "generic",
        "supports_image_inputs": provider_kind in {"openai", "google", "anthropic"},
    }


def load_internal_config_snapshot() -> tuple[InternalConfig, str]:
    config = load_internal_config()
    return config, internal_config_revision(config)


def internal_config_revision(config: InternalConfig) -> str:
    return hashlib.sha256(
        json.dumps(
            _internal_config_payload(config),
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()


def resolve_settings_for_model_profile(
    args: argparse.Namespace,
    model_profile_id: str | None,
) -> Settings:
    cloned_args = argparse.Namespace(**vars(args))
    cloned_args.model_profile = model_profile_id
    return resolve_settings(cloned_args)


def load_internal_config() -> InternalConfig:
    payload = _read_internal_config_payload()
    providers_payload = payload.get("providers")
    profiles_payload = payload.get("model_profiles")
    active_payload = payload.get("active_model_profile")

    if providers_payload is None:
        providers_payload = []
    if profiles_payload is None:
        profiles_payload = []

    if not isinstance(providers_payload, list) or not isinstance(
        profiles_payload, list
    ):
        return InternalConfig()
    if active_payload is not None and not isinstance(active_payload, str):
        return InternalConfig()

    providers: list[ProviderConfig] = []
    for item in providers_payload:
        provider = _provider_from_payload(item)
        if provider is not None:
            providers.append(provider)

    profiles: list[ModelProfileConfig] = []
    for item in profiles_payload:
        profile = _profile_from_payload(item)
        if profile is not None:
            profiles.append(profile)

    active_model_profile = active_payload if isinstance(active_payload, str) else None
    return InternalConfig(
        providers=providers,
        model_profiles=profiles,
        active_model_profile=active_model_profile,
    )


def save_internal_config(config: InternalConfig) -> None:
    save_internal_config_with_revision(config)


def save_internal_config_with_revision(
    config: InternalConfig,
    *,
    expected_revision: str | None = None,
) -> str:
    payload = _internal_config_payload(config)
    path = _internal_config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    if expected_revision is not None:
        _, current_revision = load_internal_config_snapshot()
        if current_revision != expected_revision:
            raise ConfigConflictError("Config has changed. Reload and try again.")
    with tempfile.NamedTemporaryFile(
        "w",
        delete=False,
        dir=path.parent,
        encoding="utf-8",
    ) as handle:
        json.dump(payload, handle, indent=2, sort_keys=True)
        handle.write("\n")
        temp_path = Path(handle.name)
    os.replace(temp_path, path)
    return internal_config_revision(config)


def list_provider_configs() -> list[ProviderConfig]:
    return sorted(load_internal_config().providers, key=_config_sort_key)


def list_model_profile_configs() -> tuple[list[ModelProfileConfig], str | None]:
    config = load_internal_config()
    return sorted(
        config.model_profiles, key=_config_sort_key
    ), config.active_model_profile


def create_provider_config(
    provider: ProviderConfig,
    *,
    expected_revision: str | None = None,
) -> tuple[ProviderConfig, str]:
    provider.validate()
    config = load_internal_config()
    providers = _provider_map(config)
    if provider.id in providers:
        raise ConfigError(f"Provider '{provider.id}' already exists.")
    config.providers.append(provider)
    config.providers.sort(key=_config_sort_key)
    revision = save_internal_config_with_revision(
        config, expected_revision=expected_revision
    )
    return provider, revision


def replace_provider_config(
    provider_id: str,
    updated: ProviderConfig,
    *,
    expected_revision: str | None = None,
) -> tuple[ProviderConfig, str]:
    """Replace an existing provider with a fully-built updated config."""
    config = load_internal_config()
    if _provider_map(config).get(slugify(provider_id)) is None:
        raise ConfigError(f"Unknown provider ID '{provider_id}'.")
    updated.validate()
    for profile in config.model_profiles:
        if profile.provider_id == updated.id:
            profile.validate(provider_kind=updated.kind)
    config.providers = [
        updated if existing.id == updated.id else existing
        for existing in config.providers
    ]
    config.providers.sort(key=_config_sort_key)
    revision = save_internal_config_with_revision(
        config, expected_revision=expected_revision
    )
    return updated, revision


def update_provider_config(
    provider_id: str,
    *,
    name: str | None = None,
    kind: str | None = None,
    api_key: str | None = None,
    api_key_env: str | None = None,
    responses_url: str | None = None,
    generic_api_url: str | None = None,
    expected_revision: str | None = None,
) -> tuple[ProviderConfig, str]:
    config = load_internal_config()
    providers = _provider_map(config)
    provider = providers.get(slugify(provider_id))
    if provider is None:
        raise ConfigError(f"Unknown provider ID '{provider_id}'.")
    updated = replace(
        provider,
        name=name if name is not None else provider.name,
        kind=kind if kind is not None else provider.kind,
        api_key=api_key if api_key is not None else provider.api_key,
        api_key_env=api_key_env if api_key_env is not None else provider.api_key_env,
        responses_url=(
            responses_url if responses_url is not None else provider.responses_url
        ),
        generic_api_url=(
            generic_api_url if generic_api_url is not None else provider.generic_api_url
        ),
    )
    return replace_provider_config(
        provider_id, updated, expected_revision=expected_revision
    )


def delete_provider_config(
    provider_id: str,
    *,
    expected_revision: str | None = None,
) -> str:
    config = load_internal_config()
    normalized_id = slugify(provider_id)
    provider = _provider_map(config).get(normalized_id)
    if provider is None:
        raise ConfigError(f"Unknown provider ID '{provider_id}'.")
    for profile in config.model_profiles:
        if profile.provider_id == normalized_id:
            raise ConfigError(
                f"Cannot delete provider '{normalized_id}': model profile "
                f"'{profile.id}' still references it."
            )
    config.providers = [
        existing for existing in config.providers if existing.id != normalized_id
    ]
    return save_internal_config_with_revision(
        config, expected_revision=expected_revision
    )


def create_model_profile_config(
    profile: ModelProfileConfig,
    *,
    expected_revision: str | None = None,
) -> tuple[ModelProfileConfig, str]:
    config = load_internal_config()
    providers = _provider_map(config)
    profile.validate(
        provider_kind=_require_provider(providers, profile.provider_id).kind
    )
    profiles = _profile_map(config)
    if profile.id in profiles:
        raise ConfigError(f"Model profile '{profile.id}' already exists.")
    config.model_profiles.append(profile)
    config.model_profiles.sort(key=_config_sort_key)
    revision = save_internal_config_with_revision(
        config, expected_revision=expected_revision
    )
    return profile, revision


def replace_model_profile_config(
    profile_id: str,
    updated: ModelProfileConfig,
    *,
    expected_revision: str | None = None,
) -> tuple[ModelProfileConfig, str]:
    """Replace an existing model profile with a fully-built updated config."""
    config = load_internal_config()
    if _profile_map(config).get(slugify(profile_id)) is None:
        raise ConfigError(f"Unknown model profile ID '{profile_id}'.")
    providers = _provider_map(config)
    provider = _require_provider(providers, updated.provider_id)
    updated.validate(provider_kind=provider.kind)
    config.model_profiles = [
        updated if existing.id == updated.id else existing
        for existing in config.model_profiles
    ]
    config.model_profiles.sort(key=_config_sort_key)
    revision = save_internal_config_with_revision(
        config, expected_revision=expected_revision
    )
    return updated, revision


def update_model_profile_config(
    profile_id: str,
    *,
    name: str | None = None,
    provider_id: str | None = None,
    model: str | None = None,
    sub_agent_model: str | None = None,
    reasoning_effort: str | None = None,
    max_tokens: int | None = None,
    service_tier: str | None = None,
    web_search: bool | None = None,
    max_tool_workers: int | None = None,
    max_retries: int | None = None,
    compact_threshold: int | None = None,
    expected_revision: str | None = None,
) -> tuple[ModelProfileConfig, str]:
    config = load_internal_config()
    profiles = _profile_map(config)
    profile = profiles.get(slugify(profile_id))
    if profile is None:
        raise ConfigError(f"Unknown model profile ID '{profile_id}'.")
    next_provider_id = provider_id if provider_id is not None else profile.provider_id
    updated = replace(
        profile,
        name=name if name is not None else profile.name,
        provider_id=next_provider_id,
        model=model if model is not None else profile.model,
        sub_agent_model=(
            sub_agent_model if sub_agent_model is not None else profile.sub_agent_model
        ),
        reasoning_effort=(
            reasoning_effort
            if reasoning_effort is not None
            else profile.reasoning_effort
        ),
        max_tokens=max_tokens if max_tokens is not None else profile.max_tokens,
        service_tier=(
            service_tier if service_tier is not None else profile.service_tier
        ),
        web_search=web_search if web_search is not None else profile.web_search,
        max_tool_workers=(
            max_tool_workers
            if max_tool_workers is not None
            else profile.max_tool_workers
        ),
        max_retries=max_retries if max_retries is not None else profile.max_retries,
        compact_threshold=(
            compact_threshold
            if compact_threshold is not None
            else profile.compact_threshold
        ),
    )
    return replace_model_profile_config(
        profile_id, updated, expected_revision=expected_revision
    )


def delete_model_profile_config(
    profile_id: str,
    *,
    expected_revision: str | None = None,
) -> str:
    config = load_internal_config()
    normalized_id = slugify(profile_id)
    profile = _profile_map(config).get(normalized_id)
    if profile is None:
        raise ConfigError(f"Unknown model profile ID '{profile_id}'.")
    config.model_profiles = [
        existing for existing in config.model_profiles if existing.id != normalized_id
    ]
    if config.active_model_profile == normalized_id:
        config.active_model_profile = None
    return save_internal_config_with_revision(
        config, expected_revision=expected_revision
    )


def select_active_model_profile(
    profile_id: str | None,
    *,
    expected_revision: str | None = None,
) -> tuple[str | None, str]:
    config = load_internal_config()
    if profile_id is None:
        config.active_model_profile = None
    else:
        profile = _profile_map(config).get(slugify(profile_id))
        if profile is None:
            raise ConfigError(f"Unknown model profile ID '{profile_id}'.")
        config.active_model_profile = profile.id
    revision = save_internal_config_with_revision(
        config, expected_revision=expected_revision
    )
    return config.active_model_profile, revision


def resolve_settings(args: argparse.Namespace) -> Settings:
    load_dotenv()

    internal_config = load_internal_config()
    selected_profile_id = (
        getattr(args, "model_profile", None)
        or os.getenv(MODEL_PROFILE_ENV)
        or internal_config.active_model_profile
    )

    selected_profile: ModelProfileConfig | None = None
    selected_provider: ProviderConfig | None = None
    if selected_profile_id:
        normalized_profile_id = slugify(selected_profile_id)
        selected_profile = _profile_map(internal_config).get(normalized_profile_id)
        if selected_profile is None:
            raise ConfigError(f"Unknown model profile ID '{selected_profile_id}'.")
        selected_provider = _provider_map(internal_config).get(
            selected_profile.provider_id
        )
        if selected_provider is None:
            raise ConfigError(
                f"Model profile '{selected_profile.id}' references missing provider "
                f"'{selected_profile.provider_id}'."
            )

    explicit_provider = getattr(args, "provider", None) or os.getenv(
        "PBI_AGENT_PROVIDER"
    )
    provider = explicit_provider or (
        selected_provider.kind if selected_provider else "openai"
    )

    api_key = (
        getattr(args, "api_key", None)
        or os.getenv("PBI_AGENT_API_KEY", "")
        or os.getenv(PROVIDER_API_KEY_ENVS.get(provider, ""), "")
        or (
            os.getenv(selected_provider.api_key_env, "")
            if selected_provider and selected_provider.api_key_env
            else ""
        )
        or (selected_provider.api_key if selected_provider else "")
    )
    responses_url = (
        getattr(args, "responses_url", None)
        or os.getenv("PBI_AGENT_RESPONSES_URL")
        or (selected_provider.responses_url if selected_provider else None)
        or _default_responses_url(provider)
    )
    generic_api_url = (
        getattr(args, "generic_api_url", None)
        or os.getenv("PBI_AGENT_GENERIC_API_URL")
        or (selected_provider.generic_api_url if selected_provider else None)
        or DEFAULT_GENERIC_API_URL
    )
    model = (
        getattr(args, "model", None)
        or os.getenv("PBI_AGENT_MODEL")
        or (selected_profile.model if selected_profile else None)
        or _default_model(provider)
    )
    sub_agent_model = (
        getattr(args, "sub_agent_model", None)
        or os.getenv("PBI_AGENT_SUB_AGENT_MODEL")
        or (selected_profile.sub_agent_model if selected_profile else None)
        or _default_sub_agent_model(provider)
    )
    max_tool_workers = getattr(args, "max_tool_workers", None)
    if max_tool_workers is None:
        max_tool_workers = int(
            os.getenv(
                "PBI_AGENT_MAX_TOOL_WORKERS",
                str(
                    selected_profile.max_tool_workers
                    if selected_profile
                    and selected_profile.max_tool_workers is not None
                    else 4
                ),
            )
        )
    max_retries = getattr(args, "max_retries", None)
    if max_retries is None:
        max_retries = int(
            os.getenv(
                "PBI_AGENT_MAX_RETRIES",
                str(
                    selected_profile.max_retries
                    if selected_profile and selected_profile.max_retries is not None
                    else 3
                ),
            )
        )
    default_effort = "xhigh" if provider == "openai" else "high"
    reasoning_effort = (
        getattr(args, "reasoning_effort", None)
        or os.getenv("PBI_AGENT_REASONING_EFFORT")
        or (selected_profile.reasoning_effort if selected_profile else None)
        or default_effort
    )
    compact_threshold = getattr(args, "compact_threshold", None)
    if compact_threshold is None:
        compact_threshold = int(
            os.getenv(
                "PBI_AGENT_COMPACT_THRESHOLD",
                str(
                    selected_profile.compact_threshold
                    if selected_profile
                    and selected_profile.compact_threshold is not None
                    else 150000
                ),
            )
        )
    max_tokens_raw = getattr(args, "max_tokens", None)
    if max_tokens_raw is None:
        max_tokens = int(
            os.getenv(
                "PBI_AGENT_MAX_TOKENS",
                str(
                    selected_profile.max_tokens
                    if selected_profile and selected_profile.max_tokens is not None
                    else DEFAULT_MAX_TOKENS
                ),
            )
        )
    else:
        max_tokens = int(max_tokens_raw)

    service_tier = (
        getattr(args, "service_tier", None)
        or os.getenv("PBI_AGENT_SERVICE_TIER")
        or (selected_profile.service_tier if selected_profile else None)
    )

    no_web_search = getattr(args, "no_web_search", False)
    web_search_env = os.getenv("PBI_AGENT_WEB_SEARCH")
    if no_web_search:
        web_search = False
    elif web_search_env is not None:
        web_search = web_search_env.lower() not in ("0", "false", "no")
    elif selected_profile and selected_profile.web_search is not None:
        web_search = selected_profile.web_search
    else:
        web_search = True

    return Settings(
        api_key=api_key,
        responses_url=responses_url,
        generic_api_url=generic_api_url,
        model=model,
        sub_agent_model=sub_agent_model,
        max_tokens=max_tokens,
        verbose=bool(getattr(args, "verbose", False)),
        max_tool_workers=max_tool_workers,
        max_retries=max_retries,
        reasoning_effort=reasoning_effort,
        compact_threshold=compact_threshold,
        provider=provider,
        service_tier=service_tier,
        web_search=web_search,
    )


def _internal_config_path() -> Path:
    configured_path = os.getenv(INTERNAL_CONFIG_PATH_ENV)
    if configured_path:
        return Path(configured_path).expanduser().resolve()
    return DEFAULT_INTERNAL_CONFIG_PATH


def _read_internal_config_payload() -> dict[str, Any]:
    path = _internal_config_path()
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    if not isinstance(payload, dict):
        return {}
    return payload


def _provider_from_payload(payload: object) -> ProviderConfig | None:
    if not isinstance(payload, dict):
        return None
    provider_id = payload.get("id")
    name = payload.get("name")
    kind = payload.get("kind")
    if (
        not isinstance(provider_id, str)
        or not isinstance(name, str)
        or not isinstance(kind, str)
    ):
        return None
    provider = ProviderConfig(
        id=provider_id,
        name=name,
        kind=kind,
        api_key=_optional_string(payload.get("api_key")) or "",
        api_key_env=_optional_string(payload.get("api_key_env")),
        responses_url=_optional_string(payload.get("responses_url")),
        generic_api_url=_optional_string(payload.get("generic_api_url")),
    )
    try:
        provider.validate()
    except ConfigError:
        return None
    return provider


def _profile_from_payload(payload: object) -> ModelProfileConfig | None:
    if not isinstance(payload, dict):
        return None
    profile_id = payload.get("id")
    name = payload.get("name")
    provider_id = payload.get("provider_id")
    if (
        not isinstance(profile_id, str)
        or not isinstance(name, str)
        or not isinstance(provider_id, str)
    ):
        return None
    profile = ModelProfileConfig(
        id=profile_id,
        name=name,
        provider_id=provider_id,
        model=_optional_string(payload.get("model")),
        sub_agent_model=_optional_string(payload.get("sub_agent_model")),
        reasoning_effort=_optional_string(payload.get("reasoning_effort")),
        max_tokens=_optional_int(payload.get("max_tokens")),
        service_tier=_optional_string(payload.get("service_tier")),
        web_search=_optional_bool(payload.get("web_search")),
        max_tool_workers=_optional_int(payload.get("max_tool_workers")),
        max_retries=_optional_int(payload.get("max_retries")),
        compact_threshold=_optional_int(payload.get("compact_threshold")),
    )
    try:
        profile.validate()
    except ConfigError:
        return None
    return profile


def _provider_map(config: InternalConfig) -> dict[str, ProviderConfig]:
    return {provider.id: provider for provider in config.providers}


def _profile_map(config: InternalConfig) -> dict[str, ModelProfileConfig]:
    return {profile.id: profile for profile in config.model_profiles}


def _require_provider(
    providers: dict[str, ProviderConfig], provider_id: str
) -> ProviderConfig:
    normalized_id = slugify(provider_id)
    provider = providers.get(normalized_id)
    if provider is None:
        raise ConfigError(f"Unknown provider ID '{provider_id}'.")
    return provider


def _optional_string(value: object) -> str | None:
    if isinstance(value, str):
        return value
    return None


def _optional_int(value: object) -> int | None:
    if isinstance(value, int):
        return value
    return None


def _optional_bool(value: object) -> bool | None:
    if isinstance(value, bool):
        return value
    return None


def _internal_config_payload(config: InternalConfig) -> dict[str, Any]:
    return {
        "providers": [asdict(provider) for provider in config.providers],
        "model_profiles": [asdict(profile) for profile in config.model_profiles],
        "active_model_profile": config.active_model_profile,
    }
