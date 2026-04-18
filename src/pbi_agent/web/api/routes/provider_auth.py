from __future__ import annotations

import uuid

from fastapi import APIRouter

from pbi_agent.web.api.deps import SessionManagerDep, model_from_payload
from pbi_agent.web.api.errors import config_http_error
from pbi_agent.web.api.schemas.config import (
    ProviderAuthFlowResponse,
    ProviderAuthFlowStartRequest,
    ProviderAuthImportRequest,
    ProviderAuthLogoutResponse,
    ProviderAuthResponse,
)

router = APIRouter(prefix="/api/provider-auth", tags=["provider-auth"])


@router.get("/{provider_id}", response_model=ProviderAuthResponse)
def get_provider_auth_status(
    provider_id: str,
    manager: SessionManagerDep,
) -> ProviderAuthResponse:
    try:
        payload = manager.get_provider_auth_status(provider_id)
    except Exception as exc:
        raise config_http_error(exc) from exc
    return model_from_payload(ProviderAuthResponse, payload)


@router.post("/{provider_id}/import", response_model=ProviderAuthResponse)
def import_provider_auth(
    provider_id: str,
    request: ProviderAuthImportRequest,
    manager: SessionManagerDep,
) -> ProviderAuthResponse:
    try:
        payload = manager.import_provider_auth(
            provider_id,
            access_token=request.access_token,
            refresh_token=request.refresh_token,
            account_id=request.account_id,
            email=request.email,
            plan_type=request.plan_type,
            expires_at=request.expires_at,
            id_token=request.id_token,
        )
    except Exception as exc:
        raise config_http_error(exc) from exc
    return model_from_payload(ProviderAuthResponse, payload)


@router.post("/{provider_id}/refresh", response_model=ProviderAuthResponse)
def refresh_provider_auth(
    provider_id: str,
    manager: SessionManagerDep,
) -> ProviderAuthResponse:
    try:
        payload = manager.refresh_provider_auth(provider_id)
    except Exception as exc:
        raise config_http_error(exc) from exc
    return model_from_payload(ProviderAuthResponse, payload)


@router.delete("/{provider_id}", response_model=ProviderAuthLogoutResponse)
def logout_provider_auth(
    provider_id: str,
    manager: SessionManagerDep,
) -> ProviderAuthLogoutResponse:
    try:
        payload = manager.logout_provider_auth(provider_id)
    except Exception as exc:
        raise config_http_error(exc) from exc
    return model_from_payload(ProviderAuthLogoutResponse, payload)


@router.post("/{provider_id}/flows", response_model=ProviderAuthFlowResponse)
def start_provider_auth_flow(
    provider_id: str,
    request: ProviderAuthFlowStartRequest,
    manager: SessionManagerDep,
) -> ProviderAuthFlowResponse:
    flow_id = uuid.uuid4().hex
    try:
        payload = manager.start_provider_auth_flow(
            provider_id,
            flow_id=flow_id,
            method=request.method,
        )
    except Exception as exc:
        raise config_http_error(exc) from exc
    return model_from_payload(ProviderAuthFlowResponse, payload)


@router.get("/{provider_id}/flows/{flow_id}", response_model=ProviderAuthFlowResponse)
def get_provider_auth_flow(
    provider_id: str,
    flow_id: str,
    manager: SessionManagerDep,
) -> ProviderAuthFlowResponse:
    try:
        payload = manager.get_provider_auth_flow(provider_id, flow_id)
    except Exception as exc:
        raise config_http_error(exc) from exc
    return model_from_payload(ProviderAuthFlowResponse, payload)


@router.post(
    "/{provider_id}/flows/{flow_id}/poll",
    response_model=ProviderAuthFlowResponse,
)
def poll_provider_auth_flow(
    provider_id: str,
    flow_id: str,
    manager: SessionManagerDep,
) -> ProviderAuthFlowResponse:
    try:
        payload = manager.poll_provider_auth_flow(provider_id, flow_id)
    except Exception as exc:
        raise config_http_error(exc) from exc
    return model_from_payload(ProviderAuthFlowResponse, payload)
