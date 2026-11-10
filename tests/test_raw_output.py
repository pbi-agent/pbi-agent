from __future__ import annotations

import os
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from pbi_agent.tools import raw_output


def _age(path: Path, delta: timedelta) -> None:
    stamp = (datetime.now(UTC) - delta).timestamp()
    os.utime(path, (stamp, stamp))


def test_raw_output_dir_is_per_user_internal_dir(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.undo()
    assert raw_output.raw_output_dir() == Path.home() / ".pbi-agent" / "shell-output"


def test_save_raw_output_writes_private_unique_files(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    raw_dir = tmp_path / "raw"
    monkeypatch.setattr(raw_output, "raw_output_dir", lambda: raw_dir)

    first = raw_output.save_raw_output(stdout="out", stderr="err")
    second = raw_output.save_raw_output(stdout="out", stderr="err")

    assert first is not None and second is not None
    assert first != second
    assert first.read_text(encoding="utf-8") == (
        "===== stdout =====\nout\n===== stderr =====\nerr\n"
    )
    if os.name != "nt":
        assert raw_dir.stat().st_mode & 0o777 == 0o700
        assert first.stat().st_mode & 0o777 == 0o600


def test_save_raw_output_does_not_prune(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    raw_dir = tmp_path / "raw"
    raw_dir.mkdir()
    monkeypatch.setattr(raw_output, "raw_output_dir", lambda: raw_dir)
    stale = raw_dir / f"{raw_output.RAW_OUTPUT_PREFIX}old{raw_output.RAW_OUTPUT_SUFFIX}"
    stale.write_text("x")
    _age(stale, timedelta(days=3))

    raw_output.save_raw_output(stdout="x", stderr="")

    assert stale.exists()


def test_purge_old_raw_output_files_deletes_only_old_matching_files(
    tmp_path: Path,
) -> None:
    prefix, suffix = raw_output.RAW_OUTPUT_PREFIX, raw_output.RAW_OUTPUT_SUFFIX
    stale = tmp_path / f"{prefix}old{suffix}"
    fresh = tmp_path / f"{prefix}new{suffix}"
    unrelated = tmp_path / "other.log"
    for path in (stale, fresh, unrelated):
        path.write_text("x")
    _age(stale, timedelta(hours=25))
    _age(unrelated, timedelta(days=10))

    deleted = raw_output.purge_old_raw_output_files(
        cutoff=datetime.now(UTC) - raw_output.RAW_OUTPUT_MAX_AGE, root=tmp_path
    )

    assert deleted == 1
    assert not stale.exists()
    assert fresh.exists()
    assert unrelated.exists()


def test_purge_old_raw_output_files_handles_missing_dir(tmp_path: Path) -> None:
    assert (
        raw_output.purge_old_raw_output_files(
            cutoff=datetime.now(UTC), root=tmp_path / "missing"
        )
        == 0
    )


@pytest.mark.parametrize(
    ("compressed", "truncated", "prefix"),
    [
        (False, True, "Output truncated."),
        (True, False, "Output compressed (some content summarized or omitted)."),
        (
            True,
            True,
            "Output compressed (some content summarized or omitted) and truncated.",
        ),
    ],
)
def test_raw_output_notice_reason(
    compressed: bool, truncated: bool, prefix: str
) -> None:
    notice = raw_output.raw_output_notice(
        Path("/x/f.log"), compressed=compressed, truncated=truncated, extra_note="N."
    )
    assert notice.startswith(prefix)
    assert "`/x/f.log`" in notice
    assert notice.endswith(" N.")
