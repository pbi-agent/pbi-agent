from __future__ import annotations

import base64
import json
from contextlib import asynccontextmanager
from pathlib import Path

from pbi_agent.agent import tool_runtime
from pbi_agent.mcp.pool import (
    McpServerPool,
    McpToolBinding,
    _normalize_call_tool_result,
)
from pbi_agent.models.messages import ToolCall
from pbi_agent.tools.types import ToolContext


class _FakeTool:
    def __init__(self, name: str, description: str, schema: dict[str, object]) -> None:
        self.name = name
        self.description = description
        self.inputSchema = schema


class _FakeTextContent:
    type = "text"

    def __init__(self, text: str) -> None:
        self.text = text


class _FakeImageContent:
    type = "image"

    def __init__(self, mime_type: str, data: str) -> None:
        self.mimeType = mime_type
        self.data = data


class _FakeCallToolResult:
    def __init__(
        self,
        *,
        content: list[object],
        structured_content: dict[str, object] | None = None,
        is_error: bool = False,
    ) -> None:
        self.content = content
        self.structuredContent = structured_content
        self.isError = is_error


class _FakeListToolsResponse:
    def __init__(self, tools: list[object]) -> None:
        self.tools = tools


class _FakeSession:
    def __init__(self, _read_stream: object, _write_stream: object) -> None:
        self.calls: list[tuple[str, dict[str, object]]] = []

    async def __aenter__(self) -> "_FakeSession":
        return self

    async def __aexit__(self, *_: object) -> None:
        return None

    async def initialize(self) -> None:
        return None

    async def list_tools(self) -> _FakeListToolsResponse:
        return _FakeListToolsResponse(
            [
                _FakeTool(
                    "say hi",
                    "Return a greeting.",
                    {
                        "type": "object",
                        "properties": {"name": {"type": "string"}},
                        "required": ["name"],
                    },
                )
            ]
        )

    async def call_tool(
        self,
        name: str,
        arguments: dict[str, object],
    ) -> _FakeCallToolResult:
        self.calls.append((name, arguments))
        png_base64 = base64.b64encode(b"\x89PNG\r\n\x1a\nfake").decode("ascii")
        return _FakeCallToolResult(
            content=[
                _FakeTextContent(f"Hello {arguments['name']}"),
                _FakeImageContent("image/png", png_base64),
            ],
            structured_content={"salutation": "hello"},
        )


class _FakeStdioServerParameters:
    def __init__(self, **kwargs: object) -> None:
        self.kwargs = kwargs


@asynccontextmanager
async def _fake_stdio_client(_params: object):
    yield object(), object()


@asynccontextmanager
async def _fake_streamable_http_client(
    _url: str, headers: dict[str, str] | None = None
):
    del headers
    yield object(), object(), lambda: None


def _fake_mcp_imports() -> tuple[object, object, object, object]:
    return (
        _FakeSession,
        _FakeStdioServerParameters,
        _fake_stdio_client,
        _fake_streamable_http_client,
    )


def _write_config(root: Path) -> None:
    config_dir = root / ".agents"
    config_dir.mkdir(parents=True, exist_ok=True)
    (config_dir / "mcp.json").write_text(
        '{"servers":{"echo":{"command":"uv","args":["run","server.py"],"cwd":"."}}}',
        encoding="utf-8",
    )


def _write_http_config(root: Path) -> None:
    config_dir = root / ".agents"
    config_dir.mkdir(parents=True, exist_ok=True)
    (config_dir / "mcp.json").write_text(
        '{"servers":{"github":{"type":"http","url":"https://example.test/mcp"}}}',
        encoding="utf-8",
    )


def test_mcp_server_pool_exposes_dynamic_tool(monkeypatch, tmp_path: Path) -> None:
    _write_config(tmp_path)
    monkeypatch.setattr(
        "pbi_agent.mcp.pool._import_mcp_client_components",
        _fake_mcp_imports,
    )

    with McpServerPool(tmp_path) as pool:
        catalog = pool.to_tool_catalog()
        spec = catalog.get_spec("echo__say_hi")
        handler = catalog.get_handler("echo__say_hi")

        assert spec is not None
        assert spec.description == "Return a greeting."
        assert handler is not None

        output = handler({"name": "Ada"}, ToolContext())

    assert output.result == {
        "server": "echo",
        "tool": "say hi",
        "content": [
            {"type": "text", "text": "Hello Ada"},
            {"type": "image", "mime_type": "image/png", "byte_count": 12},
        ],
        "structured_content": {"salutation": "hello"},
    }
    assert len(output.attachments) == 1
    assert output.attachments[0].mime_type == "image/png"


def test_tool_runtime_executes_dynamic_mcp_tool_without_batch_errors(
    monkeypatch, tmp_path: Path
) -> None:
    _write_config(tmp_path)
    monkeypatch.setattr(
        "pbi_agent.mcp.pool._import_mcp_client_components",
        _fake_mcp_imports,
    )

    with McpServerPool(tmp_path) as pool:
        catalog = pool.to_tool_catalog()
        batch = tool_runtime.execute_tool_calls(
            [
                ToolCall(
                    call_id="call_1",
                    name="echo__say_hi",
                    arguments={"name": "Ada"},
                )
            ],
            max_workers=1,
            context=ToolContext(tool_catalog=catalog),
        )

    assert batch.had_errors is False
    payload = json.loads(batch.results[0].output_json)
    assert payload["ok"] is True
    assert payload["result"]["server"] == "echo"
    assert payload["result"]["tool"] == "say hi"
    assert payload["result"]["structured_content"] == {"salutation": "hello"}
    assert len(batch.results[0].attachments) == 1


def test_mcp_server_pool_supports_http_transport(monkeypatch, tmp_path: Path) -> None:
    _write_http_config(tmp_path)
    monkeypatch.setattr(
        "pbi_agent.mcp.pool._import_mcp_client_components",
        _fake_mcp_imports,
    )

    with McpServerPool(tmp_path) as pool:
        catalog = pool.to_tool_catalog()
        spec = catalog.get_spec("github__say_hi")

    assert spec is not None
    assert spec.description == "Return a greeting."


def test_normalize_call_tool_result_preserves_mcp_error_payload() -> None:
    binding = McpToolBinding(
        public_name="echo__failing",
        server_name="echo",
        original_name="failing",
        description="Failing tool",
        input_schema={"type": "object"},
    )
    result = _FakeCallToolResult(
        content=[_FakeTextContent("nope")],
        structured_content={"reason": "bad input"},
        is_error=True,
    )

    output = _normalize_call_tool_result(binding=binding, result=result)

    assert output.result == {
        "server": "echo",
        "tool": "failing",
        "content": [{"type": "text", "text": "nope"}],
        "structured_content": {"reason": "bad input"},
        "is_error": True,
    }
