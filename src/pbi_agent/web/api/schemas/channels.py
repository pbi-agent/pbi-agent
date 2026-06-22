from __future__ import annotations

from pydantic import BaseModel, Field


class ChannelRuntimeStatusModel(BaseModel):
    state: str
    error: str | None = None


class TelegramChannelConfigView(BaseModel):
    enabled: bool = False
    token_source: str = "env"
    token_env_var: str = "PBI_AGENT_TELEGRAM_BOT_TOKEN"
    has_token_secret: bool = False
    allowed_users: list[str] = Field(default_factory=list)
    allowed_chats: list[str] = Field(default_factory=list)
    last_update_id: int | None = None
    status: ChannelRuntimeStatusModel


class ChannelListResponse(BaseModel):
    telegram: TelegramChannelConfigView


class TelegramChannelUpdateRequest(BaseModel):
    enabled: bool = False
    token_source: str = "env"
    token_env_var: str = "PBI_AGENT_TELEGRAM_BOT_TOKEN"
    token_secret: str | None = None
    allowed_users: list[str] = Field(default_factory=list)
    allowed_chats: list[str] = Field(default_factory=list)
