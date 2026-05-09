from __future__ import annotations

import argparse
from dataclasses import replace
from pathlib import Path
from typing import Any

from pbi_agent.auth.models import AUTH_MODE_API_KEY, StoredAuthSession
from pbi_agent.auth.service import get_provider_auth_status
from pbi_agent.config import (
    CommandConfig,
    ConfigError,
    InternalConfig,
    MaintenanceConfig,
    ModelProfileConfig,
    OPENAI_SERVICE_TIERS,
    PROVIDER_KINDS,
    ProviderConfig,
    ResolvedRuntime,
    create_model_profile_config,
    create_provider_config,
    delete_model_profile_config,
    delete_provider_config,
    list_command_configs,
    load_internal_config,
    load_internal_config_snapshot,
    provider_has_secret,
    provider_secret_source,
    provider_ui_metadata,
    replace_model_profile_config,
    replace_provider_config,
    resolve_runtime_for_profile_id,
    resolve_runtime_for_provider_id,
    resolve_web_runtime,
    select_active_model_profile,
    slugify,
    update_maintenance_config as save_maintenance_config,
)
from pbi_agent.providers.model_discovery import (
    discover_provider_models,
    manual_entry_reason,
)
from pbi_agent.session_store import (
    KanbanStageConfigRecord,
    KanbanTaskRecord,
    SessionStore,
)
from pbi_agent.skills.project_catalog import (
    ProjectSkillManifest,
    discover_installed_project_skills,
)
from pbi_agent.skills.project_installer import (
    ProjectSkillInstallResult,
    RemoteSkillCandidateSummary,
    install_project_skill,
    list_remote_project_skills,
    resolve_default_skills_source,
)
from pbi_agent.web.session.serializers import (
    _config_sort_key,
    _resolved_runtime_view,
    _serialize_saved_session_runtime,
    _serialize_session,
)
from pbi_agent.web.session.state import EventStream


class ConfigurationMixin:
    _app_stream: EventStream
    _default_runtime: ResolvedRuntime
    _directory_key: str
    _runtime_args: argparse.Namespace | None
    _workspace_root: Path

    def config_bootstrap(self) -> dict[str, Any]:
        config, revision = load_internal_config_snapshot()
        return {
            "providers": [
                self._provider_view(provider)
                for provider in sorted(
                    config.providers,
                    key=lambda item: _config_sort_key(item.name, item.id),
                )
            ],
            "model_profiles": [
                self._model_profile_view(
                    profile,
                    provider=self._require_provider(config, profile.provider_id),
                    active_profile_id=config.web.active_profile_id,
                )
                for profile in sorted(
                    config.model_profiles,
                    key=lambda item: _config_sort_key(item.name, item.id),
                )
            ],
            "commands": [
                self._command_view(command)
                for command in sorted(
                    list_command_configs(self._workspace_root),
                    key=lambda item: _config_sort_key(item.name, item.id),
                )
            ],
            "skills": self._installed_skill_views(),
            "active_profile_id": config.web.active_profile_id,
            "maintenance": self._maintenance_view(config.maintenance),
            "config_revision": revision,
            "options": {
                "provider_kinds": list(PROVIDER_KINDS),
                "reasoning_efforts": ["low", "medium", "high", "xhigh"],
                "openai_service_tiers": list(OPENAI_SERVICE_TIERS),
                "provider_metadata": {
                    provider_kind: provider_ui_metadata(provider_kind)
                    for provider_kind in PROVIDER_KINDS
                },
            },
        }

    def update_maintenance_config(
        self,
        *,
        retention_days: int,
        expected_revision: str,
    ) -> dict[str, Any]:
        config, revision = save_maintenance_config(
            retention_days=retention_days,
            expected_revision=expected_revision,
        )
        return {
            "maintenance": self._maintenance_view(config),
            "config_revision": revision,
        }

    def create_provider(
        self,
        *,
        provider_id: str | None,
        name: str,
        kind: str,
        auth_mode: str | None,
        api_key: str | None,
        api_key_env: str | None,
        responses_url: str | None,
        generic_api_url: str | None,
        expected_revision: str,
    ) -> dict[str, Any]:
        next_auth_mode = auth_mode or provider_ui_metadata(kind)["default_auth_mode"]
        self._validate_secret_inputs(
            auth_mode=next_auth_mode,
            api_key=api_key,
            api_key_env=api_key_env,
        )
        provider, revision = create_provider_config(
            ProviderConfig(
                id=slugify(provider_id or name),
                name=name,
                kind=kind,
                auth_mode=next_auth_mode,
                api_key=api_key or "",
                api_key_env=api_key_env,
                responses_url=responses_url,
                generic_api_url=generic_api_url,
            ),
            expected_revision=expected_revision,
        )
        return {"provider": self._provider_view(provider), "config_revision": revision}

    def update_provider(
        self,
        provider_id: str,
        *,
        name: str | None,
        kind: str | None,
        auth_mode: str | None,
        api_key: str | None,
        api_key_env: str | None,
        responses_url: str | None,
        generic_api_url: str | None,
        fields_set: set[str],
        expected_revision: str,
    ) -> dict[str, Any]:
        if "name" in fields_set and name is None:
            raise ConfigError("Provider name cannot be null.")
        if "kind" in fields_set and kind is None:
            raise ConfigError("Provider kind cannot be null.")
        config = load_internal_config()
        provider = self._provider_map(config).get(slugify(provider_id))
        if provider is None:
            raise ConfigError(f"Unknown provider ID '{provider_id}'.")
        next_kind = kind if "kind" in fields_set and kind is not None else provider.kind
        next_auth_mode = (
            auth_mode
            if "auth_mode" in fields_set and auth_mode is not None
            else provider_ui_metadata(next_kind)["default_auth_mode"]
            if "kind" in fields_set and kind is not None
            else provider.auth_mode
        )
        self._validate_secret_inputs(
            auth_mode=next_auth_mode,
            api_key=api_key if "api_key" in fields_set else None,
            api_key_env=api_key_env if "api_key_env" in fields_set else None,
        )
        next_api_key = provider.api_key
        next_api_key_env = provider.api_key_env
        if "api_key" in fields_set:
            next_api_key = api_key or ""
            if api_key:
                next_api_key_env = None
        if "api_key_env" in fields_set:
            next_api_key_env = (api_key_env or "").strip() or None
            if next_api_key_env:
                next_api_key = ""
        if next_auth_mode != AUTH_MODE_API_KEY:
            next_api_key = ""
            next_api_key_env = None
        merged = replace(
            provider,
            name=name if "name" in fields_set else provider.name,
            kind=next_kind,
            auth_mode=next_auth_mode,
            api_key=next_api_key,
            api_key_env=next_api_key_env,
            responses_url=(
                responses_url
                if "responses_url" in fields_set
                else provider.responses_url
            ),
            generic_api_url=(
                generic_api_url
                if "generic_api_url" in fields_set
                else provider.generic_api_url
            ),
        )
        updated, revision = replace_provider_config(
            provider_id, merged, expected_revision=expected_revision
        )
        return {"provider": self._provider_view(updated), "config_revision": revision}

    def delete_provider(
        self,
        provider_id: str,
        *,
        expected_revision: str,
    ) -> str:
        return delete_provider_config(provider_id, expected_revision=expected_revision)

    def get_provider_models(self, provider_id: str) -> dict[str, Any]:
        config = load_internal_config()
        provider = self._require_provider(config, provider_id)
        runtime = resolve_runtime_for_provider_id(
            provider.id,
            verbose=self._default_runtime.settings.verbose,
        )
        result = discover_provider_models(runtime.settings)
        error_payload = self._provider_model_error_view(result.error)
        if error_payload is None:
            reason = manual_entry_reason(provider.kind)
            if reason and result.manual_entry_required:
                error_payload = {
                    "code": "manual_entry_required",
                    "message": reason,
                    "status_code": None,
                }
        return {
            "provider_id": provider.id,
            "provider_kind": provider.kind,
            "discovery_supported": result.discovery_supported,
            "manual_entry_required": result.manual_entry_required,
            "models": [self._provider_model_view(model) for model in result.models],
            "error": error_payload,
        }

    def create_model_profile(
        self,
        *,
        profile_id: str | None,
        name: str,
        provider_id: str,
        model: str | None,
        sub_agent_model: str | None,
        reasoning_effort: str | None,
        max_tokens: int | None,
        service_tier: str | None,
        web_search: bool | None,
        max_tool_workers: int | None,
        max_retries: int | None,
        compact_threshold: int | None,
        compact_tail_turns: int | None,
        compact_preserve_recent_tokens: int | None,
        compact_tool_output_max_chars: int | None,
        expected_revision: str,
    ) -> dict[str, Any]:
        config = load_internal_config()
        provider = self._require_provider(config, provider_id)
        profile, revision = create_model_profile_config(
            ModelProfileConfig(
                id=slugify(profile_id or name),
                name=name,
                provider_id=provider.id,
                model=model,
                sub_agent_model=sub_agent_model,
                reasoning_effort=reasoning_effort,
                max_tokens=max_tokens,
                service_tier=service_tier,
                web_search=web_search,
                max_tool_workers=max_tool_workers,
                max_retries=max_retries,
                compact_threshold=compact_threshold,
                compact_tail_turns=compact_tail_turns,
                compact_preserve_recent_tokens=compact_preserve_recent_tokens,
                compact_tool_output_max_chars=compact_tool_output_max_chars,
            ),
            expected_revision=expected_revision,
        )
        # The config snapshot loaded above is stale after the save — if there was
        # no active profile, create_model_profile_config auto-activated this one.
        active_profile_id = config.web.active_profile_id or profile.id
        return {
            "model_profile": self._model_profile_view(
                profile,
                provider=provider,
                active_profile_id=active_profile_id,
            ),
            "config_revision": revision,
        }

    def update_model_profile(
        self,
        profile_id: str,
        *,
        name: str | None,
        provider_id: str | None,
        model: str | None,
        sub_agent_model: str | None,
        reasoning_effort: str | None,
        max_tokens: int | None,
        service_tier: str | None,
        web_search: bool | None,
        max_tool_workers: int | None,
        max_retries: int | None,
        compact_threshold: int | None,
        compact_tail_turns: int | None,
        compact_preserve_recent_tokens: int | None,
        compact_tool_output_max_chars: int | None,
        fields_set: set[str],
        expected_revision: str,
    ) -> dict[str, Any]:
        if "name" in fields_set and name is None:
            raise ConfigError("Model profile name cannot be null.")
        if "provider_id" in fields_set and provider_id is None:
            raise ConfigError("provider_id cannot be null.")
        config = load_internal_config()
        profile = self._profile_map(config).get(slugify(profile_id))
        if profile is None:
            raise ConfigError(f"Unknown profile ID '{profile_id}'.")
        next_provider_id = (
            slugify(provider_id)
            if "provider_id" in fields_set and provider_id is not None
            else profile.provider_id
        )
        provider = self._require_provider(config, next_provider_id)
        merged = replace(
            profile,
            name=name if "name" in fields_set else profile.name,
            provider_id=next_provider_id,
            model=model if "model" in fields_set else profile.model,
            sub_agent_model=(
                sub_agent_model
                if "sub_agent_model" in fields_set
                else profile.sub_agent_model
            ),
            reasoning_effort=(
                reasoning_effort
                if "reasoning_effort" in fields_set
                else profile.reasoning_effort
            ),
            max_tokens=max_tokens if "max_tokens" in fields_set else profile.max_tokens,
            service_tier=(
                service_tier if "service_tier" in fields_set else profile.service_tier
            ),
            web_search=web_search if "web_search" in fields_set else profile.web_search,
            max_tool_workers=(
                max_tool_workers
                if "max_tool_workers" in fields_set
                else profile.max_tool_workers
            ),
            max_retries=(
                max_retries if "max_retries" in fields_set else profile.max_retries
            ),
            compact_threshold=(
                compact_threshold
                if "compact_threshold" in fields_set
                else profile.compact_threshold
            ),
            compact_tail_turns=(
                compact_tail_turns
                if "compact_tail_turns" in fields_set
                else profile.compact_tail_turns
            ),
            compact_preserve_recent_tokens=(
                compact_preserve_recent_tokens
                if "compact_preserve_recent_tokens" in fields_set
                else profile.compact_preserve_recent_tokens
            ),
            compact_tool_output_max_chars=(
                compact_tool_output_max_chars
                if "compact_tool_output_max_chars" in fields_set
                else profile.compact_tool_output_max_chars
            ),
        )
        updated, revision = replace_model_profile_config(
            profile_id, merged, expected_revision=expected_revision
        )
        return {
            "model_profile": self._model_profile_view(
                updated,
                provider=provider,
                active_profile_id=config.web.active_profile_id,
            ),
            "config_revision": revision,
        }

    def delete_model_profile(
        self,
        profile_id: str,
        *,
        expected_revision: str,
    ) -> str:
        return delete_model_profile_config(
            profile_id, expected_revision=expected_revision
        )

    def set_active_model_profile(
        self,
        profile_id: str | None,
        *,
        expected_revision: str,
    ) -> dict[str, Any]:
        active_id, revision = select_active_model_profile(
            profile_id, expected_revision=expected_revision
        )
        return {
            "active_profile_id": active_id,
            "config_revision": revision,
        }

    def list_project_skills(self) -> dict[str, Any]:
        _, revision = load_internal_config_snapshot()
        return {
            "skills": self._installed_skill_views(),
            "config_revision": revision,
        }

    def list_project_skill_candidates(
        self,
        *,
        source: str | None,
    ) -> dict[str, Any]:
        listing = list_remote_project_skills(self._effective_skill_source(source))
        return {
            "source": listing.source,
            "ref": listing.ref,
            "candidates": [
                self._skill_candidate_view(candidate)
                for candidate in listing.candidates
            ],
        }

    def install_project_skill_from_source(
        self,
        *,
        source: str | None,
        skill_name: str,
        force: bool,
    ) -> dict[str, Any]:
        result = install_project_skill(
            self._effective_skill_source(source),
            skill_name=skill_name,
            force=force,
            workspace=self._workspace_root,
        )
        _, revision = load_internal_config_snapshot()
        return {
            "installed": self._skill_install_result_view(result),
            "skills": self._installed_skill_views(),
            "config_revision": revision,
        }

    def _resolve_task_runtime(
        self,
        record: KanbanTaskRecord,
        *,
        stage_record: KanbanStageConfigRecord | None = None,
        allow_fallback: bool = True,
    ) -> ResolvedRuntime:
        resolved_profile_id = record.model_profile_id or (
            stage_record.model_profile_id if stage_record is not None else None
        )
        if allow_fallback:
            return self._resolve_runtime_or_default(resolved_profile_id)
        return self._resolve_runtime(resolved_profile_id)

    def _resolve_runtime(self, profile_id: str | None) -> ResolvedRuntime:
        if profile_id is None:
            if self._runtime_args is None:
                return self._default_runtime
            return resolve_web_runtime(verbose=self._default_runtime.settings.verbose)
        return resolve_runtime_for_profile_id(
            profile_id,
            verbose=self._default_runtime.settings.verbose,
        )

    def _resolve_runtime_optional(
        self,
        profile_id: str | None,
    ) -> ResolvedRuntime | None:
        try:
            return self._resolve_runtime(profile_id)
        except ConfigError:
            return None

    def _resolve_runtime_or_default(
        self,
        profile_id: str | None,
    ) -> ResolvedRuntime:
        runtime = self._resolve_runtime_optional(profile_id)
        if runtime is not None:
            return runtime
        return self._default_runtime

    def _resolve_saved_session_runtime(
        self,
        session_id: str,
        *,
        fallback: ResolvedRuntime,
    ) -> ResolvedRuntime:
        try:
            with SessionStore() as store:
                record = store.get_session(session_id)
        except Exception:
            return fallback
        if record is None or record.directory != self._directory_key:
            return fallback
        if record.profile_id:
            return self._resolve_runtime_or_default(record.profile_id)
        settings = replace(
            fallback.settings,
            provider=record.provider or fallback.settings.provider,
            model=record.model or fallback.settings.model,
        )
        return ResolvedRuntime(
            settings=settings,
            provider_id=record.provider_id or fallback.provider_id,
            profile_id=None,
        )

    def _update_saved_session_runtime(
        self,
        session_id: str,
        runtime: ResolvedRuntime,
    ) -> dict[str, Any]:
        with SessionStore() as store:
            record = store.get_session(session_id)
            if record is None or record.directory != self._directory_key:
                raise KeyError(session_id)
            store.update_session(
                session_id,
                provider=runtime.settings.provider,
                provider_id=runtime.provider_id or None,
                model=runtime.settings.model,
                profile_id=runtime.profile_id or None,
            )
            updated = store.get_session(session_id)
        if updated is None:
            raise KeyError(session_id)
        serialized = _serialize_session(updated)
        self._app_stream.publish("session_updated", {"session": serialized})
        return _serialize_saved_session_runtime(updated, runtime)

    def _provider_view(self, provider: ProviderConfig) -> dict[str, Any]:
        auth_status = get_provider_auth_status(
            provider_kind=provider.kind,
            provider_id=provider.id,
            auth_mode=provider.auth_mode,
        )
        return {
            "id": provider.id,
            "name": provider.name,
            "kind": provider.kind,
            "auth_mode": provider.auth_mode,
            "responses_url": provider.responses_url,
            "generic_api_url": provider.generic_api_url,
            "secret_source": provider_secret_source(provider),
            "secret_env_var": provider.api_key_env,
            "has_secret": provider_has_secret(provider),
            "auth_status": self._auth_status_view(auth_status),
        }

    def _auth_status_view(self, status: Any) -> dict[str, Any]:
        return {
            "auth_mode": status.auth_mode,
            "backend": status.backend,
            "session_status": status.session_status,
            "has_session": status.has_session,
            "can_refresh": status.can_refresh,
            "account_id": status.account_id,
            "email": status.email,
            "plan_type": status.plan_type,
            "expires_at": status.expires_at,
        }

    def _auth_session_view(
        self, session: StoredAuthSession | None
    ) -> dict[str, Any] | None:
        if session is None:
            return None
        return {
            "provider_id": session.provider_id,
            "backend": session.backend,
            "expires_at": session.expires_at,
            "account_id": session.account_id,
            "email": session.email,
            "plan_type": session.plan_type,
        }

    def _provider_model_view(self, model: Any) -> dict[str, Any]:
        return {
            "id": model.id,
            "display_name": model.display_name,
            "created": model.created,
            "owned_by": model.owned_by,
            "input_modalities": list(model.input_modalities),
            "output_modalities": list(model.output_modalities),
            "aliases": list(model.aliases),
            "supports_reasoning_effort": model.supports_reasoning_effort,
        }

    def _provider_model_error_view(self, error: Any) -> dict[str, Any] | None:
        if error is None:
            return None
        return {
            "code": error.code,
            "message": error.message,
            "status_code": error.status_code,
        }

    def _model_profile_view(
        self,
        profile: ModelProfileConfig,
        *,
        provider: ProviderConfig,
        active_profile_id: str | None,
    ) -> dict[str, Any]:
        runtime = self._resolve_runtime_or_default(profile.id)
        return {
            "id": profile.id,
            "name": profile.name,
            "provider_id": profile.provider_id,
            "provider": {
                "id": provider.id,
                "name": provider.name,
                "kind": provider.kind,
            },
            "model": profile.model,
            "sub_agent_model": profile.sub_agent_model,
            "reasoning_effort": profile.reasoning_effort,
            "max_tokens": profile.max_tokens,
            "service_tier": profile.service_tier,
            "web_search": profile.web_search,
            "max_tool_workers": profile.max_tool_workers,
            "max_retries": profile.max_retries,
            "compact_threshold": profile.compact_threshold,
            "compact_tail_turns": profile.compact_tail_turns,
            "compact_preserve_recent_tokens": profile.compact_preserve_recent_tokens,
            "compact_tool_output_max_chars": profile.compact_tool_output_max_chars,
            "is_active_default": profile.id == active_profile_id,
            "resolved_runtime": _resolved_runtime_view(runtime),
        }

    def _command_view(self, command: CommandConfig) -> dict[str, Any]:
        return {
            "id": command.id,
            "name": command.name,
            "slash_alias": command.slash_alias,
            "description": command.description,
            "instructions": command.instructions,
            "path": command.path,
        }

    def _installed_skill_views(self) -> list[dict[str, Any]]:
        return [
            self._skill_view(skill)
            for skill in sorted(
                discover_installed_project_skills(workspace=self._workspace_root),
                key=lambda item: (item.name.casefold(), item.location.as_posix()),
            )
        ]

    def _skill_view(self, skill: ProjectSkillManifest) -> dict[str, Any]:
        return {
            "id": skill.name,
            "name": skill.name,
            "description": skill.description,
            "path": self._relative_workspace_path(skill.location),
        }

    def _skill_candidate_view(
        self, candidate: RemoteSkillCandidateSummary
    ) -> dict[str, Any]:
        return {
            "name": candidate.name,
            "description": candidate.description,
            "subpath": candidate.subpath,
        }

    def _skill_install_result_view(
        self, result: ProjectSkillInstallResult
    ) -> dict[str, Any]:
        return {
            "name": result.name,
            "install_path": self._relative_workspace_path(result.install_path),
            "source": result.source,
            "ref": result.ref,
            "subpath": result.subpath,
        }

    def _relative_workspace_path(self, path: Path) -> str:
        resolved_path = path.resolve()
        try:
            return resolved_path.relative_to(self._workspace_root.resolve()).as_posix()
        except ValueError:
            return resolved_path.as_posix()

    def _effective_skill_source(self, source: str | None) -> str:
        if source is None:
            return resolve_default_skills_source()
        stripped = source.strip()
        if not stripped:
            return resolve_default_skills_source()
        return stripped

    def _maintenance_view(self, config: MaintenanceConfig) -> dict[str, Any]:
        return {"retention_days": config.retention_days}

    def _provider_map(self, config: InternalConfig) -> dict[str, ProviderConfig]:
        return {provider.id: provider for provider in config.providers}

    def _profile_map(self, config: InternalConfig) -> dict[str, ModelProfileConfig]:
        return {profile.id: profile for profile in config.model_profiles}

    def _command_map(self) -> dict[str, CommandConfig]:
        return {
            command.id: command
            for command in list_command_configs(self._workspace_root)
        }

    def _require_provider(
        self, config: InternalConfig, provider_id: str
    ) -> ProviderConfig:
        provider = self._provider_map(config).get(slugify(provider_id))
        if provider is None:
            raise ConfigError(f"Unknown provider ID '{provider_id}'.")
        return provider

    def _validate_secret_inputs(
        self,
        *,
        auth_mode: str | None = None,
        api_key: str | None,
        api_key_env: str | None,
    ) -> None:
        if auth_mode is not None and auth_mode != AUTH_MODE_API_KEY:
            if api_key:
                raise ConfigError(
                    "api_key is only valid when provider auth_mode is 'api_key'."
                )
            if api_key_env:
                raise ConfigError(
                    "api_key_env is only valid when provider auth_mode is 'api_key'."
                )
            return
        if api_key and api_key_env:
            raise ConfigError(
                "api_key and api_key_env cannot both be set in the same request."
            )
