from __future__ import annotations

from fastapi import APIRouter, Response

from pbi_agent.web.api.deps import (
    ConfigRevisionHeader,
    SessionManagerDep,
    model_from_payload,
)
from pbi_agent.web.api.errors import config_http_error
from pbi_agent.web.api.schemas.config import (
    ActiveProfileRequest,
    ActiveProfileResponse,
    CommandListResponse,
    CommandViewModel,
    ConfigBootstrapResponse,
    ModelProfileListResponse,
    ModelProfileMutationRequest,
    ModelProfileResponse,
    ModelProfileUpdateRequest,
    ModelProfileViewModel,
    ProviderListResponse,
    ProviderModelFetchErrorModel,
    ProviderModelListResponse,
    ProviderModelViewModel,
    ProviderMutationRequest,
    ProviderResponse,
    ProviderUpdateRequest,
    ProviderViewModel,
)

router = APIRouter(prefix="/api/config", tags=["config"])


@router.get("/bootstrap", response_model=ConfigBootstrapResponse)
def config_bootstrap(manager: SessionManagerDep) -> ConfigBootstrapResponse:
    return model_from_payload(ConfigBootstrapResponse, manager.config_bootstrap())


@router.get("/providers", response_model=ProviderListResponse)
def list_providers(manager: SessionManagerDep) -> ProviderListResponse:
    payload = manager.config_bootstrap()
    return ProviderListResponse(
        providers=[
            model_from_payload(ProviderViewModel, item) for item in payload["providers"]
        ],
        config_revision=str(payload["config_revision"]),
    )


@router.post("/providers", response_model=ProviderResponse)
def create_provider(
    request: ProviderMutationRequest,
    manager: SessionManagerDep,
    expected_revision: ConfigRevisionHeader,
) -> ProviderResponse:
    try:
        payload = manager.create_provider(
            provider_id=request.id,
            name=request.name,
            kind=request.kind,
            auth_mode=request.auth_mode,
            api_key=request.api_key,
            api_key_env=request.api_key_env,
            responses_url=request.responses_url,
            generic_api_url=request.generic_api_url,
            expected_revision=expected_revision,
        )
    except Exception as exc:
        raise config_http_error(exc) from exc
    return ProviderResponse(
        provider=model_from_payload(ProviderViewModel, payload["provider"]),
        config_revision=str(payload["config_revision"]),
    )


@router.patch("/providers/{provider_id}", response_model=ProviderResponse)
def update_provider(
    provider_id: str,
    request: ProviderUpdateRequest,
    manager: SessionManagerDep,
    expected_revision: ConfigRevisionHeader,
) -> ProviderResponse:
    try:
        payload = manager.update_provider(
            provider_id,
            name=request.name,
            kind=request.kind,
            auth_mode=request.auth_mode,
            api_key=request.api_key,
            api_key_env=request.api_key_env,
            responses_url=request.responses_url,
            generic_api_url=request.generic_api_url,
            fields_set=set(request.model_fields_set),
            expected_revision=expected_revision,
        )
    except Exception as exc:
        raise config_http_error(exc) from exc
    return ProviderResponse(
        provider=model_from_payload(ProviderViewModel, payload["provider"]),
        config_revision=str(payload["config_revision"]),
    )


@router.delete("/providers/{provider_id}", status_code=204)
def delete_provider(
    provider_id: str,
    manager: SessionManagerDep,
    expected_revision: ConfigRevisionHeader,
) -> Response:
    try:
        manager.delete_provider(provider_id, expected_revision=expected_revision)
    except Exception as exc:
        raise config_http_error(exc) from exc
    return Response(status_code=204)


@router.get(
    "/providers/{provider_id}/models",
    response_model=ProviderModelListResponse,
)
def list_provider_models(
    provider_id: str,
    manager: SessionManagerDep,
) -> ProviderModelListResponse:
    try:
        payload = manager.get_provider_models(provider_id)
    except Exception as exc:
        raise config_http_error(exc) from exc
    return ProviderModelListResponse(
        provider_id=payload["provider_id"],
        provider_kind=payload["provider_kind"],
        discovery_supported=payload["discovery_supported"],
        manual_entry_required=payload["manual_entry_required"],
        models=[
            model_from_payload(ProviderModelViewModel, item)
            for item in payload["models"]
        ],
        error=(
            model_from_payload(ProviderModelFetchErrorModel, payload["error"])
            if payload["error"] is not None
            else None
        ),
    )


@router.get("/model-profiles", response_model=ModelProfileListResponse)
def list_model_profiles(manager: SessionManagerDep) -> ModelProfileListResponse:
    payload = manager.config_bootstrap()
    return ModelProfileListResponse(
        model_profiles=[
            model_from_payload(ModelProfileViewModel, item)
            for item in payload["model_profiles"]
        ],
        active_profile_id=payload["active_profile_id"],
        config_revision=str(payload["config_revision"]),
    )


@router.post("/model-profiles", response_model=ModelProfileResponse)
def create_model_profile(
    request: ModelProfileMutationRequest,
    manager: SessionManagerDep,
    expected_revision: ConfigRevisionHeader,
) -> ModelProfileResponse:
    try:
        payload = manager.create_model_profile(
            profile_id=request.id,
            name=request.name,
            provider_id=request.provider_id,
            model=request.model,
            sub_agent_model=request.sub_agent_model,
            reasoning_effort=request.reasoning_effort,
            max_tokens=request.max_tokens,
            service_tier=request.service_tier,
            web_search=request.web_search,
            max_tool_workers=request.max_tool_workers,
            max_retries=request.max_retries,
            compact_threshold=request.compact_threshold,
            expected_revision=expected_revision,
        )
    except Exception as exc:
        raise config_http_error(exc) from exc
    return ModelProfileResponse(
        model_profile=model_from_payload(
            ModelProfileViewModel, payload["model_profile"]
        ),
        config_revision=str(payload["config_revision"]),
    )


@router.patch("/model-profiles/{profile_id}", response_model=ModelProfileResponse)
def update_model_profile(
    profile_id: str,
    request: ModelProfileUpdateRequest,
    manager: SessionManagerDep,
    expected_revision: ConfigRevisionHeader,
) -> ModelProfileResponse:
    try:
        payload = manager.update_model_profile(
            profile_id,
            name=request.name,
            provider_id=request.provider_id,
            model=request.model,
            sub_agent_model=request.sub_agent_model,
            reasoning_effort=request.reasoning_effort,
            max_tokens=request.max_tokens,
            service_tier=request.service_tier,
            web_search=request.web_search,
            max_tool_workers=request.max_tool_workers,
            max_retries=request.max_retries,
            compact_threshold=request.compact_threshold,
            fields_set=set(request.model_fields_set),
            expected_revision=expected_revision,
        )
    except Exception as exc:
        raise config_http_error(exc) from exc
    return ModelProfileResponse(
        model_profile=model_from_payload(
            ModelProfileViewModel, payload["model_profile"]
        ),
        config_revision=str(payload["config_revision"]),
    )


@router.delete("/model-profiles/{profile_id}", status_code=204)
def delete_model_profile(
    profile_id: str,
    manager: SessionManagerDep,
    expected_revision: ConfigRevisionHeader,
) -> Response:
    try:
        manager.delete_model_profile(
            profile_id,
            expected_revision=expected_revision,
        )
    except Exception as exc:
        raise config_http_error(exc) from exc
    return Response(status_code=204)


@router.put(
    "/active-model-profile",
    response_model=ActiveProfileResponse,
)
def set_active_model_profile(
    request: ActiveProfileRequest,
    manager: SessionManagerDep,
    expected_revision: ConfigRevisionHeader,
) -> ActiveProfileResponse:
    try:
        payload = manager.set_active_model_profile(
            request.profile_id,
            expected_revision=expected_revision,
        )
    except Exception as exc:
        raise config_http_error(exc) from exc
    return ActiveProfileResponse(
        active_profile_id=payload["active_profile_id"],
        config_revision=str(payload["config_revision"]),
    )


@router.get("/commands", response_model=CommandListResponse)
def list_commands(manager: SessionManagerDep) -> CommandListResponse:
    payload = manager.config_bootstrap()
    return CommandListResponse(
        commands=[
            model_from_payload(CommandViewModel, item) for item in payload["commands"]
        ],
        config_revision=str(payload["config_revision"]),
    )
