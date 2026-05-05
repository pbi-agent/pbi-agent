from __future__ import annotations

import threading
import uuid
from typing import Any

from pbi_agent.agent.error_formatting import format_user_facing_error
from pbi_agent.config import ConfigError, ResolvedRuntime, load_internal_config, slugify
from pbi_agent.display.formatting import shorten
from pbi_agent.session_store import (
    KANBAN_STAGE_BACKLOG,
    KANBAN_STAGE_DONE,
    KANBAN_RUN_STATUS_FAILED,
    KanbanStageConfigRecord,
    KanbanStageConfigSpec,
    KanbanTaskRecord,
    MessageImageAttachment,
    MessageRecord,
    SessionStore,
)
from pbi_agent.web.display import WebDisplay, _plain_text
from pbi_agent.web.session.serializers import (
    _runtime_summary,
    _serialize_board_stage,
    _serialize_history_message,
    _serialize_task,
)
from pbi_agent.web.session.state import (
    EventStream,
    LiveSessionSnapshot,
    LiveSessionState,
    _now_iso,
)

_NON_RUNNABLE_BOARD_STAGE_IDS = frozenset({KANBAN_STAGE_BACKLOG, KANBAN_STAGE_DONE})


class TasksMixin:
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

    def create_task(
        self,
        *,
        title: str,
        prompt: str,
        stage: str | None = None,
        project_dir: str = ".",
        session_id: str | None = None,
        profile_id: str | None = None,
        image_upload_ids: list[str] | None = None,
    ) -> dict[str, Any]:
        self._validate_project_dir(project_dir)
        if profile_id is not None:
            self._resolve_runtime(profile_id)
        stage_id = stage or self._default_board_stage_id()
        normalized_title, normalized_prompt = self._normalize_task_content(
            title=title,
            prompt=prompt,
        )
        image_attachments = self._message_attachments_for_upload_ids(
            image_upload_ids or []
        )
        with SessionStore() as store:
            record = store.create_kanban_task(
                directory=self._directory_key,
                title=normalized_title,
                prompt=normalized_prompt,
                stage=stage_id,
                project_dir=project_dir,
                session_id=session_id,
                model_profile_id=profile_id,
                image_attachments=image_attachments,
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
        image_upload_ids: list[str] | None = None,
        image_upload_ids_present: bool = False,
    ) -> dict[str, Any]:
        with self._lock:
            if task_id in self._running_task_ids:
                raise RuntimeError("Cannot update a running task.")
        if project_dir is not None:
            self._validate_project_dir(project_dir)
        if profile_id_present and profile_id is not None:
            self._resolve_runtime(profile_id)
        image_attachments = (
            self._message_attachments_for_upload_ids(image_upload_ids or [])
            if image_upload_ids_present
            else None
        )
        with SessionStore() as store:
            current = store.get_kanban_task(task_id)
            if current is None or current.directory != self._directory_key:
                raise KeyError(task_id)
            previous_stage = current.stage
            normalized_title = current.title if title is None else title
            normalized_prompt = current.prompt if prompt is None else prompt
            if title is not None or prompt is not None:
                normalized_title, normalized_prompt = self._normalize_task_content(
                    title=normalized_title,
                    prompt=normalized_prompt,
                )
            if stage is not None or position is not None:
                current = store.move_kanban_task(
                    task_id,
                    stage=stage or current.stage,
                    position=position,
                )
                assert current is not None
            updated = store.update_kanban_task(
                task_id,
                title=normalized_title
                if title is not None or prompt is not None
                else title,
                prompt=normalized_prompt
                if title is not None or prompt is not None
                else prompt,
                project_dir=project_dir,
                session_id=session_id,
                clear_session_id=session_id_present and session_id is None,
                model_profile_id=profile_id,
                clear_model_profile_id=(profile_id_present and profile_id is None),
                image_attachments=image_attachments,
                image_attachments_present=image_upload_ids_present,
            )
        if updated is None:
            raise KeyError(task_id)
        payload = self._publish_task_updated(updated)
        if stage is not None and stage != previous_stage:
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
            self._ensure_worker_creation_allowed_locked()
            if task_id in self._running_task_ids:
                raise RuntimeError("Task is already running.")
            self._running_task_ids.add(task_id)
        worker_registered = False
        worker_started = False
        live_session: LiveSessionState | None = None
        running_record: KanbanTaskRecord | None = None
        mutated_record: KanbanTaskRecord | None = None
        initial_user_message_id: int | None = None
        try:
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
                is_continuation = False
                started_from_backlog = record.stage == KANBAN_STAGE_BACKLOG
                if started_from_backlog:
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
                    mutated_record = record
                existing_session_id = record.session_id
                if existing_session_id is not None:
                    existing_messages = store.list_messages(existing_session_id)
                    is_continuation = any(
                        message.content.strip() != record.prompt.strip()
                        for message in existing_messages
                        if message.role == "user"
                    )
                if started_from_backlog:
                    is_continuation = False
                stage_record = store.get_kanban_stage_config(
                    self._directory_key,
                    record.stage,
                )
                runtime = self._resolve_task_runtime(
                    record,
                    stage_record=stage_record,
                    allow_fallback=False,
                )
                initial_prompt = self._task_prompt_for_run(
                    record,
                    stage_record,
                    store=store,
                    is_continuation=is_continuation,
                )
                if record.session_id is None:
                    session_id = store.create_session(
                        directory=self._directory_key,
                        provider=runtime.settings.provider,
                        provider_id=runtime.provider_id or None,
                        model=runtime.settings.model,
                        profile_id=runtime.profile_id or None,
                        title=record.title,
                    )
                    updated_record = store.update_kanban_task(
                        task_id,
                        session_id=session_id,
                    )
                    if updated_record is None:
                        with self._lock:
                            self._running_task_ids.discard(task_id)
                        raise KeyError(task_id)
                    record = updated_record
                    mutated_record = record
                initial_user_message_id = None
                if not is_continuation:
                    initial_user_message_id = self._persist_task_user_prompt(
                        store,
                        record,
                        runtime,
                        initial_prompt,
                        list(record.image_attachments),
                    )
                running_record = store.set_kanban_task_running(task_id)
            if running_record is None:
                with self._lock:
                    self._running_task_ids.discard(task_id)
                raise KeyError(task_id)
            live_session = self._create_task_live_session(running_record, runtime)
            if initial_user_message_id is not None:
                self._publish_persisted_user_message(
                    live_session,
                    running_record,
                    runtime,
                    initial_prompt,
                    initial_user_message_id,
                    list(running_record.image_attachments),
                )
            self._publish_task_updated(running_record)
            worker = threading.Thread(
                target=self._run_task_worker,
                args=(task_id, live_session.live_session_id, initial_user_message_id),
                daemon=True,
                name=f"pbi-agent-web-task-{task_id[:8]}",
            )
            with self._lock:
                self._ensure_worker_creation_allowed_locked()
                live_session.worker = worker
                self._task_workers[task_id] = worker
                worker_registered = True
            worker.start()
            worker_started = True
            return self._serialize_task_record(running_record)
        except Exception as exc:
            if not worker_started:
                if worker_registered:
                    with self._lock:
                        self._task_workers.pop(task_id, None)
                        if live_session is not None:
                            live_session.worker = None
                with self._lock:
                    self._running_task_ids.discard(task_id)
                failure_record = running_record or mutated_record
                if failure_record is not None:
                    message = shorten(format_user_facing_error(exc), 200)
                    with SessionStore() as store:
                        updated = store.set_kanban_task_result(
                            task_id,
                            run_status=KANBAN_RUN_STATUS_FAILED,
                            summary=message,
                        )
                    live_sessions = []
                    if live_session is not None:
                        live_sessions.append(live_session)
                    else:
                        with self._lock:
                            live_sessions.extend(
                                candidate
                                for candidate in self._live_sessions.values()
                                if candidate.task_id == task_id
                                and candidate.worker is None
                                and candidate.status != "ended"
                            )
                    for current_live_session in live_sessions:
                        current_live_session.exit_code = 1
                        current_live_session.fatal_error = format_user_facing_error(exc)
                        with self._lock:
                            self._finalize_live_session_locked(current_live_session)
                    if updated is not None:
                        self._publish_task_updated(updated)
                self._finalize_shutdown_if_idle()
            raise

    def _create_task_live_session(
        self,
        record: KanbanTaskRecord,
        runtime: ResolvedRuntime,
    ) -> LiveSessionState:
        bound_session_id = record.session_id
        new_live_session_id = uuid.uuid4().hex
        event_stream = EventStream()
        snapshot = LiveSessionSnapshot(
            session_id=bound_session_id,
            runtime=_runtime_summary(runtime),
        )
        display = WebDisplay(
            publish_event=lambda event_type, payload, current=new_live_session_id: (
                self._publish_task_live_event(
                    current,
                    record.task_id,
                    event_type,
                    payload,
                )
            ),
            verbose=runtime.settings.verbose,
            model=runtime.settings.model,
            reasoning_effort=runtime.settings.reasoning_effort,
            bind_session=lambda next_bound_session_id, current=new_live_session_id: (
                self._bind_live_session(current, next_bound_session_id)
            ),
        )
        live_session = LiveSessionState(
            live_session_id=new_live_session_id,
            event_stream=event_stream,
            snapshot=snapshot,
            display=display,
            worker=None,
            runtime=runtime,
            bound_session_id=bound_session_id,
            created_at=_now_iso(),
            kind="task",
            task_id=record.task_id,
            project_dir=record.project_dir,
            status="starting",
        )
        with self._lock:
            self._live_sessions[new_live_session_id] = live_session
        self._create_live_run_projection(live_session)
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
        return live_session

    def _persist_task_user_prompt(
        self,
        store: SessionStore,
        record: KanbanTaskRecord,
        runtime: ResolvedRuntime,
        prompt: str,
        image_attachments: list[MessageImageAttachment],
    ) -> int | None:
        if record.session_id is None:
            return None
        return store.add_message(
            record.session_id,
            "user",
            prompt.strip(),
            provider_id=runtime.provider_id or None,
            profile_id=runtime.profile_id or None,
            image_attachments=image_attachments,
        )

    def _publish_persisted_user_message(
        self,
        live_session: LiveSessionState,
        record: KanbanTaskRecord,
        runtime: ResolvedRuntime,
        prompt: str,
        message_id: int,
        image_attachments: list[MessageImageAttachment],
    ) -> None:
        if record.session_id is None:
            return
        message = MessageRecord(
            id=message_id,
            session_id=record.session_id,
            role="user",
            content=prompt.strip(),
            provider_id=runtime.provider_id or None,
            profile_id=runtime.profile_id or None,
            image_attachments=list(image_attachments),
            created_at=_now_iso(),
        )
        self._publish_task_live_event(
            live_session.live_session_id,
            record.task_id,
            "message_added",
            _serialize_history_message(message),
        )

    def _publish_task_live_event(
        self,
        live_session_id: str,
        task_id: str,
        event_type: str,
        payload: dict[str, Any],
    ) -> dict[str, Any] | None:
        event = self._publish_live_event(live_session_id, event_type, payload)
        if event is None:
            return None
        summary = self._summary_for_task_live_event(event_type, payload)
        if summary is not None:
            with SessionStore() as store:
                updated = store.update_kanban_task(
                    task_id,
                    last_result_summary=summary,
                )
            if updated is not None:
                self._publish_task_updated(updated)
        return event

    def _summary_for_task_live_event(
        self,
        event_type: str,
        payload: dict[str, Any],
    ) -> str | None:
        if event_type == "message_added":
            content = str(payload.get("content") or "").strip()
            if content:
                return shorten(_plain_text(content), 200)
        if event_type == "thinking_updated":
            title = str(payload.get("title") or "").strip()
            if title:
                return title
            content = str(payload.get("content") or "").strip()
            if content:
                return shorten(content, 120)
        if event_type == "tool_group_added":
            tools = payload.get("tools")
            if isinstance(tools, list) and tools:
                latest = tools[-1]
                if isinstance(latest, dict):
                    text = str(latest.get("text") or latest.get("name") or "").strip()
                    if text:
                        return shorten(text, 200)
        if event_type == "wait_state" and payload.get("active"):
            return str(payload.get("message") or "Working...")
        return None

    def _publish_task_updated(self, record: KanbanTaskRecord) -> dict[str, Any]:
        payload = self._serialize_task_record(record)
        self._app_stream.publish("task_updated", {"task": payload})
        return payload

    def _serialize_task_record(self, record: KanbanTaskRecord) -> dict[str, Any]:
        stage_record = self._get_board_stage_record(record.stage)
        return _serialize_task(
            record,
            runtime=self._resolve_task_runtime(
                record,
                stage_record=stage_record,
            ),
        )

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

    def _first_runnable_board_stage_id(
        self,
        *,
        store: SessionStore | None = None,
    ) -> str | None:
        if store is None:
            with SessionStore() as owned_store:
                return self._first_runnable_board_stage_id(store=owned_store)
        stages = store.list_kanban_stage_configs(self._directory_key)
        for stage in stages:
            if not self._is_non_runnable_stage(stage.stage_id):
                return stage.stage_id
        return None

    def _should_auto_start_stage(self, stage_id: str) -> bool:
        if self._is_non_runnable_stage(stage_id):
            return False
        stage_record = self._get_board_stage_record(stage_id)
        return bool(stage_record and stage_record.auto_start)

    def _task_prompt_for_run(
        self,
        record: KanbanTaskRecord,
        stage_record: KanbanStageConfigRecord | None,
        *,
        store: SessionStore | None = None,
        is_continuation: bool = False,
    ) -> str:
        prompt = record.prompt
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
        if is_continuation:
            return command.slash_alias
        first_runnable_stage_id = self._first_runnable_board_stage_id(store=store)
        if stage_record.stage_id != first_runnable_stage_id:
            return command.slash_alias
        return (
            f"{command.slash_alias}\n{self._format_task_prompt(record.title, prompt)}"
        )

    def _normalize_task_content(
        self,
        *,
        title: str | None,
        prompt: str | None,
    ) -> tuple[str | None, str | None]:
        normalized_title = title.strip() if isinstance(title, str) else title
        normalized_prompt = prompt.strip() if isinstance(prompt, str) else prompt
        if normalized_prompt is None:
            return normalized_title, None
        derived_title = normalized_title or self._derive_task_title(normalized_prompt)
        return derived_title, normalized_prompt

    def _derive_task_title(self, prompt: str) -> str:
        lines = [line.strip(" -*\t") for line in prompt.splitlines() if line.strip()]
        if not lines:
            return "Untitled task"
        return shorten(lines[0], 80)

    def _format_task_prompt(self, title: str, prompt: str) -> str:
        return f"# Task\n{title}\n\n## Goal\n{prompt}"

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
