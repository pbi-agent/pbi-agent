from __future__ import annotations

import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

from pbi_agent.maintenance import check_update_notice, run_startup_maintenance
from pbi_agent.session_store import MessageImageAttachment, SessionStore
from pbi_agent.web import uploads


def _iso(days_ago: int) -> str:
    return (datetime.now(timezone.utc) - timedelta(days=days_ago)).isoformat()


def test_purge_old_session_run_events_leases_and_preserves_kanban(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "sessions.db"
    with SessionStore(db_path) as store:
        old_session = store.create_session("/w", "openai", "gpt", "old")
        new_session = store.create_session("/w", "openai", "gpt", "new")
        old_run = store.create_run_session(
            run_session_id="old-run",
            session_id=old_session,
            agent_name=None,
            agent_type=None,
            provider="openai",
            provider_id=None,
            profile_id=None,
            model="gpt",
        )
        new_run = store.create_run_session(
            run_session_id="new-run",
            session_id=new_session,
            agent_name=None,
            agent_type=None,
            provider="openai",
            provider_id=None,
            profile_id=None,
            model="gpt",
        )
        store.add_message(old_session, "user", "old")
        store.add_message(new_session, "user", "new")
        store.add_observability_event(
            run_session_id=old_run,
            session_id=old_session,
            step_index=1,
            event_type="api",
            timestamp=_iso(40),
        )
        store.add_observability_event(
            run_session_id=new_run,
            session_id=new_session,
            step_index=1,
            event_type="api",
            timestamp=_iso(0),
        )
        task_id = store.create_kanban_task(
            directory="/w",
            title="keep",
            prompt="keep",
            stage="backlog",
            session_id=old_session,
        ).task_id
        store.acquire_web_manager_lease(
            "/old",
            owner_id="owner",
            stale_after_seconds=999999,
        )
        store._conn.execute(  # noqa: SLF001 - targeted fixture aging
            "UPDATE sessions SET updated_at = ? WHERE session_id = ?",
            (_iso(40), old_session),
        )
        store._conn.execute(  # noqa: SLF001
            "UPDATE run_sessions SET started_at = ? WHERE run_session_id = ?",
            (_iso(40), old_run),
        )
        store._conn.execute(  # noqa: SLF001
            "UPDATE web_manager_leases SET heartbeat_at = ? WHERE directory = ?",
            (_iso(40), "/old"),
        )
        store._conn.commit()  # noqa: SLF001

        result = store.purge_old_data(_iso(30))

        assert result["sessions"] == 1
        assert store.get_session(old_session) is None
        assert store.get_session(new_session) is not None
        assert store.get_run_session(old_run) is None
        assert store.get_run_session(new_run) is not None
        preserved_task = store.list_kanban_tasks("/w")[0]
        assert preserved_task.task_id == task_id
        assert preserved_task.session_id is None
        assert (
            store._conn.execute("SELECT COUNT(*) FROM web_manager_leases").fetchone()[0]
            == 0
        )  # noqa: SLF001


def test_upload_purge_preserves_referenced_and_deletes_old_orphans(
    tmp_path: Path,
) -> None:
    cutoff = datetime.now(timezone.utc) - timedelta(days=30)
    keep = tmp_path / "keep.bin"
    old = tmp_path / "old.bin"
    stray = tmp_path / "stray.tmp"
    for path in (keep, old, stray):
        path.write_bytes(b"x")
        os.utime(path, (cutoff.timestamp() - 100, cutoff.timestamp() - 100))

    deleted = uploads.purge_old_unreferenced_uploads(
        cutoff=cutoff,
        referenced_upload_ids={"keep"},
        uploads_root=tmp_path,
    )

    assert deleted == 2
    assert keep.exists()
    assert not old.exists()
    assert not stray.exists()


def test_daily_maintenance_runs_once_and_checks_update(
    tmp_path: Path, monkeypatch
) -> None:
    db_path = tmp_path / "sessions.db"
    config_path = tmp_path / "config.json"
    uploads_root = tmp_path / "uploads"
    uploads_root.mkdir()
    old_upload = uploads_root / "orphan.bin"
    old_upload.write_bytes(b"x")
    cutoff = (datetime.now(timezone.utc) - timedelta(days=31)).timestamp()
    os.utime(old_upload, (cutoff, cutoff))

    monkeypatch.setenv("PBI_AGENT_SESSION_DB_PATH", str(db_path))
    monkeypatch.setenv("PBI_AGENT_INTERNAL_CONFIG_PATH", str(config_path))
    monkeypatch.setattr(uploads, "_UPLOADS_ROOT", uploads_root)
    with patch(
        "pbi_agent.maintenance.check_update_notice", return_value="update"
    ) as check:
        first = run_startup_maintenance()
        second = run_startup_maintenance()

    assert first.ran is True
    assert first.update_notice == "update"
    assert second.ran is False
    assert check.call_count == 1
    assert not old_upload.exists()


def test_update_notice_newer_version(monkeypatch) -> None:
    monkeypatch.setattr("pbi_agent.maintenance.__version__", "1.0.0")
    monkeypatch.setattr("pbi_agent.maintenance._latest_pypi_version", lambda: "1.2.0")

    assert check_update_notice() == (
        "Update available: pbi-agent 1.0.0 -> 1.2.0. "
        "Run: uv tool install pbi-agent --upgrade"
    )


def test_referenced_upload_ids_reads_messages_and_kanban(tmp_path: Path) -> None:
    attachment = MessageImageAttachment(
        upload_id="message-upload",
        name="image.png",
        mime_type="image/png",
        byte_count=1,
        preview_url="/api/uploads/message-upload",
    )
    with SessionStore(tmp_path / "sessions.db") as store:
        session_id = store.create_session("/w", "openai", "gpt")
        store.add_message(session_id, "user", "hi", image_attachments=[attachment])
        task = store.create_kanban_task(
            directory="/w",
            title="task",
            prompt="prompt",
            stage="backlog",
        )
        store._conn.execute(  # noqa: SLF001
            "UPDATE kanban_tasks SET image_attachments_json = ? WHERE task_id = ?",
            (json.dumps([{"upload_id": "task-upload"}]), task.task_id),
        )
        store._conn.commit()  # noqa: SLF001

        assert store.referenced_upload_ids() == {"message-upload", "task-upload"}
