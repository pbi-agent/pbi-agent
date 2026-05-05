from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

from pbi_agent.config import ResolvedRuntime
from pbi_agent.session_store import (
    KanbanStageConfigRecord,
    KanbanTaskRecord,
    MessageImageAttachment,
    MessageRecord,
    ObservabilityEventRecord,
    RunSessionRecord,
    SessionRecord,
)
from pbi_agent.web.display import persisted_message_payload
from pbi_agent.web.uploads import StoredImageUpload

if TYPE_CHECKING:
    from pbi_agent.web.session.state import LiveSessionState


_SESSION_LIFECYCLE_STATUSES = frozenset(
    {
        "idle",
        "starting",
        "running",
        "waiting_for_input",
        "ended",
        "failed",
        "stale",
    }
)
_RUN_RECORD_STATUSES = frozenset(
    {
        "started",
        "completed",
        "interrupted",
        "failed",
        "starting",
        "running",
        "waiting_for_input",
        "ended",
        "stale",
    }
)
_ACTIVE_LIVE_SESSION_STATUSES = frozenset(
    {
        "starting",
        "running",
        "waiting_for_input",
    }
)


def _normalize_session_status(
    status: str,
    *,
    fatal_error: str | None = None,
    ended_at: str | None = None,
    exit_code: int | None = None,
) -> str:
    if status in _SESSION_LIFECYCLE_STATUSES:
        return status
    if status in {"completed", "interrupted"}:
        return "ended"
    if status == "started":
        return "running"
    if fatal_error:
        return "failed"
    if ended_at is not None or exit_code is not None:
        return "ended"
    return "running"


def _session_status_from_run(record: RunSessionRecord) -> str:
    return _normalize_session_status(
        record.status,
        fatal_error=record.fatal_error,
        ended_at=record.ended_at,
        exit_code=record.exit_code,
    )


def _run_status_from_run(record: RunSessionRecord) -> str:
    status = record.status
    if status in _RUN_RECORD_STATUSES:
        return status
    if record.fatal_error:
        return "failed"
    if record.ended_at is not None or record.exit_code is not None:
        return "completed"
    return "started"


def _persisted_web_run_status(live_session: "LiveSessionState") -> str:
    if live_session.terminal_status is not None:
        return live_session.terminal_status
    if live_session.status == "ended":
        if live_session.fatal_error or (
            live_session.exit_code is not None and live_session.exit_code != 0
        ):
            return "failed"
        return "completed"
    return live_session.status


def _serialize_session(
    record: SessionRecord,
    *,
    active_live_session: "LiveSessionState | None" = None,
    active_run: RunSessionRecord | None = None,
    status_run: RunSessionRecord | None = None,
) -> dict[str, Any]:
    status = "idle"
    active_run_id = None
    active_live_session_id = None
    task_id = None
    if status_run is not None:
        status = _session_status_from_run(status_run)
    if active_run is not None:
        status = _session_status_from_run(active_run)
        active_run_id = active_run.run_session_id
        task_id = active_run.task_id
    if active_live_session is not None:
        status = active_live_session.status
        active_live_session_id = active_live_session.live_session_id
        task_id = active_live_session.task_id
    return {
        "session_id": record.session_id,
        "directory": record.directory,
        "provider": record.provider,
        "provider_id": record.provider_id,
        "model": record.model,
        "profile_id": record.profile_id,
        "previous_id": record.previous_id,
        "title": record.title,
        "total_tokens": record.total_tokens,
        "input_tokens": record.input_tokens,
        "output_tokens": record.output_tokens,
        "cost_usd": record.cost_usd,
        "created_at": record.created_at,
        "updated_at": record.updated_at,
        "status": status,
        "active_run_id": active_run_id,
        "active_live_session_id": active_live_session_id,
        "task_id": task_id,
    }


def _is_active_live_session(live_session: "LiveSessionState") -> bool:
    return (
        live_session.status in _ACTIVE_LIVE_SESSION_STATUSES
        and live_session.ended_at is None
    )


def _deserialize_json_field(raw_value: str | None) -> Any:
    if not raw_value:
        return None
    try:
        return json.loads(raw_value)
    except json.JSONDecodeError:
        return raw_value


def _web_event_from_record(record: ObservabilityEventRecord) -> dict[str, Any] | None:
    if record.event_type != "web_event":
        return None
    metadata = _deserialize_json_field(record.metadata_json)
    if not isinstance(metadata, dict):
        return None
    event_type = metadata.get("type")
    payload = metadata.get("payload")
    if not isinstance(event_type, str) or not isinstance(payload, dict):
        return None
    seq = metadata.get("seq")
    if not isinstance(seq, int) or seq <= 0:
        seq = abs(record.step_index) if record.step_index < 0 else record.step_index
    if seq <= 0:
        return None
    created_at = metadata.get("created_at")
    return {
        "seq": seq,
        "type": event_type,
        "payload": payload,
        "created_at": created_at if isinstance(created_at, str) else record.timestamp,
    }


def _timeline_snapshot_from_run(
    record: RunSessionRecord | None,
) -> dict[str, Any] | None:
    if record is None:
        return None
    snapshot = _deserialize_json_field(record.snapshot_json)
    if not isinstance(snapshot, dict):
        return None
    if not isinstance(snapshot.get("live_session_id"), str):
        return None
    return snapshot


def _copy_timeline_item_for_run(
    item: Any,
    run_session_id: str,
    *,
    namespace_non_messages: bool,
) -> Any:
    if not isinstance(item, dict):
        return item
    copied = dict(item)
    if namespace_non_messages and copied.get("kind") != "message":
        for key in ("itemId", "item_id"):
            item_id = copied.get(key)
            if isinstance(item_id, str):
                copied[key] = f"{run_session_id}:{item_id}"
    return copied


def _combined_timeline_snapshot(
    records: list[RunSessionRecord],
    current_snapshot: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    snapshots: list[tuple[str, dict[str, Any], bool]] = []
    current_live_session_id = (
        current_snapshot.get("live_session_id")
        if isinstance(current_snapshot, dict)
        else None
    )
    for record in records:
        if record.run_session_id == current_live_session_id:
            continue
        snapshot = _timeline_snapshot_from_run(record)
        if snapshot is None:
            continue
        snapshots.append((record.run_session_id, snapshot, True))
    if current_snapshot is not None:
        snapshots.append(
            (
                str(current_snapshot.get("live_session_id") or "live"),
                current_snapshot,
                False,
            )
        )
    if not snapshots:
        return None

    latest = dict(snapshots[-1][1])
    items: list[Any] = []
    sub_agents: dict[str, Any] = {}
    for run_session_id, snapshot, namespace_non_messages in snapshots:
        raw_sub_agents = snapshot.get("sub_agents")
        if isinstance(raw_sub_agents, dict):
            sub_agents.update(raw_sub_agents)
        raw_items = snapshot.get("items")
        if not isinstance(raw_items, list):
            continue
        items.extend(
            _copy_timeline_item_for_run(
                item,
                run_session_id,
                namespace_non_messages=namespace_non_messages,
            )
            for item in raw_items
        )

    latest["items"] = items
    latest["sub_agents"] = sub_agents
    return latest


def _format_shell_command_output(result: dict[str, Any] | str) -> str:
    if not isinstance(result, dict):
        return f"## Shell command output\n\n```text\n{result}\n```"
    exit_code = result.get("exit_code")
    status = "timed out" if result.get("timed_out") else f"exit code {exit_code}"
    sections = ["## Shell command output", "", f"Status: `{status}`"]
    error = str(result.get("error") or "").strip()
    if error:
        sections.extend(["", "Error:", "```text", error, "```"])
    stdout = str(result.get("stdout") or "")
    stderr = str(result.get("stderr") or "")
    sections.extend(["", "Stdout:", "```text", stdout or "(empty)", "```"])
    if result.get("stdout_truncated"):
        sections.append("_stdout truncated_")
    sections.extend(["", "Stderr:", "```text", stderr or "(empty)", "```"])
    if result.get("stderr_truncated"):
        sections.append("_stderr truncated_")
    return "\n".join(sections)


def _session_title_for_input(text: str) -> str:
    return text.strip()[:80]


def _serialize_run_session(record: RunSessionRecord) -> dict[str, Any]:
    return {
        "run_session_id": record.run_session_id,
        "session_id": record.session_id,
        "parent_run_session_id": record.parent_run_session_id,
        "agent_name": record.agent_name,
        "agent_type": record.agent_type,
        "provider": record.provider,
        "provider_id": record.provider_id,
        "profile_id": record.profile_id,
        "model": record.model,
        "status": _run_status_from_run(record),
        "started_at": record.started_at,
        "ended_at": record.ended_at,
        "total_duration_ms": record.total_duration_ms,
        "input_tokens": record.input_tokens,
        "cached_input_tokens": record.cached_input_tokens,
        "cache_write_tokens": record.cache_write_tokens,
        "cache_write_1h_tokens": record.cache_write_1h_tokens,
        "output_tokens": record.output_tokens,
        "reasoning_tokens": record.reasoning_tokens,
        "tool_use_tokens": record.tool_use_tokens,
        "provider_total_tokens": record.provider_total_tokens,
        "estimated_cost_usd": record.estimated_cost_usd,
        "total_tool_calls": record.total_tool_calls,
        "total_api_calls": record.total_api_calls,
        "error_count": record.error_count,
        "kind": record.kind,
        "task_id": record.task_id,
        "project_dir": record.project_dir,
        "last_event_seq": record.last_event_seq,
        "snapshot": _deserialize_json_field(record.snapshot_json),
        "exit_code": record.exit_code,
        "fatal_error": record.fatal_error,
        "metadata": _deserialize_json_field(record.metadata_json),
    }


def _serialize_run_as_live_session(record: RunSessionRecord) -> dict[str, Any]:
    metadata = _deserialize_json_field(record.metadata_json)
    runtime = metadata.get("runtime") if isinstance(metadata, dict) else None
    runtime = runtime if isinstance(runtime, dict) else {}
    return {
        "live_session_id": record.run_session_id,
        "run_id": record.run_session_id,
        "session_id": record.session_id,
        "resume_session_id": record.session_id,
        "task_id": record.task_id,
        "kind": record.kind if record.kind in {"session", "task"} else "session",
        "project_dir": record.project_dir or ".",
        "provider_id": record.provider_id,
        "profile_id": record.profile_id,
        "provider": record.provider or runtime.get("provider") or "",
        "model": record.model or runtime.get("model") or "",
        "reasoning_effort": str(runtime.get("reasoning_effort") or ""),
        "compact_threshold": int(runtime.get("compact_threshold") or 0),
        "created_at": record.started_at,
        "status": _session_status_from_run(record),
        "exit_code": record.exit_code,
        "fatal_error": record.fatal_error,
        "ended_at": record.ended_at,
        "last_event_seq": record.last_event_seq,
    }


def _serialize_saved_session_runtime(
    record: SessionRecord,
    runtime: ResolvedRuntime,
) -> dict[str, Any]:
    return {
        "live_session_id": record.session_id,
        "run_id": record.session_id,
        "session_id": record.session_id,
        "resume_session_id": record.session_id,
        "task_id": None,
        "kind": "session",
        "project_dir": record.directory,
        "provider_id": runtime.provider_id,
        "profile_id": runtime.profile_id,
        "provider": runtime.settings.provider,
        "model": runtime.settings.model,
        "reasoning_effort": runtime.settings.reasoning_effort,
        "compact_threshold": runtime.settings.compact_threshold,
        "created_at": record.updated_at,
        "status": "idle",
        "exit_code": None,
        "fatal_error": None,
        "ended_at": None,
        "last_event_seq": 0,
    }


def _serialize_observability_event(record: ObservabilityEventRecord) -> dict[str, Any]:
    return {
        "run_session_id": record.run_session_id,
        "session_id": record.session_id,
        "step_index": record.step_index,
        "event_type": record.event_type,
        "timestamp": record.timestamp,
        "duration_ms": record.duration_ms,
        "provider": record.provider,
        "model": record.model,
        "url": record.url,
        "request_config": _deserialize_json_field(record.request_config_json),
        "request_payload": _deserialize_json_field(record.request_payload_json),
        "response_payload": _deserialize_json_field(record.response_payload_json),
        "tool_name": record.tool_name,
        "tool_call_id": record.tool_call_id,
        "tool_input": _deserialize_json_field(record.tool_input_json),
        "tool_output": _deserialize_json_field(record.tool_output_json),
        "tool_duration_ms": record.tool_duration_ms,
        "prompt_tokens": record.prompt_tokens,
        "completion_tokens": record.completion_tokens,
        "total_tokens": record.total_tokens,
        "status_code": record.status_code,
        "success": None if record.success is None else bool(record.success),
        "error_message": record.error_message,
        "metadata": _deserialize_json_field(record.metadata_json),
    }


def _runtime_summary(runtime: ResolvedRuntime | None) -> dict[str, Any]:
    if runtime is None:
        return {
            "provider": None,
            "provider_id": None,
            "profile_id": None,
            "model": None,
            "reasoning_effort": None,
            "compact_threshold": None,
        }
    return {
        "provider": runtime.settings.provider,
        "provider_id": runtime.provider_id,
        "profile_id": runtime.profile_id,
        "model": runtime.settings.model,
        "reasoning_effort": runtime.settings.reasoning_effort,
        "compact_threshold": runtime.settings.compact_threshold,
    }


def _resolved_runtime_view(runtime: ResolvedRuntime) -> dict[str, Any]:
    return {
        "provider": runtime.settings.provider,
        "provider_id": runtime.provider_id,
        "profile_id": runtime.profile_id,
        "model": runtime.settings.model,
        "sub_agent_model": runtime.settings.sub_agent_model,
        "reasoning_effort": runtime.settings.reasoning_effort,
        "max_tokens": runtime.settings.max_tokens,
        "service_tier": runtime.settings.service_tier,
        "web_search": runtime.settings.web_search,
        "max_tool_workers": runtime.settings.max_tool_workers,
        "max_retries": runtime.settings.max_retries,
        "compact_threshold": runtime.settings.compact_threshold,
        "compact_tail_turns": runtime.settings.compact_tail_turns,
        "compact_preserve_recent_tokens": runtime.settings.compact_preserve_recent_tokens,
        "compact_tool_output_max_chars": runtime.settings.compact_tool_output_max_chars,
        "responses_url": runtime.settings.responses_url,
        "generic_api_url": runtime.settings.generic_api_url,
        "supports_image_inputs": True,
    }


def _snapshot_item_id(item: dict[str, Any]) -> str:
    return str(item.get("itemId") or item.get("item_id") or "")


def _serialize_task(
    record: KanbanTaskRecord,
    *,
    runtime: ResolvedRuntime | None,
) -> dict[str, Any]:
    return {
        "task_id": record.task_id,
        "directory": record.directory,
        "title": record.title,
        "prompt": record.prompt,
        "stage": record.stage,
        "position": record.position,
        "project_dir": record.project_dir,
        "session_id": record.session_id,
        "profile_id": record.model_profile_id,
        "run_status": record.run_status,
        "last_result_summary": record.last_result_summary,
        "created_at": record.created_at,
        "updated_at": record.updated_at,
        "last_run_started_at": record.last_run_started_at,
        "last_run_finished_at": record.last_run_finished_at,
        "image_attachments": [
            _message_image_payload(attachment)
            for attachment in record.image_attachments
        ],
        "runtime_summary": _runtime_summary(runtime),
    }


def _serialize_board_stage(record: KanbanStageConfigRecord) -> dict[str, Any]:
    return {
        "id": record.stage_id,
        "name": record.name,
        "position": record.position,
        "profile_id": record.model_profile_id,
        "command_id": record.command_id,
        "auto_start": record.auto_start,
    }


def _serialize_history_message(message: MessageRecord) -> dict[str, Any]:
    return persisted_message_payload(message)


def _preview_url(upload_id: str) -> str:
    return f"/api/uploads/{upload_id}"


def _message_image_attachment(record: StoredImageUpload) -> MessageImageAttachment:
    return MessageImageAttachment(
        upload_id=record.upload_id,
        name=record.name,
        mime_type=record.mime_type,
        byte_count=record.byte_count,
        preview_url=_preview_url(record.upload_id),
    )


def _message_image_payload(
    attachment: MessageImageAttachment,
) -> dict[str, Any]:
    return {
        "upload_id": attachment.upload_id,
        "name": attachment.name,
        "mime_type": attachment.mime_type,
        "byte_count": attachment.byte_count,
        "preview_url": attachment.preview_url,
    }


def _config_sort_key(name: str, item_id: str) -> tuple[str, str]:
    return (name.lower(), item_id)
