from __future__ import annotations

from pydantic import BaseModel


class HookViewModel(BaseModel):
    key: str
    event: str
    matcher: str | None
    command: str | None
    source: str
    source_path: str
    status_message: str | None
    timeout: int
    trust_status: str
    current_hash: str
    enabled: bool
    managed: bool
    runnable: bool
    diagnostics: list[str]


class HookListResponse(BaseModel):
    hooks: list[HookViewModel]
    diagnostics: list[str]
    review_required_count: int
    trust_bypass_active: bool = False


class HookActionRequest(BaseModel):
    key: str


class HookActionResponse(BaseModel):
    hooks: list[HookViewModel]
    diagnostics: list[str]
    review_required_count: int
    trust_bypass_active: bool = False
