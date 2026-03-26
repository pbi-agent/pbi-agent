from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

from pbi_agent import __version__
from pbi_agent.tools.output import bound_output
from pbi_agent.tools.types import ToolContext, ToolSpec

MARKDOWN_NEW_URL = "https://markdown.new/"
MAX_MARKDOWN_CHARS = 50_000
_REQUEST_TIMEOUT_SECS = 120.0

SPEC = ToolSpec(
    name="read_web_url",
    description="Fetch a public web page and return it as Markdown.",
    parameters_schema={
        "type": "object",
        "properties": {
            "url": {
                "type": "string",
                "description": "Absolute http/https URL to convert to Markdown.",
            }
        },
        "required": ["url"],
        "additionalProperties": False,
    },
)


def handle(arguments: dict[str, Any], context: ToolContext) -> dict[str, Any]:
    del context
    url_value = arguments.get("url", "")
    if not isinstance(url_value, str) or not url_value.strip():
        return {"error": "'url' must be a non-empty string."}

    normalized_url = url_value.strip()
    validation_error = _validate_url(normalized_url)
    if validation_error is not None:
        return {"error": validation_error}

    request_data = json.dumps({"url": normalized_url}).encode("utf-8")
    headers = {
        "Content-Type": "application/json",
        "Accept": "text/markdown",
        "User-Agent": f"pbi-agent/{__version__}",
    }

    try:
        req = urllib.request.Request(
            MARKDOWN_NEW_URL,
            data=request_data,
            headers=headers,
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=_REQUEST_TIMEOUT_SECS) as response:
            raw_markdown = response.read().decode("utf-8", errors="replace")

        markdown, truncated = bound_output(raw_markdown, limit=MAX_MARKDOWN_CHARS)
        result: dict[str, Any] = {
            "url": normalized_url,
            "markdown": markdown,
        }
        if truncated:
            result["markdown_truncated"] = True
        return result
    except urllib.error.HTTPError as exc:
        return {"error": _format_http_error(exc)}
    except urllib.error.URLError as exc:
        return {"error": bound_output(f"failed to fetch URL: {exc.reason}")[0]}
    except Exception as exc:
        return {"error": bound_output(str(exc))[0]}


def _validate_url(url: str) -> str | None:
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme not in {"http", "https"}:
        return "'url' must be an absolute http or https URL."
    if not parsed.netloc:
        return "'url' must be an absolute http or https URL."
    return None


def _format_http_error(exc: urllib.error.HTTPError) -> str:
    detail = ""
    try:
        body = exc.read().decode("utf-8", errors="replace").strip()
    except Exception:
        body = ""
    if body:
        detail = f": {body}"
    return bound_output(f"HTTP {exc.code} {exc.reason}{detail}")[0]
