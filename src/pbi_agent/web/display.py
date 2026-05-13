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
    PendingToolCall,
    PendingToolGroup,
    PendingToolGroupItem,
    PendingUserQuestion,
    QueuedInput,
    QueuedRuntimeChange,
    UserQuestionAnswer,
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
_APPLY_PATCH_HEADER_TO_OPERATION = {
    "*** Add File: ": "create_file",
    "*** Update File: ": "update_file",
    "*** Delete File: ": "delete_file",
}
_APPLY_PATCH_MOVE_TO_HEADER = "*** Move to: "


@dataclass(frozen=True, slots=True)
class _ApplyPatchDisplayOperation:
    operation: str
    path: str
    diff: str = ""


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


def _metadata_payload(value: Any) -> Any:
    if value is None:
        return None
    try:
        import json

        return json.loads(json.dumps(value))
    except (TypeError, ValueError):
        return str(value)


def _result_payload(value: Any) -> dict[str, Any]:
    payload = _metadata_payload(value)
    if isinstance(payload, dict):
        return payload
    if payload is None:
        return {}
    return {"result": payload}


def _tool_result_body(result: Any) -> Any:
    payload = _result_payload(result)
    body = payload.get("result")
    return body if body is not None else payload


def _tool_error_payload(result: Any) -> Any:
    payload = _result_payload(result)
    error = payload.get("error")
    if error is not None:
        return error
    body = payload.get("result")
    if isinstance(body, dict):
        return body.get("error")
    return None


def _patch_detail_from_result_body(result_body: Any, fallback_text: Any = "") -> str:
    if isinstance(result_body, dict):
        status_value = result_body.get("status")
        if (
            isinstance(status_value, str)
            and status_value.strip().lower() == "completed"
        ):
            return ""
        for key in ("error", "message"):
            value = result_body.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
    if isinstance(fallback_text, str):
        return fallback_text.strip()
    return ""


def _apply_patch_running_summary(arguments: Any) -> dict[str, Any]:
    if isinstance(arguments, dict):
        summary: dict[str, Any] = {}
        path = arguments.get("path")
        operation = arguments.get("operation_type") or arguments.get("operation")
        diff = arguments.get("diff")
        if isinstance(path, str) and path:
            summary["path"] = path
        if isinstance(operation, str) and operation:
            summary["operation"] = operation
        if isinstance(diff, str) and diff:
            summary["diff"] = diff
        if "path" in summary or "operation" in summary:
            summary["operation_count"] = 1
            if "path" in summary:
                summary["affected_paths"] = [summary["path"]]
        return summary

    if not isinstance(arguments, str) or not arguments.strip():
        return {}

    operations = _apply_patch_operations_from_v4a(arguments)
    if not operations:
        return {}

    first_hunk: list[str] = []
    capturing_first_hunk = False
    captured_first_hunk = False
    for line in arguments.splitlines():
        if _is_apply_patch_file_operation_header(line):
            capturing_first_hunk = False
            continue
        if (
            line.startswith("@@")
            and len(operations) == 1
            and operations[0].operation in {"update_file", "move_file"}
            and not captured_first_hunk
        ):
            first_hunk.append(line)
            capturing_first_hunk = True
            captured_first_hunk = True
            continue
        if capturing_first_hunk:
            if line.startswith("*** ") or line.startswith("@@"):
                capturing_first_hunk = False
                continue
            if line[:1] in {" ", "-", "+"}:
                first_hunk.append(line)

    first_operation = operations[0]
    summary = {
        "path": first_operation.path,
        "operation": first_operation.operation,
        "operation_count": len(operations),
        "affected_paths": [operation.path for operation in operations],
    }
    if first_hunk:
        summary["diff"] = "\n".join(first_hunk[:80])
    return summary


def _apply_patch_completed_summary(
    *,
    arguments: Any,
    result_body: Any,
    path: str,
    operation: str,
) -> dict[str, Any]:
    operations = _apply_patch_operations_from_result(result_body)
    if not operations:
        operations = _apply_patch_operations_from_v4a(arguments)
    if not operations:
        operations = [_ApplyPatchDisplayOperation(operation, path)] if path else []
    if not operations:
        return {}
    return {
        "operation_count": len(operations),
        "affected_paths": [operation.path for operation in operations],
    }


def _apply_patch_operations_from_result(
    result_body: Any,
) -> list[_ApplyPatchDisplayOperation]:
    if not isinstance(result_body, dict):
        return []
    raw_operations = result_body.get("operations")
    if not isinstance(raw_operations, list):
        return []
    operations: list[_ApplyPatchDisplayOperation] = []
    for item in raw_operations:
        if not isinstance(item, dict):
            continue
        operation = item.get("operation_type")
        path = item.get("path")
        move_to = item.get("move_to")
        if not isinstance(operation, str) or not isinstance(path, str) or not path:
            continue
        if isinstance(move_to, str) and move_to:
            operations.append(
                _ApplyPatchDisplayOperation("move_file", f"{path} → {move_to}")
            )
        else:
            operations.append(_ApplyPatchDisplayOperation(operation, path))
    return operations


def _apply_patch_operations_from_v4a(
    arguments: Any,
) -> list[_ApplyPatchDisplayOperation]:
    if not isinstance(arguments, str) or not arguments.strip():
        return []
    operations: list[_ApplyPatchDisplayOperation] = []
    current_operation: str | None = None
    current_path: str | None = None
    current_diff: list[str] = []

    def flush_current() -> None:
        nonlocal current_operation, current_path, current_diff
        if current_operation and current_path:
            operations.append(
                _ApplyPatchDisplayOperation(
                    current_operation,
                    current_path,
                    "\n".join(current_diff),
                )
            )
        current_operation = None
        current_path = None
        current_diff = []

    for line in arguments.splitlines():
        if line in {"*** Begin Patch", "*** End Patch"}:
            continue
        if (
            line.startswith(_APPLY_PATCH_MOVE_TO_HEADER)
            and current_operation == "update_file"
        ):
            destination = line.removeprefix(_APPLY_PATCH_MOVE_TO_HEADER).strip()
            current_operation = "move_file"
            current_path = (
                f"{current_path} → {destination}" if current_path else destination
            )
            continue
        matched_header = False
        for header, operation in _APPLY_PATCH_HEADER_TO_OPERATION.items():
            if not line.startswith(header):
                continue
            flush_current()
            path = line.removeprefix(header).strip()
            if operation == "delete_file":
                operations.append(_ApplyPatchDisplayOperation(operation, path))
            else:
                current_operation = operation
                current_path = path
            matched_header = True
            break
        if matched_header:
            continue
        if current_operation and not line.startswith("*** "):
            current_diff.append(line)
    flush_current()
    return operations


def _is_apply_patch_file_operation_header(line: str) -> bool:
    return any(line.startswith(header) for header in _APPLY_PATCH_HEADER_TO_OPERATION)


def _apply_patch_operation_call_id(call_id: str, index: int) -> str:
    if not call_id or index == 0:
        return call_id
    return f"{call_id}:{index}"


def _apply_patch_tool_group_item(
    *,
    operation: _ApplyPatchDisplayOperation,
    call_id: str,
    status: str,
    success: bool | None,
    verbose: bool,
    arguments: Any = None,
    result: Any = None,
    detail: str = "",
    error: Any = None,
    diff_line_numbers: list[dict[str, int | None]] | None = None,
) -> PendingToolGroupItem:
    tool_name, text = route_function_result(
        "apply_patch",
        verbose=verbose,
        status=(
            "[cyan]running[/cyan]"
            if status == "running"
            else status_markup(success=success)
        ),
        call_id=call_id,
        arguments={
            "path": operation.path,
            "operation_type": operation.operation,
            "detail": detail,
            "diff": operation.diff,
        },
    )
    metadata: dict[str, Any] = {
        "tool_name": tool_name,
        "path": operation.path,
        "operation": operation.operation,
        "detail": detail,
        "diff": operation.diff,
        "call_id": call_id,
        "status": status,
        "operation_count": 1,
        "affected_paths": [operation.path],
    }
    if success is not None:
        metadata["success"] = success
    if arguments is not None:
        metadata["arguments"] = _metadata_payload(arguments)
    if result is not None:
        metadata["result"] = result
    if error is not None:
        metadata["error"] = error
    if diff_line_numbers:
        metadata["diff_line_numbers"] = diff_line_numbers
    return PendingToolGroupItem(
        _plain_text(text),
        classes=tool_item_class(tool_name),
        metadata=metadata,
    )


def _apply_patch_operation_matches_diff_metadata(
    operation_item: _ApplyPatchDisplayOperation,
    *,
    path: str,
    operation: str,
    diff: str,
) -> bool:
    if diff and operation_item.diff != diff:
        return False
    if operation_item.operation == operation and operation_item.path == path:
        return True
    return (
        operation == "update_file"
        and operation_item.operation == "move_file"
        and (
            operation_item.path == path or operation_item.path.startswith(f"{path} → ")
        )
    )


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


def canonical_message_id(message_id: int) -> str:
    return f"msg-{message_id}"


def persisted_message_part_ids(message: MessageRecord) -> dict[str, Any]:
    message_id = canonical_message_id(message.id)
    return {
        "content": f"{message_id}:content",
        "file_paths": [
            f"{message_id}:file-path:{index}"
            for index, _path in enumerate(message.file_paths)
        ],
        "image_attachments": [
            f"{message_id}:image:{attachment.upload_id}"
            for attachment in message.image_attachments
        ],
    }


def persisted_message_payload(
    message: MessageRecord,
    *,
    historical: bool = True,
) -> dict[str, Any]:
    message_id = canonical_message_id(message.id)
    return {
        "item_id": message_id,
        "message_id": message_id,
        "part_ids": persisted_message_part_ids(message),
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
        "historical": historical,
        "created_at": message.created_at,
    }


def _tool_item_call_id_matches(
    item: PendingToolGroupItem,
    call_id: str,
    prefixed_call_id: str,
) -> bool:
    item_call_id = str(item.metadata.get("call_id") or "")
    return item_call_id == call_id or item_call_id.startswith(prefixed_call_id)


@dataclass(slots=True)
class _SubAgentContext:
    sub_agent_id: str
    title: str


@dataclass(slots=True)
class PendingUserQuestionsPrompt:
    prompt_id: str
    questions: list[PendingUserQuestion]

    def to_payload(self) -> dict[str, Any]:
        return {
            "prompt_id": self.prompt_id,
            "questions": [
                {
                    "question_id": question.question_id,
                    "question": question.question,
                    "suggestions": list(question.suggestions),
                    "recommended_suggestion_index": 0,
                }
                for question in self.questions
            ],
        }


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
        self._assistant_active = False
        self._processing_phase: str | None = None
        self._active_tool_group_item_id: str | None = None
        self._message_item_ids_by_signature: dict[tuple[str, str], list[str]] = {}

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

    def _remember_message_item_id(
        self,
        *,
        item_id: str,
        role: str,
        content: str,
    ) -> None:
        if self._sub_agent is not None:
            return
        self._message_item_ids_by_signature.setdefault((role, content), []).append(
            item_id
        )

    def _pop_message_item_id(self, *, role: str, content: str) -> str | None:
        item_ids = self._message_item_ids_by_signature.get((role, content))
        if not item_ids:
            return None
        item_id = item_ids.pop()
        if not item_ids:
            self._message_item_ids_by_signature.pop((role, content), None)
        return item_id

    def persisted_message(
        self,
        message: MessageRecord,
        *,
        previous_item_id: str | None = None,
    ) -> None:
        payload = persisted_message_payload(message)
        next_item_id = str(payload["item_id"])
        old_item_id = previous_item_id or self._pop_message_item_id(
            role=message.role,
            content=str(payload["content"]),
        )
        if old_item_id and old_item_id != next_item_id:
            self._publish(
                "message_rekeyed",
                {"old_item_id": old_item_id, "item": payload},
            )
            return
        self._publish("message_added", payload)

    def _status_text(self, *, success: bool | None = None) -> str:
        return "ok" if success or success is None else "failed"

    def bind_session(self, session_id: str | None) -> None:
        del session_id

    def request_shutdown(self) -> None:
        return None

    def request_interrupt(
        self, *, item_id: str | None = None, input_text: str | None = None
    ) -> None:
        del item_id, input_text
        return None

    def clear_interrupt(self) -> None:
        return None

    def interrupt_requested(self) -> bool:
        return False

    def submit_input(
        self,
        value: str,
        *,
        file_paths: list[str] | None = None,
        image_paths: list[str] | None = None,
        images=None,
        image_attachments=None,
        interactive_mode: bool = False,
        item_id: str | None = None,
    ) -> None:
        del (
            value,
            file_paths,
            image_paths,
            images,
            image_attachments,
            interactive_mode,
            item_id,
        )
        return None

    def request_new_session(self) -> None:
        raise RuntimeError(
            "This display does not support interactive new-session calls."
        )

    def ask_user_questions(
        self, questions: list[PendingUserQuestion]
    ) -> list[UserQuestionAnswer]:
        del questions
        raise RuntimeError("This display does not support interactive questions.")

    def reset_session(self) -> None:
        self._waiting_message = None
        self._assistant_active = False
        self._processing_phase = None
        self._active_thinking_widget_id = None
        self._active_tool_group_item_id = None
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

    def user_prompt(self) -> str | QueuedInput | QueuedRuntimeChange:
        raise RuntimeError("This display does not support interactive user input.")

    def assistant_start(self) -> None:
        self._assistant_active = True
        self._processing_phase = "starting"
        self._publish(
            "processing_state",
            {
                "active": True,
                "phase": "starting",
                "message": "starting assistant turn...",
            },
        )

    def assistant_stop(self) -> None:
        self._assistant_active = False
        self._processing_phase = None
        self._waiting_message = None
        self._publish(
            "processing_state",
            {"active": False, "phase": None, "message": None},
        )

    def tool_execution_start(self, calls: list[PendingToolCall]) -> None:
        displayable_calls = [call for call in calls if call.name != "sub_agent"]
        if not displayable_calls:
            return
        count = len(displayable_calls)
        label = f"Running {count} local tool{'s' if count != 1 else ''}"
        self._processing_phase = "tool_execution"
        self._publish(
            "processing_state",
            {
                "active": True,
                "phase": "tool_execution",
                "message": label,
                "active_tool_count": count,
            },
        )
        if not self._tool_group.items:
            self._tool_group.start(label, function_count=count)
        for call in displayable_calls:
            self._tool_group.update_for_function(call.name)
            if call.name == "apply_patch":
                operations = _apply_patch_operations_from_v4a(call.arguments)
                if len(operations) > 1:
                    self._replace_tool_items_for_call(
                        call.call_id,
                        [
                            _apply_patch_tool_group_item(
                                operation=operation,
                                call_id=_apply_patch_operation_call_id(
                                    call.call_id, index
                                ),
                                status="running",
                                success=None,
                                verbose=self.verbose,
                                arguments=call.arguments if index == 0 else None,
                            )
                            for index, operation in enumerate(operations)
                        ],
                    )
                    continue
            apply_patch_summary = (
                _apply_patch_running_summary(call.arguments)
                if call.name == "apply_patch"
                else {}
            )
            route_arguments = call.arguments
            if apply_patch_summary:
                route_arguments = {
                    "path": apply_patch_summary.get("path", ""),
                    "operation_type": apply_patch_summary.get("operation", ""),
                }
            tool_name, text = route_function_result(
                call.name,
                verbose=self.verbose,
                status="[cyan]running[/cyan]",
                call_id=call.call_id,
                arguments=route_arguments,
            )
            metadata = {
                "tool_name": tool_name,
                "call_id": call.call_id,
                "status": "running",
                "arguments": _metadata_payload(call.arguments),
            }
            if apply_patch_summary:
                metadata.update(apply_patch_summary)
            self._tool_group.upsert_item(
                _plain_text(text),
                call_id=call.call_id,
                classes=tool_item_class(tool_name),
                metadata=metadata,
            )
        self._publish_tool_group_update()

    def tool_execution_stop(self) -> None:
        if self._assistant_active:
            self._processing_phase = "finalizing"
            self._publish(
                "processing_state",
                {
                    "active": True,
                    "phase": "finalizing",
                    "message": "sending tool results to model...",
                },
            )

    def wait_start(self, message: str = "model is processing your request...") -> None:
        self._waiting_message = message
        self._processing_phase = "model_wait"
        self._publish(
            "processing_state",
            {"active": True, "phase": "model_wait", "message": message},
        )
        self._publish("wait_state", {"active": True, "message": message})

    def wait_stop(self) -> None:
        if self._waiting_message is None:
            return
        self._waiting_message = None
        self._publish("wait_state", {"active": False})
        if not self._assistant_active and self._processing_phase == "model_wait":
            self._processing_phase = None
            self._publish(
                "processing_state",
                {"active": False, "phase": None, "message": None},
            )

    def render_user_message(self, text: str) -> None:
        content = text.strip()
        if not content:
            return
        self._publish(
            "message_added",
            {
                "item_id": self._next_id("message"),
                "role": "user",
                "content": content,
                "markdown": False,
            },
        )

    def render_markdown(self, text: str) -> None:
        item_id = self._next_id("message")
        self._remember_message_item_id(
            item_id=item_id,
            role="assistant",
            content=text,
        )
        self._publish(
            "message_added",
            {
                "item_id": item_id,
                "role": "assistant",
                "content": text,
                "markdown": True,
            },
        )

    def render_transient_markdown(self, text: str) -> None:
        self.render_markdown(text)

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
        result: Any = None,
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
        result_body = _tool_result_body(result)
        metadata = {
            "tool_name": tool_name,
            "call_id": call_id,
            "status": "running"
            if exit_code is None and not timed_out
            else ("failed" if timed_out or exit_code not in (0, None) else "completed"),
            "success": not timed_out and exit_code == 0,
            "arguments": {
                "command": command,
                "working_directory": working_directory,
                "timeout_ms": timeout_ms,
            },
            "result": result_body,
            "error": _tool_error_payload(result),
            "command": command,
            "working_directory": working_directory,
            "timeout_ms": timeout_ms,
            "exit_code": exit_code,
            "timed_out": timed_out,
        }
        self._tool_group.add_item(
            _plain_text(text), classes=tool_item_class(tool_name), metadata=metadata
        )

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
        diff: str = "",
        diff_line_numbers: list[dict[str, int | None]] | None = None,
        tool_name: str = "apply_patch",
        arguments: Any = None,
        result: Any = None,
    ) -> None:
        if self._tool_group.function_count:
            self._tool_group.update_for_function(tool_name)
        result_body = _tool_result_body(result)
        if tool_name == "apply_patch":
            operations = _apply_patch_operations_from_v4a(arguments)
            if not operations:
                operations = _apply_patch_operations_from_result(result_body)
            if len(operations) > 1:
                detail_text = _patch_detail_from_result_body(
                    result_body,
                    result if not success else "",
                )
                error_payload = _tool_error_payload(result)
                self._replace_tool_items_for_call(
                    call_id,
                    [
                        _apply_patch_tool_group_item(
                            operation=operation_item,
                            call_id=_apply_patch_operation_call_id(call_id, index),
                            status="completed" if success else "failed",
                            success=success,
                            verbose=self.verbose,
                            arguments=arguments if index == 0 else None,
                            result=result_body if index == 0 else None,
                            detail=detail_text,
                            error=error_payload,
                            diff_line_numbers=diff_line_numbers
                            if _apply_patch_operation_matches_diff_metadata(
                                operation_item,
                                path=path,
                                operation=operation,
                                diff=diff,
                            )
                            else None,
                        )
                        for index, operation_item in enumerate(operations)
                    ],
                )
                self._publish_tool_group_update()
                return
            if len(operations) == 1:
                parsed_operation = operations[0]
                path = parsed_operation.path
                operation = parsed_operation.operation
                if parsed_operation.diff:
                    diff = parsed_operation.diff
        routed_tool_name, text = route_function_result(
            tool_name,
            verbose=self.verbose,
            status=status_markup(success=success),
            call_id=call_id,
            arguments={
                "path": path,
                "operation_type": operation,
                "detail": detail,
                "diff": diff,
            },
        )
        patch_summary = _apply_patch_completed_summary(
            arguments=arguments,
            result_body=result_body,
            path=path,
            operation=operation,
        )
        metadata = {
            "tool_name": routed_tool_name,
            "path": path,
            "operation": operation,
            "success": success,
            "detail": detail,
            "diff": diff,
            "call_id": call_id,
            "status": "completed" if success else "failed",
            "arguments": _metadata_payload(arguments),
            "result": result_body,
            "error": _tool_error_payload(result),
        }
        metadata.update(patch_summary)
        if diff_line_numbers:
            metadata["diff_line_numbers"] = diff_line_numbers

        self._tool_group.upsert_item(
            _plain_text(text),
            call_id=call_id,
            classes=tool_item_class(routed_tool_name),
            metadata=metadata,
        )
        self._publish_tool_group_update()

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
        result: Any = None,
    ) -> None:
        self._tool_group.update_for_function(name)
        tool_name, text = route_function_result(
            name,
            verbose=self.verbose,
            status=status_markup(success=success),
            call_id=call_id,
            arguments=arguments,
        )
        result_body = _tool_result_body(result)
        self._tool_group.upsert_item(
            _plain_text(text),
            call_id=call_id,
            classes=tool_item_class(tool_name),
            metadata={
                "tool_name": tool_name,
                "call_id": call_id,
                "status": "completed" if success else "failed",
                "success": success,
                "arguments": _metadata_payload(arguments),
                "result": result_body,
                "error": _tool_error_payload(result),
            },
        )
        self._publish_tool_group_update()

    def tool_group_end(self) -> None:
        if not self._tool_group.items:
            self._tool_group.reset()
            return
        self._publish_tool_group_update(final=True)
        self._tool_group.reset()
        self._clear_tool_group_item_id()

    def _publish_tool_group_update(self, *, final: bool = False) -> None:
        items = [
            {
                "text": item.text,
                "classes": item.classes,
                **({"metadata": item.metadata} if item.metadata else {}),
            }
            for item in self._tool_group.items
        ]
        self._publish(
            "tool_group_added",
            {
                "item_id": self._tool_group_item_id(),
                "label": self._tool_group.label,
                "status": "completed" if final else "running",
                "items": items,
            },
        )

    def _tool_group_item_id(self) -> str:
        current = self._active_tool_group_item_id
        if current is None:
            current = self._next_id("tool-group")
            self._active_tool_group_item_id = current
        return current

    def _clear_tool_group_item_id(self) -> None:
        self._active_tool_group_item_id = None

    def _replace_tool_items_for_call(
        self,
        call_id: str,
        items: list[PendingToolGroupItem],
    ) -> None:
        if call_id:
            prefix = f"{call_id}:"
            replacement_index: int | None = None
            kept_items: list[PendingToolGroupItem] = []
            for item in self._tool_group.items:
                if _tool_item_call_id_matches(item, call_id, prefix):
                    if replacement_index is None:
                        replacement_index = len(kept_items)
                    continue
                kept_items.append(item)
            if replacement_index is None:
                replacement_index = len(kept_items)
            kept_items[replacement_index:replacement_index] = items
            self._tool_group.items = kept_items
        else:
            self._tool_group.items.extend(items)
        self._rebuild_tool_group_call_index()

    def _rebuild_tool_group_call_index(self) -> None:
        self._tool_group.item_by_call_id.clear()
        for index, item in enumerate(self._tool_group.items):
            item_call_id = str(item.metadata.get("call_id") or "")
            if item_call_id:
                self._tool_group.item_by_call_id[item_call_id] = index

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
            self._publish("message_added", persisted_message_payload(message))


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
        self._question_response_queue: queue.Queue[list[UserQuestionAnswer]] = (
            queue.Queue()
        )
        self._question_response_event = threading.Event()
        self._pending_question_prompt: PendingUserQuestionsPrompt | None = None
        self._prompt_counter = 0
        self._shutdown = threading.Event()
        self._interrupt = threading.Event()
        self._model = model
        self._reasoning_effort = reasoning_effort
        self._bind_session_callback = bind_session
        self._input_enabled_state: bool | None = None
        self._input_state_lock = threading.Lock()
        self._input_block_prior_states: list[tuple[bool | None, int]] = []
        self._input_activity_sequence = 0

    def _publish_input_state(self, enabled: bool) -> None:
        with self._input_state_lock:
            if enabled and self._input_block_prior_states:
                return
            if self._input_enabled_state is enabled:
                return
            previous_state = self._input_enabled_state
            self._input_enabled_state = enabled
        try:
            self._publish("input_state", {"enabled": enabled})
        except Exception:
            with self._input_state_lock:
                if self._input_enabled_state is enabled:
                    self._input_enabled_state = previous_state
            raise

    def _input_state_blocked(self) -> bool:
        with self._input_state_lock:
            return bool(self._input_block_prior_states)

    def _put_input_activity(
        self,
        value: str | QueuedInput | QueuedRuntimeChange,
    ) -> None:
        with self._input_state_lock:
            self._input_activity_sequence += 1
            self._input_queue.put(value)

    def _restore_input_state_if_no_activity(self, activity_sequence: int) -> bool:
        with self._input_state_lock:
            if (
                self._input_activity_sequence != activity_sequence
                or self._input_block_prior_states
                or self._input_enabled_state is True
            ):
                return False
            previous_state = self._input_enabled_state
            self._input_enabled_state = True
            try:
                self._publish("input_state", {"enabled": True})
            except Exception:
                if self._input_enabled_state is True:
                    self._input_enabled_state = previous_state
                raise
            return True

    def begin_direct_command(self) -> None:
        """Hold interactive input disabled during a direct web command."""
        with self._input_state_lock:
            self._input_block_prior_states.append(
                (self._input_enabled_state, self._input_activity_sequence)
            )
        try:
            self._publish_input_state(False)
        except Exception:
            with self._input_state_lock:
                if self._input_block_prior_states:
                    self._input_block_prior_states.pop()
            raise

    def finish_direct_command(self) -> None:
        """Release a direct web command input hold and restore idle input state."""
        with self._input_state_lock:
            if not self._input_block_prior_states:
                return
            prior_state, prior_activity_sequence = self._input_block_prior_states.pop()
            should_restore = (
                not self._input_block_prior_states and not self._shutdown.is_set()
            )
        if not should_restore:
            return
        if prior_state is True and self._restore_input_state_if_no_activity(
            prior_activity_sequence
        ):
            return
        self._input_event.set()

    def render_transient_markdown(self, text: str) -> None:
        from pbi_agent.web.session.events import TRANSIENT_WEB_EVENT_KEY

        self._publish(
            "message_added",
            {
                TRANSIENT_WEB_EVENT_KEY: True,
                "item_id": self._next_id("message"),
                "role": "assistant",
                "content": text,
                "markdown": True,
            },
        )

    def request_shutdown(self) -> None:
        self._shutdown.set()
        self._input_event.set()
        self._question_response_event.set()

    def request_interrupt(
        self, *, item_id: str | None = None, input_text: str | None = None
    ) -> None:
        self._interrupt.set()
        self._question_response_event.set()
        self._publish(
            "processing_state",
            {
                "active": True,
                "phase": "interrupting",
                "message": "interrupting assistant turn...",
            },
        )
        if item_id:
            self._publish(
                "message_removed",
                {
                    "item_id": item_id,
                    "restore_input": input_text or "",
                },
            )

    def clear_interrupt(self) -> None:
        self._interrupt.clear()

    def interrupt_requested(self) -> bool:
        return self._interrupt.is_set()

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
        interactive_mode: bool = False,
        item_id: str | None = None,
    ) -> None:
        self.clear_interrupt()
        queued = QueuedInput(
            text=value,
            file_paths=list(file_paths or []),
            image_paths=list(image_paths or []),
            images=list(images or []),
            image_attachments=list(image_attachments or []),
            interactive_mode=interactive_mode,
            item_id=item_id,
        )
        self._put_input_activity(queued)
        self._input_event.set()
        self._publish_input_state(False)

    def request_new_session(self) -> None:
        from pbi_agent.agent.session import NEW_SESSION_SENTINEL

        self._put_input_activity(NEW_SESSION_SENTINEL)
        self._input_event.set()
        self._publish_input_state(False)

    def ask_user_questions(
        self, questions: list[PendingUserQuestion]
    ) -> list[UserQuestionAnswer]:
        if not questions:
            raise ValueError("ask_user requires at least one question.")
        self._prompt_counter += 1
        prompt = PendingUserQuestionsPrompt(
            prompt_id=f"ask-{self._prompt_counter}",
            questions=list(questions),
        )
        self._pending_question_prompt = prompt
        self._publish("user_questions_requested", prompt.to_payload())
        try:
            while True:
                try:
                    answers = self._question_response_queue.get_nowait()
                except queue.Empty:
                    if self._shutdown.is_set():
                        raise RuntimeError(
                            "Session shut down while waiting for user answers."
                        )
                    if self._interrupt.is_set():
                        raise RuntimeError(
                            "Assistant turn interrupted while waiting for user answers."
                        )
                    self._question_response_event.wait(timeout=0.5)
                    self._question_response_event.clear()
                    continue
                if self._question_response_queue.empty():
                    self._question_response_event.clear()
                return answers
        finally:
            if self._pending_question_prompt is prompt:
                self._pending_question_prompt = None
            self._publish("user_questions_resolved", {"prompt_id": prompt.prompt_id})

    def submit_question_response(
        self,
        *,
        prompt_id: str,
        answers: list[UserQuestionAnswer],
    ) -> None:
        prompt = self._pending_question_prompt
        if prompt is None or prompt.prompt_id != prompt_id:
            raise RuntimeError("No matching pending user question prompt.")
        expected_ids = {question.question_id for question in prompt.questions}
        answer_ids = {answer.question_id for answer in answers}
        if answer_ids != expected_ids:
            raise ValueError("All pending questions must be answered exactly once.")
        self._question_response_queue.put(list(answers))
        self._question_response_event.set()

    def pending_question_prompt_payload(self) -> dict[str, Any] | None:
        prompt = self._pending_question_prompt
        return prompt.to_payload() if prompt is not None else None

    def request_runtime_change(
        self,
        *,
        runtime,
        profile_id: str | None,
        persist: bool = True,
        saved_runtime=None,
    ) -> None:
        self._model = runtime.settings.model
        self._reasoning_effort = runtime.settings.reasoning_effort
        self._put_input_activity(
            QueuedRuntimeChange(
                runtime=runtime,
                profile_id=profile_id,
                persist=persist,
                saved_runtime=saved_runtime,
            )
        )
        self._input_event.set()
        self._publish_input_state(False)

    def user_prompt(self) -> str | QueuedInput | QueuedRuntimeChange:
        while True:
            try:
                value = self._input_queue.get_nowait()
            except queue.Empty:
                if self._shutdown.is_set():
                    return "exit"
                if self._input_state_blocked():
                    self._input_event.wait(timeout=0.5)
                    self._input_event.clear()
                    continue
                self._publish_input_state(True)
                self._input_event.wait(timeout=0.5)
                self._input_event.clear()
                continue
            if self._input_queue.empty():
                self._input_event.clear()
            self._publish_input_state(False)
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
