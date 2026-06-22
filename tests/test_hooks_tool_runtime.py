from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from pbi_agent.agent.tool_runtime import execute_tool_calls
from pbi_agent.config import Settings
from pbi_agent.hooks.runtime import HookRuntime, HookRuntimeResult
from pbi_agent.hooks.schemas import HookEventName
from pbi_agent.models.messages import ToolCall
from pbi_agent.tools.catalog import ToolCatalog, ToolCatalogEntry
from pbi_agent.tools.types import ToolContext, ToolOutput, ToolSpec


class FakeHookRuntime(HookRuntime):
    def __init__(self) -> None:
        self.calls: list[tuple[HookEventName, dict[str, Any]]] = []

    def run(
        self,
        event: HookEventName,
        *,
        matcher_value: str | None = None,
        payload: dict[str, Any] | None = None,
        tracer: Any = None,
    ) -> HookRuntimeResult:
        del matcher_value, tracer
        self.calls.append((event, payload or {}))
        if event == HookEventName.PRE_TOOL_USE:
            return HookRuntimeResult(
                additional_context=["pre context"],
                updated_input={"value": "rewritten"},
            )
        if event == HookEventName.POST_TOOL_USE:
            return HookRuntimeResult(
                additional_context=["extra context"],
                replacement="hook feedback",
            )
        return HookRuntimeResult()


def test_tool_runtime_pre_rewrite_and_post_replacement(tmp_path: Path) -> None:
    def handler(arguments: dict[str, Any], context: ToolContext) -> ToolOutput:
        del context
        return ToolOutput({"value": arguments["value"]})

    catalog = ToolCatalog(
        {
            "demo": ToolCatalogEntry(
                spec=ToolSpec(
                    name="demo",
                    description="demo",
                    parameters_schema={"type": "object"},
                ),
                handler=handler,
            )
        }
    )
    hook_runtime = FakeHookRuntime()

    batch = execute_tool_calls(
        [ToolCall(call_id="call-1", name="demo", arguments={"value": "original"})],
        max_workers=1,
        context=ToolContext(
            settings=Settings(),
            tool_catalog=catalog,
            workspace_root=tmp_path,
            hook_runtime=hook_runtime,
        ),
    )

    assert batch.results[0].output_json == "hook feedback"
    assert hook_runtime.calls[0][1]["tool_input"] == {"value": "original"}
    assert hook_runtime.calls[1][1]["tool_input"] == {"value": "rewritten"}
    assert batch.results[0].display_metadata["hook_context"] == (
        "pre context\n\nextra context"
    )


def test_tool_runtime_preserves_pre_context_without_post_replacement(
    tmp_path: Path,
) -> None:
    def handler(arguments: dict[str, Any], context: ToolContext) -> ToolOutput:
        del arguments, context
        return ToolOutput({"value": "ok"})

    class PreContextHookRuntime(FakeHookRuntime):
        def run(
            self,
            event: HookEventName,
            *,
            matcher_value: str | None = None,
            payload: dict[str, Any] | None = None,
            tracer: Any = None,
        ) -> HookRuntimeResult:
            del matcher_value, payload, tracer
            if event == HookEventName.PRE_TOOL_USE:
                return HookRuntimeResult(additional_context=["pre context"])
            return HookRuntimeResult()

    catalog = ToolCatalog(
        {
            "demo": ToolCatalogEntry(
                spec=ToolSpec(
                    name="demo",
                    description="demo",
                    parameters_schema={"type": "object"},
                ),
                handler=handler,
            )
        }
    )

    batch = execute_tool_calls(
        [ToolCall(call_id="call-1", name="demo", arguments={})],
        max_workers=1,
        context=ToolContext(
            settings=Settings(),
            tool_catalog=catalog,
            workspace_root=tmp_path,
            hook_runtime=PreContextHookRuntime(),
        ),
    )

    assert json.loads(batch.results[0].output_json)["hook_context"] == "pre context"
    assert batch.results[0].display_metadata["hook_context"] == "pre context"


def test_tool_runtime_pre_block(tmp_path: Path) -> None:
    def handler(arguments: dict[str, Any], context: ToolContext) -> dict[str, Any]:
        del arguments, context
        raise AssertionError("handler should not run")

    catalog = ToolCatalog(
        {
            "demo": ToolCatalogEntry(
                spec=ToolSpec(name="demo", description="demo"),
                handler=handler,
            )
        }
    )

    class BlockingHookRuntime(FakeHookRuntime):
        def run(
            self,
            event: HookEventName,
            *,
            matcher_value: str | None = None,
            payload: dict[str, Any] | None = None,
            tracer: Any = None,
        ) -> HookRuntimeResult:
            del matcher_value, payload, tracer
            if event == HookEventName.PRE_TOOL_USE:
                return HookRuntimeResult(blocked=True, block_reason="blocked")
            return HookRuntimeResult()

    batch = execute_tool_calls(
        [ToolCall(call_id="call-1", name="demo", arguments={})],
        max_workers=1,
        context=ToolContext(
            settings=Settings(),
            tool_catalog=catalog,
            workspace_root=tmp_path,
            hook_runtime=BlockingHookRuntime(),
        ),
    )

    assert batch.results[0].is_error
    assert "blocked" in batch.results[0].output_json
