from __future__ import annotations

from .routes.board import router as board_router
from .routes.channels import router as channels_router
from .routes.config import router as config_router
from .routes.events import router as events_router
from .routes.hooks import router as hooks_router
from .routes.provider_auth import router as provider_auth_router
from .routes.stt import router as stt_router
from .routes.system import router as system_router
from .routes.tasks import router as tasks_router

__all__ = [
    "board_router",
    "channels_router",
    "config_router",
    "events_router",
    "hooks_router",
    "provider_auth_router",
    "stt_router",
    "system_router",
    "tasks_router",
]
