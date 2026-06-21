from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Any

from pbi_agent import __version__
from pbi_agent.tools.output import bound_output
from pbi_agent.tools.types import ToolContext, ToolSpec

FIRECRAWL_SEARCH_URL = "https://api.firecrawl.dev/v2/search"
DEFAULT_SEARCH_LIMIT = 5
MAX_SEARCH_LIMIT = 10
MAX_TITLE_CHARS = 200
MAX_DESCRIPTION_CHARS = 600
_REQUEST_TIMEOUT_SECS = 120.0

SPEC = ToolSpec(
    name="web_search",
    description="Search web and return source results.",
    prompt_usage="Use `web_search` to search web with Firecrawl.",
    parameters_schema={
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "Search query.",
            },
            "limit": {
                "type": "integer",
                "description": (
                    "Maximum number of search results to return. Defaults to 5; "
                    "values above 10 are capped."
                ),
                "minimum": 1,
                "maximum": MAX_SEARCH_LIMIT,
            },
        },
        "required": ["query"],
        "additionalProperties": False,
    },
)


def handle(arguments: dict[str, Any], context: ToolContext) -> dict[str, Any]:
    del context
    query_value = arguments.get("query", "")
    if not isinstance(query_value, str) or not query_value.strip():
        return {"error": "'query' must be a non-empty string."}

    query = query_value.strip()
    limit = _normalize_limit(arguments.get("limit", DEFAULT_SEARCH_LIMIT))
    payload = {"query": query, "limit": limit}
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json",
        "User-Agent": f"pbi-agent/{__version__}",
    }

    try:
        req = urllib.request.Request(
            FIRECRAWL_SEARCH_URL,
            data=json.dumps(payload).encode("utf-8"),
            headers=headers,
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=_REQUEST_TIMEOUT_SECS) as response:
            raw_body = response.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as exc:
        return {"error": _format_http_error(exc)}
    except urllib.error.URLError as exc:
        return {"error": bound_output(f"failed to search web: {exc.reason}")[0]}
    except Exception as exc:
        return {"error": bound_output(str(exc))[0]}

    try:
        parsed = json.loads(raw_body)
    except json.JSONDecodeError:
        return {"error": "Firecrawl search returned invalid JSON."}

    if not isinstance(parsed, dict):
        return {"error": "Firecrawl search returned an unexpected response."}

    results = _extract_results(parsed, limit=limit)
    if results:
        return {
            "query": query,
            "results": results,
            "sources": [
                {
                    "title": result.get("title", ""),
                    "url": result.get("url", ""),
                    "snippet": result.get("description", ""),
                }
                for result in results
            ],
        }

    response_error = _firecrawl_response_error(parsed)
    if response_error:
        return {"error": response_error}
    return {"query": query, "results": []}


def _normalize_limit(value: Any) -> int:
    try:
        limit = int(value)
    except (TypeError, ValueError):
        limit = DEFAULT_SEARCH_LIMIT
    return min(max(limit, 1), MAX_SEARCH_LIMIT)


def _extract_results(parsed: dict[str, Any], *, limit: int) -> list[dict[str, Any]]:
    data = parsed.get("data")
    if not isinstance(data, dict):
        return []
    web_results = data.get("web")
    if not isinstance(web_results, list):
        return []

    results: list[dict[str, Any]] = []
    for index, item in enumerate(web_results[:limit], start=1):
        if not isinstance(item, dict):
            continue
        url = item.get("url")
        if not isinstance(url, str) or not url.strip():
            continue
        title = item.get("title")
        description = item.get("description")
        result: dict[str, Any] = {
            "url": url.strip(),
            "title": _bounded_text(title, MAX_TITLE_CHARS),
            "description": _bounded_text(description, MAX_DESCRIPTION_CHARS),
        }
        position = item.get("position")
        if isinstance(position, int):
            result["position"] = position
        else:
            result["position"] = index
        results.append(result)
    return results


def _bounded_text(value: Any, limit: int) -> str:
    if not isinstance(value, str):
        return ""
    return bound_output(value.strip(), limit=limit)[0]


def _firecrawl_response_error(parsed: dict[str, Any]) -> str:
    for key in ("error", "message"):
        value = parsed.get(key)
        if isinstance(value, str) and value.strip():
            return bound_output(value.strip())[0]
    success = parsed.get("success")
    if success is False:
        return "Firecrawl search was not successful."
    return ""


def _format_http_error(exc: urllib.error.HTTPError) -> str:
    detail = ""
    try:
        body = exc.read().decode("utf-8", errors="replace").strip()
    except Exception:
        body = ""
    if body:
        detail = f": {body}"
    return bound_output(f"HTTP {exc.code} {exc.reason}{detail}")[0]
