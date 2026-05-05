from __future__ import annotations

import threading
import uuid

from pbi_agent.agent.error_formatting import format_user_facing_error
from pbi_agent.agent.session import SessionTurnInterrupted, run_session_loop
from pbi_agent.display.formatting import shorten
from pbi_agent.session_store import (
    KANBAN_RUN_STATUS_COMPLETED,
    KANBAN_RUN_STATUS_FAILED,
    KANBAN_RUN_STATUS_RUNNING,
    SessionStore,
)
from pbi_agent.task_runner import run_single_turn_in_directory
from pbi_agent.web.display import WebDisplay
from pbi_agent.web.session.state import _now_iso
from pbi_agent.web.uploads import load_uploaded_image

_WEB_MANAGER_LEASE_HEARTBEAT_SECS = 5.0
_SHUTDOWN_INTERRUPTED_MESSAGE = "Interrupted during app shutdown."
_TASK_FINALIZATION_PERSISTENCE_FAILED_MESSAGE = (
    "Failed to persist terminal live session finalization."
)


class WorkersMixin:
    def _ensure_worker_creation_allowed_locked(self) -> None:
        if self._shutdown_requested:
            raise RuntimeError("Manager shutdown is in progress.")
        if not self._started:
            raise RuntimeError("Manager is not started.")

    def _finalize_live_session_locked(self, live_session) -> None:  # noqa: ANN001
        if live_session.ended_at is not None:
            return
        previous_status = live_session.status
        previous_ended_at = live_session.ended_at
        previous_exit_code = live_session.exit_code
        previous_fatal_error = live_session.fatal_error
        previous_terminal_status = live_session.terminal_status
        if live_session.exit_code is None:
            live_session.exit_code = 0
        live_session.status = "ended"
        live_session.ended_at = _now_iso()
        try:
            self._publish_live_event(
                live_session.live_session_id,
                "session_state",
                {
                    "state": "ended",
                    "live_session_id": live_session.live_session_id,
                    "session_id": live_session.bound_session_id,
                    "resume_session_id": live_session.bound_session_id,
                    "exit_code": live_session.exit_code,
                    "fatal_error": live_session.fatal_error,
                },
                allow_after_end=True,
            )
        except Exception:
            live_session.status = previous_status
            live_session.ended_at = previous_ended_at
            live_session.exit_code = previous_exit_code
            live_session.fatal_error = previous_fatal_error
            live_session.terminal_status = previous_terminal_status
            raise
        self._publish_live_session_lifecycle("live_session_ended", live_session)

    def _mark_task_live_session_finalization_failed_locked(
        self,
        live_session,  # noqa: ANN001
        exc: Exception,
    ) -> None:
        if live_session.ended_at is not None:
            return
        message = f"{_TASK_FINALIZATION_PERSISTENCE_FAILED_MESSAGE} {exc}"
        live_session.status = "failed"
        live_session.ended_at = _now_iso()
        if live_session.exit_code is None:
            live_session.exit_code = 1
        live_session.fatal_error = message
        live_session.snapshot.session_ended = True
        live_session.snapshot.input_enabled = False
        live_session.snapshot.wait_message = None
        live_session.snapshot.processing = None
        live_session.snapshot.pending_user_questions = None
        live_session.snapshot.fatal_error = message

    def shutdown(self) -> None:
        with self._lock:
            self._shutdown_requested = True
        sessions = list(self._live_sessions.values())
        for session in sessions:
            session.display.request_shutdown()
        for session in sessions:
            if session.worker is not None:
                session.worker.join(timeout=1.5)
        task_workers = list(self._task_workers.values())
        for worker in task_workers:
            worker.join(timeout=1.5)
        self._interrupt_noncooperative_workers()
        with self._lock:
            provider_auth_flows = list(self._provider_auth_flows.values())
            self._provider_auth_flows.clear()
        for flow in provider_auth_flows:
            self._cancel_provider_auth_flow_browser_timeout(flow)
            self._shutdown_provider_auth_flow_browser_listener(flow)
        self._finalize_shutdown_if_idle()

    def _run_session_worker(self, live_session_id: str) -> None:
        live_session = self._live_sessions[live_session_id]
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
            exit_code = run_session_loop(
                live_session.runtime,
                live_session.display,
                resume_session_id=live_session.bound_session_id,
                on_reload=self.refresh_file_mentions_cache,
            )
            if live_session.terminal_status is None:
                live_session.exit_code = exit_code
        except SessionTurnInterrupted as exc:
            live_session.exit_code = 130
            live_session.terminal_status = "interrupted"
            live_session.fatal_error = format_user_facing_error(exc)
            self._publish_live_event(
                live_session_id,
                "message_added",
                {
                    "item_id": f"interrupted-{uuid.uuid4().hex}",
                    "role": "error",
                    "content": live_session.fatal_error,
                    "markdown": False,
                },
            )
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
            self.refresh_file_mentions_cache()
            with self._lock:
                self._finalize_live_session_locked(live_session)
            self._finalize_shutdown_if_idle()

    def _run_task_worker(
        self,
        task_id: str,
        live_session_id: str | None = None,
        initial_user_message_id: int | None = None,
    ) -> None:
        live_session = (
            self._live_sessions.get(live_session_id) if live_session_id else None
        )
        current_user_message_id = initial_user_message_id
        is_initial_worker_turn = initial_user_message_id is not None
        task_result_finalization_failed = False

        def publish_summary(summary: str) -> None:
            with SessionStore() as store:
                updated = store.update_kanban_task(
                    task_id,
                    last_result_summary=summary,
                )
            if updated is not None:
                self._publish_task_updated(updated)

        try:
            if live_session is not None:
                live_session.status = "running"
                self._publish_live_event(
                    live_session.live_session_id,
                    "session_state",
                    {
                        "state": "running",
                        "live_session_id": live_session.live_session_id,
                        "session_id": live_session.bound_session_id,
                        "resume_session_id": live_session.bound_session_id,
                    },
                )
                self._publish_live_session_lifecycle(
                    "live_session_updated", live_session
                )
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
                prompt = self._task_prompt_for_run(
                    record,
                    stage_record,
                    is_continuation=not is_initial_worker_turn,
                )
                turn_image_attachments = (
                    list(record.image_attachments) if is_initial_worker_turn else []
                )
                turn_images = [
                    load_uploaded_image(attachment.upload_id)
                    for attachment in turn_image_attachments
                ]
                if current_user_message_id is None:
                    with SessionStore() as store:
                        current_user_message_id = self._persist_task_user_prompt(
                            store,
                            record,
                            runtime,
                            prompt,
                            turn_image_attachments,
                        )
                    if live_session is not None and current_user_message_id is not None:
                        self._publish_persisted_user_message(
                            live_session,
                            record,
                            runtime,
                            prompt,
                            current_user_message_id,
                            turn_image_attachments,
                        )
                outcome = run_single_turn_in_directory(
                    prompt,
                    runtime,
                    live_session.display
                    if live_session is not None
                    else WebDisplay(
                        publish_event=lambda _event_type, _payload: None,
                        verbose=runtime.settings.verbose,
                    ),
                    project_dir=record.project_dir,
                    workspace_root=self._workspace_root,
                    resume_session_id=record.session_id,
                    images=turn_images or None,
                    persisted_user_message_id=current_user_message_id,
                    replay_history=False,
                )
                if task_id in self._shutdown_interrupted_task_ids:
                    raise SessionTurnInterrupted(_SHUTDOWN_INTERRUPTED_MESSAGE)
                current_user_message_id = None
                is_initial_worker_turn = False
                if live_session is not None:
                    self._bind_live_session(
                        live_session.live_session_id,
                        outcome.session_id,
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
                terminal_task_update = status == KANBAN_RUN_STATUS_FAILED
                if not terminal_task_update:
                    terminal_task_update = (
                        next_stage_id is None
                        or next_record.stage != next_stage_id
                        or not self._should_auto_start_stage(next_stage_id)
                    )
                if terminal_task_update and live_session is not None:
                    try:
                        with self._lock:
                            self._finalize_live_session_locked(live_session)
                    except Exception as exc:
                        task_result_finalization_failed = True
                        with self._lock:
                            self._mark_task_live_session_finalization_failed_locked(
                                live_session,
                                exc,
                            )
                        break
                self._publish_task_updated(next_record)
                if terminal_task_update:
                    break
                with self._lock:
                    if self._shutdown_requested:
                        break
                    with SessionStore() as store:
                        rerunning = store.set_kanban_task_running(task_id)
                if rerunning is None:
                    break
                self._publish_task_updated(rerunning)
        except SessionTurnInterrupted as exc:
            message = shorten(format_user_facing_error(exc), 200)
            with SessionStore() as store:
                updated = store.set_kanban_task_result(
                    task_id,
                    run_status=KANBAN_RUN_STATUS_FAILED,
                    summary=message,
                )
            if live_session is not None:
                live_session.exit_code = 130
                live_session.terminal_status = "interrupted"
                live_session.fatal_error = format_user_facing_error(exc)
                self._publish_live_event(
                    live_session.live_session_id,
                    "message_added",
                    {
                        "item_id": f"interrupted-{uuid.uuid4().hex}",
                        "role": "error",
                        "content": live_session.fatal_error,
                        "markdown": False,
                    },
                )
                with self._lock:
                    self._finalize_live_session_locked(live_session)
            if updated is not None:
                self._publish_task_updated(updated)
        except Exception as exc:
            message = shorten(format_user_facing_error(exc), 200)
            with SessionStore() as store:
                updated = store.set_kanban_task_result(
                    task_id,
                    run_status=KANBAN_RUN_STATUS_FAILED,
                    summary=message,
                )
            if live_session is not None:
                live_session.exit_code = 1
                live_session.fatal_error = format_user_facing_error(exc)
                self._publish_live_event(
                    live_session.live_session_id,
                    "message_added",
                    {
                        "item_id": f"fatal-{uuid.uuid4().hex}",
                        "role": "error",
                        "content": live_session.fatal_error,
                        "markdown": False,
                    },
                )
                with self._lock:
                    self._finalize_live_session_locked(live_session)
            if updated is not None:
                self._publish_task_updated(updated)
        finally:
            if live_session is not None and not task_result_finalization_failed:
                with self._lock:
                    self._finalize_live_session_locked(live_session)
            with self._lock:
                self._running_task_ids.discard(task_id)
                self._task_workers.pop(task_id, None)
            self._finalize_shutdown_if_idle()

    def _renew_manager_lease_loop(self) -> None:
        while not self._lease_stop.wait(_WEB_MANAGER_LEASE_HEARTBEAT_SECS):
            with SessionStore() as store:
                renewed = store.renew_web_manager_lease(
                    self._directory_key,
                    owner_id=self._manager_owner_id,
                )
            if not renewed:
                self.shutdown()
                return

    def _interrupt_noncooperative_workers(self) -> None:
        stale_live_sessions = []
        stale_task_ids = []
        with self._lock:
            for live_session in self._live_sessions.values():
                worker = live_session.worker
                if worker is None or not worker.is_alive():
                    continue
                if live_session.ended_at is not None:
                    continue
                live_session.exit_code = 130
                live_session.terminal_status = "interrupted"
                live_session.fatal_error = (
                    live_session.fatal_error or _SHUTDOWN_INTERRUPTED_MESSAGE
                )
                stale_live_sessions.append(live_session)
                if live_session.task_id is not None:
                    stale_task_ids.append(live_session.task_id)
                    self._shutdown_interrupted_task_ids.add(live_session.task_id)

        for live_session in stale_live_sessions:
            self._publish_live_event(
                live_session.live_session_id,
                "message_added",
                {
                    "item_id": f"interrupted-{uuid.uuid4().hex}",
                    "role": "error",
                    "content": live_session.fatal_error,
                    "markdown": False,
                },
            )
            with self._lock:
                self._finalize_live_session_locked(live_session)

        for task_id in stale_task_ids:
            with SessionStore() as store:
                record = store.get_kanban_task(task_id)
                if record is None or record.run_status != KANBAN_RUN_STATUS_RUNNING:
                    continue
                updated = store.set_kanban_task_result(
                    task_id,
                    run_status=KANBAN_RUN_STATUS_FAILED,
                    summary=_SHUTDOWN_INTERRUPTED_MESSAGE,
                )
            if updated is not None:
                self._publish_task_updated(updated)

    def _finalize_shutdown_if_idle(self) -> None:
        with self._lock:
            if not self._started or not self._shutdown_requested:
                return
            if self._running_task_ids - self._shutdown_interrupted_task_ids:
                return
            current_thread = threading.current_thread()
            if self._has_live_worker_threads_locked(current_thread):
                return
            lease_thread = self._lease_thread
            self._lease_thread = None
            self._lease_stop.set()
            self._started = False
        if (
            lease_thread is not None
            and lease_thread is not threading.current_thread()
            and lease_thread.is_alive()
        ):
            lease_thread.join(timeout=1.0)
        with SessionStore() as store:
            store.release_web_manager_lease(
                self._directory_key,
                owner_id=self._manager_owner_id,
            )

    def _has_live_worker_threads_locked(self, current_thread: threading.Thread) -> bool:
        return any(
            worker is not current_thread and worker.is_alive()
            for worker in self._task_workers.values()
        ) or any(
            session.worker is not None
            and session.worker is not current_thread
            and session.worker.is_alive()
            for session in self._live_sessions.values()
        )
