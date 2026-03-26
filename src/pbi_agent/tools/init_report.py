"""Tool: init_report – scaffold a Power BI report project in the working directory.

Exposes the ``init_report`` logic from :mod:`pbi_agent.init_command` as a
function tool so the model can bootstrap a new PBIP project when needed.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from pbi_agent.init_command import init_report
from pbi_agent.tools.types import ToolContext, ToolSpec

SPEC = ToolSpec(
    name="init_report",
    description=(
        "Create a new Power BI PBIP report from the bundled template. "
        "Use when no existing PBIP project is present."
    ),
    parameters_schema={
        "type": "object",
        "properties": {
            "dest": {
                "type": "string",
                "description": (
                    "Target directory path.  Defaults to the current working "
                    'directory (".") if omitted.'
                ),
            },
            "force": {
                "type": "boolean",
                "description": (
                    "If true, overwrite existing template files.  Defaults to false."
                ),
            },
        },
        "required": [],
        "additionalProperties": False,
    },
    is_destructive=False,
)


def handle(arguments: dict[str, Any], context: ToolContext) -> dict[str, Any]:
    dest = Path(arguments.get("dest", ".")).resolve()
    force = bool(arguments.get("force", False))

    try:
        init_report(dest, force=force)
    except FileExistsError as exc:
        return {"success": False, "error": str(exc)}

    return {"success": True, "path": str(dest)}
