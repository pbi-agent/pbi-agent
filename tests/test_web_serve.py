from __future__ import annotations

import asyncio
from io import StringIO
from unittest.mock import Mock

from rich.console import Console

from pbi_agent.branding import PBI_AGENT_NAME, PBI_AGENT_TAGLINE
from pbi_agent.web.serve import _FaviconServer


def test_favicon_server_startup_uses_pbi_agent_banner() -> None:
    server = _FaviconServer(command="uv run pbi-agent web")
    output = StringIO()
    server.console = Console(file=output, width=80, highlight=False)

    asyncio.run(server.on_startup(Mock()))

    rendered = output.getvalue()
    assert PBI_AGENT_NAME in rendered
    assert PBI_AGENT_TAGLINE in rendered
    assert "textual-serve" not in rendered
    assert server.public_url in rendered
