from __future__ import annotations

import fnmatch
import locale
import os
from pathlib import Path
from typing import Any, Iterator

DEFAULT_MAX_ENTRIES = 200
DEFAULT_MAX_LINES = 200
DEFAULT_MAX_MATCHES = 100
MAX_LIMIT = 1_000

_UTF16_BOMS = (
    (b"\xff\xfe\x00\x00", "utf-32"),
    (b"\x00\x00\xfe\xff", "utf-32"),
    (b"\xff\xfe", "utf-16"),
    (b"\xfe\xff", "utf-16"),
)
_TEXT_CONTROL_BYTES = {7, 8, 9, 10, 12, 13, 27}


def resolve_safe_path(root: Path, raw_path: Any, *, default: str = ".") -> Path:
    path_value = raw_path if isinstance(raw_path, str) and raw_path.strip() else default
    candidate = Path(path_value)
    resolved = (
        candidate.resolve(strict=False)
        if candidate.is_absolute()
        else (root / candidate).resolve(strict=False)
    )

    try:
        resolved.relative_to(root)
    except ValueError as exc:
        raise ValueError(f"path outside workspace is not allowed: {path_value}") from exc

    return resolved


def normalize_positive_int(
    raw_value: Any,
    *,
    default: int,
    upper_bound: int = MAX_LIMIT,
) -> int:
    if not isinstance(raw_value, int) or raw_value < 1:
        return default
    return min(raw_value, upper_bound)


def relative_workspace_path(root: Path, path: Path) -> str:
    return path.resolve(strict=False).relative_to(root).as_posix()


def iter_directory_entries(path: Path, *, recursive: bool) -> Iterator[Path]:
    if not recursive:
        for entry in sorted(path.iterdir(), key=lambda item: item.name.casefold()):
            yield entry
        return

    for current_root, dirnames, filenames in os.walk(path, topdown=True, followlinks=False):
        dirnames.sort(key=str.casefold)
        filenames.sort(key=str.casefold)
        current = Path(current_root)
        for dirname in dirnames:
            yield current / dirname
        for filename in filenames:
            yield current / filename


def matches_glob(root: Path, path: Path, pattern: str | None) -> bool:
    if not isinstance(pattern, str) or not pattern.strip():
        return True

    normalized_pattern = pattern.replace("\\", "/")
    relative_path = relative_workspace_path(root, path)
    if "/" in normalized_pattern:
        return fnmatch.fnmatch(relative_path, normalized_pattern)
    return fnmatch.fnmatch(path.name, normalized_pattern)


def read_text_file(path: Path, *, encoding: str = "auto") -> tuple[str, str]:
    raw_bytes = path.read_bytes()
    normalized_encoding = (
        encoding.strip().lower() if isinstance(encoding, str) and encoding.strip() else "auto"
    )

    bom_encoding = _detect_bom_encoding(raw_bytes)
    if normalized_encoding == "auto":
        if bom_encoding is not None:
            return raw_bytes.decode(bom_encoding), bom_encoding
        if _is_probably_binary(raw_bytes):
            raise ValueError(f"binary file is not supported: {path}")
        return _decode_with_fallbacks(raw_bytes)

    try:
        return raw_bytes.decode(normalized_encoding), normalized_encoding
    except LookupError as exc:
        raise ValueError(f"unknown encoding: {encoding}") from exc
    except UnicodeDecodeError as exc:
        raise ValueError(f"failed to decode file with encoding '{encoding}'") from exc


def _decode_with_fallbacks(raw_bytes: bytes) -> tuple[str, str]:
    candidates = ["utf-8"]
    preferred_encoding = locale.getpreferredencoding(False)
    if preferred_encoding and preferred_encoding.lower() not in {"utf-8", "utf_8"}:
        candidates.append(preferred_encoding)
    candidates.append("latin-1")

    seen: set[str] = set()
    for candidate in candidates:
        normalized = candidate.lower()
        if normalized in seen:
            continue
        seen.add(normalized)
        try:
            return raw_bytes.decode(candidate), candidate
        except UnicodeDecodeError:
            continue

    raise ValueError("failed to decode file with automatic encoding detection")


def _detect_bom_encoding(raw_bytes: bytes) -> str | None:
    if raw_bytes.startswith(b"\xef\xbb\xbf"):
        return "utf-8-sig"

    for bom, encoding in _UTF16_BOMS:
        if raw_bytes.startswith(bom):
            return encoding
    return None


def _is_probably_binary(raw_bytes: bytes) -> bool:
    if not raw_bytes:
        return False

    sample = raw_bytes[:4096]
    if b"\x00" in sample:
        return True

    suspicious = sum(
        1
        for value in sample
        if value < 32 and value not in _TEXT_CONTROL_BYTES
    )
    return suspicious / len(sample) > 0.3
