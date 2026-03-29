from __future__ import annotations

import asyncio
import threading
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from pbi_agent.agent.error_formatting import format_user_facing_error
from pbi_agent.agent.session import run_chat_loop
from pbi_agent.config import Settings
from pbi_agent.media import load_workspace_image
from pbi_agent.models.messages import ImageAttachment
from pbi_agent.providers.capabilities import provider_supports_images
from pbi_agent.session_store import (
    KANBAN_RUN_STATUS_COMPLETED,
    KANBAN_RUN_STATUS_FAILED,
    KANBAN_STAGE_BACKLOG,
    KanbanTaskRecord,
    MessageImageAttachment,
    SessionRecord,
    SessionStore,
)
from pbi_agent.task_runner import run_single_turn_in_directory
from pbi_agent.ui.formatting import shorten
from pbi_agent.ui.input_mentions import MentionSearchResult, WorkspaceFileIndex
from pbi_agent.web.display import KanbanTaskDisplay, WebDisplay
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


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _serialize_session(record: SessionRecord) -> dict[str, Any]:
    return {
        "session_id": record.session_id,
        "directory": record.directory,
        "provider": record.provider,
        "model": record.model,
        "previous_id": record.previous_id,
        "title": record.title,
        "total_tokens": record.total_tokens,
        "input_tokens": record.input_tokens,
        "output_tokens": record.output_tokens,
        "cost_usd": record.cost_usd,
        "created_at": record.created_at,
        "updated_at": record.updated_at,
    }


def _serialize_task(record: KanbanTaskRecord) -> dict[str, Any]:
    return {
        "task_id": record.task_id,
        "directory": record.directory,
        "title": record.title,
        "prompt": record.prompt,
        "stage": record.stage,
        "position": record.position,
        "project_dir": record.project_dir,
        "session_id": record.session_id,
        "run_status": record.run_status,
        "last_result_summary": record.last_result_summary,
        "created_at": record.created_at,
        "updated_at": record.updated_at,
        "last_run_started_at": record.last_run_started_at,
        "last_run_finished_at": record.last_run_finished_at,
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
    display: WebDisplay
    worker: threading.Thread
    resume_session_id: str | None
    created_at: str
    status: str = "starting"
    exit_code: int | None = None
    fatal_error: str | None = None
    ended_at: str | None = None


class WebSessionManager:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._workspace_root = Path.cwd().resolve()
        self._mention_index = WorkspaceFileIndex(self._workspace_root)
        self._directory_key = str(self._workspace_root)
        self._app_stream = EventStream()
        self._chat_sessions: dict[str, LiveChatSession] = {}
        self._running_task_ids: set[str] = set()
        self._lock = threading.Lock()
        with SessionStore() as store:
            store.normalize_kanban_processing_tasks(directory=self._directory_key)

    @property
    def workspace_root(self) -> Path:
        return self._workspace_root

    @property
    def settings(self) -> Settings:
        return self._settings

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
        return {
            "workspace_root": str(self._workspace_root),
            "provider": self._settings.provider,
            "model": self._settings.model,
            "reasoning_effort": self._settings.reasoning_effort,
            "supports_image_inputs": provider_supports_images(self._settings.provider),
            "sessions": self.list_sessions(),
            "tasks": self.list_tasks(),
            "live_sessions": [
                self._serialize_live_session(item)
                for item in self._chat_sessions.values()
            ],
            "board_stages": ["backlog", "plan", "processing", "review"],
        }

    def list_sessions(self, limit: int = 30) -> list[dict[str, Any]]:
        with SessionStore() as store:
            sessions = store.list_sessions(
                self._directory_key,
                limit=limit,
                provider=self._settings.provider,
            )
        return [_serialize_session(session) for session in sessions]

    def list_tasks(self) -> list[dict[str, Any]]:
        with SessionStore() as store:
            records = store.list_kanban_tasks(self._directory_key)
        return [_serialize_task(record) for record in records]

    def create_live_chat(
        self,
        *,
        resume_session_id: str | None = None,
        live_session_id: str | None = None,
    ) -> dict[str, Any]:
        with self._lock:
            if live_session_id and live_session_id in self._chat_sessions:
                return self._serialize_live_session(
                    self._chat_sessions[live_session_id]
                )

            session_id = live_session_id or uuid.uuid4().hex
            event_stream = EventStream()
            display = WebDisplay(
                publish_event=event_stream.publish,
                verbose=self._settings.verbose,
                model=self._settings.model,
                reasoning_effort=self._settings.reasoning_effort,
                bind_session=lambda bound_session_id, current=session_id: (
                    self._bind_live_session(
                        current,
                        bound_session_id,
                    )
                ),
            )
            worker = threading.Thread(
                target=self._run_chat_worker,
                args=(session_id,),
                daemon=True,
                name=f"pbi-agent-web-chat-{session_id[:8]}",
            )
            live_session = LiveChatSession(
                live_session_id=session_id,
                event_stream=event_stream,
                display=display,
                worker=worker,
                resume_session_id=resume_session_id,
                created_at=_now_iso(),
            )
            self._chat_sessions[session_id] = live_session
            event_stream.publish(
                "session_state",
                {
                    "state": "starting",
                    "live_session_id": session_id,
                    "resume_session_id": resume_session_id,
                },
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
            if record.provider != self._settings.provider:
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
        if not provider_supports_images(self._settings.provider):
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
    ) -> dict[str, Any]:
        live_session = self._require_live_session(live_session_id)
        if live_session.status == "ended":
            raise RuntimeError("Live chat session has already ended.")
        message_text = text.strip()
        if (image_paths or image_upload_ids) and not provider_supports_images(
            self._settings.provider
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
            live_session.event_stream.publish(
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
            images=resolved_images or None,
            image_attachments=message_image_attachments or None,
        )
        return self._serialize_live_session(live_session)

    def request_new_chat(self, live_session_id: str) -> dict[str, Any]:
        live_session = self._require_live_session(live_session_id)
        if live_session.status == "ended":
            raise RuntimeError("Live chat session has already ended.")
        live_session.display.request_new_chat()
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
        stage: str = KANBAN_STAGE_BACKLOG,
        project_dir: str = ".",
        session_id: str | None = None,
    ) -> dict[str, Any]:
        self._validate_project_dir(project_dir)
        with SessionStore() as store:
            record = store.create_kanban_task(
                directory=self._directory_key,
                title=title,
                prompt=prompt,
                stage=stage,
                project_dir=project_dir,
                session_id=session_id,
            )
        return self._publish_task_updated(record)

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
        clear_session_id: bool = False,
    ) -> dict[str, Any]:
        if project_dir is not None:
            self._validate_project_dir(project_dir)
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
                clear_session_id=clear_session_id,
            )
        if updated is None:
            raise KeyError(task_id)
        return self._publish_task_updated(updated)

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
        return _serialize_task(running_record)

    def shutdown(self) -> None:
        sessions = list(self._chat_sessions.values())
        for session in sessions:
            session.display.request_shutdown()
        for session in sessions:
            session.worker.join(timeout=1.5)

    def _run_chat_worker(self, live_session_id: str) -> None:
        live_session = self._chat_sessions[live_session_id]
        live_session.status = "running"
        live_session.event_stream.publish(
            "session_state",
            {
                "state": "running",
                "live_session_id": live_session_id,
                "resume_session_id": live_session.resume_session_id,
            },
        )
        try:
            exit_code = run_chat_loop(
                self._settings,
                live_session.display,
                resume_session_id=live_session.resume_session_id,
            )
            live_session.exit_code = exit_code
        except Exception as exc:
            live_session.exit_code = 1
            live_session.fatal_error = format_user_facing_error(exc)
            live_session.event_stream.publish(
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
            live_session.event_stream.publish(
                "session_state",
                {
                    "state": "ended",
                    "live_session_id": live_session_id,
                    "exit_code": live_session.exit_code,
                    "fatal_error": live_session.fatal_error,
                },
            )

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
            with SessionStore() as store:
                record = store.get_kanban_task(task_id)
            if record is None:
                raise KeyError(task_id)

            outcome = run_single_turn_in_directory(
                record.prompt,
                self._settings,
                KanbanTaskDisplay(
                    publish_summary=publish_summary,
                    verbose=self._settings.verbose,
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
            if updated is not None:
                self._publish_task_updated(updated)
        finally:
            with self._lock:
                self._running_task_ids.discard(task_id)

    def _publish_task_updated(self, record: KanbanTaskRecord) -> dict[str, Any]:
        payload = _serialize_task(record)
        self._app_stream.publish("task_updated", {"task": payload})
        return payload

    def _bind_live_session(
        self,
        live_session_id: str,
        resume_session_id: str | None,
    ) -> None:
        live_session = self._chat_sessions.get(live_session_id)
        if live_session is None:
            return
        live_session.resume_session_id = resume_session_id

    def _serialize_live_session(self, live_session: LiveChatSession) -> dict[str, Any]:
        return {
            "live_session_id": live_session.live_session_id,
            "resume_session_id": live_session.resume_session_id,
            "created_at": live_session.created_at,
            "status": live_session.status,
            "exit_code": live_session.exit_code,
            "fatal_error": live_session.fatal_error,
            "ended_at": live_session.ended_at,
        }

    def _require_live_session(self, live_session_id: str) -> LiveChatSession:
        live_session = self._chat_sessions.get(live_session_id)
        if live_session is None:
            raise KeyError(live_session_id)
        return live_session

    def _validate_project_dir(self, project_dir: str) -> None:
        candidate = project_dir.strip() or "."
        target = (self._workspace_root / candidate).resolve()
        target.relative_to(self._workspace_root)
        if not target.exists():
            raise FileNotFoundError(f"Project directory does not exist: {target}")
        if not target.is_dir():
            raise NotADirectoryError(f"Project path is not a directory: {target}")
