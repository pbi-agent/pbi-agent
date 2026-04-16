"""Shared display protocol and tool-group buffering helpers."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol

from pbi_agent.config import ResolvedRuntime
from pbi_agent.models.messages import ImageAttachment, TokenUsage, WebSearchSource
from pbi_agent.session_store import MessageImageAttachment, MessageRecord
from pbi_agent.display.formatting import tool_group_class


@dataclass(slots=True)
class PendingToolGroupItem:
    text: str
    classes: str = ""


@dataclass(slots=True)
class QueuedInput:
    text: str
    file_paths: list[str] = field(default_factory=list)
    image_paths: list[str] = field(default_factory=list)
    images: list[ImageAttachment] = field(default_factory=list)
    image_attachments: list[MessageImageAttachment] = field(default_factory=list)


@dataclass(slots=True)
class QueuedRuntimeChange:
    runtime: ResolvedRuntime
    profile_id: str | None = None


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

    def bind_session(self, session_id: str | None) -> None: ...

    def request_shutdown(self) -> None: ...

    def submit_input(
        self,
        value: str,
        *,
        file_paths: list[str] | None = None,
        image_paths: list[str] | None = None,
        images: list[ImageAttachment] | None = None,
        image_attachments: list[MessageImageAttachment] | None = None,
    ) -> None: ...

    def request_new_session(self) -> None: ...

    def reset_session(self) -> None: ...

    def begin_sub_agent(
        self,
        *,
        task_instruction: str,
        reasoning_effort: str | None = None,
        name: str = "sub_agent",
    ) -> "DisplayProtocol": ...

    def finish_sub_agent(self, *, status: str) -> None: ...

    def welcome(
        self,
        *,
        interactive: bool = True,
        model: str | None = None,
        reasoning_effort: str | None = None,
        single_turn_hint: str | None = None,
    ) -> None: ...

    def user_prompt(self) -> str | QueuedInput | QueuedRuntimeChange: ...

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

    def overload_notice(
        self,
        *,
        wait_seconds: float,
        attempt: int,
        max_retries: int,
    ) -> None: ...

    def error(self, message: str) -> None: ...

    def debug(self, message: str) -> None: ...

    def web_search_sources(self, sources: list[WebSearchSource]) -> None: ...

    def replay_history(self, messages: list[MessageRecord]) -> None: ...


__all__ = [
    "DisplayProtocol",
    "PendingToolGroup",
    "PendingToolGroupItem",
    "QueuedInput",
    "QueuedRuntimeChange",
]
