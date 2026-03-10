"""Shared display protocol and tool-group buffering helpers."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol

from pbi_agent.models.messages import TokenUsage
from pbi_agent.ui.formatting import tool_group_class


@dataclass(slots=True)
class PendingToolGroupItem:
    text: str
    classes: str = ""


@dataclass(slots=True)
class PendingToolGroup:
    label: str = ""
    classes: str = ""
    items: list[PendingToolGroupItem] = field(default_factory=list)
    function_count: int = 0
    function_names: set[str] = field(default_factory=set)

    def start(self, label: str, *, classes: str = "", function_count: int = 0) -> None:
        self.label = label
        self.classes = classes
        self.items.clear()
        self.function_count = function_count
        self.function_names.clear()

    def add_item(self, text: str, *, classes: str = "") -> None:
        self.items.append(PendingToolGroupItem(text=text, classes=classes))

    def update_for_function(self, tool_name: str) -> None:
        normalized = tool_name.strip() or "function"
        self.function_names.add(normalized)
        count = self.function_count or max(1, len(self.items))

        if len(self.function_names) == 1:
            self.label = normalized if count == 1 else f"{normalized} ({count} calls)"
            self.classes = tool_group_class(normalized)
            return

        self.label = f"Tool calls ({count})"
        self.classes = "tool-group-mixed"

    def reset(self) -> None:
        self.label = ""
        self.classes = ""
        self.items.clear()
        self.function_count = 0
        self.function_names.clear()


class DisplayProtocol(Protocol):
    verbose: bool

    def request_shutdown(self) -> None: ...

    def submit_input(self, value: str) -> None: ...

    def welcome(
        self,
        *,
        interactive: bool = True,
        model: str | None = None,
        reasoning_effort: str | None = None,
        single_turn_hint: str | None = None,
    ) -> None: ...

    def user_prompt(self) -> str: ...

    def assistant_start(self) -> None: ...

    def wait_start(
        self, message: str = "model is processing your request..."
    ) -> None: ...

    def wait_stop(self) -> None: ...

    def render_markdown(self, text: str) -> None: ...

    def render_thinking(
        self,
        text: str | None = None,
        *,
        title: str | None = None,
        replace_existing: bool = False,
        widget_id: str | None = None,
    ) -> str | None: ...

    def render_redacted_thinking(self) -> None: ...

    def session_usage(self, usage: TokenUsage) -> None: ...

    def turn_usage(self, usage: TokenUsage, elapsed_seconds: float) -> None: ...

    def shell_start(self, commands: list[str]) -> None: ...

    def shell_command(
        self,
        command: str,
        exit_code: int | None,
        timed_out: bool,
        *,
        call_id: str = "",
        working_directory: str = ".",
        timeout_ms: int | str = "default",
    ) -> None: ...

    def patch_start(self, count: int) -> None: ...

    def patch_result(
        self,
        path: str,
        operation: str,
        success: bool,
        *,
        call_id: str = "",
        detail: str = "",
    ) -> None: ...

    def function_start(self, count: int) -> None: ...

    def function_result(
        self,
        name: str,
        success: bool,
        *,
        call_id: str = "",
        arguments: Any = None,
    ) -> None: ...

    def tool_group_end(self) -> None: ...

    def retry_notice(self, attempt: int, max_retries: int) -> None: ...

    def rate_limit_notice(
        self,
        *,
        wait_seconds: float,
        attempt: int,
        max_retries: int,
    ) -> None: ...

    def error(self, message: str) -> None: ...

    def debug(self, message: str) -> None: ...


__all__ = ["DisplayProtocol", "PendingToolGroup", "PendingToolGroupItem"]
