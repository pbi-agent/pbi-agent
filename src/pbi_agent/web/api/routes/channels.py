from __future__ import annotations

from fastapi import APIRouter

from pbi_agent.web.api.deps import SessionManagerDep, model_from_payload
from pbi_agent.web.api.schemas.channels import (
    ChannelListResponse,
    TelegramChannelUpdateRequest,
)

router = APIRouter(prefix="/api/channels", tags=["channels"])


@router.get("", response_model=ChannelListResponse)
def list_channels(manager: SessionManagerDep) -> ChannelListResponse:
    return model_from_payload(ChannelListResponse, manager.get_channels_payload())


@router.put("/telegram", response_model=ChannelListResponse)
def update_telegram_channel(
    request: TelegramChannelUpdateRequest,
    manager: SessionManagerDep,
) -> ChannelListResponse:
    payload = manager.update_telegram_channel(request.model_dump())
    return model_from_payload(ChannelListResponse, payload)


@router.post("/telegram/restart", response_model=ChannelListResponse)
def restart_telegram_channel(manager: SessionManagerDep) -> ChannelListResponse:
    return model_from_payload(
        ChannelListResponse,
        manager.restart_telegram_channel(),
    )
