from __future__ import annotations

import asyncio
import base64
import json
import logging
import os
import queue
import sys
import threading
from collections.abc import Awaitable
from contextlib import AsyncExitStack
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pbi_agent.mcp.discovery import McpServerConfig, discover_mcp_server_configs
from pbi_agent.mcp.naming import make_mcp_tool_name
from pbi_agent.models.messages import ImageAttachment
from pbi_agent.tools.catalog import ToolCatalog, ToolCatalogEntry
from pbi_agent.tools.output import MAX_OUTPUT_CHARS, bound_output
from pbi_agent.tools.types import ToolContext, ToolOutput, ToolSpec

_log = logging.getLogger(__name__)

MCP_CONNECT_TIMEOUT_SECONDS = 30.0
MCP_CALL_TOOL_TIMEOUT_SECONDS = 120.0


@dataclass(slots=True, frozen=True)
class McpToolBinding:
    public_name: str
    server_name: str
    original_name: str
    description: str
    input_schema: dict[str, Any]


@dataclass(slots=True)
class _ConnectedServer:
    config: McpServerConfig
    session: Any
    stack: AsyncExitStack
    lock: asyncio.Lock


def _warn(message: str) -> None:
    print(message, file=sys.stderr)


def _import_mcp_client_components() -> tuple[Any, Any, Any, Any]:
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client
    from mcp.client.streamable_http import streamable_http_client

    return ClientSession, StdioServerParameters, stdio_client, streamable_http_client


class _McpToolHandler:
    def __init__(self, pool: "McpServerPool", binding: McpToolBinding) -> None:
        self._pool = pool
        self._binding = binding

    def __call__(self, arguments: dict[str, Any], context: ToolContext) -> ToolOutput:
        del context
        return self._pool.call_tool(self._binding, arguments)


class McpServerPool:
    def __init__(self, workspace: Path | None = None) -> None:
        self._workspace = (workspace or Path.cwd()).resolve()
        self._configs = discover_mcp_server_configs(self._workspace)
        self._bindings: list[McpToolBinding] = []
        self._servers: dict[str, _ConnectedServer] = {}
        self._loop: asyncio.AbstractEventLoop | None = None
        self._request_queue: queue.Queue[tuple[Awaitable[Any] | None, queue.Queue]] = (
            queue.Queue()
        )
        self._thread: threading.Thread | None = None

    @property
    def bindings(self) -> list[McpToolBinding]:
        return list(self._bindings)

    def __enter__(self) -> "McpServerPool":
        if not self._configs:
            return self
        self._start_loop_thread()
        try:
            self._submit(self._connect_all())
        except Exception:
            self.__exit__(None, None, None)
            raise
        return self

    def __exit__(self, *_: object) -> None:
        if self._loop is None or self._thread is None:
            return
        self._submit(self._close_all())
        self._request_queue.put((None, queue.Queue()))
        self._thread.join(timeout=15.0)
        if self._thread.is_alive():
            _log.warning("MCP worker thread did not shut down within 15 s")
        self._thread = None
        self._loop = None

    def to_tool_catalog(self) -> ToolCatalog:
        extra_entries: list[ToolCatalogEntry] = []
        for binding in self._bindings:
            extra_entries.append(
                ToolCatalogEntry(
                    spec=ToolSpec(
                        name=binding.public_name,
                        description=binding.description,
                        parameters_schema=binding.input_schema,
                    ),
                    handler=_McpToolHandler(self, binding),
                )
            )
        return ToolCatalog.from_builtin_registry().merged(extra_entries)

    def call_tool(
        self, binding: McpToolBinding, arguments: dict[str, Any]
    ) -> ToolOutput:
        result = self._submit(self._call_tool(binding, arguments))
        return _normalize_call_tool_result(binding=binding, result=result)

    def _start_loop_thread(self) -> None:
        ready = threading.Event()

        def runner() -> None:
            loop = asyncio.new_event_loop()
            self._loop = loop
            asyncio.set_event_loop(loop)
            ready.set()
            try:
                while True:
                    coroutine, result_queue = self._request_queue.get()
                    if coroutine is None:
                        break
                    try:
                        result = loop.run_until_complete(coroutine)
                    except BaseException as exc:
                        result_queue.put((False, exc))
                    else:
                        result_queue.put((True, result))
            finally:
                loop.close()

        self._thread = threading.Thread(
            target=runner,
            name="pbi-agent-mcp",
            daemon=True,
        )
        self._thread.start()
        ready.wait()

    def _submit(self, coroutine: Awaitable[Any]) -> Any:
        if self._thread is None:
            raise RuntimeError("MCP worker thread is not running.")
        result_queue: queue.Queue = queue.Queue(maxsize=1)
        self._request_queue.put((coroutine, result_queue))
        ok, value = result_queue.get()
        if ok:
            return value
        raise value

    async def _connect_all(self) -> None:
        seen_tool_names: set[str] = set()
        for config in self._configs:
            try:
                server, bindings = await self._connect_server(config)
            except Exception as exc:
                _warn(
                    f"Skipping MCP server {config.name!r} from {config.location}: {exc}"
                )
                continue
            self._servers[config.name] = server
            for binding in bindings:
                if binding.public_name in seen_tool_names:
                    _warn(
                        "Skipping MCP tool "
                        f"{binding.original_name!r} from server {config.name!r}: "
                        f"duplicate public tool name {binding.public_name!r}."
                    )
                    continue
                seen_tool_names.add(binding.public_name)
                self._bindings.append(binding)

    async def _connect_server(
        self,
        config: McpServerConfig,
    ) -> tuple[_ConnectedServer, list[McpToolBinding]]:
        ClientSession, StdioServerParameters, stdio_client, streamablehttp_client = (
            _import_mcp_client_components()
        )
        stack = AsyncExitStack()
        try:
            if config.transport == "http":
                read_stream, write_stream, _ = await stack.enter_async_context(
                    streamablehttp_client(
                        config.url or "", headers=config.headers or None
                    )
                )
            else:
                env = os.environ.copy()
                env.update(config.env)
                server_params = StdioServerParameters(
                    command=config.command or "",
                    args=list(config.args),
                    env=env,
                    cwd=str(config.cwd) if config.cwd is not None else None,
                )
                read_stream, write_stream = await stack.enter_async_context(
                    stdio_client(server_params)
                )
            session = await stack.enter_async_context(
                ClientSession(read_stream, write_stream)
            )
            await asyncio.wait_for(
                session.initialize(), timeout=MCP_CONNECT_TIMEOUT_SECONDS
            )
            response = await asyncio.wait_for(
                session.list_tools(), timeout=MCP_CONNECT_TIMEOUT_SECONDS
            )
        except Exception:
            await stack.aclose()
            raise
        bindings = _bindings_for_server(config, getattr(response, "tools", []))
        return (
            _ConnectedServer(
                config=config,
                session=session,
                stack=stack,
                lock=asyncio.Lock(),
            ),
            bindings,
        )

    async def _close_all(self) -> None:
        for name, server in self._servers.items():
            try:
                await server.stack.aclose()
            except Exception:
                _log.warning("Failed to close MCP server %r", name, exc_info=True)
        self._servers.clear()
        self._bindings.clear()

    async def _call_tool(
        self,
        binding: McpToolBinding,
        arguments: dict[str, Any],
    ) -> Any:
        server = self._servers.get(binding.server_name)
        if server is None:
            raise RuntimeError(
                f"MCP server {binding.server_name!r} is no longer connected."
            )
        async with server.lock:
            return await asyncio.wait_for(
                server.session.call_tool(binding.original_name, arguments),
                timeout=MCP_CALL_TOOL_TIMEOUT_SECONDS,
            )


def _bindings_for_server(
    config: McpServerConfig,
    tools: list[Any],
) -> list[McpToolBinding]:
    bindings: list[McpToolBinding] = []
    for tool in tools:
        original_name = str(_attr_or_key(tool, "name", "")).strip()
        if not original_name:
            continue
        public_name = make_mcp_tool_name(config.name, original_name)
        description = str(_attr_or_key(tool, "description", "")).strip()
        schema = _attr_or_key(tool, "inputSchema", None)
        if not isinstance(schema, dict):
            schema = _attr_or_key(tool, "input_schema", None)
        if not isinstance(schema, dict):
            schema = {"type": "object", "properties": {}, "additionalProperties": True}
        bindings.append(
            McpToolBinding(
                public_name=public_name,
                server_name=config.name,
                original_name=original_name,
                description=description or f"MCP tool {config.name}/{original_name}",
                input_schema=schema,
            )
        )
    return bindings


def _normalize_call_tool_result(
    *,
    binding: McpToolBinding,
    result: Any,
) -> ToolOutput:
    attachments: list[ImageAttachment] = []
    content_items: list[dict[str, Any]] = []

    raw_content = _attr_or_key(result, "content", [])
    if not isinstance(raw_content, list):
        raw_content = []
    for index, item in enumerate(raw_content):
        block, attachment = _normalize_content_block(binding, item, index=index)
        if block is not None:
            content_items.append(block)
        if attachment is not None:
            attachments.append(attachment)

    payload: dict[str, Any] = {
        "server": binding.server_name,
        "tool": binding.original_name,
        "content": content_items,
    }

    structured = _attr_or_key(result, "structuredContent", None)
    if structured is None:
        structured = _attr_or_key(result, "structured_content", None)
    if structured is not None:
        payload["structured_content"] = structured

    is_error = _attr_or_key(result, "isError", None)
    if is_error is None:
        is_error = _attr_or_key(result, "is_error", False)
    if is_error:
        payload["is_error"] = True

    return ToolOutput(result=payload, attachments=attachments)


def _normalize_content_block(
    binding: McpToolBinding,
    item: Any,
    *,
    index: int,
) -> tuple[dict[str, Any] | None, ImageAttachment | None]:
    block_type = str(_attr_or_key(item, "type", "")).strip()
    if block_type == "text":
        return {
            "type": "text",
            "text": _bounded_text(str(_attr_or_key(item, "text", ""))),
        }, None

    if block_type == "image":
        attachment = _image_attachment_for_mcp_item(binding, item, index=index)
        if attachment is None:
            return {"type": "image", "error": "invalid image content"}, None
        return (
            {
                "type": "image",
                "mime_type": attachment.mime_type,
                "byte_count": attachment.byte_count,
            },
            attachment,
        )

    if block_type == "resource":
        resource = _attr_or_key(item, "resource", None)
        return _normalize_resource_block(resource), None

    if block_type:
        return {"type": block_type, "data": _bounded_text(_compact_json(item))}, None
    return None, None


def _normalize_resource_block(resource: Any) -> dict[str, Any]:
    if resource is None:
        return {"type": "resource", "error": "missing resource"}

    uri = str(_attr_or_key(resource, "uri", ""))
    mime_type = str(_attr_or_key(resource, "mimeType", ""))
    text = _attr_or_key(resource, "text", None)
    if isinstance(text, str):
        return {
            "type": "resource_text",
            "uri": uri,
            "mime_type": mime_type,
            "text": _bounded_text(text),
        }

    blob = _attr_or_key(resource, "blob", None)
    if isinstance(blob, str):
        try:
            size_bytes = len(base64.b64decode(blob, validate=False))
        except Exception:
            size_bytes = len(blob)
        return {
            "type": "resource_blob",
            "uri": uri,
            "mime_type": mime_type,
            "byte_count": size_bytes,
        }

    return {
        "type": "resource",
        "uri": uri,
        "mime_type": mime_type,
    }


def _image_attachment_for_mcp_item(
    binding: McpToolBinding,
    item: Any,
    *,
    index: int,
) -> ImageAttachment | None:
    mime_type = str(_attr_or_key(item, "mimeType", "")).strip()
    data = _attr_or_key(item, "data", None)
    if not mime_type or not data:
        return None

    if isinstance(data, bytes):
        raw_bytes = data
        data_base64 = base64.b64encode(data).decode("ascii")
    elif isinstance(data, str):
        data_base64 = data
        try:
            raw_bytes = base64.b64decode(data, validate=False)
        except Exception:
            raw_bytes = data.encode("utf-8", errors="replace")
    else:
        return None

    return ImageAttachment(
        path=f"mcp/{binding.server_name}/{binding.original_name}/{index}",
        mime_type=mime_type,
        data_base64=data_base64,
        byte_count=len(raw_bytes),
    )


def _attr_or_key(value: Any, name: str, default: Any) -> Any:
    if isinstance(value, dict):
        return value.get(name, default)
    return getattr(value, name, default)


def _compact_json(value: Any) -> str:
    try:
        return json.dumps(value, separators=(",", ":"), ensure_ascii=False, default=str)
    except TypeError:
        return str(value)


def _bounded_text(text: str) -> str:
    return bound_output(text, limit=MAX_OUTPUT_CHARS)[0]
