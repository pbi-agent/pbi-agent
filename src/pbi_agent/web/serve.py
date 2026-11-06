from __future__ import annotations

from pbi_agent.web.app_factory import create_app
from pbi_agent.web.server_runtime import (
    PBIWebServer,
    main,
)
from pbi_agent.web.server_runtime import (
    create_default_fastapi_app as _create_default_fastapi_app,
)
from pbi_agent.web.server_runtime import (
    default_settings_namespace as _default_settings_namespace,
)
from pbi_agent.web.server_runtime import (
    parse_args as _parse_args,
)

__all__ = [
    "PBIWebServer",
    "_create_default_fastapi_app",
    "_default_settings_namespace",
    "_parse_args",
    "app",
    "create_app",
    "main",
]

app = _create_default_fastapi_app()
