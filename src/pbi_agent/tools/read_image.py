from __future__ import annotations

from pathlib import Path
from typing import Any

from pbi_agent.media import load_workspace_image
from pbi_agent.tools.types import ToolContext, ToolOutput, ToolSpec

SPEC = ToolSpec(
    name="read_image",
    description="Read a workspace image file and attach it to the model context.",
    parameters_schema={
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": (
                    "Image path relative to the workspace root "
                    "(or absolute within workspace)."
                ),
            }
        },
        "required": ["path"],
        "additionalProperties": False,
    },
)


def handle(
    arguments: dict[str, Any], context: ToolContext
) -> dict[str, Any] | ToolOutput:
    del context
    path_value = arguments.get("path", "")
    if not isinstance(path_value, str) or not path_value.strip():
        return {"error": "'path' must be a non-empty string."}

    root = Path.cwd().resolve()
    try:
        image = load_workspace_image(root, path_value)
    except Exception as exc:
        return {"error": str(exc)}

    summary = {
        "path": image.path,
        "mime_type": image.mime_type,
        "byte_count": image.byte_count,
    }
    return ToolOutput(result=summary, attachments=[image])
