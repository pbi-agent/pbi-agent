from __future__ import annotations

import uuid
from pathlib import Path
from typing import Any, Literal

from pbi_agent.agent.error_formatting import format_user_facing_error
from pbi_agent.media import load_workspace_image
from pbi_agent.models.messages import ImageAttachment
from pbi_agent.session_store import MessageImageAttachment
from pbi_agent.web.session.serializers import (
    _message_image_attachment,
    _message_image_payload,
)
from pbi_agent.web.session.state import (
    LiveSessionState,
    QueuedFollowUpInput,
    _now_iso,
)
from pbi_agent.web.uploads import load_uploaded_image, load_uploaded_image_record

FollowUpDelivery = Literal["checkpoint", "after_finish"]


class FollowUpsMixin:
    _live_sessions: dict[str, LiveSessionState]
    _workspace_root: Path
    _find_live_session_for_saved_session: Any
    _publish_live_event: Any
    _serialize_live_session: Any
    submit_session_input: Any

    def _message_attachments_for_upload_ids(
        self,
        upload_ids: list[str],
    ) -> list[MessageImageAttachment]:
        return [
            _message_image_attachment(load_uploaded_image_record(upload_id))
            for upload_id in upload_ids
        ]

    def _validate_follow_up_submission(
        self,
        live_session: LiveSessionState,
        text: str,
    ) -> None:
        if live_session.snapshot.pending_user_questions is not None:
            raise RuntimeError(
                "Cannot queue a follow-up while the assistant is waiting for answers."
            )
        if text.strip().startswith("!"):
            raise RuntimeError(
                "Shell commands cannot be sent as follow-ups while the assistant is processing."
            )

    def _should_defer_follow_up(self, live_session: LiveSessionState) -> bool:
        processing_active = bool((live_session.snapshot.processing or {}).get("active"))
        return (
            processing_active
            and not live_session.snapshot.input_enabled
            and live_session.snapshot.pending_user_questions is None
        )

    def _queue_deferred_follow_up(
        self,
        live_session: LiveSessionState,
        *,
        text: str,
        file_paths: list[str] | None = None,
        image_paths: list[str] | None = None,
        image_upload_ids: list[str] | None = None,
        profile_id: str | None = None,
        interactive_mode: bool = False,
        include_tool_history: bool = False,
    ) -> dict[str, Any]:
        follow_up = self._build_queued_follow_up(
            delivery="after_finish",
            text=text,
            file_paths=file_paths,
            image_paths=image_paths,
            image_upload_ids=image_upload_ids,
            profile_id=profile_id,
            interactive_mode=interactive_mode,
            include_tool_history=include_tool_history,
        )
        live_session.queued_follow_ups.append(follow_up)
        self._publish_queued_follow_ups_updated(live_session)
        return self._serialize_live_session(live_session)

    def _queue_checkpoint_follow_up(
        self,
        live_session: LiveSessionState,
        *,
        text: str,
        file_paths: list[str] | None = None,
        image_paths: list[str] | None = None,
        image_upload_ids: list[str] | None = None,
        profile_id: str | None = None,
        interactive_mode: bool = False,
        include_tool_history: bool = False,
    ) -> dict[str, Any]:
        follow_up = self._build_queued_follow_up(
            delivery="checkpoint",
            text=text,
            file_paths=file_paths,
            image_paths=image_paths,
            image_upload_ids=image_upload_ids,
            profile_id=profile_id,
            interactive_mode=interactive_mode,
            include_tool_history=include_tool_history,
        )
        live_session.queued_follow_ups.append(follow_up)
        self._publish_queued_follow_ups_updated(live_session)
        try:
            resolved_images, message_image_attachments = self._resolve_follow_up_images(
                follow_up
            )
            live_session.display.submit_checkpoint_follow_up(
                follow_up.text,
                file_paths=follow_up.file_paths,
                images=resolved_images or None,
                image_attachments=message_image_attachments or None,
                interactive_mode=interactive_mode,
                include_tool_history=include_tool_history,
                item_id=follow_up.follow_up_id,
            )
        except Exception:
            self._pop_queued_follow_up(live_session, follow_up.follow_up_id)
            self._publish_queued_follow_ups_updated(live_session)
            raise
        return self._serialize_live_session(live_session)

    def _build_queued_follow_up(
        self,
        *,
        delivery: FollowUpDelivery,
        text: str,
        file_paths: list[str] | None,
        image_paths: list[str] | None,
        image_upload_ids: list[str] | None,
        profile_id: str | None,
        interactive_mode: bool,
        include_tool_history: bool,
    ) -> QueuedFollowUpInput:
        message_text = text.strip()
        if not message_text and not image_paths and not image_upload_ids:
            raise RuntimeError("Follow-up message cannot be empty.")
        uploads = list(image_upload_ids or [])
        image_attachments = [
            _message_image_payload(attachment)
            for attachment in self._message_attachments_for_upload_ids(uploads)
        ]
        return QueuedFollowUpInput(
            follow_up_id=uuid.uuid4().hex,
            delivery=delivery,
            text=message_text,
            file_paths=list(file_paths or []),
            image_paths=list(image_paths or []),
            image_upload_ids=uploads,
            image_attachments=image_attachments,
            profile_id=profile_id,
            interactive_mode=interactive_mode,
            include_tool_history=include_tool_history,
            created_at=_now_iso(),
        )

    def _resolve_follow_up_images(
        self,
        follow_up: QueuedFollowUpInput,
    ) -> tuple[list[ImageAttachment], list[MessageImageAttachment]]:
        resolved_images = [
            load_workspace_image(self._workspace_root, image_path)
            for image_path in follow_up.image_paths
        ]
        resolved_images.extend(
            load_uploaded_image(upload_id) for upload_id in follow_up.image_upload_ids
        )
        return (
            resolved_images,
            self._message_attachments_for_upload_ids(follow_up.image_upload_ids),
        )

    def _queued_follow_ups_payload(
        self,
        live_session: LiveSessionState,
    ) -> list[dict[str, Any]]:
        return [
            {
                "id": item.follow_up_id,
                "delivery": item.delivery,
                "text": item.text,
                "file_paths": list(item.file_paths),
                "image_attachments": list(item.image_attachments),
                "image_count": len(item.image_paths) + len(item.image_upload_ids),
                "created_at": item.created_at,
                "failed": item.failed,
                "error": item.error,
            }
            for item in live_session.queued_follow_ups
        ]

    def _publish_queued_follow_ups_updated(
        self,
        live_session: LiveSessionState,
    ) -> None:
        self._publish_live_event(
            live_session.live_session_id,
            "queued_follow_ups_updated",
            {"queued_follow_ups": self._queued_follow_ups_payload(live_session)},
        )

    def _pop_queued_follow_up(
        self,
        live_session: LiveSessionState,
        follow_up_id: str,
    ) -> QueuedFollowUpInput:
        for index, item in enumerate(live_session.queued_follow_ups):
            if item.follow_up_id == follow_up_id:
                return live_session.queued_follow_ups.pop(index)
        raise KeyError(follow_up_id)

    def mark_checkpoint_follow_up_delivered(
        self,
        live_session_id: str,
        follow_up_id: str,
    ) -> bool:
        live_session = self._live_sessions.get(live_session_id)
        if live_session is None:
            return False
        try:
            item = self._pop_queued_follow_up(live_session, follow_up_id)
        except KeyError:
            return False
        if item.delivery == "checkpoint":
            self._publish_queued_follow_ups_updated(live_session)
            return True
        live_session.queued_follow_ups.insert(0, item)
        return False

    def cancel_saved_session_follow_up(
        self,
        session_id: str,
        follow_up_id: str,
    ) -> dict[str, Any]:
        live_session = self._find_live_session_for_saved_session(session_id)
        if live_session is None:
            raise KeyError(session_id)
        self._pop_queued_follow_up(live_session, follow_up_id)
        self._publish_queued_follow_ups_updated(live_session)
        return self._serialize_live_session(live_session)

    def send_saved_session_follow_up(
        self,
        session_id: str,
        follow_up_id: str,
        *,
        manual: bool = True,
    ) -> dict[str, Any]:
        live_session = self._find_live_session_for_saved_session(session_id)
        if live_session is None:
            raise KeyError(session_id)
        return self._send_queued_follow_up(
            live_session,
            follow_up_id,
            manual=manual,
        )

    def _send_queued_follow_up(
        self,
        live_session: LiveSessionState,
        follow_up_id: str,
        *,
        manual: bool,
        allow_checkpoint_fallback: bool = False,
    ) -> dict[str, Any]:
        if live_session.status == "ended":
            raise RuntimeError("Live session has already ended.")
        if live_session.snapshot.pending_user_questions is not None:
            raise RuntimeError(
                "Cannot send a follow-up while the assistant is waiting for answers."
            )
        item = next(
            (
                candidate
                for candidate in live_session.queued_follow_ups
                if candidate.follow_up_id == follow_up_id
            ),
            None,
        )
        if item is None:
            raise KeyError(follow_up_id)
        if item.delivery == "checkpoint" and not allow_checkpoint_fallback:
            raise RuntimeError(
                "Checkpoint follow-ups are sent at the next safe checkpoint."
            )
        if (
            manual
            and item.delivery == "after_finish"
            and (
                not live_session.snapshot.input_enabled
                or live_session.snapshot.pending_user_questions is not None
                or bool((live_session.snapshot.processing or {}).get("active"))
            )
        ):
            raise RuntimeError(
                "After-finish follow-ups can only be sent once the assistant is ready."
            )
        item = self._pop_queued_follow_up(live_session, follow_up_id)
        self._publish_queued_follow_ups_updated(live_session)
        try:
            return self.submit_session_input(
                live_session.live_session_id,
                text=item.text,
                file_paths=item.file_paths,
                image_paths=item.image_paths,
                image_upload_ids=item.image_upload_ids,
                profile_id=item.profile_id,
                interactive_mode=item.interactive_mode,
                include_tool_history=item.include_tool_history,
            )
        except Exception as exc:
            item.failed = True
            item.error = format_user_facing_error(exc)
            live_session.queued_follow_ups.insert(0, item)
            self._publish_queued_follow_ups_updated(live_session)
            if manual:
                raise
            self._publish_live_event(
                live_session.live_session_id,
                "message_added",
                {
                    "item_id": f"follow-up-error-{uuid.uuid4().hex}",
                    "role": "error",
                    "content": item.error,
                    "markdown": False,
                },
            )
            return self._serialize_live_session(live_session)

    def _maybe_submit_deferred_follow_up(self, live_session_id: str) -> None:
        live_session = self._live_sessions.get(live_session_id)
        if live_session is None or live_session.status == "ended":
            return
        if not live_session.snapshot.input_enabled:
            return
        if live_session.snapshot.pending_user_questions is not None:
            return
        if bool((live_session.snapshot.processing or {}).get("active")):
            return
        item = next(
            (
                entry
                for entry in live_session.queued_follow_ups
                if not entry.failed
                and (entry.delivery == "after_finish" or entry.delivery == "checkpoint")
            ),
            None,
        )
        if item is None:
            return
        self._send_queued_follow_up(
            live_session,
            item.follow_up_id,
            manual=False,
            allow_checkpoint_fallback=True,
        )
