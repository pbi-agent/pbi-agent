"""Shared local tool execution helpers for provider backends."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, TYPE_CHECKING

from pbi_agent.agent.tool_display import (
    build_tool_result_callback,
    display_tool_execution_start,
    finalize_tool_execution,
)
from pbi_agent.agent.tool_runtime import (
    ToolExecutionBatch,
    execute_tool_calls as _execute_tool_calls,
)
from pbi_agent.config import Settings
from pbi_agent.display.protocol import DisplayProtocol
from pbi_agent.models.messages import TokenUsage, ToolCall
from pbi_agent.tools.availability import effective_excluded_tool_names
from pbi_agent.tools.catalog import ToolCatalog
from pbi_agent.tools.types import ParentContextSnapshot, ToolContext, ToolResult

if TYPE_CHECKING:
    from pathlib import Path

    from pbi_agent.hooks.runtime import HookRuntime
    from pbi_agent.observability import RunTracer

ToolResultSerializer = Callable[[ToolResult], dict[str, Any]]
ToolCallExecutor = Callable[..., ToolExecutionBatch]


def execute_provider_tool_calls(
    function_calls: list[ToolCall],
    *,
    max_workers: int,
    settings: Settings,
    display: DisplayProtocol,
    session_usage: TokenUsage,
    turn_usage: TokenUsage,
    tool_catalog: ToolCatalog,
    excluded_tools: set[str],
    serialize_result: ToolResultSerializer,
    sub_agent_depth: int = 0,
    parent_context: ParentContextSnapshot | None = None,
    tracer: "RunTracer | None" = None,
    tool_availability_overridden: bool = False,
    workspace_root: "Path | None" = None,
    workspace_directory_key: str | None = None,
    hook_runtime: "HookRuntime | None" = None,
    session_id: str | None = None,
    turn_id: str | None = None,
    current_model: str | None = None,
    execute_calls: ToolCallExecutor = _execute_tool_calls,
) -> tuple[list[dict[str, Any]], bool]:
    """Execute tool calls and serialize results into a provider-native shape."""
    if not function_calls:
        return [], False

    displayable_calls = [call for call in function_calls if call.name != "sub_agent"]
    if displayable_calls:
        display.function_start(len(displayable_calls))
        display_tool_execution_start(display, displayable_calls)
    try:
        batch = execute_calls(
            function_calls,
            max_workers=max_workers,
            context=ToolContext(
                settings=settings,
                display=display,
                session_usage=session_usage,
                turn_usage=turn_usage,
                sub_agent_depth=sub_agent_depth,
                tool_catalog=tool_catalog,
                disabled_tool_names=effective_excluded_tool_names(
                    settings, excluded_tools
                ),
                tool_availability_overridden=tool_availability_overridden,
                parent_context=parent_context,
                tracer=tracer,
                workspace_root=workspace_root,
                workspace_directory_key=workspace_directory_key,
                hook_runtime=hook_runtime,
                session_id=session_id,
                turn_id=turn_id,
                current_model=current_model,
            ),
            on_result=build_tool_result_callback(display),
        )
        finalize_tool_execution(display)
    except Exception:
        if displayable_calls:
            display.tool_execution_stop()
        raise
    if displayable_calls:
        display.tool_group_end()
    return [serialize_result(result) for result in batch.results], batch.had_errors
