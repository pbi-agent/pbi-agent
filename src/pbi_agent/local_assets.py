"""Pinned downloads of on-device models and their native runtimes.

Shared by the local features (session titles, speech-to-text): every file is
fetched resumably, checked against a pinned size and SHA-256, and only then
moved to its final name, so a file or directory that exists is complete.
"""

from __future__ import annotations

import hashlib
import logging
import os
import platform
import shutil
import tarfile
import time
import urllib.error
import urllib.request
import zipfile
from dataclasses import dataclass
from pathlib import Path

from pbi_agent import __version__

_log = logging.getLogger(__name__)

_DOWNLOAD_TIMEOUT_SECS = 30
_DOWNLOAD_ATTEMPTS = 5
_CHUNK_BYTES = 1 << 20
LOCK_STALE_SECS = 120
_MACHINES = {"x86_64": "x64", "amd64": "x64", "arm64": "arm64", "aarch64": "arm64"}


@dataclass(frozen=True, slots=True)
class Asset:
    url: str
    sha256: str
    size: int


def machine() -> str | None:
    """This host's CPU architecture as ``x64`` or ``arm64``."""
    return _MACHINES.get(platform.machine().lower())


def part_path(destination: Path) -> Path:
    return destination.with_name(destination.name + ".part")


def claim(lock_file: Path) -> bool:
    """Cross-process single flight: the downloader refreshes the lock file's
    mtime, so an old one belongs to a process that died."""
    try:
        if time.time() - lock_file.stat().st_mtime < LOCK_STALE_SECS:
            return False
        lock_file.unlink(missing_ok=True)
    except FileNotFoundError:
        pass
    try:
        os.close(os.open(lock_file, os.O_CREAT | os.O_EXCL | os.O_WRONLY))
    except FileExistsError:
        return False
    return True


def download(asset: Asset, destination: Path, lock_file: Path) -> None:
    """Resumable download to ``<destination>.part``; renamed into place only
    after the size and SHA-256 match."""
    part = part_path(destination)
    for attempt in range(1, _DOWNLOAD_ATTEMPTS + 1):
        try:
            _fetch(asset, part, lock_file)
            break
        except (urllib.error.URLError, TimeoutError, ConnectionError) as exc:
            if attempt == _DOWNLOAD_ATTEMPTS:
                raise
            _log.debug("Download of %s interrupted (%s); resuming.", asset.url, exc)
            time.sleep(min(2**attempt, 30))
    digest = hashlib.sha256()
    with part.open("rb") as handle:
        while chunk := handle.read(_CHUNK_BYTES):
            digest.update(chunk)
    if part.stat().st_size != asset.size or digest.hexdigest() != asset.sha256:
        part.unlink(missing_ok=True)
        raise ValueError(f"checksum mismatch for {asset.url}")
    os.replace(part, destination)


def _fetch(asset: Asset, part: Path, lock_file: Path) -> None:
    offset = part.stat().st_size if part.exists() else 0
    if offset > asset.size:
        part.unlink()
        offset = 0
    if offset == asset.size:
        return
    headers = {"User-Agent": f"pbi-agent/{__version__}"}
    if offset:
        headers["Range"] = f"bytes={offset}-"
    request = urllib.request.Request(asset.url, headers=headers)
    with urllib.request.urlopen(request, timeout=_DOWNLOAD_TIMEOUT_SECS) as response:
        resumed = offset > 0 and response.status == 206
        with part.open("ab" if resumed else "wb") as handle:
            while chunk := response.read(_CHUNK_BYTES):
                handle.write(chunk)
                lock_file.touch()


def extract(archive: Path, destination: Path) -> None:
    staging = destination.with_name(destination.name + ".tmp")
    shutil.rmtree(staging, ignore_errors=True)
    staging.mkdir(parents=True)
    if archive.name.endswith(".zip"):
        with zipfile.ZipFile(archive) as bundle:
            root = staging.resolve()
            for member in bundle.namelist():
                if not (staging / member).resolve().is_relative_to(root):
                    raise ValueError(f"unsafe path in archive: {member}")
            bundle.extractall(staging)
    else:
        with tarfile.open(archive) as bundle:
            bundle.extractall(staging, filter="data")
    shutil.rmtree(destination, ignore_errors=True)
    os.replace(staging, destination)
