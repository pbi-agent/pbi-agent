from __future__ import annotations

import threading
import uuid
from pathlib import Path
from typing import Any

from pbi_agent.agent.error_formatting import format_user_facing_error
from pbi_agent.agent.session import (
    COMPACT_COMMAND,
    TEMPORARY_LOCAL_COMMANDS,
    _normalize_user_command,
)
from pbi_agent.config import ConfigError, find_command_config_by_alias
from pbi_agent.display.protocol import QueuedInput, UserQuestionAnswer
from pbi_agent.media import load_workspace_image
from pbi_agent.models.messages import ImageAttachment
from pbi_agent.session_store import (
    KANBAN_RUN_STATUS_RUNNING,
    MessageImageAttachment,
    MessageRecord,
    SessionStore,
)
from pbi_agent.tools import shell as shell_tool
from pbi_agent.tools.types import ToolContext
from pbi_agent.web.display import WebDisplay, persisted_message_payload
from pbi_agent.web.session.serializers import (
    _format_shell_command_output,
    _is_active_live_session,
    _message_image_attachment,
    _message_image_payload,
    _persisted_web_run_status,
    _runtime_summary,
    _serialize_session,
    _session_title_for_input,
    _snapshot_item_id,
)
from pbi_agent.web.session.events import TRANSIENT_WEB_EVENT_KEY
from pbi_agent.web.session.state import (
    EventStream,
    LiveSessionSnapshot,
    LiveSessionState,
    _now_iso,
)
from pbi_agent.web.uploads import (
    load_uploaded_image,
    load_uploaded_image_record,
    store_image_attachment,
    store_uploaded_image_bytes,
)

_LOCAL_COMMANDS = TEMPORARY_LOCAL_COMMANDS | {COMPACT_COMMAND}


class LiveSessionsMixin:
    _app_stream: EventStream
    _directory_key: str
    _ensure_worker_creation_allowed_locked: Any
    _finalize_live_session_locked: Any
    _live_sessions: dict[str, LiveSessionState]
    _lock: threading.Lock
    _publish_live_event: Any
    _require_saved_session: Any
    _resolve_runtime: Any
    _resolve_saved_session_runtime: Any
    _run_session_worker: Any
    _update_saved_session_runtime: Any
    _workspace_context: Any
    _workspace_root: Path

    def list_live_sessions(self) -> list[dict[str, Any]]:
        with self._lock:
            sessions = list(self._live_sessions.values())
        return [self._serialize_live_session(session) for session in sessions]

    def get_live_session_detail(self, live_session_id: str) -> dict[str, Any]:
        live_session = self._require_live_session(live_session_id)
        return {
            "live_session": self._serialize_live_session(live_session),
            "snapshot": self._serialize_live_snapshot(live_session),
        }

    def create_live_session(
        self,
        *,
        session_id: str | None = None,
        live_session_id: str | None = None,
        profile_id: str | None = None,
        reuse_existing: bool = True,
    ) -> dict[str, Any]:
        runtime = self._resolve_runtime(profile_id)
        bound_session_id = session_id
        with self._lock:
            if bound_session_id is not None:
                self._require_saved_session(bound_session_id)
                if profile_id is None:
                    runtime = self._resolve_saved_session_runtime(
                        bound_session_id,
                        fallback=runtime,
                    )
                else:
                    self._update_saved_session_runtime(bound_session_id, runtime)
            if bound_session_id is not None and reuse_existing:
                existing_live_session = (
                    self._find_live_session_for_saved_session_locked(bound_session_id)
                )
                if existing_live_session is not None:
                    return self._serialize_live_session(existing_live_session)
            if live_session_id and live_session_id in self._live_sessions:
                return self._serialize_live_session(
                    self._live_sessions[live_session_id]
                )
            self._ensure_worker_creation_allowed_locked()

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
                target=self._run_session_worker,
                args=(new_live_session_id,),
                daemon=True,
                name=f"pbi-agent-web-session-{new_live_session_id[:8]}",
            )
            live_session = LiveSessionState(
                live_session_id=new_live_session_id,
                event_stream=event_stream,
                snapshot=snapshot,
                display=display,
                worker=worker,
                runtime=runtime,
                bound_session_id=bound_session_id,
                created_at=_now_iso(),
            )
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
            try:
                worker.start()
            except Exception as exc:
                live_session.worker = None
                live_session.exit_code = 1
                live_session.fatal_error = format_user_facing_error(exc)
                self._publish_live_event(
                    new_live_session_id,
                    "message_added",
                    {
                        "item_id": f"fatal-{uuid.uuid4().hex}",
                        "role": "error",
                        "content": live_session.fatal_error,
                        "markdown": False,
                    },
                )
                self._finalize_live_session_locked(live_session)
                raise
            return self._serialize_live_session(live_session)

    def _message_attachments_for_upload_ids(
        self,
        upload_ids: list[str],
    ) -> list[MessageImageAttachment]:
        return [
            _message_image_attachment(load_uploaded_image_record(upload_id))
            for upload_id in upload_ids
        ]

    def upload_task_images(
        self,
        *,
        files: list[tuple[str, bytes]],
    ) -> list[dict[str, Any]]:
        attachments: list[dict[str, Any]] = []
        for original_name, raw_bytes in files:
            safe_name = (original_name or "task-image.png").strip() or "task-image.png"
            record = store_uploaded_image_bytes(raw_bytes=raw_bytes, name=safe_name)
            attachments.append(
                _message_image_payload(_message_image_attachment(record))
            )
        return attachments

    def upload_session_images(
        self,
        live_session_id: str,
        *,
        files: list[tuple[str, bytes]],
    ) -> list[dict[str, Any]]:
        live_session = self._require_live_session(live_session_id)
        if live_session.status == "ended":
            raise RuntimeError("Live session has already ended.")
        return self._store_session_image_uploads(files)

    def upload_saved_session_images(
        self,
        session_id: str,
        *,
        files: list[tuple[str, bytes]],
    ) -> list[dict[str, Any]]:
        self._require_saved_session(session_id)
        live_session = self._find_live_session_for_saved_session(session_id)
        if live_session is not None and live_session.status == "ended":
            raise RuntimeError("Session run has already ended.")
        return self._store_session_image_uploads(files)

    def _store_session_image_uploads(
        self,
        files: list[tuple[str, bytes]],
    ) -> list[dict[str, Any]]:
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

    def submit_session_input(
        self,
        live_session_id: str,
        *,
        text: str,
        file_paths: list[str] | None = None,
        image_paths: list[str] | None = None,
        image_upload_ids: list[str] | None = None,
        profile_id: str | None = None,
        interactive_mode: bool = False,
    ) -> dict[str, Any]:
        live_session = self._require_live_session(live_session_id)
        if live_session.status == "ended":
            raise RuntimeError("Live session has already ended.")
        command_profile_id = self._command_profile_id_for_submission(
            text,
        )
        selected_runtime = self._resolve_runtime(profile_id)
        current_runtime = live_session.runtime
        requested_runtime = (
            self._resolve_runtime(command_profile_id)
            if command_profile_id is not None
            else selected_runtime
        )
        restore_runtime = selected_runtime
        should_restore_runtime = False
        if command_profile_id is None:
            if selected_runtime.profile_id != current_runtime.profile_id:
                self._queue_runtime_change(live_session, profile_id)
        else:
            if selected_runtime.profile_id != current_runtime.profile_id:
                live_session.runtime = selected_runtime
                if live_session.bound_session_id is not None:
                    self._update_saved_session_runtime(
                        live_session.bound_session_id,
                        selected_runtime,
                    )
                self._publish_live_session_runtime(live_session)
                self._publish_live_session_lifecycle(
                    "live_session_updated",
                    live_session,
                )
            if requested_runtime.profile_id != current_runtime.profile_id:
                self._queue_transient_runtime_change(
                    live_session,
                    requested_runtime,
                )
            should_restore_runtime = (
                requested_runtime.profile_id != restore_runtime.profile_id
            )
        message_text = text.strip()
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
        optimistic_item_id = f"user-{uuid.uuid4().hex}"
        if message_text or message_image_attachments:
            is_temporary_command = (
                _normalize_user_command(message_text) in TEMPORARY_LOCAL_COMMANDS
            )
            self._publish_live_event(
                live_session_id,
                "message_added",
                {
                    **({TRANSIENT_WEB_EVENT_KEY: True} if is_temporary_command else {}),
                    "item_id": optimistic_item_id,
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
            interactive_mode=interactive_mode,
            item_id=optimistic_item_id,
        )
        if should_restore_runtime:
            live_session.display.request_runtime_change(
                runtime=restore_runtime,
                profile_id=restore_runtime.profile_id,
                persist=False,
                saved_runtime=restore_runtime,
            )
        self._set_latest_queued_input_item_id(live_session, optimistic_item_id)
        return self._serialize_live_session(live_session)

    def submit_saved_session_input(
        self,
        session_id: str,
        *,
        text: str,
        file_paths: list[str] | None = None,
        image_paths: list[str] | None = None,
        image_upload_ids: list[str] | None = None,
        profile_id: str | None = None,
        interactive_mode: bool = False,
    ) -> dict[str, Any]:
        self._ensure_saved_session_title(session_id, text)
        live_session = self._find_live_session_for_saved_session(session_id)
        reuse_existing = True
        if live_session is not None and live_session.kind == "task":
            with SessionStore() as store:
                task = (
                    store.get_kanban_task(live_session.task_id)
                    if live_session.task_id is not None
                    else None
                )
            if task is not None and task.run_status == KANBAN_RUN_STATUS_RUNNING:
                raise RuntimeError("Task session is still running.")
            live_session = None
            reuse_existing = False
        if live_session is None:
            created = self.create_live_session(
                session_id=session_id,
                profile_id=profile_id,
                reuse_existing=reuse_existing,
            )
            live_session_id = str(created["live_session_id"])
        else:
            live_session_id = live_session.live_session_id
        return self.submit_session_input(
            live_session_id,
            text=text,
            file_paths=file_paths,
            image_paths=image_paths,
            image_upload_ids=image_upload_ids,
            profile_id=profile_id,
            interactive_mode=interactive_mode,
        )

    def _command_profile_id_for_submission(
        self,
        text: str,
    ) -> str | None:
        stripped = text.strip()
        if not stripped.startswith("/"):
            return None
        head = stripped.split(maxsplit=1)[0]
        if _normalize_user_command(head) in _LOCAL_COMMANDS:
            return None
        try:
            command = find_command_config_by_alias(head, workspace=self._workspace_root)
        except ConfigError:
            return None
        if command is None or command.model_profile_id is None:
            return None
        return command.model_profile_id

    def _ensure_saved_session_title(self, session_id: str, text: str) -> None:
        title = _session_title_for_input(text)
        if not title:
            return
        with SessionStore() as store:
            record = store.get_session(session_id)
            if record is None or record.directory != self._directory_key:
                raise KeyError(session_id)
            if record.title.strip():
                return
            store.update_session(session_id, title=title)
            updated = store.get_session(session_id)
        if updated is not None:
            self._app_stream.publish(
                "session_updated",
                {"session": _serialize_session(updated)},
            )

    def submit_question_response(
        self,
        live_session_id: str,
        *,
        prompt_id: str,
        answers: list[dict[str, Any]],
    ) -> dict[str, Any]:
        live_session = self._require_live_session(live_session_id)
        if live_session.status == "ended":
            raise RuntimeError("Live session has already ended.")
        pending = live_session.snapshot.pending_user_questions
        if not isinstance(pending, dict) or pending.get("prompt_id") != prompt_id:
            raise RuntimeError("No matching pending user question prompt.")
        questions = pending.get("questions")
        if not isinstance(questions, list):
            raise RuntimeError("Pending user question prompt is invalid.")
        question_by_id = {
            str(question.get("question_id") or ""): question
            for question in questions
            if isinstance(question, dict)
        }
        parsed_answers: list[UserQuestionAnswer] = []
        seen_ids: set[str] = set()
        for raw_answer in answers:
            question_id = str(raw_answer.get("question_id") or "").strip()
            if not question_id or question_id not in question_by_id:
                raise ValueError("Question response contains an unknown question id.")
            if question_id in seen_ids:
                raise ValueError("Question response contains duplicate answers.")
            seen_ids.add(question_id)
            answer_text = str(raw_answer.get("answer") or "").strip()
            selected_index = raw_answer.get("selected_suggestion_index")
            custom_note = str(raw_answer.get("custom_note") or "").strip()
            question = question_by_id[question_id]
            suggestions = question.get("suggestions")
            if not isinstance(suggestions, list) or len(suggestions) != 3:
                raise RuntimeError("Pending user question suggestions are invalid.")
            if not isinstance(selected_index, int) or selected_index not in {0, 1, 2}:
                raise ValueError(
                    "Question answers must include a selected suggestion index."
                )
            answer_text = str(suggestions[selected_index])
            if custom_note:
                answer_text = f"{answer_text}\n\nAdditional note: {custom_note}"
            parsed_answers.append(
                UserQuestionAnswer(
                    question_id=question_id,
                    question=str(question.get("question") or ""),
                    answer=answer_text,
                    custom=bool(custom_note),
                )
            )
        if seen_ids != set(question_by_id):
            raise ValueError("All pending questions must be answered.")
        live_session.display.submit_question_response(
            prompt_id=prompt_id,
            answers=parsed_answers,
        )
        return self._serialize_live_session(live_session)

    def submit_saved_session_question_response(
        self,
        session_id: str,
        *,
        prompt_id: str,
        answers: list[dict[str, Any]],
    ) -> dict[str, Any]:
        live_session = self._find_live_session_for_saved_session(session_id)
        if live_session is None:
            raise KeyError(session_id)
        return self.submit_question_response(
            live_session.live_session_id,
            prompt_id=prompt_id,
            answers=answers,
        )

    def interrupt_live_session(self, live_session_id: str) -> dict[str, Any]:
        live_session = self._require_live_session(live_session_id)
        if live_session.status == "ended":
            raise RuntimeError("Live session has already ended.")
        processing_active = bool((live_session.snapshot.processing or {}).get("active"))
        input_disabled = not live_session.snapshot.input_enabled
        if not (processing_active or input_disabled):
            raise RuntimeError("Live session is not currently processing a turn.")
        item = self._latest_live_user_item(live_session)
        item_id = _snapshot_item_id(item) if item is not None else None
        input_text = str((item or {}).get("content") or "")
        live_session.display.request_interrupt(
            item_id=item_id,
            input_text=input_text,
        )
        return self._serialize_live_session(live_session)

    def interrupt_saved_session(self, session_id: str) -> dict[str, Any]:
        live_session = self._find_live_session_for_saved_session(session_id)
        if live_session is None:
            raise KeyError(session_id)
        return self.interrupt_live_session(live_session.live_session_id)

    def run_shell_command(
        self,
        live_session_id: str,
        *,
        command: str,
    ) -> dict[str, Any]:
        live_session = self._require_live_session(live_session_id)
        if live_session.status == "ended":
            raise RuntimeError("Live session has already ended.")
        normalized_command = command.strip()
        if not normalized_command:
            raise ValueError("Shell command must be a non-empty string.")
        user_content = f"!{normalized_command}"
        user_message = self._persist_live_session_message(
            live_session,
            role="user",
            content=user_content,
        )
        live_session.display.begin_direct_command()
        try:
            self._publish_live_event(
                live_session_id,
                "message_added",
                persisted_message_payload(user_message)
                if user_message is not None
                else {
                    "item_id": f"user-{uuid.uuid4().hex}",
                    "role": "user",
                    "content": user_content,
                    "file_paths": [],
                    "image_attachments": [],
                    "markdown": False,
                },
            )
            live_session.display.shell_start([normalized_command])
            result = shell_tool.handle(
                {"command": normalized_command},
                ToolContext(
                    settings=live_session.runtime.settings, display=live_session.display
                ),
            )
            exit_code = result.get("exit_code") if isinstance(result, dict) else 1
            timed_out = (
                bool(result.get("timed_out")) if isinstance(result, dict) else False
            )
            live_session.display.shell_command(
                normalized_command,
                exit_code if isinstance(exit_code, int) else None,
                timed_out,
                result={"ok": True, "result": result},
            )
            live_session.display.tool_group_end()
            assistant_content = _format_shell_command_output(result)
            assistant_message = self._persist_live_session_message(
                live_session,
                role="assistant",
                content=assistant_content,
            )
            self._publish_live_event(
                live_session_id,
                "message_added",
                persisted_message_payload(assistant_message)
                if assistant_message is not None
                else {
                    "item_id": f"shell-output-{uuid.uuid4().hex}",
                    "role": "assistant",
                    "content": assistant_content,
                    "markdown": True,
                },
            )
        finally:
            live_session.display.finish_direct_command()
        return self._serialize_live_session(live_session)

    def run_saved_session_shell_command(
        self,
        session_id: str,
        *,
        command: str,
    ) -> dict[str, Any]:
        live_session = self._find_live_session_for_saved_session(session_id)
        if live_session is None:
            created = self.create_live_session(session_id=session_id)
            live_session_id = str(created["live_session_id"])
        else:
            live_session_id = live_session.live_session_id
        return self.run_shell_command(live_session_id, command=command)

    def _persist_live_session_message(
        self,
        live_session: LiveSessionState,
        *,
        role: str,
        content: str,
    ) -> MessageRecord | None:
        with SessionStore() as store:
            session = store.get_session(live_session.bound_session_id or "")
            if session is None or session.directory != self._directory_key:
                return None
            message_id = store.add_message(
                session.session_id,
                role,
                content,
                provider_id=live_session.runtime.provider_id or None,
                profile_id=live_session.runtime.profile_id or None,
            )
            return store.get_message(message_id)

    def request_new_session(
        self,
        live_session_id: str,
        *,
        profile_id: str | None = None,
    ) -> dict[str, Any]:
        live_session = self._require_live_session(live_session_id)
        if live_session.status == "ended":
            raise RuntimeError("Live session has already ended.")
        requested_runtime = self._resolve_runtime(profile_id)
        if requested_runtime.profile_id != live_session.runtime.profile_id:
            self._queue_runtime_change(live_session, profile_id)
        live_session.display.request_new_session()
        return self._serialize_live_session(live_session)

    def request_saved_new_session(
        self,
        session_id: str,
        *,
        profile_id: str | None = None,
    ) -> dict[str, Any]:
        live_session = self._find_live_session_for_saved_session(session_id)
        if live_session is None:
            return self.create_live_session(
                session_id=session_id,
                profile_id=profile_id,
            )
        return self.request_new_session(
            live_session.live_session_id,
            profile_id=profile_id,
        )

    def set_live_session_profile(
        self,
        live_session_id: str,
        *,
        profile_id: str | None = None,
    ) -> dict[str, Any]:
        live_session = self._require_live_session(live_session_id)
        if live_session.status == "ended":
            raise RuntimeError("Live session has already ended.")
        requested_runtime = self._resolve_runtime(profile_id)
        if requested_runtime.profile_id != live_session.runtime.profile_id:
            self._queue_runtime_change(live_session, profile_id)
        return self._serialize_live_session(live_session)

    def set_saved_session_profile(
        self,
        session_id: str,
        *,
        profile_id: str | None = None,
    ) -> dict[str, Any]:
        requested_runtime = self._resolve_runtime(profile_id)
        live_session = self._find_live_session_for_saved_session(session_id)
        if live_session is None:
            return self._update_saved_session_runtime(session_id, requested_runtime)
        return self.set_live_session_profile(
            live_session.live_session_id,
            profile_id=profile_id,
        )

    def _find_live_session_for_saved_session(
        self,
        session_id: str,
    ) -> LiveSessionState | None:
        with self._lock:
            return self._find_live_session_for_saved_session_locked(session_id)

    def _find_live_session_for_saved_session_locked(
        self,
        session_id: str,
    ) -> LiveSessionState | None:
        active_live_sessions = []
        for live_session in self._live_sessions.values():
            if live_session.bound_session_id != session_id:
                continue
            if not _is_active_live_session(live_session):
                continue
            active_live_sessions.append(live_session)
        if not active_live_sessions:
            return None

        with SessionStore() as store:
            for live_session in reversed(active_live_sessions):
                if live_session.kind != "task" or live_session.task_id is None:
                    continue
                task = store.get_kanban_task(live_session.task_id)
                if task is not None and task.run_status == KANBAN_RUN_STATUS_RUNNING:
                    return live_session
        return active_live_sessions[-1]

    def _find_stream_live_session_for_saved_session(
        self,
        session_id: str,
    ) -> LiveSessionState | None:
        with self._lock:
            active_live_session = self._find_live_session_for_saved_session_locked(
                session_id
            )
            if active_live_session is not None:
                return active_live_session
            for live_session in reversed(self._live_sessions.values()):
                if live_session.bound_session_id == session_id:
                    return live_session
        return None

    def _bind_live_session(
        self,
        live_session_id: str,
        session_id: str | None,
    ) -> None:
        live_session = self._live_sessions.get(live_session_id)
        if live_session is None:
            return
        previous_session_id = live_session.bound_session_id
        live_session.bound_session_id = session_id
        live_session.snapshot.session_id = session_id
        self._update_live_run_projection(live_session)
        if previous_session_id != session_id:
            self._publish_live_session_lifecycle("live_session_bound", live_session)

    def _serialize_live_session(self, live_session: LiveSessionState) -> dict[str, Any]:
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
            "compact_threshold": live_session.runtime.settings.compact_threshold,
            "created_at": live_session.created_at,
            "status": live_session.status,
            "exit_code": live_session.exit_code,
            "fatal_error": live_session.fatal_error,
            "ended_at": live_session.ended_at,
            "last_event_seq": live_session.snapshot.last_event_seq,
        }

    def _serialize_live_snapshot(
        self, live_session: LiveSessionState
    ) -> dict[str, Any]:
        return {
            "live_session_id": live_session.live_session_id,
            "session_id": live_session.snapshot.session_id,
            "runtime": live_session.snapshot.runtime,
            "input_enabled": live_session.snapshot.input_enabled,
            "wait_message": live_session.snapshot.wait_message,
            "processing": live_session.snapshot.processing,
            "session_usage": live_session.snapshot.session_usage,
            "turn_usage": live_session.snapshot.turn_usage,
            "session_ended": live_session.snapshot.session_ended,
            "fatal_error": live_session.snapshot.fatal_error,
            "pending_user_questions": live_session.snapshot.pending_user_questions,
            "items": list(live_session.snapshot.items),
            "sub_agents": dict(live_session.snapshot.sub_agents),
            "last_event_seq": live_session.snapshot.last_event_seq,
        }

    def _create_live_run_projection(self, live_session: LiveSessionState) -> None:
        with SessionStore() as store:
            if store.get_run_session(live_session.live_session_id) is not None:
                return
            store.create_run_session(
                run_session_id=live_session.live_session_id,
                session_id=live_session.bound_session_id,
                agent_name="main",
                agent_type="web_session",
                provider=live_session.runtime.settings.provider,
                provider_id=live_session.runtime.provider_id,
                profile_id=live_session.runtime.profile_id,
                model=live_session.runtime.settings.model,
                status=_persisted_web_run_status(live_session),
                kind=live_session.kind,
                task_id=live_session.task_id,
                project_dir=live_session.project_dir,
                last_event_seq=live_session.snapshot.last_event_seq,
                snapshot=self._serialize_live_snapshot(live_session),
                exit_code=live_session.exit_code,
                fatal_error=live_session.fatal_error,
                metadata={
                    "source": "web",
                    "directory": self._directory_key,
                    "workspace_root": str(self._workspace_root),
                    "workspace_display_path": self._workspace_context.display_path,
                    "live_session_id": live_session.live_session_id,
                    "runtime": _runtime_summary(live_session.runtime),
                },
            )

    def _update_live_run_projection(self, live_session: LiveSessionState) -> None:
        with SessionStore() as store:
            store.update_run_session(
                live_session.live_session_id,
                session_id=live_session.bound_session_id,
                clear_session_id=live_session.bound_session_id is None,
                status=_persisted_web_run_status(live_session),
                ended_at=live_session.ended_at,
                kind=live_session.kind,
                task_id=live_session.task_id,
                project_dir=live_session.project_dir,
                last_event_seq=live_session.snapshot.last_event_seq,
                snapshot=self._serialize_live_snapshot(live_session),
                exit_code=live_session.exit_code,
                fatal_error=live_session.fatal_error,
            )

    def _require_live_session(self, live_session_id: str) -> LiveSessionState:
        live_session = self._live_sessions.get(live_session_id)
        if live_session is None:
            raise KeyError(live_session_id)
        return live_session

    def _queue_runtime_change(
        self,
        live_session: LiveSessionState,
        profile_id: str | None,
    ) -> None:
        runtime = self._resolve_runtime(profile_id)
        live_session.runtime = runtime
        live_session.display.request_runtime_change(
            runtime=runtime,
            profile_id=runtime.profile_id,
        )
        if live_session.bound_session_id is not None:
            self._update_saved_session_runtime(live_session.bound_session_id, runtime)
        self._publish_live_session_runtime(live_session)
        self._publish_live_session_lifecycle("live_session_updated", live_session)

    def _queue_transient_runtime_change(
        self,
        live_session: LiveSessionState,
        runtime,
    ) -> None:
        live_session.display.request_runtime_change(
            runtime=runtime,
            profile_id=runtime.profile_id,
            persist=False,
            saved_runtime=live_session.runtime,
        )

    def _publish_live_session_runtime(self, live_session: LiveSessionState) -> None:
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
                "compact_threshold": live_session.runtime.settings.compact_threshold,
            },
        )

    def _latest_live_user_item(
        self,
        live_session: LiveSessionState,
    ) -> dict[str, Any] | None:
        for item in reversed(live_session.snapshot.items):
            if item.get("kind") != "message":
                continue
            if item.get("role") != "user":
                continue
            item_id = _snapshot_item_id(item)
            if item_id and not item_id.startswith("history-"):
                return item
        return None

    def _set_latest_queued_input_item_id(
        self,
        live_session: LiveSessionState,
        item_id: str,
    ) -> None:
        queued = getattr(live_session.display, "_input_queue", None)
        mutex = getattr(queued, "mutex", None)
        if queued is None or mutex is None:
            return
        with mutex:
            for item in reversed(list(queued.queue)):
                if isinstance(item, QueuedInput) and item.item_id is None:
                    item.item_id = item_id
                    return

    def _publish_live_session_lifecycle(
        self,
        event_type: str,
        live_session: LiveSessionState,
    ) -> None:
        self._app_stream.publish(
            event_type,
            {"live_session": self._serialize_live_session(live_session)},
        )
