from __future__ import annotations

from fastapi import APIRouter

from pbi_agent.config import Settings
from pbi_agent.hooks.discovery import discover_hooks
from pbi_agent.hooks.schemas import HookDefinition, HookTrustStatus
from pbi_agent.hooks.trust import HookTrustStore
from pbi_agent.web.api.deps import SessionManagerDep
from pbi_agent.web.api.errors import bad_request, not_found
from pbi_agent.web.api.schemas.hooks import (
    HookActionRequest,
    HookActionResponse,
    HookListResponse,
    HookViewModel,
)

router = APIRouter(prefix="/api/hooks", tags=["hooks"])


@router.get("", response_model=HookListResponse)
def list_hooks(manager: SessionManagerDep) -> HookListResponse:
    return _payload(manager)


@router.post("/trust", response_model=HookActionResponse)
def trust_hook(
    request: HookActionRequest,
    manager: SessionManagerDep,
) -> HookActionResponse:
    hook = _find_hook(manager, request.key)
    if hook is None:
        raise not_found("Hook not found.")
    if not hook.managed:
        HookTrustStore().trust(hook.key, hook.current_hash)
    return _action_payload(manager)


@router.post("/enable", response_model=HookActionResponse)
def enable_hook(
    request: HookActionRequest,
    manager: SessionManagerDep,
) -> HookActionResponse:
    hook = _find_hook(manager, request.key)
    if hook is None:
        raise not_found("Hook not found.")
    if hook.managed:
        raise bad_request("Managed hooks cannot be enabled manually.")
    HookTrustStore().set_enabled(hook.key, True)
    return _action_payload(manager)


@router.post("/disable", response_model=HookActionResponse)
def disable_hook(
    request: HookActionRequest,
    manager: SessionManagerDep,
) -> HookActionResponse:
    hook = _find_hook(manager, request.key)
    if hook is None:
        raise not_found("Hook not found.")
    if hook.managed:
        raise bad_request("Managed hooks cannot be disabled.")
    HookTrustStore().set_enabled(hook.key, False)
    return _action_payload(manager)


def _payload(manager: SessionManagerDep) -> HookListResponse:
    discovery = _discover(manager)
    hooks = [_model(hook) for hook in discovery.hooks]
    review_required = sum(
        1
        for hook in discovery.hooks
        if hook.trust_status in {HookTrustStatus.UNTRUSTED, HookTrustStatus.MODIFIED}
    )
    return HookListResponse(
        hooks=hooks,
        diagnostics=list(discovery.diagnostics),
        review_required_count=review_required,
        trust_bypass_active=bool(
            getattr(_manager_settings(manager), "dangerously_bypass_hook_trust", False)
        ),
    )


def _action_payload(manager: SessionManagerDep) -> HookActionResponse:
    payload = _payload(manager)
    return HookActionResponse.model_validate(payload.model_dump())


def _discover(manager: SessionManagerDep):
    return discover_hooks(
        getattr(manager, "_workspace_root"), _manager_settings(manager)
    )


def _manager_settings(manager: SessionManagerDep) -> Settings:
    settings = getattr(manager, "_settings")
    if isinstance(settings, Settings):
        return settings
    return settings.settings


def _find_hook(manager: SessionManagerDep, key: str) -> HookDefinition | None:
    for hook in _discover(manager).hooks:
        if hook.key == key:
            return hook
    return None


def _model(hook: HookDefinition) -> HookViewModel:
    return HookViewModel(
        key=hook.key,
        event=hook.event.value,
        matcher=hook.matcher,
        command=hook.handler.command,
        source=hook.source,
        source_path=str(hook.source_path),
        status_message=hook.handler.status_message,
        timeout=hook.handler.normalized_timeout,
        trust_status=hook.trust_status.value,
        current_hash=hook.current_hash,
        enabled=hook.enabled,
        managed=hook.managed,
        runnable=hook.runnable,
        diagnostics=list(hook.diagnostics),
    )
