"""SQLite-backed session store for persisting session metadata."""

from __future__ import annotations

import json
import os
import sqlite3
import threading
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path


SESSION_DB_PATH_ENV = "PBI_AGENT_SESSION_DB_PATH"
DEFAULT_SESSION_DB_PATH = Path.home() / ".pbi-agent" / "sessions.db"

KANBAN_STAGE_BACKLOG = "backlog"
KANBAN_STAGE_PLAN = "plan"
KANBAN_STAGE_PROCESSING = "processing"
KANBAN_STAGE_REVIEW = "review"
KANBAN_STAGES = (
    KANBAN_STAGE_BACKLOG,
    KANBAN_STAGE_PLAN,
    KANBAN_STAGE_PROCESSING,
    KANBAN_STAGE_REVIEW,
)

KANBAN_RUN_STATUS_IDLE = "idle"
KANBAN_RUN_STATUS_RUNNING = "running"
KANBAN_RUN_STATUS_COMPLETED = "completed"
KANBAN_RUN_STATUS_FAILED = "failed"

_SCHEMA = """\
CREATE TABLE IF NOT EXISTS sessions (
    session_id    TEXT PRIMARY KEY,
    directory     TEXT NOT NULL,
    provider      TEXT NOT NULL,
    provider_id   TEXT,
    model         TEXT NOT NULL DEFAULT '',
    profile_id    TEXT,
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
    id                     INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id             TEXT NOT NULL REFERENCES sessions(session_id),
    role                   TEXT NOT NULL,
    content                TEXT NOT NULL DEFAULT '',
    provider_id            TEXT,
    profile_id             TEXT,
    file_paths_json        TEXT NOT NULL DEFAULT '[]',
    image_attachments_json TEXT NOT NULL DEFAULT '[]',
    created_at             TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_messages_session_id ON messages(session_id, id);

CREATE TABLE IF NOT EXISTS kanban_tasks (
    task_id               TEXT PRIMARY KEY,
    directory             TEXT NOT NULL,
    title                 TEXT NOT NULL,
    prompt                TEXT NOT NULL DEFAULT '',
    stage                 TEXT NOT NULL,
    position              INTEGER NOT NULL DEFAULT 0,
    project_dir           TEXT NOT NULL DEFAULT '.',
    session_id            TEXT,
    model_profile_id      TEXT,
    run_status            TEXT NOT NULL DEFAULT 'idle',
    last_result_summary   TEXT NOT NULL DEFAULT '',
    created_at            TEXT NOT NULL,
    updated_at            TEXT NOT NULL,
    last_run_started_at   TEXT,
    last_run_finished_at  TEXT
);
CREATE INDEX IF NOT EXISTS idx_kanban_tasks_directory
    ON kanban_tasks(directory, stage, position, updated_at DESC);
"""


@dataclass(slots=True)
class SessionRecord:
    session_id: str
    directory: str
    provider: str
    provider_id: str | None
    model: str
    profile_id: str | None
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
    provider_id: str | None = None
    profile_id: str | None = None
    file_paths: list[str] = field(default_factory=list)
    image_attachments: list["MessageImageAttachment"] = field(default_factory=list)


@dataclass(slots=True)
class MessageImageAttachment:
    upload_id: str
    name: str
    mime_type: str
    byte_count: int
    preview_url: str


@dataclass(slots=True)
class KanbanTaskRecord:
    task_id: str
    directory: str
    title: str
    prompt: str
    stage: str
    position: int
    project_dir: str
    session_id: str | None
    model_profile_id: str | None
    run_status: str
    last_result_summary: str
    created_at: str
    updated_at: str
    last_run_started_at: str | None
    last_run_finished_at: str | None


def _db_path() -> Path:
    configured = os.getenv(SESSION_DB_PATH_ENV)
    if configured:
        return Path(configured).expanduser().resolve()
    return DEFAULT_SESSION_DB_PATH


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _serialize_image_attachments(
    image_attachments: list[MessageImageAttachment] | None,
) -> str:
    if not image_attachments:
        return "[]"
    return json.dumps(
        [
            {
                "upload_id": attachment.upload_id,
                "name": attachment.name,
                "mime_type": attachment.mime_type,
                "byte_count": attachment.byte_count,
                "preview_url": attachment.preview_url,
            }
            for attachment in image_attachments
        ]
    )


def _serialize_file_paths(file_paths: list[str] | None) -> str:
    if not file_paths:
        return "[]"
    return json.dumps([path for path in file_paths if isinstance(path, str)])


def _deserialize_file_paths(raw_value: object) -> list[str]:
    if not isinstance(raw_value, str) or not raw_value.strip():
        return []
    try:
        payload = json.loads(raw_value)
    except json.JSONDecodeError:
        return []
    if not isinstance(payload, list):
        return []
    return [item for item in payload if isinstance(item, str)]


def _deserialize_image_attachments(raw_value: object) -> list[MessageImageAttachment]:
    if not isinstance(raw_value, str) or not raw_value.strip():
        return []
    try:
        payload = json.loads(raw_value)
    except json.JSONDecodeError:
        return []
    if not isinstance(payload, list):
        return []
    attachments: list[MessageImageAttachment] = []
    for item in payload:
        if not isinstance(item, dict):
            continue
        upload_id = item.get("upload_id")
        name = item.get("name")
        mime_type = item.get("mime_type")
        preview_url = item.get("preview_url")
        byte_count = item.get("byte_count")
        if not all(
            isinstance(value, str) and value for value in (upload_id, name, mime_type)
        ):
            continue
        if not isinstance(preview_url, str):
            continue
        if not isinstance(byte_count, int):
            byte_count = 0
        attachments.append(
            MessageImageAttachment(
                upload_id=upload_id,
                name=name,
                mime_type=mime_type,
                byte_count=byte_count,
                preview_url=preview_url,
            )
        )
    return attachments


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
        self._ensure_schema()

    def __enter__(self) -> SessionStore:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def close(self) -> None:
        self._conn.close()

    def _ensure_schema(self) -> None:
        session_columns = {
            row["name"]
            for row in self._conn.execute("PRAGMA table_info(sessions)").fetchall()
        }
        if "provider_id" not in session_columns:
            self._conn.execute("ALTER TABLE sessions ADD COLUMN provider_id TEXT")
        if "profile_id" not in session_columns:
            self._conn.execute("ALTER TABLE sessions ADD COLUMN profile_id TEXT")

        message_columns = {
            row["name"]
            for row in self._conn.execute("PRAGMA table_info(messages)").fetchall()
        }
        if "provider_id" not in message_columns:
            self._conn.execute("ALTER TABLE messages ADD COLUMN provider_id TEXT")
        if "profile_id" not in message_columns:
            self._conn.execute("ALTER TABLE messages ADD COLUMN profile_id TEXT")
        if "file_paths_json" not in message_columns:
            self._conn.execute(
                "ALTER TABLE messages "
                "ADD COLUMN file_paths_json TEXT NOT NULL DEFAULT '[]'"
            )
        if "image_attachments_json" not in message_columns:
            self._conn.execute(
                "ALTER TABLE messages "
                "ADD COLUMN image_attachments_json TEXT NOT NULL DEFAULT '[]'"
            )
        self._conn.commit()

    def create_session(
        self,
        directory: str,
        provider: str,
        model: str,
        title: str = "",
        *,
        provider_id: str | None = None,
        profile_id: str | None = None,
    ) -> str:
        session_id = uuid.uuid4().hex
        now = _now_iso()
        with self._lock:
            self._conn.execute(
                "INSERT INTO sessions "
                "(session_id, directory, provider, provider_id, model, profile_id, previous_id, title, "
                "total_tokens, input_tokens, output_tokens, cost_usd, "
                "created_at, updated_at) "
                "VALUES (?, ?, ?, ?, ?, ?, NULL, ?, 0, 0, 0, 0.0, ?, ?)",
                (
                    session_id,
                    directory,
                    provider,
                    provider_id,
                    model,
                    profile_id,
                    title,
                    now,
                    now,
                ),
            )
            self._conn.commit()
        return session_id

    def update_session(
        self,
        session_id: str,
        *,
        previous_id: str | None = None,
        clear_previous_id: bool = False,
        title: str | None = None,
        provider: str | None = None,
        provider_id: str | None = None,
        total_tokens: int | None = None,
        input_tokens: int | None = None,
        output_tokens: int | None = None,
        cost_usd: float | None = None,
        model: str | None = None,
        profile_id: str | None = None,
    ) -> None:
        clauses: list[str] = []
        params: list[object] = []
        if clear_previous_id:
            clauses.append("previous_id = NULL")
        elif previous_id is not None:
            clauses.append("previous_id = ?")
            params.append(previous_id)
        if title is not None:
            clauses.append("title = ?")
            params.append(title)
        if provider is not None:
            clauses.append("provider = ?")
            params.append(provider)
        if provider_id is not None:
            clauses.append("provider_id = ?")
            params.append(provider_id)
        if model is not None:
            clauses.append("model = ?")
            params.append(model)
        if profile_id is not None:
            clauses.append("profile_id = ?")
            params.append(profile_id)
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

    def delete_session(self, session_id: str) -> bool:
        with self._lock:
            row = self._conn.execute(
                "SELECT 1 FROM sessions WHERE session_id = ?",
                (session_id,),
            ).fetchone()
            if row is None:
                return False
            self._conn.execute(
                "DELETE FROM messages WHERE session_id = ?",
                (session_id,),
            )
            self._conn.execute(
                "DELETE FROM sessions WHERE session_id = ?",
                (session_id,),
            )
            self._conn.commit()
        return True

    def add_message(
        self,
        session_id: str,
        role: str,
        content: str,
        *,
        file_paths: list[str] | None = None,
        provider_id: str | None = None,
        profile_id: str | None = None,
        image_attachments: list[MessageImageAttachment] | None = None,
    ) -> int:
        now = _now_iso()
        with self._lock:
            cursor = self._conn.execute(
                "INSERT INTO messages "
                "(session_id, role, content, provider_id, profile_id, file_paths_json, image_attachments_json, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    session_id,
                    role,
                    content,
                    provider_id,
                    profile_id,
                    _serialize_file_paths(file_paths),
                    _serialize_image_attachments(image_attachments),
                    now,
                ),
            )
            self._conn.commit()
        return cursor.lastrowid  # type: ignore[return-value]

    def list_messages(self, session_id: str) -> list[MessageRecord]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT * FROM messages WHERE session_id = ? ORDER BY id ASC",
                (session_id,),
            ).fetchall()
        messages: list[MessageRecord] = []
        for row in rows:
            data = dict(row)
            messages.append(
                MessageRecord(
                    id=data["id"],
                    session_id=data["session_id"],
                    role=data["role"],
                    content=data["content"],
                    provider_id=data.get("provider_id"),
                    profile_id=data.get("profile_id"),
                    file_paths=_deserialize_file_paths(data.get("file_paths_json")),
                    image_attachments=_deserialize_image_attachments(
                        data.get("image_attachments_json")
                    ),
                    created_at=data["created_at"],
                )
            )
        return messages

    # -- kanban tasks -----------------------------------------------------

    def create_kanban_task(
        self,
        *,
        directory: str,
        title: str,
        prompt: str,
        stage: str = KANBAN_STAGE_BACKLOG,
        project_dir: str = ".",
        session_id: str | None = None,
        model_profile_id: str | None = None,
    ) -> KanbanTaskRecord:
        if stage not in KANBAN_STAGES:
            raise ValueError(f"unsupported kanban stage: {stage}")
        task_id = uuid.uuid4().hex
        now = _now_iso()
        project_dir_value = project_dir.strip() or "."
        with self._lock:
            position = self._next_kanban_position_locked(directory, stage)
            self._conn.execute(
                "INSERT INTO kanban_tasks "
                "(task_id, directory, title, prompt, stage, position, project_dir, "
                "session_id, model_profile_id, run_status, last_result_summary, created_at, updated_at, "
                "last_run_started_at, last_run_finished_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL, NULL)",
                (
                    task_id,
                    directory,
                    title,
                    prompt,
                    stage,
                    position,
                    project_dir_value,
                    session_id,
                    model_profile_id,
                    KANBAN_RUN_STATUS_IDLE,
                    "",
                    now,
                    now,
                ),
            )
            self._conn.commit()
            row = self._conn.execute(
                "SELECT * FROM kanban_tasks WHERE task_id = ?",
                (task_id,),
            ).fetchone()
        assert row is not None
        return KanbanTaskRecord(**dict(row))

    def get_kanban_task(self, task_id: str) -> KanbanTaskRecord | None:
        with self._lock:
            row = self._conn.execute(
                "SELECT * FROM kanban_tasks WHERE task_id = ?",
                (task_id,),
            ).fetchone()
        if row is None:
            return None
        return KanbanTaskRecord(**dict(row))

    def list_kanban_tasks(self, directory: str) -> list[KanbanTaskRecord]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT * FROM kanban_tasks "
                "WHERE directory = ? "
                "ORDER BY CASE stage "
                "WHEN ? THEN 0 "
                "WHEN ? THEN 1 "
                "WHEN ? THEN 2 "
                "WHEN ? THEN 3 "
                "ELSE 4 END, position ASC, updated_at DESC",
                (
                    directory,
                    KANBAN_STAGE_BACKLOG,
                    KANBAN_STAGE_PLAN,
                    KANBAN_STAGE_PROCESSING,
                    KANBAN_STAGE_REVIEW,
                ),
            ).fetchall()
        return [KanbanTaskRecord(**dict(row)) for row in rows]

    def update_kanban_task(
        self,
        task_id: str,
        *,
        title: str | None = None,
        prompt: str | None = None,
        stage: str | None = None,
        project_dir: str | None = None,
        session_id: str | None = None,
        clear_session_id: bool = False,
        model_profile_id: str | None = None,
        clear_model_profile_id: bool = False,
        run_status: str | None = None,
        last_result_summary: str | None = None,
        last_run_started_at: str | None = None,
        last_run_finished_at: str | None = None,
    ) -> KanbanTaskRecord | None:
        clauses: list[str] = []
        params: list[object] = []
        if title is not None:
            clauses.append("title = ?")
            params.append(title)
        if prompt is not None:
            clauses.append("prompt = ?")
            params.append(prompt)
        if stage is not None:
            if stage not in KANBAN_STAGES:
                raise ValueError(f"unsupported kanban stage: {stage}")
            clauses.append("stage = ?")
            params.append(stage)
        if project_dir is not None:
            clauses.append("project_dir = ?")
            params.append(project_dir.strip() or ".")
        if clear_session_id:
            clauses.append("session_id = NULL")
        elif session_id is not None:
            clauses.append("session_id = ?")
            params.append(session_id)
        if clear_model_profile_id:
            clauses.append("model_profile_id = NULL")
        elif model_profile_id is not None:
            clauses.append("model_profile_id = ?")
            params.append(model_profile_id)
        if run_status is not None:
            clauses.append("run_status = ?")
            params.append(run_status)
        if last_result_summary is not None:
            clauses.append("last_result_summary = ?")
            params.append(last_result_summary)
        if last_run_started_at is not None:
            clauses.append("last_run_started_at = ?")
            params.append(last_run_started_at)
        if last_run_finished_at is not None:
            clauses.append("last_run_finished_at = ?")
            params.append(last_run_finished_at)
        if not clauses:
            return self.get_kanban_task(task_id)
        clauses.append("updated_at = ?")
        params.append(_now_iso())
        params.append(task_id)
        with self._lock:
            self._conn.execute(
                f"UPDATE kanban_tasks SET {', '.join(clauses)} WHERE task_id = ?",
                params,
            )
            self._conn.commit()
            row = self._conn.execute(
                "SELECT * FROM kanban_tasks WHERE task_id = ?",
                (task_id,),
            ).fetchone()
        if row is None:
            return None
        return KanbanTaskRecord(**dict(row))

    def move_kanban_task(
        self,
        task_id: str,
        *,
        stage: str,
        position: int | None = None,
    ) -> KanbanTaskRecord | None:
        if stage not in KANBAN_STAGES:
            raise ValueError(f"unsupported kanban stage: {stage}")
        with self._lock:
            current = self._conn.execute(
                "SELECT * FROM kanban_tasks WHERE task_id = ?",
                (task_id,),
            ).fetchone()
            if current is None:
                return None
            record = KanbanTaskRecord(**dict(current))
            old_stage = record.stage
            old_position = record.position
            target_position = position
            if old_stage == stage:
                max_position = max(
                    self._next_kanban_position_locked(record.directory, stage) - 1,
                    0,
                )
                if target_position is None:
                    target_position = old_position
                target_position = min(max(target_position, 0), max_position)
                if target_position > old_position:
                    self._conn.execute(
                        "UPDATE kanban_tasks "
                        "SET position = position - 1, updated_at = ? "
                        "WHERE directory = ? AND stage = ? "
                        "AND position > ? AND position <= ?",
                        (
                            _now_iso(),
                            record.directory,
                            stage,
                            old_position,
                            target_position,
                        ),
                    )
                elif target_position < old_position:
                    self._conn.execute(
                        "UPDATE kanban_tasks "
                        "SET position = position + 1, updated_at = ? "
                        "WHERE directory = ? AND stage = ? "
                        "AND position >= ? AND position < ?",
                        (
                            _now_iso(),
                            record.directory,
                            stage,
                            target_position,
                            old_position,
                        ),
                    )
            else:
                if target_position is None:
                    target_position = self._next_kanban_position_locked(
                        record.directory, stage
                    )
                else:
                    self._shift_kanban_positions_locked(
                        record.directory,
                        stage,
                        start=max(target_position, 0),
                        delta=1,
                    )
            self._conn.execute(
                "UPDATE kanban_tasks "
                "SET stage = ?, position = ?, updated_at = ? "
                "WHERE task_id = ?",
                (stage, max(target_position, 0), _now_iso(), task_id),
            )
            if old_stage != stage:
                self._shift_kanban_positions_locked(
                    record.directory,
                    old_stage,
                    start=old_position + 1,
                    delta=-1,
                )
            self._conn.commit()
            row = self._conn.execute(
                "SELECT * FROM kanban_tasks WHERE task_id = ?",
                (task_id,),
            ).fetchone()
        assert row is not None
        return KanbanTaskRecord(**dict(row))

    def delete_kanban_task(self, task_id: str) -> bool:
        with self._lock:
            current = self._conn.execute(
                "SELECT directory, stage, position FROM kanban_tasks WHERE task_id = ?",
                (task_id,),
            ).fetchone()
            if current is None:
                return False
            self._conn.execute(
                "DELETE FROM kanban_tasks WHERE task_id = ?",
                (task_id,),
            )
            self._shift_kanban_positions_locked(
                str(current["directory"]),
                str(current["stage"]),
                start=int(current["position"]) + 1,
                delta=-1,
            )
            self._conn.commit()
        return True

    def set_kanban_task_running(self, task_id: str) -> KanbanTaskRecord | None:
        now = _now_iso()
        task = self.move_kanban_task(task_id, stage=KANBAN_STAGE_PROCESSING)
        if task is None:
            return None
        return self.update_kanban_task(
            task_id,
            run_status=KANBAN_RUN_STATUS_RUNNING,
            last_run_started_at=now,
            last_result_summary="Running...",
        )

    def set_kanban_task_result(
        self,
        task_id: str,
        *,
        run_status: str,
        summary: str,
        session_id: str | None = None,
    ) -> KanbanTaskRecord | None:
        if run_status not in {
            KANBAN_RUN_STATUS_COMPLETED,
            KANBAN_RUN_STATUS_FAILED,
            KANBAN_RUN_STATUS_IDLE,
            KANBAN_RUN_STATUS_RUNNING,
        }:
            raise ValueError(f"unsupported kanban run status: {run_status}")
        task = self.move_kanban_task(task_id, stage=KANBAN_STAGE_REVIEW)
        if task is None:
            return None
        return self.update_kanban_task(
            task_id,
            run_status=run_status,
            last_result_summary=summary,
            session_id=session_id,
            last_run_finished_at=_now_iso(),
        )

    def normalize_kanban_processing_tasks(self, *, directory: str | None = None) -> int:
        clauses = [
            "stage = ?",
            "run_status = ?",
            "last_result_summary = ?",
            "updated_at = ?",
            "last_run_finished_at = ?",
        ]
        params: list[object] = [
            KANBAN_STAGE_REVIEW,
            KANBAN_RUN_STATUS_FAILED,
            "Interrupted while the app was not running.",
            _now_iso(),
            _now_iso(),
        ]
        where = "WHERE run_status = ? OR stage = ?"
        params.extend([KANBAN_RUN_STATUS_RUNNING, KANBAN_STAGE_PROCESSING])
        if directory is not None:
            where += " AND directory = ?"
            params.append(directory)
        with self._lock:
            cursor = self._conn.execute(
                f"UPDATE kanban_tasks SET {', '.join(clauses)} {where}",
                params,
            )
            self._conn.commit()
            return int(cursor.rowcount or 0)

    def _next_kanban_position_locked(self, directory: str, stage: str) -> int:
        row = self._conn.execute(
            "SELECT COALESCE(MAX(position), -1) AS max_position "
            "FROM kanban_tasks WHERE directory = ? AND stage = ?",
            (directory, stage),
        ).fetchone()
        max_position = int(row["max_position"]) if row is not None else -1
        return max_position + 1

    def _shift_kanban_positions_locked(
        self,
        directory: str,
        stage: str,
        *,
        start: int,
        delta: int,
    ) -> None:
        if delta == 0:
            return
        comparator = ">=" if delta > 0 else ">="
        self._conn.execute(
            f"UPDATE kanban_tasks "
            f"SET position = position + ?, updated_at = ? "
            f"WHERE directory = ? AND stage = ? AND position {comparator} ?",
            (delta, _now_iso(), directory, stage, start),
        )
