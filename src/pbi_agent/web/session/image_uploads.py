from __future__ import annotations

from typing import Any

from pbi_agent.web.session.serializers import (
    _message_image_attachment,
    _message_image_payload,
)
from pbi_agent.web.session.state import LiveSessionState
from pbi_agent.web.uploads import store_uploaded_image_bytes


class ImageUploadsMixin:
    _find_live_session_for_saved_session: Any
    _require_live_session: Any
    _require_saved_session: Any

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
        live_session: LiveSessionState = self._require_live_session(live_session_id)
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
        live_session: LiveSessionState | None = (
            self._find_live_session_for_saved_session(session_id)
        )
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
