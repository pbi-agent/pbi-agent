from __future__ import annotations

import base64
import json
import uuid
from dataclasses import dataclass
from pathlib import Path

from pbi_agent.media import load_image_bytes
from pbi_agent.models.messages import ImageAttachment

_UPLOADS_ROOT = Path.home() / ".pbi-agent" / "web_uploads"


@dataclass(slots=True)
class StoredImageUpload:
    upload_id: str
    name: str
    mime_type: str
    byte_count: int


def _metadata_path(upload_id: str) -> Path:
    return _UPLOADS_ROOT / f"{upload_id}.json"


def _data_path(upload_id: str) -> Path:
    return _UPLOADS_ROOT / f"{upload_id}.bin"


def _ensure_uploads_root() -> Path:
    _UPLOADS_ROOT.mkdir(parents=True, exist_ok=True)
    return _UPLOADS_ROOT


def store_uploaded_image_bytes(
    *,
    raw_bytes: bytes,
    name: str,
    upload_id: str | None = None,
) -> StoredImageUpload:
    image = load_image_bytes(name, raw_bytes)
    return store_image_attachment(image, upload_id=upload_id)


def store_image_attachment(
    image: ImageAttachment,
    *,
    upload_id: str | None = None,
) -> StoredImageUpload:
    _ensure_uploads_root()
    resolved_upload_id = upload_id or uuid.uuid4().hex
    metadata_path = _metadata_path(resolved_upload_id)
    data_path = _data_path(resolved_upload_id)
    data_path.write_bytes(base64.b64decode(image.data_base64))
    metadata_path.write_text(
        json.dumps(
            {
                "upload_id": resolved_upload_id,
                "name": image.path,
                "mime_type": image.mime_type,
                "byte_count": image.byte_count,
            }
        ),
        encoding="utf-8",
    )
    return StoredImageUpload(
        upload_id=resolved_upload_id,
        name=image.path,
        mime_type=image.mime_type,
        byte_count=image.byte_count,
    )


def load_uploaded_image(upload_id: str) -> ImageAttachment:
    record = load_uploaded_image_record(upload_id)
    raw_bytes = _data_path(upload_id).read_bytes()
    return load_image_bytes(record.name, raw_bytes)


def load_uploaded_image_record(upload_id: str) -> StoredImageUpload:
    metadata_path = _metadata_path(upload_id)
    if not metadata_path.exists():
        raise KeyError(upload_id)
    payload = json.loads(metadata_path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise KeyError(upload_id)
    name = payload.get("name")
    mime_type = payload.get("mime_type")
    byte_count = payload.get("byte_count")
    if not isinstance(name, str) or not isinstance(mime_type, str):
        raise KeyError(upload_id)
    if not isinstance(byte_count, int):
        byte_count = 0
    return StoredImageUpload(
        upload_id=upload_id,
        name=name,
        mime_type=mime_type,
        byte_count=byte_count,
    )


def uploaded_image_path(upload_id: str) -> Path:
    load_uploaded_image_record(upload_id)
    path = _data_path(upload_id)
    if not path.exists():
        raise KeyError(upload_id)
    return path


def delete_uploaded_images(upload_ids: list[str]) -> None:
    for upload_id in upload_ids:
        for target in (_metadata_path(upload_id), _data_path(upload_id)):
            try:
                target.unlink()
            except FileNotFoundError:
                continue
