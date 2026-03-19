"""SQLite-backed session store for persisting session metadata."""

from __future__ import annotations

import os
import sqlite3
import threading
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path


SESSION_DB_PATH_ENV = "PBI_AGENT_SESSION_DB_PATH"
DEFAULT_SESSION_DB_PATH = Path.home() / ".pbi-agent" / "sessions.db"

_SCHEMA = """\
CREATE TABLE IF NOT EXISTS sessions (
    session_id    TEXT PRIMARY KEY,
    directory     TEXT NOT NULL,
    provider      TEXT NOT NULL,
    model         TEXT NOT NULL DEFAULT '',
    previous_id   TEXT,
    title         TEXT NOT NULL DEFAULT '',
    total_tokens  INTEGER NOT NULL DEFAULT 0,
    input_tokens  INTEGER NOT NULL DEFAULT 0,
    output_tokens INTEGER NOT NULL DEFAULT 0,
    cost_usd      REAL NOT NULL DEFAULT 0.0,
    created_at    TEXT NOT NULL,
    updated_at    TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_sessions_directory ON sessions(directory);
CREATE INDEX IF NOT EXISTS idx_sessions_updated_at ON sessions(updated_at DESC);

CREATE TABLE IF NOT EXISTS messages (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id  TEXT NOT NULL REFERENCES sessions(session_id),
    role        TEXT NOT NULL,
    content     TEXT NOT NULL DEFAULT '',
    created_at  TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_messages_session_id ON messages(session_id, id);
"""


@dataclass(slots=True)
class SessionRecord:
    session_id: str
    directory: str
    provider: str
    model: str
    previous_id: str | None
    title: str
    total_tokens: int
    input_tokens: int
    output_tokens: int
    cost_usd: float
    created_at: str
    updated_at: str


@dataclass(slots=True)
class MessageRecord:
    id: int
    session_id: str
    role: str
    content: str
    created_at: str


def _db_path() -> Path:
    configured = os.getenv(SESSION_DB_PATH_ENV)
    if configured:
        return Path(configured).expanduser().resolve()
    return DEFAULT_SESSION_DB_PATH


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class SessionStore:
    """Thread-safe SQLite session store."""

    def __init__(self, db_path: Path | None = None) -> None:
        self._path = db_path or _db_path()
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(
            str(self._path),
            check_same_thread=False,
        )
        self._conn.row_factory = sqlite3.Row
        self._lock = threading.Lock()
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.executescript(_SCHEMA)

    def __enter__(self) -> SessionStore:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def close(self) -> None:
        self._conn.close()

    def create_session(
        self,
        directory: str,
        provider: str,
        model: str,
        title: str = "",
    ) -> str:
        session_id = uuid.uuid4().hex
        now = _now_iso()
        with self._lock:
            self._conn.execute(
                "INSERT INTO sessions "
                "(session_id, directory, provider, model, previous_id, title, "
                "total_tokens, input_tokens, output_tokens, cost_usd, "
                "created_at, updated_at) "
                "VALUES (?, ?, ?, ?, NULL, ?, 0, 0, 0, 0.0, ?, ?)",
                (session_id, directory, provider, model, title, now, now),
            )
            self._conn.commit()
        return session_id

    def update_session(
        self,
        session_id: str,
        *,
        previous_id: str | None = None,
        title: str | None = None,
        total_tokens: int | None = None,
        input_tokens: int | None = None,
        output_tokens: int | None = None,
        cost_usd: float | None = None,
    ) -> None:
        clauses: list[str] = []
        params: list[object] = []
        if previous_id is not None:
            clauses.append("previous_id = ?")
            params.append(previous_id)
        if title is not None:
            clauses.append("title = ?")
            params.append(title)
        if total_tokens is not None:
            clauses += [
                "total_tokens = ?",
                "input_tokens = ?",
                "output_tokens = ?",
                "cost_usd = ?",
            ]
            params += [
                total_tokens,
                input_tokens or 0,
                output_tokens or 0,
                cost_usd or 0.0,
            ]
        if not clauses:
            return
        clauses.append("updated_at = ?")
        params.append(_now_iso())
        params.append(session_id)
        sql = f"UPDATE sessions SET {', '.join(clauses)} WHERE session_id = ?"
        with self._lock:
            self._conn.execute(sql, params)
            self._conn.commit()

    def get_session(self, session_id: str) -> SessionRecord | None:
        with self._lock:
            row = self._conn.execute(
                "SELECT * FROM sessions WHERE session_id = ?", (session_id,)
            ).fetchone()
        if row is None:
            return None
        return SessionRecord(**dict(row))

    def list_sessions(
        self,
        directory: str,
        limit: int = 20,
        provider: str | None = None,
    ) -> list[SessionRecord]:
        if provider:
            sql = "SELECT * FROM sessions WHERE directory = ? AND provider = ? ORDER BY updated_at DESC LIMIT ?"
            params: tuple[object, ...] = (directory, provider, limit)
        else:
            sql = "SELECT * FROM sessions WHERE directory = ? ORDER BY updated_at DESC LIMIT ?"
            params = (directory, limit)
        with self._lock:
            rows = self._conn.execute(sql, params).fetchall()
        return [SessionRecord(**dict(r)) for r in rows]

    def list_all_sessions(self, limit: int = 20) -> list[SessionRecord]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT * FROM sessions ORDER BY updated_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [SessionRecord(**dict(r)) for r in rows]

    def add_message(
        self,
        session_id: str,
        role: str,
        content: str,
    ) -> int:
        now = _now_iso()
        with self._lock:
            cursor = self._conn.execute(
                "INSERT INTO messages (session_id, role, content, created_at) "
                "VALUES (?, ?, ?, ?)",
                (session_id, role, content, now),
            )
            self._conn.commit()
        return cursor.lastrowid  # type: ignore[return-value]

    def list_messages(self, session_id: str) -> list[MessageRecord]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT * FROM messages WHERE session_id = ? ORDER BY id ASC",
                (session_id,),
            ).fetchall()
        return [MessageRecord(**dict(r)) for r in rows]
