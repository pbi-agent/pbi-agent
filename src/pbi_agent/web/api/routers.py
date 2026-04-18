from __future__ import annotations

from .routes.board import router as board_router
from .routes.live_sessions import router as live_sessions_router
from .routes.config import router as config_router
from .routes.events import router as events_router
from .routes.provider_auth import router as provider_auth_router
from .routes.system import router as system_router
from .routes.tasks import router as tasks_router

__all__ = [
    "board_router",
    "live_sessions_router",
    "config_router",
    "events_router",
    "provider_auth_router",
    "system_router",
    "tasks_router",
]
