#!/usr/bin/env python3
"""Opt-in migration for existing sessions.db files; uses only the Python stdlib.

Stop all pbi-agent processes using the database, then explicitly select it:
    python3 scripts/migrate_messages_is_local_command.py /path/to/sessions.db

A unique, private *.bak SQLite backup is created beside the database before any
schema change. SQLite's backup API includes committed WAL data. A write lock
prevents concurrent writes between the backup and migration; a busy database
fails after five seconds. No application modules or default database are loaded.

Reruns validate the existing column and exit without creating another backup.
Historical rows receive 0: local-command provenance cannot safely be inferred.
Keep the printed backup path. To restore, stop all database users, move the
database and any -wal/-shm sidecars aside, then copy the backup to the original
path. Do not restore over a live database.
"""

from __future__ import annotations

import argparse
from contextlib import closing
import os
from pathlib import Path
import sqlite3
import sys
import tempfile


def _needs_migration(connection: sqlite3.Connection) -> bool:
    table = connection.execute(
        "SELECT type FROM sqlite_schema WHERE name = 'messages' COLLATE NOCASE"
    ).fetchone()
    if table is None or table[0] != "table":
        raise ValueError(
            "Expected an existing messages table; database was not changed."
        )
    for column in connection.execute("PRAGMA table_xinfo(messages)"):
        _, name, column_type, not_null, default, primary_key, hidden = column
        if name.casefold() != "is_local_command":
            continue
        if (
            column_type.upper() != "INTEGER"
            or not_null != 1
            or default != "0"
            or primary_key != 0
            or hidden != 0
        ):
            raise ValueError(
                "Existing messages.is_local_command is incompatible: expected "
                "INTEGER NOT NULL DEFAULT 0. Database was not changed."
            )
        return False
    return True


def _backup_database(database: Path) -> Path:
    descriptor, filename = tempfile.mkstemp(
        prefix=f"{database.name}.before-is-local-command-",
        suffix=".bak",
        dir=database.parent,
    )
    os.close(descriptor)
    backup = Path(filename)
    try:
        # Use a separate read connection: backing up the connection holding an
        # active write transaction can hang. The caller's reserved write lock
        # keeps this reader's snapshot identical to the pre-migration state.
        with (
            closing(
                sqlite3.connect(f"{database.as_uri()}?mode=ro", uri=True)
            ) as source,
            closing(sqlite3.connect(str(backup))) as destination,
        ):
            source.backup(destination)
            if destination.execute("PRAGMA quick_check").fetchall() != [("ok",)]:
                raise ValueError("Backup integrity check failed.")
    except BaseException:
        backup.unlink(missing_ok=True)
        raise
    return backup


def migrate(database: Path) -> Path | None:
    """Return the completed backup path, or None if already migrated."""
    database = database.expanduser().resolve(strict=True)
    if not database.is_file():
        raise ValueError(f"Not a database file: {database}")
    # mode=rw forbids silently creating a new database on a mistyped path.
    with closing(
        sqlite3.connect(
            f"{database.as_uri()}?mode=rw", uri=True, timeout=5, isolation_level=None
        )
    ) as connection:
        connection.execute("BEGIN IMMEDIATE")
        backup = None
        try:
            if not _needs_migration(connection):
                connection.rollback()
                return None
            backup = _backup_database(database)
            connection.execute(
                "ALTER TABLE messages ADD COLUMN "
                "is_local_command INTEGER NOT NULL DEFAULT 0"
            )
            connection.commit()
        except BaseException:
            connection.rollback()
            if backup is not None:
                print(f"Pre-migration backup retained: {backup}", file=sys.stderr)
            raise
    return backup


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "database", type=Path, help="Existing sessions.db path (required)"
    )
    args = parser.parse_args(argv)
    try:
        backup = migrate(args.database)
    except (OSError, sqlite3.Error, ValueError) as exc:
        print(f"Migration failed: {exc}", file=sys.stderr)
        return 1
    if backup is None:
        print("Already migrated: messages.is_local_command is valid; no changes made.")
    else:
        print(f"Backup: {backup}")
        print("Added messages.is_local_command; existing rows default to 0.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
