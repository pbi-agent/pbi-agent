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
FIRECRAWL_SCRAPE_URL = "https://api.firecrawl.dev/v2/scrape"
MAX_MARKDOWN_CHARS = 50_000
_REQUEST_TIMEOUT_SECS = 120.0

SPEC = ToolSpec(
    name="read_web_url",
    description="Fetch a public web page and return it as Markdown.",
    prompt_usage="Use `read_web_url` to fetch a public web page as Markdown.",
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

    firecrawl_markdown, firecrawl_error = _fetch_firecrawl_markdown(normalized_url)
    if firecrawl_markdown is not None:
        return _markdown_result(firecrawl_markdown)

    fallback_markdown, fallback_error = _fetch_markdown_new(normalized_url)
    if fallback_markdown is not None:
        return _markdown_result(fallback_markdown)

    firecrawl_detail = firecrawl_error or "Firecrawl scrape returned no Markdown."
    fallback_detail = fallback_error or "markdown.new fallback returned no Markdown."
    error = (
        f"Firecrawl scrape failed: {firecrawl_detail}; "
        f"markdown.new fallback failed: {fallback_detail}"
    )
    return {"error": bound_output(error)[0]}


def _markdown_result(raw_markdown: str) -> dict[str, Any]:
    markdown, truncated = bound_output(raw_markdown, limit=MAX_MARKDOWN_CHARS)
    result: dict[str, Any] = {
        "markdown": markdown,
    }
    if truncated:
        result["markdown_truncated"] = True
    return result


def _fetch_firecrawl_markdown(url: str) -> tuple[str | None, str | None]:
    request_data = json.dumps({"url": url}).encode("utf-8")
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json",
        "User-Agent": f"pbi-agent/{__version__}",
    }

    try:
        req = urllib.request.Request(
            FIRECRAWL_SCRAPE_URL,
            data=request_data,
            headers=headers,
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=_REQUEST_TIMEOUT_SECS) as response:
            raw_body = response.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as exc:
        return None, _format_http_error(exc)
    except urllib.error.URLError as exc:
        return None, bound_output(f"failed to fetch URL: {exc.reason}")[0]
    except Exception as exc:
        return None, bound_output(str(exc))[0]

    try:
        parsed = json.loads(raw_body)
    except json.JSONDecodeError:
        return None, bound_output("Firecrawl scrape returned invalid JSON.")[0]

    if not isinstance(parsed, dict):
        return None, "Firecrawl scrape returned an unexpected response."

    data = parsed.get("data")
    if isinstance(data, dict):
        markdown = data.get("markdown")
        if isinstance(markdown, str) and markdown.strip():
            return markdown, None

    response_error = _firecrawl_response_error(parsed)
    if response_error:
        return None, response_error
    return None, "Firecrawl scrape returned no Markdown."


def _fetch_markdown_new(url: str) -> tuple[str | None, str | None]:
    request_data = json.dumps({"url": url}).encode("utf-8")
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

        if raw_markdown.strip():
            return raw_markdown, None
        return None, "markdown.new returned no Markdown."
    except urllib.error.HTTPError as exc:
        return None, _format_http_error(exc)
    except urllib.error.URLError as exc:
        return None, bound_output(f"failed to fetch URL: {exc.reason}")[0]
    except Exception as exc:
        return None, bound_output(str(exc))[0]


def _firecrawl_response_error(parsed: dict[str, Any]) -> str:
    for key in ("error", "message"):
        value = parsed.get(key)
        if isinstance(value, str) and value.strip():
            return bound_output(value.strip())[0]
    success = parsed.get("success")
    if success is False:
        return "Firecrawl scrape was not successful."
    return ""


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
