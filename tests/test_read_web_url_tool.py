from __future__ import annotations

import json
import urllib.error
import urllib.request

from pbi_agent.tools import read_web_url as read_web_url_tool
from pbi_agent.tools import web_search as web_search_tool
from pbi_agent.tools.types import ToolContext


class _FakeResponse:
    def __init__(self, body: str, *, headers: dict[str, str] | None = None) -> None:
        self._body = body.encode("utf-8")
        self.headers = headers or {}

    def read(self) -> bytes:
        return self._body

    def __enter__(self) -> "_FakeResponse":
        return self

    def __exit__(self, *_: object) -> None:
        return None


def test_read_web_url_returns_firecrawl_markdown(monkeypatch) -> None:
    seen: dict[str, object] = {}

    def fake_urlopen(
        request: urllib.request.Request,
        timeout: float,
    ) -> _FakeResponse:
        seen["url"] = request.full_url
        seen["method"] = request.get_method()
        seen["accept"] = request.get_header("Accept")
        seen["content_type"] = request.headers.get("Content-type")
        seen["body"] = json.loads(request.data.decode("utf-8"))
        seen["timeout"] = timeout
        return _FakeResponse(
            json.dumps({"success": True, "data": {"markdown": "# Example\n\nBody"}})
        )

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)

    result = read_web_url_tool.handle(
        {"url": "https://example.com/docs"},
        ToolContext(),
    )

    assert result == {
        "markdown": "# Example\n\nBody",
    }
    assert seen == {
        "url": read_web_url_tool.FIRECRAWL_SCRAPE_URL,
        "method": "POST",
        "accept": "application/json",
        "content_type": "application/json",
        "body": {"url": "https://example.com/docs"},
        "timeout": read_web_url_tool._REQUEST_TIMEOUT_SECS,
    }


def test_read_web_url_bounds_large_markdown(monkeypatch) -> None:
    long_markdown = (
        f"# Start\n\nprefix-{'x' * (read_web_url_tool.MAX_MARKDOWN_CHARS + 200)}-suffix"
    )

    monkeypatch.setattr(
        urllib.request,
        "urlopen",
        lambda request, timeout: _FakeResponse(
            json.dumps({"success": True, "data": {"markdown": long_markdown}})
        ),
    )

    result = read_web_url_tool.handle({"url": "https://example.com"}, ToolContext())

    assert result["markdown_truncated"] is True
    assert len(result["markdown"]) <= read_web_url_tool.MAX_MARKDOWN_CHARS
    assert result["markdown"].startswith("# Start\n\nprefix-")
    assert result["markdown"].endswith("-suffix")
    assert "chars omitted" in result["markdown"]


def test_read_web_url_rejects_invalid_urls_before_network(monkeypatch) -> None:
    called = False

    def fake_urlopen(request: urllib.request.Request, timeout: float) -> _FakeResponse:
        del request, timeout
        nonlocal called
        called = True
        return _FakeResponse("unused")

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)

    result = read_web_url_tool.handle({"url": "ftp://example.com"}, ToolContext())

    assert result == {"error": "'url' must be an absolute http or https URL."}
    assert called is False


def test_read_web_url_falls_back_to_markdown_new_for_firecrawl_rate_limit(
    monkeypatch,
) -> None:
    seen_urls: list[str] = []

    def fake_urlopen(
        request: urllib.request.Request,
        timeout: float,
    ) -> _FakeResponse:
        del timeout
        seen_urls.append(request.full_url)
        if request.full_url == read_web_url_tool.FIRECRAWL_SCRAPE_URL:
            raise urllib.error.HTTPError(
                read_web_url_tool.FIRECRAWL_SCRAPE_URL,
                429,
                "Too Many Requests",
                hdrs=None,
                fp=None,
            )
        assert request.full_url == read_web_url_tool.MARKDOWN_NEW_URL
        assert request.get_header("Accept") == "text/markdown"
        return _FakeResponse("# Fallback\n\nBody")

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)

    result = read_web_url_tool.handle({"url": "https://example.com"}, ToolContext())

    assert result == {
        "markdown": "# Fallback\n\nBody",
    }
    assert seen_urls == [
        read_web_url_tool.FIRECRAWL_SCRAPE_URL,
        read_web_url_tool.MARKDOWN_NEW_URL,
    ]


def test_read_web_url_falls_back_to_markdown_new_for_empty_firecrawl_markdown(
    monkeypatch,
) -> None:
    calls = 0

    def fake_urlopen(
        request: urllib.request.Request,
        timeout: float,
    ) -> _FakeResponse:
        del timeout
        nonlocal calls
        calls += 1
        if request.full_url == read_web_url_tool.FIRECRAWL_SCRAPE_URL:
            return _FakeResponse(json.dumps({"success": True, "data": {}}))
        return _FakeResponse("# Fallback")

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)

    result = read_web_url_tool.handle({"url": "https://example.com"}, ToolContext())

    assert result == {
        "markdown": "# Fallback",
    }
    assert calls == 2


def test_read_web_url_reports_network_failures(monkeypatch) -> None:
    def fake_urlopen(
        request: urllib.request.Request,
        timeout: float,
    ) -> _FakeResponse:
        del request, timeout
        raise urllib.error.URLError("temporary failure")

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)

    result = read_web_url_tool.handle({"url": "https://example.com"}, ToolContext())

    assert result == {
        "error": (
            "Firecrawl scrape failed: failed to fetch URL: temporary failure; "
            "markdown.new fallback failed: failed to fetch URL: temporary failure"
        )
    }


def test_web_search_returns_firecrawl_results(monkeypatch) -> None:
    seen: dict[str, object] = {}

    def fake_urlopen(
        request: urllib.request.Request,
        timeout: float,
    ) -> _FakeResponse:
        seen["url"] = request.full_url
        seen["method"] = request.get_method()
        seen["accept"] = request.get_header("Accept")
        seen["content_type"] = request.headers.get("Content-type")
        seen["body"] = json.loads(request.data.decode("utf-8"))
        seen["timeout"] = timeout
        return _FakeResponse(
            json.dumps(
                {
                    "success": True,
                    "data": {
                        "web": [
                            {
                                "url": "https://example.com/a",
                                "title": "Alpha",
                                "description": "First result",
                                "position": 1,
                            },
                            {
                                "url": "https://example.com/b",
                                "title": "Beta",
                                "description": "Second result",
                                "position": 2,
                            },
                        ]
                    },
                }
            )
        )

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)

    result = web_search_tool.handle(
        {"query": "btc live price", "limit": 2},
        ToolContext(),
    )

    assert result == {
        "query": "btc live price",
        "results": [
            {
                "url": "https://example.com/a",
                "title": "Alpha",
                "description": "First result",
                "position": 1,
            },
            {
                "url": "https://example.com/b",
                "title": "Beta",
                "description": "Second result",
                "position": 2,
            },
        ],
        "sources": [
            {
                "title": "Alpha",
                "url": "https://example.com/a",
                "snippet": "First result",
            },
            {
                "title": "Beta",
                "url": "https://example.com/b",
                "snippet": "Second result",
            },
        ],
    }
    assert seen == {
        "url": web_search_tool.FIRECRAWL_SEARCH_URL,
        "method": "POST",
        "accept": "application/json",
        "content_type": "application/json",
        "body": {"query": "btc live price", "limit": 2},
        "timeout": web_search_tool._REQUEST_TIMEOUT_SECS,
    }
