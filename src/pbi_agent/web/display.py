from __future__ import annotations

import queue
import threading
from dataclasses import dataclass
from typing import Any, Callable

from rich.text import Text

from pbi_agent.models.messages import TokenUsage, WebSearchSource
from pbi_agent.session_store import MessageRecord
from pbi_agent.display.protocol import (
    DisplayProtocol,
    PendingToolGroup,
    QueuedInput,
    QueuedRuntimeChange,
)
from pbi_agent.display.formatting import (
    REDACTED_THINKING_NOTICE,
    format_wait_seconds,
    format_web_search_sources_item,
    resolve_reasoning_panel,
    route_function_result,
    shorten,
    status_markup,
    tool_item_class,
)


EventPublisher = Callable[[str, dict[str, Any]], None]
SummaryPublisher = Callable[[str], None]
SessionBinder = Callable[[str | None], None]
_ATTACHED_IMAGES_MARKER = "[attached images:"


def _plain_text(markup: str) -> str:
    if not markup:
        return ""
    return Text.from_markup(markup).plain


def _usage_payload(usage: TokenUsage) -> dict[str, Any]:
    snap = usage.snapshot()
    return {
        "input_tokens": snap.input_tokens,
        "cached_input_tokens": snap.cached_input_tokens,
        "cache_write_tokens": snap.cache_write_tokens,
        "cache_write_1h_tokens": snap.cache_write_1h_tokens,
        "output_tokens": snap.output_tokens,
        "reasoning_tokens": snap.reasoning_tokens,
        "tool_use_tokens": snap.tool_use_tokens,
        "provider_total_tokens": snap.provider_total_tokens,
        "sub_agent_input_tokens": snap.sub_agent_input_tokens,
        "sub_agent_output_tokens": snap.sub_agent_output_tokens,
        "sub_agent_reasoning_tokens": snap.sub_agent_reasoning_tokens,
        "sub_agent_tool_use_tokens": snap.sub_agent_tool_use_tokens,
        "sub_agent_provider_total_tokens": snap.sub_agent_provider_total_tokens,
        "sub_agent_cost_usd": snap.sub_agent_cost_usd,
        "context_tokens": snap.context_tokens,
        "total_tokens": snap.total_tokens,
        "estimated_cost_usd": snap.estimated_cost_usd,
        "main_agent_total_tokens": snap.main_agent_total_tokens,
        "sub_agent_total_tokens": snap.sub_agent_total_tokens,
        "model": snap.model,
        "service_tier": snap.service_tier,
    }


def history_message_content(message: MessageRecord) -> str:
    content = message.content
    if message.role != "user" or not message.image_attachments:
        return content
    stripped = content.strip()
    if stripped.startswith(_ATTACHED_IMAGES_MARKER) and stripped.endswith("]"):
        return ""
    marker_index = content.rfind(f"\n\n{_ATTACHED_IMAGES_MARKER}")
    if marker_index >= 0 and content.rstrip().endswith("]"):
        return content[:marker_index]
    return content


@dataclass(slots=True)
class _SubAgentContext:
    sub_agent_id: str
    title: str


class _EventDisplayBase(DisplayProtocol):
    def __init__(
        self,
        *,
        publish_event: EventPublisher,
        verbose: bool = False,
        sub_agent: _SubAgentContext | None = None,
    ) -> None:
        self.verbose = verbose
        self._publish_event = publish_event
        self._sub_agent = sub_agent
        self._counter = 0
        self._tool_group = PendingToolGroup()
        self._active_thinking_widget_id: str | None = None
        self._waiting_message: str | None = None

    def _next_id(self, prefix: str) -> str:
        self._counter += 1
        suffix = f"{self._counter}"
        if self._sub_agent is not None:
            return f"{self._sub_agent.sub_agent_id}-{prefix}-{suffix}"
        return f"{prefix}-{suffix}"

    def _publish(self, event_type: str, payload: dict[str, Any]) -> None:
        if self._sub_agent is not None:
            payload = {**payload, "sub_agent_id": self._sub_agent.sub_agent_id}
        self._publish_event(event_type, payload)

    def _status_text(self, *, success: bool | None = None) -> str:
        return "ok" if success or success is None else "failed"

    def bind_session(self, session_id: str | None) -> None:
        del session_id

    def request_shutdown(self) -> None:
        return None

    def submit_input(
        self,
        value: str,
        *,
        file_paths: list[str] | None = None,
        image_paths: list[str] | None = None,
        images=None,
        image_attachments=None,
    ) -> None:
        del value, file_paths, image_paths, images, image_attachments
        return None

    def request_new_session(self) -> None:
        raise RuntimeError(
            "This display does not support interactive new-session calls."
        )

    def reset_session(self) -> None:
        self._waiting_message = None
        self._active_thinking_widget_id = None
        self._tool_group.reset()
        self._publish("session_reset", {})

    def begin_sub_agent(
        self,
        *,
        task_instruction: str,
        reasoning_effort: str | None = None,
        name: str = "sub_agent",
    ) -> DisplayProtocol:
        summary = shorten(task_instruction.strip() or "task", 72)
        title = f"{name} · {summary}"
        if reasoning_effort:
            title = f"{title} · {reasoning_effort}"
        sub_agent_id = self._next_id("subagent")
        self._publish(
            "sub_agent_state",
            {
                "sub_agent_id": sub_agent_id,
                "title": title,
                "status": "running",
            },
        )
        return WebSubAgentDisplay(
            publish_event=self._publish_event,
            verbose=self.verbose,
            sub_agent=_SubAgentContext(sub_agent_id=sub_agent_id, title=title),
        )

    def finish_sub_agent(self, *, status: str) -> None:
        del status

    def welcome(
        self,
        *,
        interactive: bool = True,
        model: str | None = None,
        reasoning_effort: str | None = None,
        single_turn_hint: str | None = None,
    ) -> None:
        self._publish(
            "welcome",
            {
                "interactive": interactive,
                "model": model,
                "reasoning_effort": reasoning_effort,
                "single_turn_hint": single_turn_hint,
            },
        )

    def user_prompt(self) -> str | QueuedInput:
        raise RuntimeError("This display does not support interactive user input.")

    def assistant_start(self) -> None:
        return None

    def wait_start(self, message: str = "model is processing your request...") -> None:
        self._waiting_message = message
        self._publish("wait_state", {"active": True, "message": message})

    def wait_stop(self) -> None:
        if self._waiting_message is None:
            return
        self._waiting_message = None
        self._publish("wait_state", {"active": False})

    def render_markdown(self, text: str) -> None:
        self._publish(
            "message_added",
            {
                "item_id": self._next_id("message"),
                "role": "assistant",
                "content": text,
                "markdown": True,
            },
        )

    def render_thinking(
        self,
        text: str | None = None,
        *,
        title: str | None = None,
        replace_existing: bool = False,
        widget_id: str | None = None,
    ) -> str | None:
        summary = title or ""
        body, widget_title = resolve_reasoning_panel(text, summary)
        if body is None and not summary.strip():
            return None

        resolved_widget_id = widget_id
        if resolved_widget_id is None and replace_existing:
            resolved_widget_id = self._active_thinking_widget_id
        if resolved_widget_id is None:
            resolved_widget_id = self._next_id("thinking")
        if replace_existing:
            self._active_thinking_widget_id = resolved_widget_id

        self._publish(
            "thinking_updated",
            {
                "item_id": resolved_widget_id,
                "title": widget_title,
                "content": body or "",
            },
        )
        return resolved_widget_id

    def render_redacted_thinking(self) -> None:
        self._publish(
            "thinking_updated",
            {
                "item_id": self._next_id("thinking"),
                "title": "Thinking",
                "content": REDACTED_THINKING_NOTICE,
            },
        )

    def session_usage(self, usage: TokenUsage) -> None:
        self._publish(
            "usage_updated",
            {
                "scope": "session",
                "usage": _usage_payload(usage),
            },
        )

    def turn_usage(self, usage: TokenUsage, elapsed_seconds: float) -> None:
        self._publish(
            "usage_updated",
            {
                "scope": "turn",
                "usage": _usage_payload(usage),
                "elapsed_seconds": elapsed_seconds,
            },
        )

    def shell_start(self, commands: list[str]) -> None:
        count = len(commands)
        self._tool_group.start(
            f"Running {count} shell command{'s' if count != 1 else ''}"
        )

    def shell_command(
        self,
        command: str,
        exit_code: int | None,
        timed_out: bool,
        *,
        call_id: str = "",
        working_directory: str = ".",
        timeout_ms: int | str = "default",
    ) -> None:
        tool_name, text = route_function_result(
            "shell",
            verbose=self.verbose,
            status=status_markup(timed_out=timed_out, exit_code=exit_code),
            call_id=call_id,
            arguments={
                "command": command,
                "working_directory": working_directory,
                "timeout_ms": timeout_ms,
            },
        )
        self._tool_group.add_item(_plain_text(text), classes=tool_item_class(tool_name))

    def patch_start(self, count: int) -> None:
        self._tool_group.start(f"Editing {count} file{'s' if count != 1 else ''}")

    def patch_result(
        self,
        path: str,
        operation: str,
        success: bool,
        *,
        call_id: str = "",
        detail: str = "",
    ) -> None:
        tool_name, text = route_function_result(
            "apply_patch",
            verbose=self.verbose,
            status=status_markup(success=success),
            call_id=call_id,
            arguments={
                "path": path,
                "operation_type": operation,
                "detail": detail,
            },
        )
        self._tool_group.add_item(_plain_text(text), classes=tool_item_class(tool_name))

    def function_start(self, count: int) -> None:
        self._tool_group.start(
            f"Tool call{'s' if count != 1 else ''}",
            function_count=count,
        )

    def function_result(
        self,
        name: str,
        success: bool,
        *,
        call_id: str = "",
        arguments: Any = None,
    ) -> None:
        self._tool_group.update_for_function(name)
        tool_name, text = route_function_result(
            name,
            verbose=self.verbose,
            status=status_markup(success=success),
            call_id=call_id,
            arguments=arguments,
        )
        self._tool_group.add_item(_plain_text(text), classes=tool_item_class(tool_name))

    def tool_group_end(self) -> None:
        if not self._tool_group.items:
            self._tool_group.reset()
            return
        self._publish(
            "tool_group_added",
            {
                "item_id": self._next_id("tool-group"),
                "label": self._tool_group.label,
                "items": [
                    {"text": item.text, "classes": item.classes}
                    for item in self._tool_group.items
                ],
            },
        )
        self._tool_group.reset()

    def retry_notice(self, attempt: int, max_retries: int) -> None:
        self.wait_stop()
        self._publish(
            "message_added",
            {
                "item_id": self._next_id("notice"),
                "role": "notice",
                "content": f"Retrying... ({attempt}/{max_retries})",
                "markdown": False,
            },
        )

    def rate_limit_notice(
        self,
        *,
        wait_seconds: float,
        attempt: int,
        max_retries: int,
    ) -> None:
        self.wait_stop()
        self._publish(
            "message_added",
            {
                "item_id": self._next_id("notice"),
                "role": "notice",
                "content": (
                    "Rate limit reached. Retrying in "
                    f"{format_wait_seconds(wait_seconds)}s ({attempt}/{max_retries})"
                ),
                "markdown": False,
            },
        )

    def overload_notice(
        self,
        *,
        wait_seconds: float,
        attempt: int,
        max_retries: int,
    ) -> None:
        self.wait_stop()
        self._publish(
            "message_added",
            {
                "item_id": self._next_id("notice"),
                "role": "notice",
                "content": (
                    "Provider overloaded. Retrying in "
                    f"{format_wait_seconds(wait_seconds)}s ({attempt}/{max_retries})"
                ),
                "markdown": False,
            },
        )

    def error(self, message: str) -> None:
        self.wait_stop()
        self._tool_group.reset()
        self._publish(
            "message_added",
            {
                "item_id": self._next_id("error"),
                "role": "error",
                "content": message,
                "markdown": False,
            },
        )

    def debug(self, message: str) -> None:
        if not self.verbose:
            return
        self._publish(
            "message_added",
            {
                "item_id": self._next_id("debug"),
                "role": "debug",
                "content": message,
                "markdown": False,
            },
        )

    def web_search_sources(self, sources: list[WebSearchSource]) -> None:
        if not sources:
            return
        source_dicts = [
            {"title": source.title, "url": source.url, "snippet": source.snippet}
            for source in sources
        ]
        text = _plain_text(
            format_web_search_sources_item(source_dicts, verbose=self.verbose)
        )
        self._publish(
            "tool_group_added",
            {
                "item_id": self._next_id("tool-group"),
                "label": "web search",
                "items": [{"text": text, "classes": tool_item_class("web_search")}],
            },
        )

    def replay_history(self, messages: list[MessageRecord]) -> None:
        for message in messages:
            self._publish(
                "message_added",
                {
                    "item_id": f"history-{message.id}",
                    "role": message.role,
                    "content": history_message_content(message),
                    "file_paths": list(message.file_paths),
                    "image_attachments": [
                        {
                            "upload_id": attachment.upload_id,
                            "name": attachment.name,
                            "mime_type": attachment.mime_type,
                            "byte_count": attachment.byte_count,
                            "preview_url": attachment.preview_url,
                        }
                        for attachment in message.image_attachments
                    ],
                    "markdown": message.role == "assistant",
                    "historical": True,
                },
            )


class WebDisplay(_EventDisplayBase):
    def __init__(
        self,
        *,
        publish_event: EventPublisher,
        verbose: bool = False,
        model: str | None = None,
        reasoning_effort: str | None = None,
        bind_session: SessionBinder | None = None,
    ) -> None:
        super().__init__(publish_event=publish_event, verbose=verbose)
        self._input_queue: queue.Queue[str | QueuedInput | QueuedRuntimeChange] = (
            queue.Queue()
        )
        self._input_event = threading.Event()
        self._shutdown = threading.Event()
        self._model = model
        self._reasoning_effort = reasoning_effort
        self._bind_session_callback = bind_session

    def request_shutdown(self) -> None:
        self._shutdown.set()
        self._input_event.set()

    def bind_session(self, session_id: str | None) -> None:
        if self._bind_session_callback is not None:
            self._bind_session_callback(session_id)
        self._publish(
            "session_identity",
            {"session_id": session_id, "resume_session_id": session_id},
        )

    def submit_input(
        self,
        value: str,
        *,
        file_paths: list[str] | None = None,
        image_paths: list[str] | None = None,
        images=None,
        image_attachments=None,
    ) -> None:
        queued: str | QueuedInput = value
        if file_paths or image_paths or images or image_attachments:
            queued = QueuedInput(
                text=value,
                file_paths=list(file_paths or []),
                image_paths=list(image_paths or []),
                images=list(images or []),
                image_attachments=list(image_attachments or []),
            )
        self._input_queue.put(queued)
        self._input_event.set()
        self._publish("input_state", {"enabled": False})

    def request_new_session(self) -> None:
        from pbi_agent.agent.session import NEW_SESSION_SENTINEL

        self._input_queue.put(NEW_SESSION_SENTINEL)
        self._input_event.set()
        self._publish("input_state", {"enabled": False})

    def request_runtime_change(
        self,
        *,
        runtime,
        profile_id: str | None,
    ) -> None:
        self._model = runtime.settings.model
        self._reasoning_effort = runtime.settings.reasoning_effort
        self._input_queue.put(
            QueuedRuntimeChange(
                runtime=runtime,
                profile_id=profile_id,
            )
        )
        self._input_event.set()
        self._publish("input_state", {"enabled": False})

    def user_prompt(self) -> str | QueuedInput | QueuedRuntimeChange:
        while True:
            try:
                value = self._input_queue.get_nowait()
            except queue.Empty:
                if self._shutdown.is_set():
                    return "exit"
                self._publish("input_state", {"enabled": True})
                self._input_event.wait(timeout=0.5)
                self._input_event.clear()
                continue
            if self._input_queue.empty():
                self._input_event.clear()
            self._publish("input_state", {"enabled": False})
            return value


class WebSubAgentDisplay(_EventDisplayBase):
    def __init__(
        self,
        *,
        publish_event: EventPublisher,
        verbose: bool = False,
        sub_agent: _SubAgentContext,
    ) -> None:
        super().__init__(
            publish_event=publish_event,
            verbose=verbose,
            sub_agent=sub_agent,
        )
        self._title = sub_agent.title

    def finish_sub_agent(self, *, status: str) -> None:
        self.wait_stop()
        self._publish(
            "sub_agent_state",
            {
                "sub_agent_id": self._sub_agent.sub_agent_id if self._sub_agent else "",
                "title": self._title,
                "status": status,
            },
        )


class KanbanTaskDisplay(_EventDisplayBase):
    def __init__(
        self,
        *,
        publish_summary: SummaryPublisher,
        verbose: bool = False,
    ) -> None:
        super().__init__(publish_event=self._discard_event, verbose=verbose)
        self._publish_summary = publish_summary

    def _discard_event(self, event_type: str, payload: dict[str, Any]) -> None:
        del event_type, payload

    def _update_summary(self, summary: str) -> None:
        self._publish_summary(summary.strip() or "Running...")

    def welcome(
        self,
        *,
        interactive: bool = True,
        model: str | None = None,
        reasoning_effort: str | None = None,
        single_turn_hint: str | None = None,
    ) -> None:
        del interactive, model, reasoning_effort
        if single_turn_hint:
            self._update_summary(single_turn_hint)

    def request_new_session(self) -> None:
        raise RuntimeError("Kanban task display does not support interactive session.")

    def reset_session(self) -> None:
        return None

    def user_prompt(self) -> str:
        raise RuntimeError("Kanban task display does not support user input.")

    def render_markdown(self, text: str) -> None:
        self._update_summary(shorten(_plain_text(text), 200))

    def render_thinking(
        self,
        text: str | None = None,
        *,
        title: str | None = None,
        replace_existing: bool = False,
        widget_id: str | None = None,
    ) -> str | None:
        del replace_existing, widget_id
        if title:
            self._update_summary(title)
        elif text:
            self._update_summary(shorten(text, 120))
        return None

    def render_redacted_thinking(self) -> None:
        self._update_summary("Thinking was redacted.")

    def session_usage(self, usage: TokenUsage) -> None:
        del usage

    def turn_usage(self, usage: TokenUsage, elapsed_seconds: float) -> None:
        del usage, elapsed_seconds

    def wait_start(self, message: str = "model is processing your request...") -> None:
        self._update_summary(message)

    def wait_stop(self) -> None:
        return None

    def tool_group_end(self) -> None:
        if not self._tool_group.items:
            self._tool_group.reset()
            return
        latest = self._tool_group.items[-1].text
        self._update_summary(shorten(latest, 200))
        self._tool_group.reset()

    def retry_notice(self, attempt: int, max_retries: int) -> None:
        self._update_summary(f"Retrying ({attempt}/{max_retries})")

    def rate_limit_notice(
        self,
        *,
        wait_seconds: float,
        attempt: int,
        max_retries: int,
    ) -> None:
        self._update_summary(
            f"Rate limited. Retrying in {format_wait_seconds(wait_seconds)}s "
            f"({attempt}/{max_retries})"
        )

    def overload_notice(
        self,
        *,
        wait_seconds: float,
        attempt: int,
        max_retries: int,
    ) -> None:
        self._update_summary(
            f"Provider overloaded. Retrying in {format_wait_seconds(wait_seconds)}s "
            f"({attempt}/{max_retries})"
        )

    def error(self, message: str) -> None:
        self._update_summary(shorten(message, 200))

    def debug(self, message: str) -> None:
        if self.verbose:
            self._update_summary(shorten(message, 200))
