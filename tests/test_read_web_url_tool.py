from __future__ import annotations

import urllib.error
import urllib.request

from pbi_agent.tools import read_web_url as read_web_url_tool
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


def test_read_web_url_returns_markdown(monkeypatch) -> None:
    seen: dict[str, object] = {}

    def fake_urlopen(
        request: urllib.request.Request,
        timeout: float,
    ) -> _FakeResponse:
        seen["url"] = request.full_url
        seen["method"] = request.get_method()
        seen["accept"] = request.get_header("Accept")
        seen["content_type"] = request.headers.get("Content-type")
        seen["body"] = request.data.decode("utf-8")
        seen["timeout"] = timeout
        return _FakeResponse("# Example\n\nBody", headers={"x-markdown-tokens": "725"})

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)

    result = read_web_url_tool.handle(
        {"url": "https://example.com/docs"},
        ToolContext(),
    )

    assert result == {
        "url": "https://example.com/docs",
        "markdown": "# Example\n\nBody",
    }
    assert seen == {
        "url": read_web_url_tool.MARKDOWN_NEW_URL,
        "method": "POST",
        "accept": "text/markdown",
        "content_type": "application/json",
        "body": '{"url": "https://example.com/docs"}',
        "timeout": read_web_url_tool._REQUEST_TIMEOUT_SECS,
    }


def test_read_web_url_bounds_large_markdown(monkeypatch) -> None:
    long_markdown = (
        f"# Start\n\nprefix-{'x' * (read_web_url_tool.MAX_MARKDOWN_CHARS + 200)}-suffix"
    )

    monkeypatch.setattr(
        urllib.request,
        "urlopen",
        lambda request, timeout: _FakeResponse(long_markdown),
    )

    result = read_web_url_tool.handle({"url": "https://example.com"}, ToolContext())

    assert result["url"] == "https://example.com"
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


def test_read_web_url_reports_http_errors(monkeypatch) -> None:
    def fake_urlopen(
        request: urllib.request.Request,
        timeout: float,
    ) -> _FakeResponse:
        del request, timeout
        raise urllib.error.HTTPError(
            read_web_url_tool.MARKDOWN_NEW_URL,
            429,
            "Too Many Requests",
            hdrs=None,
            fp=None,
        )

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)

    result = read_web_url_tool.handle({"url": "https://example.com"}, ToolContext())

    assert result == {"error": "HTTP 429 Too Many Requests"}


def test_read_web_url_reports_network_failures(monkeypatch) -> None:
    def fake_urlopen(
        request: urllib.request.Request,
        timeout: float,
    ) -> _FakeResponse:
        del request, timeout
        raise urllib.error.URLError("temporary failure")

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)

    result = read_web_url_tool.handle({"url": "https://example.com"}, ToolContext())

    assert result == {"error": "failed to fetch URL: temporary failure"}
