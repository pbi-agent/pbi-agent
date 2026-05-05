from __future__ import annotations

from typing import Any

from pbi_agent.session_store import KanbanTaskRecord, SessionRecord, SessionStore
from pbi_agent.web.session.serializers import (
    _RUN_RECORD_STATUSES,
    _combined_timeline_snapshot,
    _deserialize_json_field,
    _serialize_history_message,
    _serialize_observability_event,
    _serialize_run_as_live_session,
    _serialize_run_session,
    _serialize_session,
    _session_status_from_run,
)
from pbi_agent.web.uploads import delete_uploaded_images


class SavedSessionsMixin:
    def list_sessions(self, limit: int = 30) -> list[dict[str, Any]]:
        with SessionStore() as store:
            sessions = store.list_sessions(
                self._directory_key,
                limit=limit,
            )
            active_runs = {
                session.session_id: store.get_latest_session_run(
                    session.session_id,
                    include_ended=False,
                )
                for session in sessions
            }
            latest_runs = {
                session.session_id: store.get_latest_session_run(
                    session.session_id,
                    include_ended=True,
                )
                for session in sessions
            }
            latest_web_runs = {
                session.session_id: store.get_latest_web_session_run(session.session_id)
                for session in sessions
            }
        return [
            _serialize_session(
                session,
                active_live_session=self._find_live_session_for_saved_session(
                    session.session_id
                ),
                active_run=active_runs.get(session.session_id),
                status_run=latest_web_runs.get(session.session_id)
                or latest_runs.get(session.session_id),
            )
            for session in sessions
        ]

    def create_session_record(
        self,
        *,
        title: str = "",
        profile_id: str | None = None,
    ) -> dict[str, Any]:
        runtime = self._resolve_runtime(profile_id)
        with SessionStore() as store:
            session_id = store.create_session(
                str(self._workspace_root),
                runtime.settings.provider,
                runtime.settings.model,
                title=title,
                provider_id=runtime.provider_id,
                profile_id=runtime.profile_id,
            )
            record = store.get_session(session_id)
        if record is None:
            raise KeyError(session_id)
        serialized = _serialize_session(record)
        self._app_stream.publish("session_created", {"session": serialized})
        return serialized

    def get_session_detail(self, session_id: str) -> dict[str, Any]:
        with SessionStore() as store:
            record = store.get_session(session_id)
            if record is None or record.directory != self._directory_key:
                raise KeyError(session_id)
            messages = store.list_messages(session_id)
            latest_run = store.get_latest_session_run(session_id, include_ended=True)
            active_run = store.get_latest_session_run(session_id, include_ended=False)
            latest_web_run = store.get_latest_web_session_run(session_id)
            web_runs = store.list_web_session_runs(session_id)
        live_session = self._find_live_session_for_saved_session(session_id)
        serialized_active_live_session = (
            self._serialize_live_session(live_session)
            if live_session is not None
            else None
        )
        serialized_active_run = (
            _serialize_run_as_live_session(active_run)
            if active_run is not None and live_session is None
            else None
        )
        live_snapshot = (
            self._serialize_live_snapshot(live_session)
            if live_session is not None
            else None
        )
        timeline = _combined_timeline_snapshot(web_runs, live_snapshot)
        return {
            "session": _serialize_session(
                record,
                active_live_session=live_session,
                active_run=active_run,
                status_run=active_run or latest_web_run or latest_run,
            ),
            "status": live_session.status
            if live_session is not None
            else _session_status_from_run(active_run)
            if active_run is not None
            else _session_status_from_run(latest_web_run)
            if latest_web_run is not None
            else _session_status_from_run(latest_run)
            if latest_run is not None
            else "idle",
            "history_items": [
                _serialize_history_message(message) for message in messages
            ],
            "timeline": timeline,
            "live_session": serialized_active_live_session,
            "active_live_session": serialized_active_live_session,
            "active_run": serialized_active_run,
        }

    def update_session_title(self, session_id: str, title: str) -> dict[str, Any]:
        with SessionStore() as store:
            record = store.get_session(session_id)
            if record is None or record.directory != self._directory_key:
                raise KeyError(session_id)
            store.update_session(session_id, title=title)
            updated = store.get_session(session_id)
        if updated is None:
            raise KeyError(session_id)
        serialized = _serialize_session(updated)
        self._app_stream.publish("session_updated", {"session": serialized})
        return serialized

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
            "events": [
                _serialize_observability_event(event)
                for event in events
                if event.event_type != "web_event"
            ],
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
            if run_dict.get("status") not in _RUN_RECORD_STATUSES:
                run_dict["status"] = (
                    "failed" if run_dict.get("fatal_error") else "started"
                )
            # Drop the autoincrement id; it's an internal detail.
            run_dict.pop("id", None)
            run_dict["session_title"] = session_title
            runs.append(run_dict)
        return {"runs": runs, "total_count": total_count}

    def delete_session(self, session_id: str) -> None:
        with self._lock:
            if self._find_live_session_for_saved_session_locked(session_id) is not None:
                raise RuntimeError(
                    "Cannot delete a session while an active run is still running."
                )

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
                if any(
                    task.task_id in self._running_task_ids for task in affected_tasks
                ):
                    raise RuntimeError(
                        "Cannot delete a session while an active run is still running."
                    )
                updated_tasks: list[KanbanTaskRecord] = []
                for task in affected_tasks:
                    updated = store.update_kanban_task(
                        task.task_id, clear_session_id=True
                    )
                    if updated is not None:
                        updated_tasks.append(updated)

                task_upload_ids = {
                    attachment.upload_id
                    for task in store.list_kanban_tasks(self._directory_key)
                    for attachment in task.image_attachments
                }
                upload_ids = [
                    attachment.upload_id
                    for message in store.list_messages(session_id)
                    for attachment in message.image_attachments
                    if attachment.upload_id not in task_upload_ids
                ]

                deleted = store.delete_session(session_id)

        if not deleted:
            raise KeyError(session_id)

        delete_uploaded_images(upload_ids)

        for task in updated_tasks:
            self._publish_task_updated(task)

    def _require_saved_session(self, session_id: str) -> SessionRecord:
        with SessionStore() as store:
            record = store.get_session(session_id)
        if record is None or record.directory != self._directory_key:
            raise KeyError(session_id)
        return record
