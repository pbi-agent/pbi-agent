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
KANBAN_STAGE_REVIEW = "review"
KANBAN_STAGE_DONE = "done"
KANBAN_DEFAULT_STAGE_SPECS = (
    {
        "stage_id": KANBAN_STAGE_BACKLOG,
        "name": "Backlog",
        "command_id": None,
        "auto_start": False,
    },
    {
        "stage_id": KANBAN_STAGE_DONE,
        "name": "Done",
        "command_id": None,
        "auto_start": False,
    },
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

CREATE TABLE IF NOT EXISTS run_sessions (
    id                      INTEGER PRIMARY KEY AUTOINCREMENT,
    run_session_id          TEXT NOT NULL UNIQUE,
    session_id              TEXT REFERENCES sessions(session_id),
    parent_run_session_id   TEXT,
    agent_name              TEXT,
    agent_type              TEXT,
    provider                TEXT,
    provider_id             TEXT,
    profile_id              TEXT,
    model                   TEXT,
    status                  TEXT NOT NULL,
    started_at              TEXT NOT NULL,
    ended_at                TEXT,
    total_duration_ms       INTEGER,
    input_tokens            INTEGER NOT NULL DEFAULT 0,
    cached_input_tokens     INTEGER NOT NULL DEFAULT 0,
    cache_write_tokens      INTEGER NOT NULL DEFAULT 0,
    cache_write_1h_tokens   INTEGER NOT NULL DEFAULT 0,
    output_tokens           INTEGER NOT NULL DEFAULT 0,
    reasoning_tokens        INTEGER NOT NULL DEFAULT 0,
    tool_use_tokens         INTEGER NOT NULL DEFAULT 0,
    provider_total_tokens   INTEGER NOT NULL DEFAULT 0,
    estimated_cost_usd      REAL NOT NULL DEFAULT 0.0,
    total_tool_calls        INTEGER NOT NULL DEFAULT 0,
    total_api_calls         INTEGER NOT NULL DEFAULT 0,
    error_count             INTEGER NOT NULL DEFAULT 0,
    metadata_json           TEXT NOT NULL DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS idx_run_sessions_session_id
    ON run_sessions(session_id, started_at DESC);
CREATE INDEX IF NOT EXISTS idx_run_sessions_parent_run_session_id
    ON run_sessions(parent_run_session_id);
CREATE INDEX IF NOT EXISTS idx_run_sessions_started_at
    ON run_sessions(started_at DESC);

CREATE TABLE IF NOT EXISTS observability_events (
    id                    INTEGER PRIMARY KEY AUTOINCREMENT,
    run_session_id        TEXT NOT NULL,
    session_id            TEXT,
    step_index            INTEGER NOT NULL,
    event_type            TEXT NOT NULL,
    timestamp             TEXT NOT NULL,
    duration_ms           INTEGER,
    provider              TEXT,
    model                 TEXT,
    url                   TEXT,
    request_config_json   TEXT,
    request_payload_json  TEXT,
    response_payload_json TEXT,
    tool_name             TEXT,
    tool_call_id          TEXT,
    tool_input_json       TEXT,
    tool_output_json      TEXT,
    tool_duration_ms      INTEGER,
    prompt_tokens         INTEGER,
    completion_tokens     INTEGER,
    total_tokens          INTEGER,
    status_code           INTEGER,
    success               INTEGER,
    error_message         TEXT,
    metadata_json         TEXT NOT NULL DEFAULT '{}'
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_observability_events_run_step
    ON observability_events(run_session_id, step_index);
CREATE INDEX IF NOT EXISTS idx_observability_events_session_id
    ON observability_events(session_id, timestamp);
CREATE INDEX IF NOT EXISTS idx_observability_events_run_session_id
    ON observability_events(run_session_id, timestamp);
CREATE INDEX IF NOT EXISTS idx_observability_events_event_type
    ON observability_events(event_type, timestamp);
CREATE INDEX IF NOT EXISTS idx_observability_events_timestamp
    ON observability_events(timestamp);

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

CREATE TABLE IF NOT EXISTS kanban_stage_configs (
    directory         TEXT NOT NULL,
    stage_id          TEXT NOT NULL,
    name              TEXT NOT NULL,
    position          INTEGER NOT NULL,
    model_profile_id  TEXT,
    command_id           TEXT,
    auto_start        INTEGER NOT NULL DEFAULT 0,
    created_at        TEXT NOT NULL,
    updated_at        TEXT NOT NULL,
    PRIMARY KEY (directory, stage_id)
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_kanban_stage_configs_position
    ON kanban_stage_configs(directory, position);

CREATE TABLE IF NOT EXISTS web_manager_leases (
    directory     TEXT PRIMARY KEY,
    owner_id      TEXT NOT NULL,
    heartbeat_at  TEXT NOT NULL,
    created_at    TEXT NOT NULL,
    updated_at    TEXT NOT NULL
);
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
class RunSessionRecord:
    id: int
    run_session_id: str
    session_id: str | None
    parent_run_session_id: str | None
    agent_name: str | None
    agent_type: str | None
    provider: str | None
    provider_id: str | None
    profile_id: str | None
    model: str | None
    status: str
    started_at: str
    ended_at: str | None
    total_duration_ms: int | None
    input_tokens: int
    cached_input_tokens: int
    cache_write_tokens: int
    cache_write_1h_tokens: int
    output_tokens: int
    reasoning_tokens: int
    tool_use_tokens: int
    provider_total_tokens: int
    estimated_cost_usd: float
    total_tool_calls: int
    total_api_calls: int
    error_count: int
    metadata_json: str


@dataclass(slots=True)
class ObservabilityEventRecord:
    id: int
    run_session_id: str
    session_id: str | None
    step_index: int
    event_type: str
    timestamp: str
    duration_ms: int | None
    provider: str | None
    model: str | None
    url: str | None
    request_config_json: str | None
    request_payload_json: str | None
    response_payload_json: str | None
    tool_name: str | None
    tool_call_id: str | None
    tool_input_json: str | None
    tool_output_json: str | None
    tool_duration_ms: int | None
    prompt_tokens: int | None
    completion_tokens: int | None
    total_tokens: int | None
    status_code: int | None
    success: int | None
    error_message: str | None
    metadata_json: str


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


@dataclass(slots=True)
class KanbanStageConfigSpec:
    stage_id: str
    name: str
    model_profile_id: str | None = None
    command_id: str | None = None
    auto_start: bool = False


@dataclass(slots=True)
class KanbanStageConfigRecord:
    directory: str
    stage_id: str
    name: str
    position: int
    model_profile_id: str | None
    command_id: str | None
    auto_start: bool
    created_at: str
    updated_at: str


_KANBAN_FIXED_STAGE_NAMES = {
    KANBAN_STAGE_BACKLOG: "Backlog",
    KANBAN_STAGE_DONE: "Done",
}


def _normalize_kanban_stage_specs(
    stages: list[KanbanStageConfigSpec],
) -> list[KanbanStageConfigSpec]:
    fixed_ids = set(_KANBAN_FIXED_STAGE_NAMES)
    stage_map = {item.stage_id: item for item in stages}
    middle_stages = [item for item in stages if item.stage_id not in fixed_ids]
    normalized: list[KanbanStageConfigSpec] = [
        KanbanStageConfigSpec(
            stage_id=KANBAN_STAGE_BACKLOG,
            name=_KANBAN_FIXED_STAGE_NAMES[KANBAN_STAGE_BACKLOG],
            model_profile_id=None,
            command_id=None,
            auto_start=False,
        )
    ]
    normalized.extend(middle_stages)
    normalized.append(
        KanbanStageConfigSpec(
            stage_id=KANBAN_STAGE_DONE,
            name=_KANBAN_FIXED_STAGE_NAMES[KANBAN_STAGE_DONE],
            model_profile_id=None,
            command_id=None,
            auto_start=False,
        )
    )
    for stage_id in (KANBAN_STAGE_BACKLOG, KANBAN_STAGE_DONE):
        existing = stage_map.get(stage_id)
        if existing is None:
            continue
        if stage_id == KANBAN_STAGE_BACKLOG:
            normalized[0] = KanbanStageConfigSpec(
                stage_id=stage_id,
                name=_KANBAN_FIXED_STAGE_NAMES[stage_id],
                model_profile_id=None,
                command_id=None,
                auto_start=False,
            )
        else:
            normalized[-1] = KanbanStageConfigSpec(
                stage_id=stage_id,
                name=_KANBAN_FIXED_STAGE_NAMES[stage_id],
                model_profile_id=None,
                command_id=None,
                auto_start=False,
            )
    return normalized


def _default_kanban_stage_specs() -> list[KanbanStageConfigSpec]:
    return [
        KanbanStageConfigSpec(
            stage_id=str(spec["stage_id"]),
            name=str(spec["name"]),
            model_profile_id=None,
            command_id=(
                str(spec["command_id"])
                if isinstance(spec.get("command_id"), str) and spec.get("command_id")
                else None
            ),
            auto_start=bool(spec["auto_start"]),
        )
        for spec in KANBAN_DEFAULT_STAGE_SPECS
    ]


def _db_path() -> Path:
    configured = os.getenv(SESSION_DB_PATH_ENV)
    if configured:
        return Path(configured).expanduser().resolve()
    return DEFAULT_SESSION_DB_PATH


def _normalize_directory_key(directory: str) -> str:
    return directory.lower()


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _is_stale_timestamp(timestamp: str, *, stale_after_seconds: float) -> bool:
    try:
        observed = datetime.fromisoformat(timestamp)
    except ValueError:
        return True
    if observed.tzinfo is None:
        observed = observed.replace(tzinfo=timezone.utc)
    age_seconds = (datetime.now(timezone.utc) - observed).total_seconds()
    return age_seconds > stale_after_seconds


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


def _serialize_json(value: object, *, default: str = "{}") -> str:
    if value is None:
        return default
    return json.dumps(value, sort_keys=True)


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


def _kanban_stage_config_record(row: sqlite3.Row) -> KanbanStageConfigRecord:
    data = dict(row)
    return KanbanStageConfigRecord(
        directory=str(data["directory"]),
        stage_id=str(data["stage_id"]),
        name=str(data["name"]),
        position=int(data["position"]),
        model_profile_id=data.get("model_profile_id"),
        command_id=data.get("command_id"),
        auto_start=bool(data.get("auto_start")),
        created_at=str(data["created_at"]),
        updated_at=str(data["updated_at"]),
    )


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
        self._normalize_directory_keys()

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

    def _normalize_directory_keys(self) -> None:
        self._conn.execute(
            "UPDATE sessions SET directory = LOWER(directory) "
            "WHERE directory != LOWER(directory)"
        )
        self._conn.execute(
            "UPDATE kanban_tasks SET directory = LOWER(directory) "
            "WHERE directory != LOWER(directory)"
        )
        self._conn.execute(
            "UPDATE kanban_stage_configs SET directory = LOWER(directory) "
            "WHERE directory != LOWER(directory)"
        )
        self._conn.execute(
            "UPDATE web_manager_leases SET directory = LOWER(directory) "
            "WHERE directory != LOWER(directory)"
        )
        self._conn.commit()

    def acquire_web_manager_lease(
        self,
        directory: str,
        *,
        owner_id: str,
        stale_after_seconds: float,
    ) -> bool:
        normalized_directory = _normalize_directory_key(directory)
        now = _now_iso()
        with self._lock:
            row = self._conn.execute(
                "SELECT owner_id, heartbeat_at FROM web_manager_leases "
                "WHERE directory = ?",
                (normalized_directory,),
            ).fetchone()
            if row is None:
                self._conn.execute(
                    "INSERT INTO web_manager_leases "
                    "(directory, owner_id, heartbeat_at, created_at, updated_at) "
                    "VALUES (?, ?, ?, ?, ?)",
                    (normalized_directory, owner_id, now, now, now),
                )
                self._conn.commit()
                return True

            current_owner = str(row["owner_id"])
            if current_owner == owner_id:
                self._conn.execute(
                    "UPDATE web_manager_leases "
                    "SET heartbeat_at = ?, updated_at = ? "
                    "WHERE directory = ?",
                    (now, now, normalized_directory),
                )
                self._conn.commit()
                return True

            heartbeat_at = str(row["heartbeat_at"])
            if not _is_stale_timestamp(
                heartbeat_at,
                stale_after_seconds=stale_after_seconds,
            ):
                return False

            self._conn.execute(
                "UPDATE web_manager_leases "
                "SET owner_id = ?, heartbeat_at = ?, created_at = ?, updated_at = ? "
                "WHERE directory = ?",
                (owner_id, now, now, now, normalized_directory),
            )
            self._conn.commit()
            return True

    def renew_web_manager_lease(self, directory: str, *, owner_id: str) -> bool:
        normalized_directory = _normalize_directory_key(directory)
        now = _now_iso()
        with self._lock:
            cursor = self._conn.execute(
                "UPDATE web_manager_leases "
                "SET heartbeat_at = ?, updated_at = ? "
                "WHERE directory = ? AND owner_id = ?",
                (now, now, normalized_directory, owner_id),
            )
            self._conn.commit()
            return bool(cursor.rowcount)

    def release_web_manager_lease(self, directory: str, *, owner_id: str) -> bool:
        normalized_directory = _normalize_directory_key(directory)
        with self._lock:
            cursor = self._conn.execute(
                "DELETE FROM web_manager_leases WHERE directory = ? AND owner_id = ?",
                (normalized_directory, owner_id),
            )
            self._conn.commit()
            return bool(cursor.rowcount)

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
        normalized_directory = _normalize_directory_key(directory)
        with self._lock:
            self._conn.execute(
                "INSERT INTO sessions "
                "(session_id, directory, provider, provider_id, model, profile_id, previous_id, title, "
                "total_tokens, input_tokens, output_tokens, cost_usd, "
                "created_at, updated_at) "
                "VALUES (?, ?, ?, ?, ?, ?, NULL, ?, 0, 0, 0, 0.0, ?, ?)",
                (
                    session_id,
                    normalized_directory,
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
        normalized_directory = _normalize_directory_key(directory)
        if provider:
            sql = "SELECT * FROM sessions WHERE directory = ? AND provider = ? ORDER BY updated_at DESC LIMIT ?"
            params: tuple[object, ...] = (normalized_directory, provider, limit)
        else:
            sql = "SELECT * FROM sessions WHERE directory = ? ORDER BY updated_at DESC LIMIT ?"
            params = (normalized_directory, limit)
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
                "DELETE FROM observability_events WHERE session_id = ?",
                (session_id,),
            )
            self._conn.execute(
                "DELETE FROM run_sessions WHERE session_id = ?",
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

    def create_run_session(
        self,
        *,
        session_id: str | None,
        agent_name: str | None,
        agent_type: str | None,
        provider: str | None,
        provider_id: str | None,
        profile_id: str | None,
        model: str | None,
        status: str = "started",
        parent_run_session_id: str | None = None,
        metadata: dict[str, object] | None = None,
    ) -> str:
        run_session_id = uuid.uuid4().hex
        now = _now_iso()
        with self._lock:
            self._conn.execute(
                "INSERT INTO run_sessions "
                "(run_session_id, session_id, parent_run_session_id, agent_name, "
                "agent_type, provider, provider_id, profile_id, model, status, "
                "started_at, metadata_json) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    run_session_id,
                    session_id,
                    parent_run_session_id,
                    agent_name,
                    agent_type,
                    provider,
                    provider_id,
                    profile_id,
                    model,
                    status,
                    now,
                    _serialize_json(metadata, default="{}"),
                ),
            )
            self._conn.commit()
        return run_session_id

    def update_run_session(
        self,
        run_session_id: str,
        *,
        status: str | None = None,
        ended_at: str | None = None,
        total_duration_ms: int | None = None,
        input_tokens: int | None = None,
        cached_input_tokens: int | None = None,
        cache_write_tokens: int | None = None,
        cache_write_1h_tokens: int | None = None,
        output_tokens: int | None = None,
        reasoning_tokens: int | None = None,
        tool_use_tokens: int | None = None,
        provider_total_tokens: int | None = None,
        estimated_cost_usd: float | None = None,
        total_tool_calls: int | None = None,
        total_api_calls: int | None = None,
        error_count: int | None = None,
        metadata: dict[str, object] | None = None,
    ) -> None:
        clauses: list[str] = []
        params: list[object] = []
        scalar_values = {
            "status": status,
            "ended_at": ended_at,
            "total_duration_ms": total_duration_ms,
            "input_tokens": input_tokens,
            "cached_input_tokens": cached_input_tokens,
            "cache_write_tokens": cache_write_tokens,
            "cache_write_1h_tokens": cache_write_1h_tokens,
            "output_tokens": output_tokens,
            "reasoning_tokens": reasoning_tokens,
            "tool_use_tokens": tool_use_tokens,
            "provider_total_tokens": provider_total_tokens,
            "estimated_cost_usd": estimated_cost_usd,
            "total_tool_calls": total_tool_calls,
            "total_api_calls": total_api_calls,
            "error_count": error_count,
        }
        for key, value in scalar_values.items():
            if value is None:
                continue
            clauses.append(f"{key} = ?")
            params.append(value)
        if metadata is not None:
            clauses.append("metadata_json = ?")
            params.append(_serialize_json(metadata, default="{}"))
        if not clauses:
            return
        params.append(run_session_id)
        with self._lock:
            self._conn.execute(
                f"UPDATE run_sessions SET {', '.join(clauses)} "
                "WHERE run_session_id = ?",
                params,
            )
            self._conn.commit()

    def get_run_session(self, run_session_id: str) -> RunSessionRecord | None:
        with self._lock:
            row = self._conn.execute(
                "SELECT * FROM run_sessions WHERE run_session_id = ?",
                (run_session_id,),
            ).fetchone()
        if row is None:
            return None
        return RunSessionRecord(**dict(row))

    def list_run_sessions(self, session_id: str) -> list[RunSessionRecord]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT * FROM run_sessions WHERE session_id = ? "
                "ORDER BY started_at ASC, id ASC",
                (session_id,),
            ).fetchall()
        return [RunSessionRecord(**dict(row)) for row in rows]

    def add_observability_event(
        self,
        *,
        run_session_id: str,
        session_id: str | None,
        step_index: int,
        event_type: str,
        timestamp: str | None = None,
        duration_ms: int | None = None,
        provider: str | None = None,
        model: str | None = None,
        url: str | None = None,
        request_config: object | None = None,
        request_payload: object | None = None,
        response_payload: object | None = None,
        tool_name: str | None = None,
        tool_call_id: str | None = None,
        tool_input: object | None = None,
        tool_output: object | None = None,
        tool_duration_ms: int | None = None,
        prompt_tokens: int | None = None,
        completion_tokens: int | None = None,
        total_tokens: int | None = None,
        status_code: int | None = None,
        success: bool | None = None,
        error_message: str | None = None,
        metadata: dict[str, object] | None = None,
    ) -> int:
        with self._lock:
            cursor = self._conn.execute(
                "INSERT INTO observability_events "
                "(run_session_id, session_id, step_index, event_type, timestamp, "
                "duration_ms, provider, model, url, request_config_json, "
                "request_payload_json, response_payload_json, tool_name, "
                "tool_call_id, tool_input_json, tool_output_json, tool_duration_ms, "
                "prompt_tokens, completion_tokens, total_tokens, status_code, "
                "success, error_message, metadata_json) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, "
                "?, ?, ?, ?, ?)",
                (
                    run_session_id,
                    session_id,
                    step_index,
                    event_type,
                    timestamp or _now_iso(),
                    duration_ms,
                    provider,
                    model,
                    url,
                    _serialize_json(request_config, default="null"),
                    _serialize_json(request_payload, default="null"),
                    _serialize_json(response_payload, default="null"),
                    tool_name,
                    tool_call_id,
                    _serialize_json(tool_input, default="null"),
                    _serialize_json(tool_output, default="null"),
                    tool_duration_ms,
                    prompt_tokens,
                    completion_tokens,
                    total_tokens,
                    status_code,
                    None if success is None else int(success),
                    error_message,
                    _serialize_json(metadata, default="{}"),
                ),
            )
            self._conn.commit()
        return cursor.lastrowid  # type: ignore[return-value]

    def list_observability_events(
        self,
        *,
        run_session_id: str,
    ) -> list[ObservabilityEventRecord]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT * FROM observability_events WHERE run_session_id = ? "
                "ORDER BY step_index ASC, id ASC",
                (run_session_id,),
            ).fetchall()
        return [ObservabilityEventRecord(**dict(row)) for row in rows]

    # -- dashboard / observability aggregation ----------------------------

    def get_dashboard_stats(
        self,
        *,
        directory: str | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> dict[str, object]:
        """Return aggregated overview, provider/model breakdown, and daily buckets."""
        normalized_dir = _normalize_directory_key(directory) if directory else None

        base_where = "WHERE 1=1"
        params: list[object] = []
        if normalized_dir is not None:
            base_where += " AND s.directory = ?"
            params.append(normalized_dir)
        if start_date is not None:
            base_where += " AND rs.started_at >= ?"
            params.append(start_date)
        if end_date is not None:
            base_where += " AND rs.started_at <= ?"
            params.append(end_date)

        join_clause = (
            "FROM run_sessions rs JOIN sessions s ON rs.session_id = s.session_id"
        )

        with self._lock:
            # -- overview --
            overview_row = self._conn.execute(
                f"SELECT "
                "COUNT(DISTINCT rs.session_id) AS total_sessions, "
                "COUNT(*) AS total_runs, "
                "COALESCE(SUM(rs.input_tokens), 0) AS total_input_tokens, "
                "COALESCE(SUM(rs.cached_input_tokens), 0) AS total_cached_tokens, "
                "COALESCE(SUM(rs.output_tokens), 0) AS total_output_tokens, "
                "COALESCE(SUM(rs.reasoning_tokens), 0) AS total_reasoning_tokens, "
                "COALESCE(SUM(rs.estimated_cost_usd), 0.0) AS total_cost, "
                "COALESCE(SUM(rs.total_api_calls), 0) AS total_api_calls, "
                "COALESCE(SUM(rs.total_tool_calls), 0) AS total_tool_calls, "
                "COALESCE(SUM(rs.error_count), 0) AS total_errors, "
                "AVG(rs.total_duration_ms) AS avg_duration_ms, "
                "COUNT(CASE WHEN rs.status = 'completed' THEN 1 END) AS completed_runs, "
                "COUNT(CASE WHEN rs.status = 'failed' THEN 1 END) AS failed_runs "
                f"{join_clause} {base_where}",
                params,
            ).fetchone()

            overview = (
                dict(overview_row)
                if overview_row
                else {
                    "total_sessions": 0,
                    "total_runs": 0,
                    "total_input_tokens": 0,
                    "total_cached_tokens": 0,
                    "total_output_tokens": 0,
                    "total_reasoning_tokens": 0,
                    "total_cost": 0.0,
                    "total_api_calls": 0,
                    "total_tool_calls": 0,
                    "total_errors": 0,
                    "avg_duration_ms": None,
                    "completed_runs": 0,
                    "failed_runs": 0,
                }
            )

            # -- provider/model breakdown --
            breakdown_rows = self._conn.execute(
                f"SELECT "
                "rs.provider, rs.model, "
                "COUNT(*) AS run_count, "
                "COALESCE(SUM(rs.input_tokens + rs.output_tokens), 0) AS total_tokens, "
                "COALESCE(SUM(rs.estimated_cost_usd), 0.0) AS total_cost, "
                "AVG(rs.total_duration_ms) AS avg_duration_ms, "
                "COALESCE(SUM(rs.error_count), 0) AS error_count, "
                "COALESCE(SUM(rs.total_api_calls), 0) AS total_api_calls, "
                "COALESCE(SUM(rs.total_tool_calls), 0) AS total_tool_calls "
                f"{join_clause} {base_where} "
                "GROUP BY rs.provider, rs.model "
                "ORDER BY total_tokens DESC",
                params,
            ).fetchall()
            breakdown = [dict(row) for row in breakdown_rows]

            # -- daily time-series buckets --
            daily_rows = self._conn.execute(
                f"SELECT "
                "DATE(rs.started_at) AS date, "
                "COUNT(*) AS runs, "
                "COALESCE(SUM(rs.input_tokens + rs.output_tokens), 0) AS tokens, "
                "COALESCE(SUM(rs.estimated_cost_usd), 0.0) AS cost, "
                "COALESCE(SUM(rs.error_count), 0) AS errors "
                f"{join_clause} {base_where} "
                "GROUP BY DATE(rs.started_at) "
                "ORDER BY date ASC",
                params,
            ).fetchall()
            daily = [dict(row) for row in daily_rows]

        return {
            "overview": overview,
            "breakdown": breakdown,
            "daily": daily,
        }

    _ALLOWED_RUN_SORT_COLUMNS = frozenset(
        {
            "started_at",
            "ended_at",
            "total_duration_ms",
            "estimated_cost_usd",
            "input_tokens",
            "output_tokens",
            "error_count",
            "total_tool_calls",
            "total_api_calls",
        }
    )

    def list_all_run_sessions(
        self,
        *,
        directory: str | None = None,
        limit: int = 50,
        offset: int = 0,
        status: str | None = None,
        provider: str | None = None,
        model: str | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
        sort_by: str = "started_at",
        sort_dir: str = "desc",
    ) -> tuple[list[dict[str, object]], int]:
        """Return a page of run_sessions with optional filters + total count.

        Each dict in the returned list has all run_sessions columns plus
        ``session_title`` (from the joined sessions table).
        """
        normalized_dir = _normalize_directory_key(directory) if directory else None

        where_clauses = ["1=1"]
        params: list[object] = []
        if normalized_dir is not None:
            where_clauses.append("s.directory = ?")
            params.append(normalized_dir)
        if status is not None:
            where_clauses.append("rs.status = ?")
            params.append(status)
        if provider is not None:
            where_clauses.append("rs.provider = ?")
            params.append(provider)
        if model is not None:
            where_clauses.append("rs.model = ?")
            params.append(model)
        if start_date is not None:
            where_clauses.append("rs.started_at >= ?")
            params.append(start_date)
        if end_date is not None:
            where_clauses.append("rs.started_at <= ?")
            params.append(end_date)

        where = " AND ".join(where_clauses)
        join = (
            "FROM run_sessions rs LEFT JOIN sessions s ON rs.session_id = s.session_id"
        )

        # Sanitise sort column to prevent injection.
        if sort_by not in self._ALLOWED_RUN_SORT_COLUMNS:
            sort_by = "started_at"
        direction = "ASC" if sort_dir.upper() == "ASC" else "DESC"

        with self._lock:
            total_row = self._conn.execute(
                f"SELECT COUNT(*) AS cnt {join} WHERE {where}",
                params,
            ).fetchone()
            total_count: int = total_row["cnt"] if total_row else 0

            rows = self._conn.execute(
                f"SELECT rs.*, s.title AS session_title {join} "
                f"WHERE {where} "
                f"ORDER BY rs.{sort_by} {direction}, rs.id DESC "
                "LIMIT ? OFFSET ?",
                [*params, limit, offset],
            ).fetchall()

        results: list[dict[str, object]] = [dict(row) for row in rows]
        return results, total_count

    # -- kanban tasks -----------------------------------------------------

    def list_kanban_stage_configs(
        self, directory: str
    ) -> list[KanbanStageConfigRecord]:
        normalized_directory = _normalize_directory_key(directory)
        with self._lock:
            self._ensure_canonical_kanban_stages_locked(normalized_directory)
            rows = self._conn.execute(
                "SELECT * FROM kanban_stage_configs "
                "WHERE directory = ? ORDER BY position ASC, stage_id ASC",
                (normalized_directory,),
            ).fetchall()
        return [_kanban_stage_config_record(row) for row in rows]

    def get_kanban_stage_config(
        self, directory: str, stage_id: str
    ) -> KanbanStageConfigRecord | None:
        normalized_directory = _normalize_directory_key(directory)
        with self._lock:
            self._ensure_canonical_kanban_stages_locked(normalized_directory)
            row = self._conn.execute(
                "SELECT * FROM kanban_stage_configs "
                "WHERE directory = ? AND stage_id = ?",
                (normalized_directory, stage_id),
            ).fetchone()
        if row is None:
            return None
        return _kanban_stage_config_record(row)

    def replace_kanban_stage_configs(
        self,
        directory: str,
        *,
        stages: list[KanbanStageConfigSpec],
    ) -> list[KanbanStageConfigRecord]:
        normalized_directory = _normalize_directory_key(directory)
        if not stages:
            raise ValueError("board must contain at least one stage")
        normalized: list[KanbanStageConfigSpec] = []
        seen_stage_ids: set[str] = set()
        for item in stages:
            stage_id = item.stage_id.strip()
            name = item.name.strip()
            if not stage_id:
                raise ValueError("stage ID cannot be empty")
            if not name:
                raise ValueError("stage name cannot be empty")
            if stage_id in seen_stage_ids:
                raise ValueError(f"duplicate stage ID: {stage_id}")
            seen_stage_ids.add(stage_id)
            normalized.append(
                KanbanStageConfigSpec(
                    stage_id=stage_id,
                    name=name,
                    model_profile_id=(
                        item.model_profile_id.strip()
                        if isinstance(item.model_profile_id, str)
                        and item.model_profile_id.strip()
                        else None
                    ),
                    command_id=(
                        item.command_id.strip()
                        if isinstance(item.command_id, str) and item.command_id.strip()
                        else None
                    ),
                    auto_start=bool(item.auto_start),
                )
            )
        normalized = _normalize_kanban_stage_specs(normalized)
        seen_stage_ids = {item.stage_id for item in normalized}
        with self._lock:
            existing = {
                row["stage_id"]: row
                for row in self._conn.execute(
                    "SELECT * FROM kanban_stage_configs WHERE directory = ?",
                    (normalized_directory,),
                ).fetchall()
            }
            task_rows = self._conn.execute(
                "SELECT DISTINCT stage FROM kanban_tasks WHERE directory = ?",
                (normalized_directory,),
            ).fetchall()
            missing_task_stages = sorted(
                {
                    str(row["stage"])
                    for row in task_rows
                    if str(row["stage"]) not in seen_stage_ids
                }
            )
            if missing_task_stages:
                raise ValueError(
                    "cannot remove stages that still contain tasks: "
                    + ", ".join(missing_task_stages)
                )
            now = _now_iso()
            self._conn.execute(
                "DELETE FROM kanban_stage_configs WHERE directory = ?",
                (normalized_directory,),
            )
            for position, item in enumerate(normalized):
                created_at = (
                    str(existing[item.stage_id]["created_at"])
                    if item.stage_id in existing
                    else now
                )
                self._conn.execute(
                    "INSERT INTO kanban_stage_configs "
                    "(directory, stage_id, name, position, model_profile_id, command_id, "
                    "auto_start, created_at, updated_at) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        normalized_directory,
                        item.stage_id,
                        item.name,
                        position,
                        item.model_profile_id,
                        item.command_id,
                        1 if item.auto_start else 0,
                        created_at,
                        now,
                    ),
                )
            self._conn.commit()
            rows = self._conn.execute(
                "SELECT * FROM kanban_stage_configs "
                "WHERE directory = ? ORDER BY position ASC, stage_id ASC",
                (normalized_directory,),
            ).fetchall()
        return [_kanban_stage_config_record(row) for row in rows]

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
        task_id = uuid.uuid4().hex
        now = _now_iso()
        project_dir_value = project_dir.strip() or "."
        normalized_directory = _normalize_directory_key(directory)
        with self._lock:
            self._require_kanban_stage_locked(normalized_directory, stage)
            position = self._next_kanban_position_locked(normalized_directory, stage)
            self._conn.execute(
                "INSERT INTO kanban_tasks "
                "(task_id, directory, title, prompt, stage, position, project_dir, "
                "session_id, model_profile_id, run_status, last_result_summary, created_at, updated_at, "
                "last_run_started_at, last_run_finished_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL, NULL)",
                (
                    task_id,
                    normalized_directory,
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
        normalized_directory = _normalize_directory_key(directory)
        with self._lock:
            self._ensure_canonical_kanban_stages_locked(normalized_directory)
            rows = self._conn.execute(
                "SELECT task.* FROM kanban_tasks AS task "
                "LEFT JOIN kanban_stage_configs AS stage_cfg "
                "ON stage_cfg.directory = task.directory AND stage_cfg.stage_id = task.stage "
                "WHERE task.directory = ? "
                "ORDER BY "
                "CASE WHEN stage_cfg.position IS NULL THEN 1 ELSE 0 END ASC, "
                "stage_cfg.position ASC, task.position ASC, task.updated_at DESC",
                (normalized_directory,),
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
        clear_last_run_started_at: bool = False,
        clear_last_run_finished_at: bool = False,
    ) -> KanbanTaskRecord | None:
        with self._lock:
            current_row = self._conn.execute(
                "SELECT directory FROM kanban_tasks WHERE task_id = ?",
                (task_id,),
            ).fetchone()
        if current_row is None:
            return None
        current_directory = str(current_row["directory"])
        clauses: list[str] = []
        params: list[object] = []
        if title is not None:
            clauses.append("title = ?")
            params.append(title)
        if prompt is not None:
            clauses.append("prompt = ?")
            params.append(prompt)
        if stage is not None:
            self._require_kanban_stage_locked(current_directory, stage)
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
        elif clear_last_run_started_at:
            clauses.append("last_run_started_at = NULL")
        if last_run_finished_at is not None:
            clauses.append("last_run_finished_at = ?")
            params.append(last_run_finished_at)
        elif clear_last_run_finished_at:
            clauses.append("last_run_finished_at = NULL")
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
        with self._lock:
            current = self._conn.execute(
                "SELECT * FROM kanban_tasks WHERE task_id = ?",
                (task_id,),
            ).fetchone()
            if current is None:
                return None
            record = KanbanTaskRecord(**dict(current))
            self._require_kanban_stage_locked(record.directory, stage)
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
        return self.update_kanban_task(
            task_id,
            run_status=KANBAN_RUN_STATUS_RUNNING,
            last_run_started_at=now,
            clear_last_run_finished_at=True,
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
        return self.update_kanban_task(
            task_id,
            run_status=run_status,
            last_result_summary=summary,
            session_id=session_id,
            last_run_finished_at=_now_iso(),
        )

    def normalize_kanban_running_tasks(self, *, directory: str | None = None) -> int:
        clauses = [
            "run_status = ?",
            "last_result_summary = ?",
            "updated_at = ?",
            "last_run_finished_at = ?",
        ]
        params: list[object] = [
            KANBAN_RUN_STATUS_FAILED,
            "Interrupted while the app was not running.",
            _now_iso(),
            _now_iso(),
        ]
        where = "WHERE run_status = ?"
        params.append(KANBAN_RUN_STATUS_RUNNING)
        if directory is not None:
            where += " AND directory = ?"
            params.append(_normalize_directory_key(directory))
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

    def _ensure_canonical_kanban_stages_locked(self, directory: str) -> None:
        rows = self._conn.execute(
            "SELECT * FROM kanban_stage_configs "
            "WHERE directory = ? ORDER BY position ASC, stage_id ASC",
            (directory,),
        ).fetchall()
        if rows:
            existing_records = [_kanban_stage_config_record(row) for row in rows]
            desired_specs = _normalize_kanban_stage_specs(
                [
                    KanbanStageConfigSpec(
                        stage_id=record.stage_id,
                        name=record.name,
                        model_profile_id=record.model_profile_id,
                        command_id=record.command_id,
                        auto_start=record.auto_start,
                    )
                    for record in existing_records
                ]
            )
            records_match = len(existing_records) == len(desired_specs) and all(
                record.stage_id == spec.stage_id
                and record.position == position
                and record.name == spec.name
                and record.model_profile_id == spec.model_profile_id
                and record.command_id == spec.command_id
                and record.auto_start == spec.auto_start
                for position, (record, spec) in enumerate(
                    zip(existing_records, desired_specs, strict=False)
                )
            )
            if records_match:
                return
            existing_by_id = {record.stage_id: record for record in existing_records}
        else:
            desired_specs = _default_kanban_stage_specs()
            existing_by_id = {}
        now = _now_iso()
        self._conn.execute(
            "DELETE FROM kanban_stage_configs WHERE directory = ?",
            (directory,),
        )
        for position, spec in enumerate(desired_specs):
            existing = existing_by_id.get(spec.stage_id)
            self._conn.execute(
                "INSERT INTO kanban_stage_configs "
                "(directory, stage_id, name, position, model_profile_id, command_id, "
                "auto_start, created_at, updated_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    directory,
                    spec.stage_id,
                    spec.name,
                    position,
                    spec.model_profile_id,
                    spec.command_id,
                    1 if spec.auto_start else 0,
                    existing.created_at if existing is not None else now,
                    now,
                ),
            )
        self._conn.commit()

    def _require_kanban_stage_locked(self, directory: str, stage: str) -> None:
        self._ensure_canonical_kanban_stages_locked(directory)
        row = self._conn.execute(
            "SELECT 1 FROM kanban_stage_configs "
            "WHERE directory = ? AND stage_id = ? LIMIT 1",
            (directory, stage),
        ).fetchone()
        if row is None:
            raise ValueError(f"unsupported kanban stage: {stage}")
