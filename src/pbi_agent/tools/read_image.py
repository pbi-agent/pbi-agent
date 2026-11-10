from __future__ import annotations

from pathlib import Path
from typing import Any

from pbi_agent.media import load_workspace_image
from pbi_agent.tools.output import bound_output
from pbi_agent.tools.types import ToolContext, ToolOutput, ToolSpec

SPEC = ToolSpec(
    name="read_image",
    description=(
        "Attach an image file (png/jpg/jpeg/webp/heic/heif) to your "
        "context so you can see it. Use `shell` for text files."
    ),
    prompt_usage=(
        "Use `read_image` to view an image file, e.g. "
        '`{"path":"docs/screenshot.png"}`; read and search text with `shell`.'
    ),
    parameters_schema={
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "Image file path: workspace-relative or absolute.",
            },
        },
        "required": ["path"],
        "additionalProperties": False,
    },
)


def handle(arguments: dict[str, Any], context: ToolContext) -> ToolOutput:
    workspace_root = (
        context.workspace_root if context.workspace_root is not None else Path.cwd()
    ).resolve()
    try:
        image = load_workspace_image(workspace_root, arguments.get("path"))
    except Exception as exc:
        return ToolOutput(result={"error": bound_output(str(exc))[0]}, is_error=True)
    summary = {
        "path": image.path,
        "mime_type": image.mime_type,
        "byte_count": image.byte_count,
    }
    return ToolOutput(result=summary, attachments=[image])
