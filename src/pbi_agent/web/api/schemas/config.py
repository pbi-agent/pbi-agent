from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from pbi_agent.web.api.deps import NonEmptyString


class ProviderKindMetadataModel(BaseModel):
    default_auth_mode: str
    auth_modes: list[str]
    default_model: str
    default_sub_agent_model: str | None
    default_responses_url: str | None
    default_generic_api_url: str | None
    supports_responses_url: bool
    supports_generic_api_url: bool
    supports_service_tier: bool
    supports_native_web_search: bool
    supports_image_inputs: bool


class ConfigOptionsModel(BaseModel):
    provider_kinds: list[str]
    reasoning_efforts: list[str]
    openai_service_tiers: list[str]
    provider_metadata: dict[str, ProviderKindMetadataModel]


class ProviderViewModel(BaseModel):
    id: str
    name: str
    kind: str
    auth_mode: str
    responses_url: str | None
    generic_api_url: str | None
    secret_source: Literal["none", "plaintext", "env_var"]
    secret_env_var: str | None
    has_secret: bool
    auth_status: "ProviderAuthStatusModel"


class ProviderAuthStatusModel(BaseModel):
    auth_mode: str
    backend: str | None
    session_status: str
    has_session: bool
    can_refresh: bool
    account_id: str | None
    email: str | None
    plan_type: str | None
    expires_at: int | None


class ProviderAuthSessionModel(BaseModel):
    provider_id: str
    backend: str
    expires_at: int | None
    account_id: str | None
    email: str | None
    plan_type: str | None


class ProviderMutationRequest(BaseModel):
    id: str | None = None
    name: NonEmptyString
    kind: NonEmptyString
    auth_mode: str = "api_key"
    api_key: str | None = None
    api_key_env: str | None = None
    responses_url: str | None = None
    generic_api_url: str | None = None


class ProviderUpdateRequest(BaseModel):
    name: NonEmptyString | None = None
    kind: NonEmptyString | None = None
    auth_mode: str | None = None
    api_key: str | None = None
    api_key_env: str | None = None
    responses_url: str | None = None
    generic_api_url: str | None = None


class ProviderListResponse(BaseModel):
    providers: list[ProviderViewModel]
    config_revision: str


class ProviderResponse(BaseModel):
    provider: ProviderViewModel
    config_revision: str


class ProviderAuthImportRequest(BaseModel):
    access_token: NonEmptyString
    refresh_token: str | None = None
    account_id: str | None = None
    email: str | None = None
    plan_type: str | None = None
    expires_at: int | None = None
    id_token: str | None = None


class ProviderAuthResponse(BaseModel):
    provider: ProviderViewModel
    auth_status: ProviderAuthStatusModel
    session: ProviderAuthSessionModel | None = None


class ProviderAuthLogoutResponse(BaseModel):
    provider: ProviderViewModel
    auth_status: ProviderAuthStatusModel
    removed: bool


class ProviderAuthFlowStartRequest(BaseModel):
    method: Literal["browser", "device"]


class ProviderAuthFlowViewModel(BaseModel):
    flow_id: str
    provider_id: str
    backend: str
    method: Literal["browser", "device"]
    status: Literal["pending", "completed", "failed"]
    authorization_url: str | None = None
    callback_url: str | None = None
    verification_url: str | None = None
    user_code: str | None = None
    interval_seconds: int | None = None
    error_message: str | None = None
    created_at: str
    updated_at: str


class ProviderAuthFlowResponse(BaseModel):
    provider: ProviderViewModel
    auth_status: ProviderAuthStatusModel
    flow: ProviderAuthFlowViewModel
    session: ProviderAuthSessionModel | None = None


class ModelProfileProviderModel(BaseModel):
    id: str
    name: str
    kind: str


class ResolvedRuntimeViewModel(BaseModel):
    provider: str
    provider_id: str
    profile_id: str
    model: str
    sub_agent_model: str | None
    reasoning_effort: str
    max_tokens: int
    service_tier: str | None
    web_search: bool
    max_tool_workers: int
    max_retries: int
    compact_threshold: int
    responses_url: str
    generic_api_url: str
    supports_image_inputs: bool


class ModelProfileViewModel(BaseModel):
    id: str
    name: str
    provider_id: str
    provider: ModelProfileProviderModel
    model: str | None
    sub_agent_model: str | None
    reasoning_effort: str | None
    max_tokens: int | None
    service_tier: str | None
    web_search: bool | None
    max_tool_workers: int | None
    max_retries: int | None
    compact_threshold: int | None
    is_active_default: bool
    resolved_runtime: ResolvedRuntimeViewModel


class ModelProfileMutationRequest(BaseModel):
    id: str | None = None
    name: NonEmptyString
    provider_id: NonEmptyString
    model: str | None = None
    sub_agent_model: str | None = None
    reasoning_effort: str | None = None
    max_tokens: int | None = Field(default=None, ge=1)
    service_tier: str | None = None
    web_search: bool | None = None
    max_tool_workers: int | None = Field(default=None, ge=1)
    max_retries: int | None = Field(default=None, ge=0)
    compact_threshold: int | None = Field(default=None, ge=1)


class ModelProfileUpdateRequest(BaseModel):
    name: NonEmptyString | None = None
    provider_id: NonEmptyString | None = None
    model: str | None = None
    sub_agent_model: str | None = None
    reasoning_effort: str | None = None
    max_tokens: int | None = Field(default=None, ge=1)
    service_tier: str | None = None
    web_search: bool | None = None
    max_tool_workers: int | None = Field(default=None, ge=1)
    max_retries: int | None = Field(default=None, ge=0)
    compact_threshold: int | None = Field(default=None, ge=1)


class ModelProfileListResponse(BaseModel):
    model_profiles: list[ModelProfileViewModel]
    active_profile_id: str | None
    config_revision: str


class ModelProfileResponse(BaseModel):
    model_profile: ModelProfileViewModel
    config_revision: str


class ActiveProfileRequest(BaseModel):
    profile_id: str | None = None


class ActiveProfileResponse(BaseModel):
    active_profile_id: str | None
    config_revision: str


class CommandViewModel(BaseModel):
    id: str
    name: str
    slash_alias: str
    description: str
    instructions: str
    path: str


class CommandListResponse(BaseModel):
    commands: list[CommandViewModel]
    config_revision: str


class ConfigBootstrapResponse(BaseModel):
    providers: list[ProviderViewModel]
    model_profiles: list[ModelProfileViewModel]
    commands: list[CommandViewModel]
    active_profile_id: str | None
    config_revision: str
    options: ConfigOptionsModel
