from __future__ import annotations

from pathlib import Path
from typing import Any

from pbi_agent.tools.output import bound_output
from pbi_agent.tools.types import ToolContext, ToolSpec
from pbi_agent.tools.workspace_access import DEFAULT_MAX_LINES
from pbi_agent.tools.workspace_access import normalize_positive_int
from pbi_agent.tools.workspace_access import read_text_file
from pbi_agent.tools.workspace_access import relative_workspace_path
from pbi_agent.tools.workspace_access import resolve_safe_path

MAX_READ_FILE_OUTPUT_CHARS = 12_000

SPEC = ToolSpec(
    name="read_file",
    description=(
        "Read a text file from the workspace with line-range support. "
        "Use this for safe cross-platform file inspection instead of shell commands."
    ),
    parameters_schema={
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": (
                    "File path relative to the workspace root "
                    "(or absolute within workspace)."
                ),
            },
            "start_line": {
                "type": "integer",
                "description": "1-based starting line number. Defaults to 1.",
            },
            "max_lines": {
                "type": "integer",
                "description": "Maximum number of lines to return. Defaults to 200.",
            },
            "encoding": {
                "type": "string",
                "description": "Text encoding to use. Defaults to 'auto'.",
                "default": "auto",
            },
        },
        "required": ["path"],
        "additionalProperties": False,
    },
)


def handle(arguments: dict[str, Any], context: ToolContext) -> dict[str, Any]:
    del context
    path_value = arguments.get("path", "")
    if not isinstance(path_value, str) or not path_value.strip():
        return {"error": "'path' must be a non-empty string."}

    root = Path.cwd().resolve()
    start_line = normalize_positive_int(arguments.get("start_line"), default=1)
    max_lines = normalize_positive_int(arguments.get("max_lines"), default=DEFAULT_MAX_LINES)
    encoding = arguments.get("encoding", "auto")

    try:
        target_path = resolve_safe_path(root, path_value)
        if not target_path.exists():
            return {"error": f"path not found: {target_path}"}
        if not target_path.is_file():
            return {"error": f"path is not a file: {target_path}"}

        content, detected_encoding = read_text_file(target_path, encoding=str(encoding))
        lines = content.splitlines(keepends=True)
        line_count = len(lines)
        start_index = min(start_line - 1, line_count)
        end_index = min(start_index + max_lines, line_count)
        selected = "".join(lines[start_index:end_index])
        bounded_content, content_truncated = bound_output(
            selected, limit=MAX_READ_FILE_OUTPUT_CHARS
        )

        result: dict[str, Any] = {
            "path": relative_workspace_path(root, target_path),
            "encoding": detected_encoding,
            "start_line": start_index + 1 if line_count else 1,
            "end_line": end_index,
            "total_lines": line_count,
            "content": bounded_content,
        }
        if start_index > 0 or end_index < line_count:
            result["windowed"] = True
        if content_truncated:
            result["content_truncated"] = True
        return result
    except Exception as exc:
        return {"error": bound_output(str(exc))[0]}
