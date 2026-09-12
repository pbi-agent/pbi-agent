from __future__ import annotations

from contextlib import closing
import importlib.util
import os
from pathlib import Path
import sqlite3
import subprocess
import sys

import pytest

from pbi_agent.session_store import SessionStore, _SCHEMA


SCRIPT = (
    Path(__file__).resolve().parents[1]
    / "scripts"
    / "migrate_messages_is_local_command.py"
)
SPEC = importlib.util.spec_from_file_location("migrate_local_command", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
migration = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(migration)


def legacy_database(path: Path) -> None:
    with closing(sqlite3.connect(path)) as connection:
        connection.executescript(
            _SCHEMA.replace(
                "    is_local_command       INTEGER NOT NULL DEFAULT 0,\n", ""
            )
        )
        connection.execute(
            "INSERT INTO sessions (session_id, directory, provider, created_at, updated_at)"
            " VALUES ('session', '/workspace', 'openai', 'now', 'now')"
        )
        connection.executemany(
            "INSERT INTO messages (session_id, role, content, created_at)"
            " VALUES ('session', ?, ?, 'now')",
            [
                ("user", "!ordinary prompt"),
                ("assistant", "## Shell command output\nNot reliable provenance"),
            ],
        )
        connection.commit()


def columns(path: Path) -> list[str]:
    with closing(sqlite3.connect(path)) as connection:
        return [row[1] for row in connection.execute("PRAGMA table_info(messages)")]


def test_migrates_preserves_data_and_creates_restorable_backup(tmp_path: Path) -> None:
    database = tmp_path / "sessions with spaces #?.db"
    legacy_database(database)
    with closing(sqlite3.connect(database)) as connection:
        before = list(connection.iterdump())

    backup = migration.migrate(database)

    assert backup is not None and backup.parent == tmp_path
    if os.name == "posix":
        assert backup.stat().st_mode & 0o777 == 0o600
    with closing(sqlite3.connect(backup)) as connection:
        assert list(connection.iterdump()) == before
        assert connection.execute("PRAGMA integrity_check").fetchone() == ("ok",)
    assert "is_local_command" not in columns(backup)
    with SessionStore(db_path=database) as store:
        messages = store.list_messages("session")
        assert [message.content for message in messages] == [
            "!ordinary prompt",
            "## Shell command output\nNot reliable provenance",
        ]
        assert all(not message.is_local_command for message in messages)
        message_id = store.add_message("session", "user", "!pwd", is_local_command=True)
        message = store.get_message(message_id)
        assert message is not None and message.is_local_command
    with closing(sqlite3.connect(database)) as connection:
        connection.execute(
            "INSERT INTO messages (session_id, role, content, created_at)"
            " VALUES ('session', 'user', 'new ordinary prompt', 'now')"
        )
        assert connection.execute(
            "SELECT is_local_command FROM messages ORDER BY id DESC LIMIT 1"
        ).fetchone() == (0,)


def test_rerun_preserves_values_and_does_not_create_backup(tmp_path: Path) -> None:
    database = tmp_path / "sessions.db"
    legacy_database(database)
    migration.migrate(database)
    with closing(sqlite3.connect(database)) as connection:
        connection.execute("UPDATE messages SET is_local_command = 1 WHERE id = 1")
        connection.commit()
    backups = list(tmp_path.glob("*.bak"))

    assert migration.migrate(database) is None
    assert list(tmp_path.glob("*.bak")) == backups
    with closing(sqlite3.connect(database)) as connection:
        assert connection.execute(
            "SELECT is_local_command FROM messages ORDER BY id"
        ).fetchall() == [(1,), (0,)]


def test_backup_includes_committed_wal_data(tmp_path: Path) -> None:
    database = tmp_path / "sessions.db"
    legacy_database(database)
    with closing(sqlite3.connect(database)) as writer:
        writer.execute("PRAGMA journal_mode=WAL")
        writer.execute("PRAGMA wal_autocheckpoint=0")
        writer.execute("UPDATE messages SET content = 'committed WAL row' WHERE id = 1")
        writer.commit()
        assert Path(f"{database}-wal").stat().st_size > 0

        backup = migration.migrate(database)

        with closing(sqlite3.connect(backup)) as connection:
            assert connection.execute(
                "SELECT content FROM messages WHERE id = 1"
            ).fetchone() == ("committed WAL row",)
            assert "is_local_command" not in columns(backup)


@pytest.mark.parametrize(
    "definition",
    ["TEXT", "INTEGER DEFAULT 0", "INTEGER NOT NULL DEFAULT 1"],
)
def test_rejects_incompatible_existing_column(tmp_path: Path, definition: str) -> None:
    database = tmp_path / "sessions.db"
    legacy_database(database)
    with closing(sqlite3.connect(database)) as connection:
        connection.execute(
            f"ALTER TABLE messages ADD COLUMN is_local_command {definition}"
        )
    before = database.read_bytes()

    with pytest.raises(ValueError, match="incompatible"):
        migration.migrate(database)

    assert database.read_bytes() == before
    assert not list(tmp_path.glob("*.bak"))


@pytest.mark.parametrize("kind", ["missing", "empty", "invalid", "view"])
def test_rejects_bad_input_without_creating_database_or_backup(
    tmp_path: Path, kind: str
) -> None:
    database = tmp_path / "sessions.db"
    if kind == "empty":
        database.touch()
    elif kind == "invalid":
        database.write_text("not sqlite")
    elif kind == "view":
        with closing(sqlite3.connect(database)) as connection:
            connection.execute("CREATE VIEW messages AS SELECT 1 AS id")
    before = database.read_bytes() if database.exists() else None

    with pytest.raises((OSError, ValueError, sqlite3.Error)):
        migration.migrate(database)

    assert (database.read_bytes() if database.exists() else None) == before
    assert not list(tmp_path.glob("*.bak"))


def test_backup_failure_leaves_schema_unchanged(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    database = tmp_path / "sessions.db"
    legacy_database(database)

    def fail(*args: object, **kwargs: object) -> None:
        raise OSError("backup unavailable")

    monkeypatch.setattr(migration.tempfile, "mkstemp", fail)
    with pytest.raises(OSError, match="backup unavailable"):
        migration.migrate(database)
    assert "is_local_command" not in columns(database)
    assert not list(tmp_path.glob("*.bak"))


def test_incomplete_backup_is_removed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    database = tmp_path / "sessions.db"
    legacy_database(database)
    real_connect = sqlite3.connect

    class FailedBackupConnection(sqlite3.Connection):
        def backup(self, *args: object, **kwargs: object) -> None:
            raise sqlite3.OperationalError("backup interrupted")

    def connect(*args: object, **kwargs: object) -> sqlite3.Connection:
        kwargs["factory"] = FailedBackupConnection
        return real_connect(*args, **kwargs)

    with monkeypatch.context() as patch:
        patch.setattr(migration.sqlite3, "connect", connect)
        with pytest.raises(sqlite3.OperationalError, match="backup interrupted"):
            migration.migrate(database)
    assert "is_local_command" not in columns(database)
    assert not list(tmp_path.glob("*.bak"))


def test_busy_database_fails_without_changes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    database = tmp_path / "sessions.db"
    legacy_database(database)
    real_connect = sqlite3.connect

    def connect(*args: object, **kwargs: object) -> sqlite3.Connection:
        kwargs["timeout"] = 0.01
        return real_connect(*args, **kwargs)

    with closing(real_connect(database)) as writer:
        writer.execute("BEGIN IMMEDIATE")
        with monkeypatch.context() as patch:
            patch.setattr(migration.sqlite3, "connect", connect)
            with pytest.raises(sqlite3.OperationalError, match="locked"):
                migration.migrate(database)
        writer.rollback()
    assert "is_local_command" not in columns(database)
    assert not list(tmp_path.glob("*.bak"))


def test_alter_failure_retains_backup_and_rolls_back(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    database = tmp_path / "sessions.db"
    legacy_database(database)
    real_connect = sqlite3.connect

    def connect(*args: object, **kwargs: object) -> sqlite3.Connection:
        connection = real_connect(*args, **kwargs)
        connection.set_authorizer(
            lambda action, *_: (
                sqlite3.SQLITE_DENY
                if action == sqlite3.SQLITE_ALTER_TABLE
                else sqlite3.SQLITE_OK
            )
        )
        return connection

    with monkeypatch.context() as patch:
        patch.setattr(migration.sqlite3, "connect", connect)
        with pytest.raises(sqlite3.DatabaseError, match="not authorized"):
            migration.migrate(database)

    assert "is_local_command" not in columns(database)
    backup = next(tmp_path.glob("*.bak"))
    assert "is_local_command" not in columns(backup)
    assert str(backup) in capsys.readouterr().err
    # The failed transaction released its lock, and a retry keeps the old backup.
    assert migration.migrate(database) != backup
    assert backup.exists()


def test_standalone_cli_requires_explicit_path_and_reports_results(
    tmp_path: Path,
) -> None:
    database = tmp_path / "sessions.db"
    legacy_database(database)

    def run(*args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, str(SCRIPT), *args],
            cwd=tmp_path,
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
        )

    assert run().returncode == 2
    assert not list(tmp_path.glob("*.bak"))
    result = run(str(database))
    assert result.returncode == 0, result.stderr
    assert "Backup:" in result.stdout
    result = run(str(database))
    assert result.returncode == 0, result.stderr
    assert "Already migrated" in result.stdout
    result = run(str(tmp_path / "missing.db"))
    assert result.returncode == 1
    assert "Migration failed:" in result.stderr
