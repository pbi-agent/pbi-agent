from __future__ import annotations

import hashlib
import io
import tarfile
from pathlib import Path

import pytest

from pbi_agent import local_assets


def _archive(tmp_path: Path) -> Path:
    archive = tmp_path / "bundle.tar.bz2"
    payload = b"binary"
    with tarfile.open(archive, "w:bz2") as bundle:
        info = tarfile.TarInfo("bin/tool.exe")
        info.size = len(payload)
        bundle.addfile(info, io.BytesIO(payload))
    return archive


def _deny_rename(source: Path, destination: Path) -> None:
    raise PermissionError(5, "Access is denied")


def test_extract_copies_when_windows_refuses_the_rename(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(local_assets.os, "replace", _deny_rename)
    destination = tmp_path / "runtime"

    local_assets.extract(_archive(tmp_path), destination)

    assert (destination / "bin" / "tool.exe").read_bytes() == b"binary"
    assert not (tmp_path / "runtime.tmp").exists()


def test_extract_keeps_the_copy_when_the_staging_directory_stays_locked(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(local_assets.os, "replace", _deny_rename)
    real_rmtree = local_assets.shutil.rmtree

    def rmtree(path: Path, ignore_errors: bool = False) -> None:
        if Path(path).name != "runtime.tmp":
            real_rmtree(path, ignore_errors=ignore_errors)

    monkeypatch.setattr(local_assets.shutil, "rmtree", rmtree)
    destination = tmp_path / "runtime"

    local_assets.extract(_archive(tmp_path), destination)
    # A leftover staging directory does not block the next install.
    local_assets.extract(_archive(tmp_path), destination)

    assert (destination / "bin" / "tool.exe").read_bytes() == b"binary"


def test_failed_copy_leaves_no_partial_destination(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(local_assets.os, "replace", _deny_rename)

    def copytree(source: Path, destination: Path, **_: object) -> None:
        (Path(destination) / "bin").mkdir(parents=True)
        raise OSError("disk full")

    monkeypatch.setattr(local_assets.shutil, "copytree", copytree)
    destination = tmp_path / "runtime"

    with pytest.raises(OSError, match="disk full"):
        local_assets.extract(_archive(tmp_path), destination)
    assert not destination.exists()


def test_download_copies_the_part_file_when_windows_refuses_the_rename(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    payload = b"model"
    asset = local_assets.Asset(
        "https://example.invalid/model.bin", hashlib.sha256(payload).hexdigest(), 5
    )
    destination = tmp_path / "model.bin"
    local_assets.part_path(destination).write_bytes(payload)
    monkeypatch.setattr(local_assets.os, "replace", _deny_rename)

    local_assets.download(asset, destination, tmp_path / "download.lock")

    assert destination.read_bytes() == payload
    assert not local_assets.part_path(destination).exists()


def test_extract_replaces_an_existing_destination(tmp_path: Path) -> None:
    destination = tmp_path / "runtime"
    (destination / "stale").mkdir(parents=True)

    local_assets.extract(_archive(tmp_path), destination)

    assert not (destination / "stale").exists()
    assert (destination / "bin" / "tool.exe").is_file()
