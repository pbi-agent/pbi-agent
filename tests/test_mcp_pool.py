from __future__ import annotations

import asyncio
import base64
import json
import subprocess
import sys
from contextlib import asynccontextmanager
from pathlib import Path

import httpx
import pytest
from mcp.shared._httpx_utils import create_mcp_http_client

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
async def _fake_streamable_http_client(_url: str, *, http_client: httpx.AsyncClient):
    assert not http_client.is_closed
    yield object(), object(), lambda: None


def _fake_mcp_imports() -> tuple[object, object, object, object, object]:
    return (
        _FakeSession,
        _FakeStdioServerParameters,
        _fake_stdio_client,
        _fake_streamable_http_client,
        create_mcp_http_client,
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


@pytest.mark.parametrize("headers", [{}, {"Authorization": "Bearer test-token"}])
@pytest.mark.parametrize(
    "failure",
    [
        None,
        "initialize",
        "tools/list",
        "http:initialize",
        "http:tools/call",
        "network:initialize",
        "network:tools/call",
        "timeout:initialize",
        "timeout:tools/call",
    ],
)
@pytest.mark.parametrize("server_count", [1, 2])
def test_mcp_http_real_sdk_requests_and_cleanup(
    monkeypatch, tmp_path: Path, capsys, caplog, headers, failure, server_count
) -> None:
    """Keep the real SDK session/transport; replace only its network client."""
    config_dir = tmp_path / ".agents"
    config_dir.mkdir()
    server_headers = {
        f"server-{i}.test": (
            {"Authorization": f"{headers['Authorization']}-{i}"} if headers else {}
        )
        for i in range(server_count)
    }
    (config_dir / "mcp.json").write_text(
        json.dumps(
            {
                "servers": {
                    f"remote{i}": {
                        "type": "http",
                        "url": f"https://server-{i}.test/mcp",
                        "headers": server_headers[f"server-{i}.test"],
                    }
                    for i in range(server_count)
                }
            }
        ),
        encoding="utf-8",
    )
    requests: list[httpx.Request] = []
    clients: list[httpx.AsyncClient] = []
    if failure and failure.startswith("timeout:"):
        monkeypatch.setattr("pbi_agent.mcp.pool.MCP_CONNECT_TIMEOUT_SECONDS", 0.1)
        monkeypatch.setattr("pbi_agent.mcp.pool.MCP_CALL_TOOL_TIMEOUT_SECONDS", 0.1)

    async def respond(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.method == "GET":
            return httpx.Response(405)
        if request.method == "DELETE":
            return httpx.Response(204)
        message = json.loads(request.content)
        method = message["method"]
        fail_method = failure.split(":", 1)[-1] if failure else None
        if request.url.host == "server-0.test" and method == fail_method:
            if failure.startswith("http:"):
                return httpx.Response(401 if method == "initialize" else 503)
            if failure.startswith("network:"):
                raise httpx.ConnectError("test connection failure", request=request)
            if failure.startswith("timeout:"):
                await asyncio.sleep(30)
            return httpx.Response(
                200,
                json={
                    "jsonrpc": "2.0",
                    "id": message["id"],
                    "error": {"code": -32603, "message": "test failure"},
                },
            )
        if method == "notifications/initialized":
            return httpx.Response(202)
        result = {
            "initialize": {
                "protocolVersion": "2025-11-25",
                "capabilities": {"tools": {}},
                "serverInfo": {"name": "test-server", "version": "1"},
            },
            "tools/list": {
                "tools": [
                    {
                        "name": "greet",
                        "description": "Return a greeting.",
                        "inputSchema": {"type": "object"},
                    }
                ]
            },
            "tools/call": {"content": [{"type": "text", "text": "Hello Ada"}]},
        }[method]
        return httpx.Response(
            200,
            headers={"mcp-session-id": "test-session"},
            json={"jsonrpc": "2.0", "id": message["id"], "result": result},
        )

    def create_client(headers=None):
        client = httpx.AsyncClient(
            headers=headers, transport=httpx.MockTransport(respond)
        )
        clients.append(client)
        return client

    monkeypatch.setattr("mcp.shared._httpx_utils.create_mcp_http_client", create_client)
    startup_failure = failure is not None and not failure.endswith("tools/call")
    with McpServerPool(tmp_path) as pool:
        assert len(pool.bindings) == server_count - int(startup_failure)
        for binding in pool.bindings:
            if (
                failure
                and failure.endswith("tools/call")
                and binding.server_name == "remote0"
            ):
                with pytest.raises(Exception):
                    pool.call_tool(binding, {"name": "Ada"})
            else:
                output = pool.call_tool(binding, {"name": "Ada"})
                assert output.result["content"] == [
                    {"type": "text", "text": "Hello Ada"}
                ]
        if failure is None:
            assert all(not client.is_closed for client in clients)

    assert len(clients) == server_count
    assert all(client.is_closed for client in clients)
    assert requests
    for request in requests:
        assert request.headers.get("authorization") == server_headers[
            request.url.host
        ].get("Authorization")
    if startup_failure:
        assert "Skipping MCP server" in capsys.readouterr().err
    else:
        for i in range(server_count):
            server_requests = [
                request
                for request in requests
                if request.url.host == f"server-{i}.test"
            ]
            assert [
                json.loads(request.content)["method"]
                for request in server_requests
                if request.method == "POST"
            ] == [
                "initialize",
                "notifications/initialized",
                "tools/list",
                "tools/call",
            ]
            assert server_requests[-1].method == "DELETE"
            assert server_requests[-1].headers["mcp-session-id"] == "test-session"
        assert capsys.readouterr().err == ""
    assert "Failed to close MCP server" not in caplog.text
    assert "Attempted to exit cancel scope" not in caplog.text


def test_mcp_stdio_real_sdk_lifecycle(tmp_path: Path, capsys, caplog) -> None:
    """The HTTP lifecycle fix must also preserve SDK-owned stdio task groups."""
    config_dir = tmp_path / ".agents"
    config_dir.mkdir()
    script = """
import json
import sys

for line in sys.stdin:
    message = json.loads(line)
    if "id" not in message:
        continue
    result = {
        "initialize": {
            "protocolVersion": "2025-11-25",
            "capabilities": {"tools": {}},
            "serverInfo": {"name": "test-server", "version": "1"},
        },
        "tools/list": {
            "tools": [{"name": "greet", "inputSchema": {"type": "object"}}]
        },
        "tools/call": {"content": [{"type": "text", "text": "Hello Ada"}]},
    }[message["method"]]
    print(json.dumps({"jsonrpc": "2.0", "id": message["id"], "result": result}), flush=True)
"""
    (config_dir / "mcp.json").write_text(
        json.dumps(
            {
                "servers": {
                    "local": {
                        "command": sys.executable,
                        "args": ["-u", "-c", script],
                    }
                }
            }
        ),
        encoding="utf-8",
    )
    with McpServerPool(tmp_path) as pool:
        assert len(pool.bindings) == 1
        output = pool.call_tool(pool.bindings[0], {"name": "Ada"})
        assert output.result["content"] == [{"type": "text", "text": "Hello Ada"}]
    assert capsys.readouterr().err == ""
    assert "Failed to close MCP server" not in caplog.text
    assert "MCP server 'local' disconnected" not in caplog.text


def test_idle_mcp_worker_does_not_prevent_process_exit(tmp_path: Path) -> None:
    # Web shutdown may stop waiting for a daemon session still in a provider call.
    # An idle MCP worker must not leave a non-daemon executor blocked on queue.get.
    script = """
import asyncio
import sys
import threading
from pathlib import Path
from pbi_agent.mcp.pool import McpServerPool

pool = McpServerPool(Path(sys.argv[1]))
pool._start_loop_thread()
pool._submit(asyncio.sleep(0))
idle = threading.Event()
pool._loop.call_soon_threadsafe(idle.set)
assert idle.wait(2)
# Deliberately leave the daemon worker running, as at application shutdown.
"""
    result = subprocess.run(
        [sys.executable, "-c", script, str(tmp_path)],
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert result.returncode == 0, result.stderr[:4000]


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
