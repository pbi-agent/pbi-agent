from __future__ import annotations

import base64
from pathlib import Path
from typing import Any

from pbi_agent.models.messages import ImageAttachment
from pbi_agent.tools.workspace_access import relative_workspace_path
from pbi_agent.tools.workspace_access import resolve_safe_path

SUPPORTED_IMAGE_MIME_TYPES = (
    "image/png",
    "image/jpeg",
    "image/webp",
    "image/heic",
    "image/heif",
)
_MAX_IMAGE_BYTES = 20 * 1024 * 1024  # 20 MB
_MIME_LABELS = {
    "image/png": "PNG",
    "image/jpeg": "JPEG",
    "image/webp": "WEBP",
    "image/heic": "HEIC",
    "image/heif": "HEIF",
}
_HEIC_BRANDS = {"heic", "heix", "hevc", "hevx", "heim", "heis"}
_HEIF_BRANDS = {"mif1", "msf1", "heif"}


def load_workspace_image(root: Path, raw_path: Any) -> ImageAttachment:
    if not isinstance(raw_path, str) or not raw_path.strip():
        raise ValueError("image path must be a non-empty string")

    target_path = resolve_safe_path(root, raw_path)
    if not target_path.exists():
        raise ValueError(f"path not found: {target_path}")
    if not target_path.is_file():
        raise ValueError(f"path is not a file: {target_path}")

    return load_image_bytes(
        relative_workspace_path(root, target_path),
        target_path.read_bytes(),
    )


def load_image_bytes(path_label: str, raw_bytes: bytes) -> ImageAttachment:
    if not isinstance(path_label, str) or not path_label.strip():
        raise ValueError("image path must be a non-empty string")
    if len(raw_bytes) > _MAX_IMAGE_BYTES:
        size_mb = len(raw_bytes) / (1024 * 1024)
        raise ValueError(
            f"image too large: {Path(path_label).name} is {size_mb:.1f} MB "
            f"(limit: {_MAX_IMAGE_BYTES // (1024 * 1024)} MB)"
        )
    mime_type = detect_image_mime_type(raw_bytes)
    if mime_type is None:
        allowed = ", ".join(_MIME_LABELS[mime] for mime in SUPPORTED_IMAGE_MIME_TYPES)
        raise ValueError(
            f"unsupported image format: {Path(path_label).name} (allowed: {allowed})"
        )

    return ImageAttachment(
        path=path_label.strip(),
        mime_type=mime_type,
        data_base64=base64.b64encode(raw_bytes).decode("ascii"),
        byte_count=len(raw_bytes),
    )


def detect_image_mime_type(raw_bytes: bytes) -> str | None:
    if raw_bytes.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if raw_bytes.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if len(raw_bytes) >= 12 and raw_bytes[:4] == b"RIFF" and raw_bytes[8:12] == b"WEBP":
        return "image/webp"
    heif_mime_type = _detect_heif_mime_type(raw_bytes)
    if heif_mime_type is not None:
        return heif_mime_type
    return None


def _detect_heif_mime_type(raw_bytes: bytes) -> str | None:
    if len(raw_bytes) < 12 or raw_bytes[4:8] != b"ftyp":
        return None

    brands = [raw_bytes[8:12]]
    compatible_brands = raw_bytes[16:]
    brands.extend(
        compatible_brands[index : index + 4]
        for index in range(0, len(compatible_brands) - 3, 4)
    )
    for brand in brands:
        brand_name = brand.decode("ascii", errors="ignore").strip()
        if brand_name in _HEIC_BRANDS:
            return "image/heic"
        if brand_name in _HEIF_BRANDS:
            return "image/heif"
    return None


def data_url_for_image(image: ImageAttachment) -> str:
    return f"data:{image.mime_type};base64,{image.data_base64}"
