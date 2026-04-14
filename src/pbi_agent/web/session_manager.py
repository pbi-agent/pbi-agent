from __future__ import annotations

import argparse
import asyncio
import json
import threading
import uuid
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from pbi_agent.agent.error_formatting import format_user_facing_error
from pbi_agent.agent.session import run_chat_loop
from pbi_agent.config import (
    ConfigError,
    InternalConfig,
    ModelProfileConfig,
    CommandConfig,
    OPENAI_SERVICE_TIERS,
    PROVIDER_KINDS,
    ProviderConfig,
    ResolvedRuntime,
    Settings,
    create_model_profile_config,
    create_provider_config,
    delete_model_profile_config,
    delete_provider_config,
    list_command_configs,
    load_internal_config,
    load_internal_config_snapshot,
    provider_has_secret,
    provider_secret_source,
    provider_ui_metadata,
    replace_model_profile_config,
    replace_provider_config,
    resolve_runtime_for_profile_id,
    resolve_web_runtime,
    select_active_model_profile,
    slugify,
)
from pbi_agent.display.formatting import shorten
from pbi_agent.media import load_workspace_image
from pbi_agent.models.messages import ImageAttachment
from pbi_agent.providers.capabilities import provider_supports_images
from pbi_agent.session_store import (
    KANBAN_STAGE_BACKLOG,
    KANBAN_STAGE_DONE,
    KANBAN_RUN_STATUS_COMPLETED,
    KANBAN_RUN_STATUS_FAILED,
    KanbanStageConfigRecord,
    KanbanStageConfigSpec,
    KanbanTaskRecord,
    MessageRecord,
    MessageImageAttachment,
    ObservabilityEventRecord,
    RunSessionRecord,
    SessionRecord,
    SessionStore,
)
from pbi_agent.task_runner import run_single_turn_in_directory
from pbi_agent.web.command_registry import (
    list_slash_commands,
    search_slash_command_tuples,
)
from pbi_agent.web.display import (
    KanbanTaskDisplay,
    WebDisplay,
    history_message_content,
)
from pbi_agent.web.input_mentions import MentionSearchResult, WorkspaceFileIndex
from pbi_agent.web.uploads import (
    StoredImageUpload,
    delete_uploaded_images,
    load_uploaded_image,
    load_uploaded_image_record,
    store_image_attachment,
    store_uploaded_image_bytes,
)


APP_EVENT_STREAM_ID = "app"
_MAX_EVENT_HISTORY = 1000
_NON_RUNNABLE_BOARD_STAGE_IDS = frozenset({KANBAN_STAGE_BACKLOG, KANBAN_STAGE_DONE})


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _serialize_session(record: SessionRecord) -> dict[str, Any]:
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
    }


def _deserialize_json_field(raw_value: str | None) -> Any:
    if not raw_value:
        return None
    try:
        return json.loads(raw_value)
    except json.JSONDecodeError:
        return raw_value


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
        "status": record.status,
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
        "metadata": _deserialize_json_field(record.metadata_json),
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


def _runtime_summary(runtime: ResolvedRuntime | None) -> dict[str, str | None]:
    if runtime is None:
        return {
            "provider": None,
            "provider_id": None,
            "profile_id": None,
            "model": None,
            "reasoning_effort": None,
        }
    return {
        "provider": runtime.settings.provider,
        "provider_id": runtime.provider_id,
        "profile_id": runtime.profile_id,
        "model": runtime.settings.model,
        "reasoning_effort": runtime.settings.reasoning_effort,
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
        "responses_url": runtime.settings.responses_url,
        "generic_api_url": runtime.settings.generic_api_url,
        "supports_image_inputs": provider_supports_images(runtime.settings.provider),
    }


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
    return {
        "item_id": f"history-{message.id}",
        "role": message.role,
        "content": history_message_content(message),
        "file_paths": list(message.file_paths),
        "image_attachments": [
            _message_image_payload(attachment)
            for attachment in message.image_attachments
        ],
        "markdown": message.role == "assistant",
        "historical": True,
        "created_at": message.created_at,
    }


def _preview_url(upload_id: str) -> str:
    return f"/api/chat/uploads/{upload_id}"


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


class EventStream:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._events: list[dict[str, Any]] = []
        self._subscribers: dict[
            str, tuple[asyncio.AbstractEventLoop, asyncio.Queue]
        ] = {}
        self._sequence = 0

    def publish(self, event_type: str, payload: dict[str, Any]) -> dict[str, Any]:
        with self._lock:
            self._sequence += 1
            event = {
                "seq": self._sequence,
                "type": event_type,
                "payload": payload,
                "created_at": _now_iso(),
            }
            self._events.append(event)
            if len(self._events) > _MAX_EVENT_HISTORY:
                self._events = self._events[-_MAX_EVENT_HISTORY:]
            subscribers = list(self._subscribers.values())
        for loop, queue in subscribers:
            loop.call_soon_threadsafe(queue.put_nowait, event)
        return event

    def snapshot(self) -> list[dict[str, Any]]:
        with self._lock:
            return list(self._events)

    def subscribe(self) -> tuple[str, asyncio.Queue]:
        subscriber_id = uuid.uuid4().hex
        queue: asyncio.Queue = asyncio.Queue()
        with self._lock:
            self._subscribers[subscriber_id] = (asyncio.get_running_loop(), queue)
        return subscriber_id, queue

    def unsubscribe(self, subscriber_id: str) -> None:
        with self._lock:
            self._subscribers.pop(subscriber_id, None)


@dataclass(slots=True)
class LiveChatSession:
    live_session_id: str
    event_stream: EventStream
    snapshot: LiveSessionSnapshot
    display: WebDisplay
    worker: threading.Thread
    runtime: ResolvedRuntime
    bound_session_id: str | None
    created_at: str
    kind: str = "chat"
    task_id: str | None = None
    project_dir: str = "."
    status: str = "starting"
    exit_code: int | None = None
    fatal_error: str | None = None
    ended_at: str | None = None


@dataclass(slots=True)
class LiveSessionSnapshot:
    session_id: str | None = None
    runtime: dict[str, str | None] | None = None
    input_enabled: bool = False
    wait_message: str | None = None
    session_usage: dict[str, Any] | None = None
    turn_usage: dict[str, Any] | None = None
    session_ended: bool = False
    fatal_error: str | None = None
    items: list[dict[str, Any]] = None  # type: ignore[assignment]
    sub_agents: dict[str, dict[str, str]] = None  # type: ignore[assignment]
    last_event_seq: int = 0

    def __post_init__(self) -> None:
        if self.items is None:
            self.items = []
        if self.sub_agents is None:
            self.sub_agents = {}


class WebSessionManager:
    def __init__(
        self,
        settings: Settings | ResolvedRuntime,
        *,
        runtime_args: argparse.Namespace | None = None,
    ) -> None:
        self._default_runtime = (
            settings
            if isinstance(settings, ResolvedRuntime)
            else ResolvedRuntime(settings=settings, provider_id=None, profile_id=None)
        )
        self._runtime_args = runtime_args
        self._workspace_root = Path.cwd().resolve()
        self._mention_index = WorkspaceFileIndex(self._workspace_root)
        self._directory_key = str(self._workspace_root).lower()
        self._app_stream = EventStream()
        self._chat_sessions: dict[str, LiveChatSession] = {}
        self._running_task_ids: set[str] = set()
        self._lock = threading.Lock()
        with SessionStore() as store:
            store.normalize_kanban_running_tasks(directory=self._directory_key)

    @property
    def workspace_root(self) -> Path:
        return self._workspace_root

    @property
    def settings(self) -> Settings:
        runtime = self._resolve_runtime_optional(None)
        if runtime is not None:
            return runtime.settings
        return self._default_runtime.settings

    def warm_file_mentions_cache(self) -> None:
        self._mention_index.warm_cache()

    def search_file_mentions(
        self,
        query: str,
        *,
        limit: int = 20,
    ) -> list[MentionSearchResult]:
        return self._mention_index.search(query, limit=limit)

    def bootstrap(self) -> dict[str, Any]:
        default_runtime = self._resolve_runtime_optional(None)
        return {
            "workspace_root": str(self._workspace_root),
            "provider": (
                default_runtime.settings.provider
                if default_runtime is not None
                else None
            ),
            "provider_id": default_runtime.provider_id if default_runtime else None,
            "profile_id": default_runtime.profile_id if default_runtime else None,
            "model": default_runtime.settings.model if default_runtime else None,
            "reasoning_effort": (
                default_runtime.settings.reasoning_effort
                if default_runtime is not None
                else None
            ),
            "supports_image_inputs": (
                provider_supports_images(default_runtime.settings.provider)
                if default_runtime is not None
                else False
            ),
            "sessions": self.list_sessions(),
            "tasks": self.list_tasks(),
            "live_sessions": [
                self._serialize_live_session(item)
                for item in self._chat_sessions.values()
            ],
            "board_stages": self.list_board_stages(),
        }

    def config_bootstrap(self) -> dict[str, Any]:
        config, revision = load_internal_config_snapshot()
        return {
            "providers": [
                self._provider_view(provider)
                for provider in sorted(
                    config.providers,
                    key=lambda item: _config_sort_key(item.name, item.id),
                )
            ],
            "model_profiles": [
                self._model_profile_view(
                    profile,
                    provider=self._require_provider(config, profile.provider_id),
                    active_profile_id=config.web.active_profile_id,
                )
                for profile in sorted(
                    config.model_profiles,
                    key=lambda item: _config_sort_key(item.name, item.id),
                )
            ],
            "commands": [
                self._command_view(command)
                for command in sorted(
                    list_command_configs(self._workspace_root),
                    key=lambda item: _config_sort_key(item.name, item.id),
                )
            ],
            "active_profile_id": config.web.active_profile_id,
            "config_revision": revision,
            "options": {
                "provider_kinds": list(PROVIDER_KINDS),
                "reasoning_efforts": ["low", "medium", "high", "xhigh"],
                "openai_service_tiers": list(OPENAI_SERVICE_TIERS),
                "provider_metadata": {
                    provider_kind: provider_ui_metadata(provider_kind)
                    for provider_kind in PROVIDER_KINDS
                },
            },
        }

    def search_slash_commands(
        self,
        query: str,
        *,
        limit: int = 10,
    ) -> list[dict[str, str]]:
        command_tuples = [
            (
                command.name,
                command.description,
                command.hidden_keywords,
                command.kind,
            )
            for command in list_slash_commands()
        ]
        for command in list_command_configs(self._workspace_root):
            command_tuples.append(
                (
                    command.slash_alias,
                    command.description or f"Activate {command.name}",
                    f"{command.name} command prompt preset",
                    "command",
                )
            )
        return [
            {"name": name, "description": description, "kind": kind}
            for name, description, _keywords, kind in search_slash_command_tuples(
                query,
                command_tuples,
                limit=limit,
            )
        ]

    def list_sessions(self, limit: int = 30) -> list[dict[str, Any]]:
        with SessionStore() as store:
            sessions = store.list_sessions(
                self._directory_key,
                limit=limit,
            )
        return [_serialize_session(session) for session in sessions]

    def get_session_detail(self, session_id: str) -> dict[str, Any]:
        with SessionStore() as store:
            record = store.get_session(session_id)
            if record is None or record.directory != self._directory_key:
                raise KeyError(session_id)
            messages = store.list_messages(session_id)
        live_session = self._find_live_session_for_saved_session(session_id)
        return {
            "session": _serialize_session(record),
            "history_items": [
                _serialize_history_message(message) for message in messages
            ],
            "live_session": (
                self._serialize_live_session(live_session)
                if live_session is not None
                else None
            ),
            "active_live_session": (
                self._serialize_live_session(live_session)
                if live_session is not None
                else None
            ),
        }

    def list_session_runs(self, session_id: str) -> list[dict[str, Any]]:
        with SessionStore() as store:
            session = store.get_session(session_id)
            if session is None or session.directory != self._directory_key:
                raise KeyError(session_id)
            runs = store.list_run_sessions(session_id)
        return [_serialize_run_session(run) for run in runs]

    def get_run_detail(
        self, run_session_id: str, *, global_scope: bool = False
    ) -> dict[str, Any]:
        with SessionStore() as store:
            run = store.get_run_session(run_session_id)
            if run is None or run.session_id is None:
                raise KeyError(run_session_id)
            if not global_scope:
                session = store.get_session(run.session_id)
                if session is None or session.directory != self._directory_key:
                    raise KeyError(run_session_id)
            events = store.list_observability_events(run_session_id=run_session_id)
        return {
            "run": _serialize_run_session(run),
            "events": [_serialize_observability_event(event) for event in events],
        }

    def get_dashboard_stats(
        self,
        *,
        start_date: str | None = None,
        end_date: str | None = None,
        global_scope: bool = False,
    ) -> dict[str, Any]:
        directory = None if global_scope else self._directory_key
        with SessionStore() as store:
            return store.get_dashboard_stats(
                directory=directory,
                start_date=start_date,
                end_date=end_date,
            )

    def list_all_runs(
        self,
        *,
        limit: int = 50,
        offset: int = 0,
        status: str | None = None,
        provider: str | None = None,
        model: str | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
        sort_by: str = "started_at",
        sort_dir: str = "desc",
        global_scope: bool = False,
    ) -> dict[str, Any]:
        directory = None if global_scope else self._directory_key
        with SessionStore() as store:
            rows, total_count = store.list_all_run_sessions(
                directory=directory,
                limit=limit,
                offset=offset,
                status=status,
                provider=provider,
                model=model,
                start_date=start_date,
                end_date=end_date,
                sort_by=sort_by,
                sort_dir=sort_dir,
            )
        # Serialise each row dict — the store returns raw dicts with
        # metadata_json still as a JSON string, so we deserialise it here.
        runs: list[dict[str, Any]] = []
        for row in rows:
            run_dict = dict(row)
            session_title = run_dict.pop("session_title", None)
            # Deserialise metadata_json → metadata
            raw_meta = run_dict.pop("metadata_json", "{}")
            run_dict["metadata"] = _deserialize_json_field(raw_meta)
            # Drop the autoincrement id; it's an internal detail.
            run_dict.pop("id", None)
            run_dict["session_title"] = session_title
            runs.append(run_dict)
        return {"runs": runs, "total_count": total_count}

    def list_live_sessions(self) -> list[dict[str, Any]]:
        with self._lock:
            sessions = list(self._chat_sessions.values())
        return [self._serialize_live_session(session) for session in sessions]

    def get_live_session_detail(self, live_session_id: str) -> dict[str, Any]:
        live_session = self._require_live_session(live_session_id)
        return {
            "live_session": self._serialize_live_session(live_session),
            "snapshot": self._serialize_live_snapshot(live_session),
        }

    def list_tasks(self) -> list[dict[str, Any]]:
        with SessionStore() as store:
            records = store.list_kanban_tasks(self._directory_key)
            stage_records = {
                item.stage_id: item
                for item in store.list_kanban_stage_configs(self._directory_key)
            }
        return [
            _serialize_task(
                record,
                runtime=self._resolve_task_runtime(
                    record,
                    stage_record=stage_records.get(record.stage),
                ),
            )
            for record in records
        ]

    def list_board_stages(self) -> list[dict[str, Any]]:
        with SessionStore() as store:
            records = store.list_kanban_stage_configs(self._directory_key)
        return [_serialize_board_stage(record) for record in records]

    def replace_board_stages(
        self, *, stages: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        if not stages:
            raise ConfigError("Board must contain at least one stage.")
        config = load_internal_config()
        profiles = self._profile_map(config)
        commands = self._command_map()
        stage_specs: list[KanbanStageConfigSpec] = []
        seen_stage_ids: set[str] = set()
        for item in stages:
            raw_id = str(item.get("id") or "").strip()
            raw_name = str(item.get("name") or "").strip()
            if not raw_name:
                raise ConfigError("Stage name cannot be empty.")
            stage_id = slugify(raw_id or raw_name)
            if stage_id in seen_stage_ids:
                raise ConfigError(f"Stage '{stage_id}' already exists.")
            seen_stage_ids.add(stage_id)
            is_fixed_stage = stage_id in _NON_RUNNABLE_BOARD_STAGE_IDS
            if is_fixed_stage:
                raw_name = "Backlog" if stage_id == KANBAN_STAGE_BACKLOG else "Done"
                profile_id = None
                command_id = None
                auto_start = False
            else:
                profile_id = item.get("profile_id")
                if profile_id is not None:
                    profile_key = slugify(str(profile_id))
                    if profiles.get(profile_key) is None:
                        raise ConfigError(f"Unknown profile ID '{profile_id}'.")
                    profile_id = profile_key
                command_id = item.get("command_id")
                if command_id is not None:
                    command_key = slugify(str(command_id))
                    if commands.get(command_key) is None:
                        raise ConfigError(f"Unknown command ID '{command_id}'.")
                    command_id = command_key
                auto_start = bool(item.get("auto_start"))
            stage_specs.append(
                KanbanStageConfigSpec(
                    stage_id=stage_id,
                    name=raw_name,
                    model_profile_id=profile_id,
                    command_id=command_id,
                    auto_start=auto_start,
                )
            )
        with SessionStore() as store:
            records = store.replace_kanban_stage_configs(
                self._directory_key,
                stages=stage_specs,
            )
        payload = [_serialize_board_stage(record) for record in records]
        self._app_stream.publish("board_stages_updated", {"board_stages": payload})
        return payload

    def create_live_chat(
        self,
        *,
        session_id: str | None = None,
        live_session_id: str | None = None,
        profile_id: str | None = None,
    ) -> dict[str, Any]:
        runtime = self._resolve_runtime(profile_id)
        bound_session_id = session_id
        if bound_session_id is not None:
            self._require_saved_session(bound_session_id)
            runtime = self._resolve_saved_session_runtime(
                bound_session_id,
                fallback=runtime,
            )
        with self._lock:
            if bound_session_id is not None:
                existing_live_session = (
                    self._find_live_session_for_saved_session_locked(bound_session_id)
                )
                if existing_live_session is not None:
                    return self._serialize_live_session(existing_live_session)
            if live_session_id and live_session_id in self._chat_sessions:
                return self._serialize_live_session(
                    self._chat_sessions[live_session_id]
                )

            new_live_session_id = live_session_id or uuid.uuid4().hex
            event_stream = EventStream()
            snapshot = LiveSessionSnapshot(
                session_id=bound_session_id,
                runtime=_runtime_summary(runtime),
            )
            display = WebDisplay(
                publish_event=lambda event_type, payload, current=new_live_session_id: (
                    self._publish_live_event(
                        current,
                        event_type,
                        payload,
                    )
                ),
                verbose=runtime.settings.verbose,
                model=runtime.settings.model,
                reasoning_effort=runtime.settings.reasoning_effort,
                bind_session=lambda next_bound_session_id, current=new_live_session_id: (
                    self._bind_live_session(
                        current,
                        next_bound_session_id,
                    )
                ),
            )
            worker = threading.Thread(
                target=self._run_chat_worker,
                args=(new_live_session_id,),
                daemon=True,
                name=f"pbi-agent-web-chat-{new_live_session_id[:8]}",
            )
            live_session = LiveChatSession(
                live_session_id=new_live_session_id,
                event_stream=event_stream,
                snapshot=snapshot,
                display=display,
                worker=worker,
                runtime=runtime,
                bound_session_id=bound_session_id,
                created_at=_now_iso(),
            )
            self._chat_sessions[new_live_session_id] = live_session
            self._publish_live_session_runtime(live_session)
            self._publish_live_event(
                new_live_session_id,
                "session_state",
                {
                    "state": "starting",
                    "live_session_id": new_live_session_id,
                    "session_id": bound_session_id,
                    "resume_session_id": bound_session_id,
                },
            )
            self._app_stream.publish(
                "live_session_started",
                {"live_session": self._serialize_live_session(live_session)},
            )
            worker.start()
            return self._serialize_live_session(live_session)

    def delete_session(self, session_id: str) -> None:
        with SessionStore() as store:
            record = store.get_session(session_id)
            if record is None:
                raise KeyError(session_id)
            if record.directory != self._directory_key:
                raise KeyError(session_id)

            affected_tasks = [
                task
                for task in store.list_kanban_tasks(self._directory_key)
                if task.session_id == session_id
            ]
            updated_tasks: list[KanbanTaskRecord] = []
            for task in affected_tasks:
                updated = store.update_kanban_task(task.task_id, clear_session_id=True)
                if updated is not None:
                    updated_tasks.append(updated)

            upload_ids = [
                attachment.upload_id
                for message in store.list_messages(session_id)
                for attachment in message.image_attachments
            ]

            deleted = store.delete_session(session_id)

        if not deleted:
            raise KeyError(session_id)

        delete_uploaded_images(upload_ids)

        for task in updated_tasks:
            self._publish_task_updated(task)

    def upload_chat_images(
        self,
        live_session_id: str,
        *,
        files: list[tuple[str, bytes]],
    ) -> list[dict[str, Any]]:
        live_session = self._require_live_session(live_session_id)
        if live_session.status == "ended":
            raise RuntimeError("Live chat session has already ended.")
        if not provider_supports_images(live_session.runtime.settings.provider):
            raise ValueError("Image inputs are not supported by the current provider.")

        attachments: list[dict[str, Any]] = []
        for original_name, raw_bytes in files:
            safe_name = (
                original_name or "pasted-image.png"
            ).strip() or "pasted-image.png"
            record = store_uploaded_image_bytes(raw_bytes=raw_bytes, name=safe_name)
            attachments.append(
                _message_image_payload(_message_image_attachment(record))
            )
        return attachments

    def submit_chat_input(
        self,
        live_session_id: str,
        *,
        text: str,
        file_paths: list[str] | None = None,
        image_paths: list[str] | None = None,
        image_upload_ids: list[str] | None = None,
        profile_id: str | None = None,
    ) -> dict[str, Any]:
        live_session = self._require_live_session(live_session_id)
        if live_session.status == "ended":
            raise RuntimeError("Live chat session has already ended.")
        requested_runtime = self._resolve_runtime(profile_id)
        if requested_runtime.profile_id != live_session.runtime.profile_id:
            self._queue_runtime_change(live_session, profile_id)
        message_text = text.strip()
        if (image_paths or image_upload_ids) and not provider_supports_images(
            live_session.runtime.settings.provider
        ):
            raise ValueError("Image inputs are not supported by the current provider.")
        resolved_images: list[ImageAttachment] = []
        message_image_attachments: list[MessageImageAttachment] = []
        for image_path in image_paths or []:
            image = load_workspace_image(self._workspace_root, image_path)
            resolved_images.append(image)
            message_image_attachments.append(
                _message_image_attachment(store_image_attachment(image))
            )
        for upload_id in image_upload_ids or []:
            resolved_images.append(load_uploaded_image(upload_id))
            message_image_attachments.append(
                _message_image_attachment(load_uploaded_image_record(upload_id))
            )
        if message_text or message_image_attachments:
            self._publish_live_event(
                live_session_id,
                "message_added",
                {
                    "item_id": f"user-{uuid.uuid4().hex}",
                    "role": "user",
                    "content": message_text,
                    "file_paths": list(file_paths or []),
                    "image_attachments": [
                        _message_image_payload(attachment)
                        for attachment in message_image_attachments
                    ],
                    "markdown": False,
                },
            )
        live_session.display.submit_input(
            message_text,
            file_paths=file_paths,
            images=resolved_images or None,
            image_attachments=message_image_attachments or None,
        )
        return self._serialize_live_session(live_session)

    def request_new_chat(
        self,
        live_session_id: str,
        *,
        profile_id: str | None = None,
    ) -> dict[str, Any]:
        live_session = self._require_live_session(live_session_id)
        if live_session.status == "ended":
            raise RuntimeError("Live chat session has already ended.")
        requested_runtime = self._resolve_runtime(profile_id)
        if requested_runtime.profile_id != live_session.runtime.profile_id:
            self._queue_runtime_change(live_session, profile_id)
        live_session.display.request_new_chat()
        return self._serialize_live_session(live_session)

    def set_live_chat_profile(
        self,
        live_session_id: str,
        *,
        profile_id: str | None = None,
    ) -> dict[str, Any]:
        live_session = self._require_live_session(live_session_id)
        if live_session.status == "ended":
            raise RuntimeError("Live chat session has already ended.")
        requested_runtime = self._resolve_runtime(profile_id)
        if requested_runtime.profile_id != live_session.runtime.profile_id:
            self._queue_runtime_change(live_session, profile_id)
        return self._serialize_live_session(live_session)

    def get_event_stream(self, stream_id: str) -> EventStream:
        if stream_id == APP_EVENT_STREAM_ID:
            return self._app_stream
        live_session = self._chat_sessions.get(stream_id)
        if live_session is None:
            raise KeyError(stream_id)
        return live_session.event_stream

    def create_task(
        self,
        *,
        title: str,
        prompt: str,
        stage: str | None = None,
        project_dir: str = ".",
        session_id: str | None = None,
        profile_id: str | None = None,
    ) -> dict[str, Any]:
        self._validate_project_dir(project_dir)
        if profile_id is not None:
            self._resolve_runtime(profile_id)
        stage_id = stage or self._default_board_stage_id()
        with SessionStore() as store:
            record = store.create_kanban_task(
                directory=self._directory_key,
                title=title,
                prompt=prompt,
                stage=stage_id,
                project_dir=project_dir,
                session_id=session_id,
                model_profile_id=profile_id,
            )
        payload = self._publish_task_updated(record)
        return self._maybe_auto_start_task(record) or payload

    def update_task(
        self,
        task_id: str,
        *,
        title: str | None = None,
        prompt: str | None = None,
        stage: str | None = None,
        position: int | None = None,
        project_dir: str | None = None,
        session_id: str | None = None,
        session_id_present: bool = False,
        profile_id: str | None = None,
        profile_id_present: bool = False,
    ) -> dict[str, Any]:
        if project_dir is not None:
            self._validate_project_dir(project_dir)
        if profile_id_present and profile_id is not None:
            self._resolve_runtime(profile_id)
        with SessionStore() as store:
            current = store.get_kanban_task(task_id)
            if current is None or current.directory != self._directory_key:
                raise KeyError(task_id)
            if stage is not None or position is not None:
                current = store.move_kanban_task(
                    task_id,
                    stage=stage or current.stage,
                    position=position,
                )
                assert current is not None
            updated = store.update_kanban_task(
                task_id,
                title=title,
                prompt=prompt,
                project_dir=project_dir,
                session_id=session_id,
                clear_session_id=session_id_present and session_id is None,
                model_profile_id=profile_id,
                clear_model_profile_id=(profile_id_present and profile_id is None),
            )
        if updated is None:
            raise KeyError(task_id)
        payload = self._publish_task_updated(updated)
        if stage is not None and stage != current.stage:
            return self._maybe_auto_start_task(updated) or payload
        return payload

    def delete_task(self, task_id: str) -> None:
        with self._lock:
            if task_id in self._running_task_ids:
                raise RuntimeError("Cannot delete a running task.")
        with SessionStore() as store:
            record = store.get_kanban_task(task_id)
            if record is None or record.directory != self._directory_key:
                raise KeyError(task_id)
            deleted = store.delete_kanban_task(task_id)
        if not deleted:
            raise KeyError(task_id)
        self._app_stream.publish("task_deleted", {"task_id": task_id})

    def run_task(self, task_id: str) -> dict[str, Any]:
        with self._lock:
            if task_id in self._running_task_ids:
                raise RuntimeError("Task is already running.")
            self._running_task_ids.add(task_id)
        with SessionStore() as store:
            record = store.get_kanban_task(task_id)
            if record is None or record.directory != self._directory_key:
                with self._lock:
                    self._running_task_ids.discard(task_id)
                raise KeyError(task_id)
            if self._is_non_runnable_stage(record.stage):
                if record.stage == KANBAN_STAGE_DONE:
                    with self._lock:
                        self._running_task_ids.discard(task_id)
                    raise RuntimeError("Done tasks cannot run.")
            if record.stage == KANBAN_STAGE_BACKLOG:
                next_stage_id = self._next_runnable_board_stage_id(
                    record.stage,
                    store=store,
                )
                if next_stage_id is None:
                    with self._lock:
                        self._running_task_ids.discard(task_id)
                    raise RuntimeError(
                        "Backlog tasks require a runnable board stage before they can run."
                    )
                moved_record = store.move_kanban_task(task_id, stage=next_stage_id)
                if moved_record is None:
                    with self._lock:
                        self._running_task_ids.discard(task_id)
                    raise KeyError(task_id)
                record = moved_record
            stage_record = store.get_kanban_stage_config(
                self._directory_key,
                record.stage,
            )
            self._resolve_task_runtime(
                record,
                stage_record=stage_record,
                allow_fallback=False,
            )
            running_record = store.set_kanban_task_running(task_id)
        if running_record is None:
            with self._lock:
                self._running_task_ids.discard(task_id)
            raise KeyError(task_id)
        self._publish_task_updated(running_record)
        worker = threading.Thread(
            target=self._run_task_worker,
            args=(task_id,),
            daemon=True,
            name=f"pbi-agent-web-task-{task_id[:8]}",
        )
        worker.start()
        return self._serialize_task_record(running_record)

    def create_provider(
        self,
        *,
        provider_id: str | None,
        name: str,
        kind: str,
        api_key: str | None,
        api_key_env: str | None,
        responses_url: str | None,
        generic_api_url: str | None,
        expected_revision: str,
    ) -> dict[str, Any]:
        self._validate_secret_inputs(api_key=api_key, api_key_env=api_key_env)
        provider, revision = create_provider_config(
            ProviderConfig(
                id=slugify(provider_id or name),
                name=name,
                kind=kind,
                api_key=api_key or "",
                api_key_env=api_key_env,
                responses_url=responses_url,
                generic_api_url=generic_api_url,
            ),
            expected_revision=expected_revision,
        )
        return {"provider": self._provider_view(provider), "config_revision": revision}

    def update_provider(
        self,
        provider_id: str,
        *,
        name: str | None,
        kind: str | None,
        api_key: str | None,
        api_key_env: str | None,
        responses_url: str | None,
        generic_api_url: str | None,
        fields_set: set[str],
        expected_revision: str,
    ) -> dict[str, Any]:
        if "name" in fields_set and name is None:
            raise ConfigError("Provider name cannot be null.")
        if "kind" in fields_set and kind is None:
            raise ConfigError("Provider kind cannot be null.")
        self._validate_secret_inputs(
            api_key=api_key if "api_key" in fields_set else None,
            api_key_env=api_key_env if "api_key_env" in fields_set else None,
        )
        config = load_internal_config()
        provider = self._provider_map(config).get(slugify(provider_id))
        if provider is None:
            raise ConfigError(f"Unknown provider ID '{provider_id}'.")
        next_api_key = provider.api_key
        next_api_key_env = provider.api_key_env
        if "api_key" in fields_set:
            next_api_key = api_key or ""
            if api_key:
                next_api_key_env = None
        if "api_key_env" in fields_set:
            next_api_key_env = (api_key_env or "").strip() or None
            if next_api_key_env:
                next_api_key = ""
        merged = replace(
            provider,
            name=name if "name" in fields_set else provider.name,
            kind=kind if "kind" in fields_set else provider.kind,
            api_key=next_api_key,
            api_key_env=next_api_key_env,
            responses_url=(
                responses_url
                if "responses_url" in fields_set
                else provider.responses_url
            ),
            generic_api_url=(
                generic_api_url
                if "generic_api_url" in fields_set
                else provider.generic_api_url
            ),
        )
        updated, revision = replace_provider_config(
            provider_id, merged, expected_revision=expected_revision
        )
        return {"provider": self._provider_view(updated), "config_revision": revision}

    def delete_provider(
        self,
        provider_id: str,
        *,
        expected_revision: str,
    ) -> str:
        return delete_provider_config(provider_id, expected_revision=expected_revision)

    def create_model_profile(
        self,
        *,
        profile_id: str | None,
        name: str,
        provider_id: str,
        model: str | None,
        sub_agent_model: str | None,
        reasoning_effort: str | None,
        max_tokens: int | None,
        service_tier: str | None,
        web_search: bool | None,
        max_tool_workers: int | None,
        max_retries: int | None,
        compact_threshold: int | None,
        expected_revision: str,
    ) -> dict[str, Any]:
        config = load_internal_config()
        provider = self._require_provider(config, provider_id)
        profile, revision = create_model_profile_config(
            ModelProfileConfig(
                id=slugify(profile_id or name),
                name=name,
                provider_id=provider.id,
                model=model,
                sub_agent_model=sub_agent_model,
                reasoning_effort=reasoning_effort,
                max_tokens=max_tokens,
                service_tier=service_tier,
                web_search=web_search,
                max_tool_workers=max_tool_workers,
                max_retries=max_retries,
                compact_threshold=compact_threshold,
            ),
            expected_revision=expected_revision,
        )
        # The config snapshot loaded above is stale after the save — if there was
        # no active profile, create_model_profile_config auto-activated this one.
        active_profile_id = config.web.active_profile_id or profile.id
        return {
            "model_profile": self._model_profile_view(
                profile,
                provider=provider,
                active_profile_id=active_profile_id,
            ),
            "config_revision": revision,
        }

    def update_model_profile(
        self,
        profile_id: str,
        *,
        name: str | None,
        provider_id: str | None,
        model: str | None,
        sub_agent_model: str | None,
        reasoning_effort: str | None,
        max_tokens: int | None,
        service_tier: str | None,
        web_search: bool | None,
        max_tool_workers: int | None,
        max_retries: int | None,
        compact_threshold: int | None,
        fields_set: set[str],
        expected_revision: str,
    ) -> dict[str, Any]:
        if "name" in fields_set and name is None:
            raise ConfigError("Model profile name cannot be null.")
        if "provider_id" in fields_set and provider_id is None:
            raise ConfigError("provider_id cannot be null.")
        config = load_internal_config()
        profile = self._profile_map(config).get(slugify(profile_id))
        if profile is None:
            raise ConfigError(f"Unknown profile ID '{profile_id}'.")
        next_provider_id = (
            slugify(provider_id)
            if "provider_id" in fields_set and provider_id is not None
            else profile.provider_id
        )
        provider = self._require_provider(config, next_provider_id)
        merged = replace(
            profile,
            name=name if "name" in fields_set else profile.name,
            provider_id=next_provider_id,
            model=model if "model" in fields_set else profile.model,
            sub_agent_model=(
                sub_agent_model
                if "sub_agent_model" in fields_set
                else profile.sub_agent_model
            ),
            reasoning_effort=(
                reasoning_effort
                if "reasoning_effort" in fields_set
                else profile.reasoning_effort
            ),
            max_tokens=max_tokens if "max_tokens" in fields_set else profile.max_tokens,
            service_tier=(
                service_tier if "service_tier" in fields_set else profile.service_tier
            ),
            web_search=web_search if "web_search" in fields_set else profile.web_search,
            max_tool_workers=(
                max_tool_workers
                if "max_tool_workers" in fields_set
                else profile.max_tool_workers
            ),
            max_retries=(
                max_retries if "max_retries" in fields_set else profile.max_retries
            ),
            compact_threshold=(
                compact_threshold
                if "compact_threshold" in fields_set
                else profile.compact_threshold
            ),
        )
        updated, revision = replace_model_profile_config(
            profile_id, merged, expected_revision=expected_revision
        )
        return {
            "model_profile": self._model_profile_view(
                updated,
                provider=provider,
                active_profile_id=config.web.active_profile_id,
            ),
            "config_revision": revision,
        }

    def delete_model_profile(
        self,
        profile_id: str,
        *,
        expected_revision: str,
    ) -> str:
        return delete_model_profile_config(
            profile_id, expected_revision=expected_revision
        )

    def set_active_model_profile(
        self,
        profile_id: str | None,
        *,
        expected_revision: str,
    ) -> dict[str, Any]:
        active_id, revision = select_active_model_profile(
            profile_id, expected_revision=expected_revision
        )
        return {
            "active_profile_id": active_id,
            "config_revision": revision,
        }

    def shutdown(self) -> None:
        sessions = list(self._chat_sessions.values())
        for session in sessions:
            session.display.request_shutdown()
        for session in sessions:
            session.worker.join(timeout=1.5)

    def _run_chat_worker(self, live_session_id: str) -> None:
        live_session = self._chat_sessions[live_session_id]
        live_session.status = "running"
        self._publish_live_event(
            live_session_id,
            "session_state",
            {
                "state": "running",
                "live_session_id": live_session_id,
                "session_id": live_session.bound_session_id,
                "resume_session_id": live_session.bound_session_id,
            },
        )
        self._publish_live_session_lifecycle("live_session_updated", live_session)
        try:
            exit_code = run_chat_loop(
                live_session.runtime,
                live_session.display,
                resume_session_id=live_session.bound_session_id,
            )
            live_session.exit_code = exit_code
        except Exception as exc:
            live_session.exit_code = 1
            live_session.fatal_error = format_user_facing_error(exc)
            self._publish_live_event(
                live_session_id,
                "message_added",
                {
                    "item_id": f"fatal-{uuid.uuid4().hex}",
                    "role": "error",
                    "content": live_session.fatal_error,
                    "markdown": False,
                },
            )
        finally:
            live_session.status = "ended"
            live_session.ended_at = _now_iso()
            self._publish_live_event(
                live_session_id,
                "session_state",
                {
                    "state": "ended",
                    "live_session_id": live_session_id,
                    "session_id": live_session.bound_session_id,
                    "resume_session_id": live_session.bound_session_id,
                    "exit_code": live_session.exit_code,
                    "fatal_error": live_session.fatal_error,
                },
            )
            self._publish_live_session_lifecycle("live_session_ended", live_session)

    def _run_task_worker(self, task_id: str) -> None:
        def publish_summary(summary: str) -> None:
            with SessionStore() as store:
                updated = store.update_kanban_task(
                    task_id,
                    last_result_summary=summary,
                )
            if updated is not None:
                self._publish_task_updated(updated)

        try:
            while True:
                with SessionStore() as store:
                    record = store.get_kanban_task(task_id)
                    stage_record = store.get_kanban_stage_config(
                        self._directory_key,
                        record.stage if record is not None else "",
                    )
                if record is None:
                    raise KeyError(task_id)

                runtime = self._resolve_task_runtime(
                    record,
                    stage_record=stage_record,
                    allow_fallback=False,
                )
                outcome = run_single_turn_in_directory(
                    self._task_prompt_for_run(record.prompt, stage_record),
                    runtime,
                    KanbanTaskDisplay(
                        publish_summary=publish_summary,
                        verbose=runtime.settings.verbose,
                    ),
                    project_dir=record.project_dir,
                    workspace_root=self._workspace_root,
                    resume_session_id=record.session_id,
                )
                if outcome.tool_errors:
                    status = KANBAN_RUN_STATUS_FAILED
                    summary = shorten(
                        (outcome.text or "Completed with tool errors.").strip(),
                        200,
                    )
                else:
                    status = KANBAN_RUN_STATUS_COMPLETED
                    summary = shorten((outcome.text or "Completed.").strip(), 200)

                with SessionStore() as store:
                    updated = store.set_kanban_task_result(
                        task_id,
                        run_status=status,
                        summary=summary,
                        session_id=outcome.session_id,
                    )
                    if updated is None:
                        raise KeyError(task_id)
                    next_stage_id: str | None = None
                    if status == KANBAN_RUN_STATUS_FAILED:
                        next_record = updated
                    else:
                        next_stage_id = self._next_board_stage_id(
                            updated.stage, store=store
                        )
                        if next_stage_id is not None:
                            moved = store.move_kanban_task(task_id, stage=next_stage_id)
                            next_record = moved or updated
                        else:
                            next_record = updated
                self._publish_task_updated(next_record)
                if status == KANBAN_RUN_STATUS_FAILED:
                    break
                if next_stage_id is None or next_record.stage != next_stage_id:
                    break
                if not self._should_auto_start_stage(next_stage_id):
                    break
                with SessionStore() as store:
                    rerunning = store.set_kanban_task_running(task_id)
                if rerunning is None:
                    break
                self._publish_task_updated(rerunning)
        except Exception as exc:
            message = shorten(format_user_facing_error(exc), 200)
            with SessionStore() as store:
                updated = store.set_kanban_task_result(
                    task_id,
                    run_status=KANBAN_RUN_STATUS_FAILED,
                    summary=message,
                )
            if updated is not None:
                self._publish_task_updated(updated)
        finally:
            with self._lock:
                self._running_task_ids.discard(task_id)

    def _publish_task_updated(self, record: KanbanTaskRecord) -> dict[str, Any]:
        payload = self._serialize_task_record(record)
        self._app_stream.publish("task_updated", {"task": payload})
        return payload

    def _require_saved_session(self, session_id: str) -> SessionRecord:
        with SessionStore() as store:
            record = store.get_session(session_id)
        if record is None or record.directory != self._directory_key:
            raise KeyError(session_id)
        return record

    def _find_live_session_for_saved_session(
        self,
        session_id: str,
    ) -> LiveChatSession | None:
        with self._lock:
            return self._find_live_session_for_saved_session_locked(session_id)

    def _find_live_session_for_saved_session_locked(
        self,
        session_id: str,
    ) -> LiveChatSession | None:
        for live_session in self._chat_sessions.values():
            if live_session.bound_session_id != session_id:
                continue
            if live_session.status == "ended":
                continue
            return live_session
        return None

    def _bind_live_session(
        self,
        live_session_id: str,
        session_id: str | None,
    ) -> None:
        live_session = self._chat_sessions.get(live_session_id)
        if live_session is None:
            return
        previous_session_id = live_session.bound_session_id
        live_session.bound_session_id = session_id
        live_session.snapshot.session_id = session_id
        if previous_session_id != session_id:
            self._publish_live_session_lifecycle("live_session_bound", live_session)

    def _serialize_live_session(self, live_session: LiveChatSession) -> dict[str, Any]:
        return {
            "live_session_id": live_session.live_session_id,
            "session_id": live_session.bound_session_id,
            "resume_session_id": live_session.bound_session_id,
            "task_id": live_session.task_id,
            "kind": live_session.kind,
            "project_dir": live_session.project_dir,
            "provider_id": live_session.runtime.provider_id,
            "profile_id": live_session.runtime.profile_id,
            "provider": live_session.runtime.settings.provider,
            "model": live_session.runtime.settings.model,
            "reasoning_effort": live_session.runtime.settings.reasoning_effort,
            "created_at": live_session.created_at,
            "status": live_session.status,
            "exit_code": live_session.exit_code,
            "fatal_error": live_session.fatal_error,
            "ended_at": live_session.ended_at,
            "last_event_seq": live_session.snapshot.last_event_seq,
        }

    def _serialize_live_snapshot(self, live_session: LiveChatSession) -> dict[str, Any]:
        return {
            "live_session_id": live_session.live_session_id,
            "session_id": live_session.snapshot.session_id,
            "runtime": live_session.snapshot.runtime,
            "input_enabled": live_session.snapshot.input_enabled,
            "wait_message": live_session.snapshot.wait_message,
            "session_usage": live_session.snapshot.session_usage,
            "turn_usage": live_session.snapshot.turn_usage,
            "session_ended": live_session.snapshot.session_ended,
            "fatal_error": live_session.snapshot.fatal_error,
            "items": list(live_session.snapshot.items),
            "sub_agents": dict(live_session.snapshot.sub_agents),
            "last_event_seq": live_session.snapshot.last_event_seq,
        }

    def _serialize_task_record(self, record: KanbanTaskRecord) -> dict[str, Any]:
        stage_record = self._get_board_stage_record(record.stage)
        return _serialize_task(
            record,
            runtime=self._resolve_task_runtime(
                record,
                stage_record=stage_record,
            ),
        )

    def _require_live_session(self, live_session_id: str) -> LiveChatSession:
        live_session = self._chat_sessions.get(live_session_id)
        if live_session is None:
            raise KeyError(live_session_id)
        return live_session

    def _get_board_stage_record(self, stage_id: str) -> KanbanStageConfigRecord | None:
        with SessionStore() as store:
            return store.get_kanban_stage_config(self._directory_key, stage_id)

    def _default_board_stage_id(self) -> str:
        with SessionStore() as store:
            stages = store.list_kanban_stage_configs(self._directory_key)
        if not stages:
            raise ConfigError("Board must contain at least one stage.")
        return stages[0].stage_id

    def _next_board_stage_id(
        self,
        current_stage_id: str,
        *,
        store: SessionStore | None = None,
    ) -> str | None:
        if store is None:
            with SessionStore() as owned_store:
                return self._next_board_stage_id(current_stage_id, store=owned_store)
        stages = store.list_kanban_stage_configs(self._directory_key)
        for index, stage in enumerate(stages):
            if stage.stage_id == current_stage_id:
                if index + 1 < len(stages):
                    return stages[index + 1].stage_id
                return None
        return None

    def _next_runnable_board_stage_id(
        self,
        current_stage_id: str,
        *,
        store: SessionStore | None = None,
    ) -> str | None:
        next_stage_id = self._next_board_stage_id(current_stage_id, store=store)
        while next_stage_id is not None and self._is_non_runnable_stage(next_stage_id):
            next_stage_id = self._next_board_stage_id(next_stage_id, store=store)
        return next_stage_id

    def _is_non_runnable_stage(self, stage_id: str) -> bool:
        return stage_id in _NON_RUNNABLE_BOARD_STAGE_IDS

    def _should_auto_start_stage(self, stage_id: str) -> bool:
        if self._is_non_runnable_stage(stage_id):
            return False
        stage_record = self._get_board_stage_record(stage_id)
        return bool(stage_record and stage_record.auto_start)

    def _resolve_task_runtime(
        self,
        record: KanbanTaskRecord,
        *,
        stage_record: KanbanStageConfigRecord | None = None,
        allow_fallback: bool = True,
    ) -> ResolvedRuntime:
        resolved_profile_id = record.model_profile_id or (
            stage_record.model_profile_id if stage_record is not None else None
        )
        if allow_fallback:
            return self._resolve_runtime_or_default(resolved_profile_id)
        return self._resolve_runtime(resolved_profile_id)

    def _task_prompt_for_run(
        self,
        prompt: str,
        stage_record: KanbanStageConfigRecord | None,
    ) -> str:
        stripped_prompt = prompt.strip()
        if (
            not stripped_prompt
            or stripped_prompt.startswith("/")
            or stage_record is None
            or not stage_record.command_id
        ):
            return prompt
        command = self._command_map().get(stage_record.command_id)
        if command is None:
            return prompt
        return f"{command.slash_alias} {prompt}"

    def _maybe_auto_start_task(self, record: KanbanTaskRecord) -> dict[str, Any] | None:
        if not self._should_auto_start_stage(record.stage):
            return None
        return self.run_task(record.task_id)

    def _validate_project_dir(self, project_dir: str) -> None:
        candidate = project_dir.strip() or "."
        target = (self._workspace_root / candidate).resolve()
        target.relative_to(self._workspace_root)
        if not target.exists():
            raise FileNotFoundError(f"Project directory does not exist: {target}")
        if not target.is_dir():
            raise NotADirectoryError(f"Project path is not a directory: {target}")

    def _resolve_runtime(self, profile_id: str | None) -> ResolvedRuntime:
        if profile_id is None:
            if self._runtime_args is None:
                return self._default_runtime
            return resolve_web_runtime(verbose=self._default_runtime.settings.verbose)
        return resolve_runtime_for_profile_id(
            profile_id,
            verbose=self._default_runtime.settings.verbose,
        )

    def _resolve_runtime_optional(
        self,
        profile_id: str | None,
    ) -> ResolvedRuntime | None:
        try:
            return self._resolve_runtime(profile_id)
        except ConfigError:
            return None

    def _resolve_runtime_or_default(
        self,
        profile_id: str | None,
    ) -> ResolvedRuntime:
        runtime = self._resolve_runtime_optional(profile_id)
        if runtime is not None:
            return runtime
        return self._default_runtime

    def _resolve_saved_session_runtime(
        self,
        session_id: str,
        *,
        fallback: ResolvedRuntime,
    ) -> ResolvedRuntime:
        try:
            with SessionStore() as store:
                record = store.get_session(session_id)
        except Exception:
            return fallback
        if record is None or record.directory != self._directory_key:
            return fallback
        if record.profile_id:
            return self._resolve_runtime_or_default(record.profile_id)
        settings = replace(
            fallback.settings,
            provider=record.provider or fallback.settings.provider,
            model=record.model or fallback.settings.model,
        )
        return ResolvedRuntime(
            settings=settings,
            provider_id=record.provider_id or fallback.provider_id,
            profile_id=None,
        )

    def _queue_runtime_change(
        self,
        live_session: LiveChatSession,
        profile_id: str | None,
    ) -> None:
        runtime = self._resolve_runtime(profile_id)
        live_session.runtime = runtime
        live_session.display.request_runtime_change(
            runtime=runtime,
            profile_id=runtime.profile_id,
        )
        self._publish_live_session_runtime(live_session)
        self._publish_live_session_lifecycle("live_session_updated", live_session)

    def _publish_live_session_runtime(self, live_session: LiveChatSession) -> None:
        self._publish_live_event(
            live_session.live_session_id,
            "session_runtime_updated",
            {
                "live_session_id": live_session.live_session_id,
                "session_id": live_session.bound_session_id,
                "resume_session_id": live_session.bound_session_id,
                "provider_id": live_session.runtime.provider_id,
                "profile_id": live_session.runtime.profile_id,
                "provider": live_session.runtime.settings.provider,
                "model": live_session.runtime.settings.model,
                "reasoning_effort": live_session.runtime.settings.reasoning_effort,
            },
        )

    def _publish_live_event(
        self,
        live_session_id: str,
        event_type: str,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        live_session = self._chat_sessions[live_session_id]
        event = live_session.event_stream.publish(event_type, payload)
        self._apply_live_event(live_session, event)
        return event

    def _apply_live_event(
        self,
        live_session: LiveChatSession,
        event: dict[str, Any],
    ) -> None:
        snapshot = live_session.snapshot
        snapshot.last_event_seq = int(event["seq"])
        payload = event["payload"]
        event_type = event["type"]

        if event_type == "chat_reset":
            snapshot.items = []
            snapshot.sub_agents = {}
            snapshot.wait_message = None
            snapshot.turn_usage = None
            snapshot.session_ended = False
            snapshot.fatal_error = None
            return
        if event_type == "session_identity":
            snapshot.session_id = (
                payload["session_id"]
                if isinstance(payload.get("session_id"), str)
                else None
            )
            return
        if event_type == "input_state":
            snapshot.input_enabled = bool(payload.get("enabled"))
            return
        if event_type == "wait_state":
            snapshot.wait_message = (
                str(payload.get("message") or "Working...")
                if payload.get("active")
                else None
            )
            return
        if event_type == "usage_updated":
            if payload.get("scope") == "session":
                snapshot.session_usage = payload.get("usage")
            else:
                snapshot.turn_usage = {
                    "usage": payload.get("usage"),
                    "elapsed_seconds": payload.get("elapsed_seconds"),
                }
            return
        if event_type in {"message_added", "thinking_updated", "tool_group_added"}:
            item = dict(payload)
            item["kind"] = (
                "message"
                if event_type == "message_added"
                else "thinking"
                if event_type == "thinking_updated"
                else "tool_group"
            )
            item["itemId"] = str(payload.get("item_id") or "")
            snapshot.items = self._upsert_snapshot_item(snapshot.items, item)
            return
        if event_type == "sub_agent_state":
            sub_agent_id = str(payload.get("sub_agent_id") or "")
            snapshot.sub_agents[sub_agent_id] = {
                "title": str(payload.get("title") or "sub_agent"),
                "status": str(payload.get("status") or "running"),
            }
            return
        if event_type == "session_state":
            if "session_id" in payload:
                snapshot.session_id = (
                    payload["session_id"]
                    if isinstance(payload.get("session_id"), str)
                    else None
                )
            if payload.get("state") == "ended":
                snapshot.session_ended = True
                snapshot.input_enabled = False
                snapshot.wait_message = None
                snapshot.fatal_error = (
                    str(payload["fatal_error"])
                    if isinstance(payload.get("fatal_error"), str)
                    else None
                )
            else:
                snapshot.session_ended = False
                snapshot.fatal_error = None
            return
        if event_type == "session_runtime_updated":
            snapshot.runtime = {
                "provider": payload.get("provider"),
                "provider_id": payload.get("provider_id"),
                "profile_id": payload.get("profile_id"),
                "model": payload.get("model"),
                "reasoning_effort": payload.get("reasoning_effort"),
            }

    def _upsert_snapshot_item(
        self,
        items: list[dict[str, Any]],
        next_item: dict[str, Any],
    ) -> list[dict[str, Any]]:
        item_id = str(next_item.get("itemId") or "")
        for index, item in enumerate(items):
            if str(item.get("itemId") or "") != item_id:
                continue
            updated = list(items)
            updated[index] = next_item
            return updated
        return [*items, next_item]

    def _publish_live_session_lifecycle(
        self,
        event_type: str,
        live_session: LiveChatSession,
    ) -> None:
        self._app_stream.publish(
            event_type,
            {"live_session": self._serialize_live_session(live_session)},
        )

    def _provider_view(self, provider: ProviderConfig) -> dict[str, Any]:
        return {
            "id": provider.id,
            "name": provider.name,
            "kind": provider.kind,
            "responses_url": provider.responses_url,
            "generic_api_url": provider.generic_api_url,
            "secret_source": provider_secret_source(provider),
            "secret_env_var": provider.api_key_env,
            "has_secret": provider_has_secret(provider),
        }

    def _model_profile_view(
        self,
        profile: ModelProfileConfig,
        *,
        provider: ProviderConfig,
        active_profile_id: str | None,
    ) -> dict[str, Any]:
        runtime = self._resolve_runtime_or_default(profile.id)
        return {
            "id": profile.id,
            "name": profile.name,
            "provider_id": profile.provider_id,
            "provider": {
                "id": provider.id,
                "name": provider.name,
                "kind": provider.kind,
            },
            "model": profile.model,
            "sub_agent_model": profile.sub_agent_model,
            "reasoning_effort": profile.reasoning_effort,
            "max_tokens": profile.max_tokens,
            "service_tier": profile.service_tier,
            "web_search": profile.web_search,
            "max_tool_workers": profile.max_tool_workers,
            "max_retries": profile.max_retries,
            "compact_threshold": profile.compact_threshold,
            "is_active_default": profile.id == active_profile_id,
            "resolved_runtime": _resolved_runtime_view(runtime),
        }

    def _command_view(self, command: CommandConfig) -> dict[str, Any]:
        return {
            "id": command.id,
            "name": command.name,
            "slash_alias": command.slash_alias,
            "description": command.description,
            "instructions": command.instructions,
            "path": command.path,
        }

    def _provider_map(self, config: InternalConfig) -> dict[str, ProviderConfig]:
        return {provider.id: provider for provider in config.providers}

    def _profile_map(self, config: InternalConfig) -> dict[str, ModelProfileConfig]:
        return {profile.id: profile for profile in config.model_profiles}

    def _command_map(self) -> dict[str, CommandConfig]:
        return {
            command.id: command
            for command in list_command_configs(self._workspace_root)
        }

    def _require_provider(
        self, config: InternalConfig, provider_id: str
    ) -> ProviderConfig:
        provider = self._provider_map(config).get(slugify(provider_id))
        if provider is None:
            raise ConfigError(f"Unknown provider ID '{provider_id}'.")
        return provider

    def _validate_secret_inputs(
        self,
        *,
        api_key: str | None,
        api_key_env: str | None,
    ) -> None:
        if api_key and api_key_env:
            raise ConfigError(
                "api_key and api_key_env cannot both be set in the same request."
            )
