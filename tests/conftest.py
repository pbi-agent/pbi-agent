from __future__ import annotations

import json
import urllib.error

from email.message import Message
from io import BytesIO
from typing import Any, Callable

import pytest

from pbi_agent.models.messages import TokenUsage


class DisplaySpy:
    def __init__(self) -> None:
        self.wait_messages: list[str] = []
        self.wait_stop_calls = 0
        self.retry_notices: list[tuple[int, int]] = []
        self.rate_limit_notices: list[tuple[float, int, int]] = []
        self.overload_notices: list[tuple[float, int, int]] = []
        self.session_usage_snapshots: list[TokenUsage] = []
        self.thinking_calls: list[dict[str, object | None]] = []
        self.redacted_thinking_calls = 0
        self.markdown_calls: list[str] = []
        self.function_counts: list[int] = []
        self.function_results: list[dict[str, object]] = []
        self.tool_group_end_count = 0

    def begin_sub_agent(
        self,
        *,
        task_instruction: str,
        reasoning_effort: str | None = None,
    ) -> DisplaySpy:
        del task_instruction, reasoning_effort
        return self

    def finish_sub_agent(self, *, status: str) -> None:
        del status

    def wait_start(self, message: str = "") -> None:
        self.wait_messages.append(message)

    def wait_stop(self) -> None:
        self.wait_stop_calls += 1

    def retry_notice(self, attempt: int, max_retries: int) -> None:
        self.retry_notices.append((attempt, max_retries))

    def rate_limit_notice(
        self,
        *,
        wait_seconds: float,
        attempt: int,
        max_retries: int,
    ) -> None:
        self.rate_limit_notices.append((wait_seconds, attempt, max_retries))

    def overload_notice(
        self,
        *,
        wait_seconds: float,
        attempt: int,
        max_retries: int,
    ) -> None:
        self.overload_notices.append((wait_seconds, attempt, max_retries))

    def session_usage(self, usage: TokenUsage) -> None:
        self.session_usage_snapshots.append(usage.snapshot())

    def render_thinking(
        self,
        text: str | None = None,
        *,
        title: str | None = None,
        replace_existing: bool = False,
        widget_id: str | None = None,
    ) -> str | None:
        self.thinking_calls.append(
            {
                "text": text,
                "title": title,
                "replace_existing": replace_existing,
                "widget_id": widget_id,
            }
        )
        return widget_id or f"thinking-{len(self.thinking_calls)}"

    def render_redacted_thinking(self) -> None:
        self.redacted_thinking_calls += 1

    def render_markdown(self, text: str) -> None:
        self.markdown_calls.append(text)

    def function_start(self, count: int) -> None:
        self.function_counts.append(count)

    def function_result(
        self,
        *,
        name: str,
        success: bool,
        call_id: str,
        arguments: object,
    ) -> None:
        self.function_results.append(
            {
                "name": name,
                "success": success,
                "call_id": call_id,
                "arguments": arguments,
            }
        )

    def tool_group_end(self) -> None:
        self.tool_group_end_count += 1


class FakeHTTPResponse:
    def __init__(self, payload: dict[str, Any]) -> None:
        self._payload = payload

    def read(self) -> bytes:
        return json.dumps(self._payload).encode("utf-8")

    def __enter__(self) -> FakeHTTPResponse:
        return self

    def __exit__(self, *_: object) -> None:
        return None


@pytest.fixture
def display_spy() -> DisplaySpy:
    return DisplaySpy()


@pytest.fixture(autouse=True)
def isolate_internal_config_path(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    monkeypatch.setenv(
        "PBI_AGENT_INTERNAL_CONFIG_PATH", str(tmp_path / "internal-config.json")
    )


@pytest.fixture
def make_http_response() -> Callable[[dict[str, Any]], FakeHTTPResponse]:
    def factory(payload: dict[str, Any]) -> FakeHTTPResponse:
        return FakeHTTPResponse(payload)

    return factory


@pytest.fixture
def make_http_error() -> Callable[..., urllib.error.HTTPError]:
    def factory(
        *,
        url: str = "https://example.invalid",
        code: int,
        body: str = "",
        headers: dict[str, str] | None = None,
    ) -> urllib.error.HTTPError:
        message = Message()
        for key, value in (headers or {}).items():
            message[key] = str(value)
        return urllib.error.HTTPError(
            url=url,
            code=code,
            msg=f"HTTP {code}",
            hdrs=message,
            fp=BytesIO(body.encode("utf-8")),
        )

    return factory
