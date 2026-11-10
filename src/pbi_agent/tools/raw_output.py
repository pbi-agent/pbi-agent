"""Raw shell output files saved when returned output is truncated or compressed.

Files live in a per-user internal directory and are purged by age during the
daily startup maintenance (see ``pbi_agent.maintenance``), never on the hot
path of a shell call.
"""

from __future__ import annotations

import os
import uuid
from contextlib import suppress
from datetime import datetime, timedelta
from pathlib import Path

RAW_OUTPUT_DIR_NAME = "shell-output"
RAW_OUTPUT_PREFIX = "shell-output-"
RAW_OUTPUT_SUFFIX = ".log"
RAW_OUTPUT_MAX_AGE = timedelta(hours=24)


def raw_output_dir() -> Path:
    """Per-user internal directory for raw shell output files."""
    return Path.home() / ".pbi-agent" / RAW_OUTPUT_DIR_NAME


def save_raw_output(*, stdout: str, stderr: str) -> Path | None:
    """Write the full raw stdout/stderr to a unique per-user file.

    Returns the file path, or ``None`` when the file could not be written.
    """
    directory = raw_output_dir()
    try:
        directory.mkdir(mode=0o700, parents=True, exist_ok=True)
    except OSError:
        return None
    path = directory / f"{RAW_OUTPUT_PREFIX}{uuid.uuid4().hex}{RAW_OUTPUT_SUFFIX}"
    content = f"===== stdout =====\n{stdout}\n===== stderr =====\n{stderr}\n"
    try:
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8", errors="replace") as handle:
            handle.write(content)
    except OSError:
        with suppress(OSError):
            path.unlink()
        return None
    return path


def purge_old_raw_output_files(*, cutoff: datetime, root: Path | None = None) -> int:
    """Delete raw output files last modified before ``cutoff``.

    Only files matching the raw output naming pattern are considered. Errors
    are ignored. Returns the number of deleted files.
    """
    directory = root or raw_output_dir()
    if not directory.is_dir():
        return 0
    cutoff_timestamp = cutoff.timestamp()
    deleted = 0
    try:
        candidates = list(directory.glob(f"{RAW_OUTPUT_PREFIX}*{RAW_OUTPUT_SUFFIX}"))
    except OSError:
        return 0
    for path in candidates:
        try:
            if not path.is_file() or path.stat().st_mtime >= cutoff_timestamp:
                continue
            path.unlink()
            deleted += 1
        except OSError:
            continue
    return deleted


def raw_output_notice(
    path: Path,
    *,
    compressed: bool,
    truncated: bool,
    extra_note: str | None = None,
) -> str:
    if compressed and truncated:
        reason = "Output compressed (some content summarized or omitted) and truncated."
    elif compressed:
        reason = "Output compressed (some content summarized or omitted)."
    else:
        reason = "Output truncated."
    notice = (
        f"{reason} Full raw output saved to `{path}`. Read it with shell if you "
        "need the complete content."
    )
    if extra_note:
        notice = f"{notice} {extra_note}"
    return notice
