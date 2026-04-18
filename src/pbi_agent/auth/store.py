from __future__ import annotations

import json
import os
import tempfile
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from pbi_agent.auth.models import StoredAuthSession

AUTH_STORE_PATH_ENV = "PBI_AGENT_AUTH_STORE_PATH"
DEFAULT_AUTH_STORE_PATH = Path.home() / ".pbi-agent" / "auth.json"


def auth_store_path() -> Path:
    configured_path = os.getenv(AUTH_STORE_PATH_ENV)
    if configured_path:
        return Path(configured_path).expanduser()
    return DEFAULT_AUTH_STORE_PATH


def load_auth_store_payload() -> dict[str, Any]:
    path = auth_store_path()
    if not path.exists():
        return {"sessions": {}}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"sessions": {}}
    if not isinstance(payload, dict):
        return {"sessions": {}}
    sessions = payload.get("sessions")
    if not isinstance(sessions, dict):
        payload["sessions"] = {}
    return payload


def load_auth_sessions() -> dict[str, StoredAuthSession]:
    payload = load_auth_store_payload()
    sessions_payload = payload.get("sessions", {})
    sessions: dict[str, StoredAuthSession] = {}
    for provider_id, item in sessions_payload.items():
        if not isinstance(provider_id, str) or not isinstance(item, dict):
            continue
        session = _session_from_payload(provider_id, item)
        if session is not None:
            sessions[provider_id] = session
    return sessions


def load_auth_session(provider_id: str) -> StoredAuthSession | None:
    return load_auth_sessions().get(provider_id)


def save_auth_session(session: StoredAuthSession) -> None:
    payload = load_auth_store_payload()
    sessions_payload = payload.setdefault("sessions", {})
    sessions_payload[session.provider_id] = asdict(session)
    _save_auth_store_payload(payload)


def delete_auth_session(provider_id: str) -> bool:
    payload = load_auth_store_payload()
    sessions_payload = payload.setdefault("sessions", {})
    if provider_id not in sessions_payload:
        return False
    del sessions_payload[provider_id]
    _save_auth_store_payload(payload)
    return True


def build_auth_session(
    *,
    provider_id: str,
    backend: str,
    access_token: str,
    refresh_token: str | None = None,
    expires_at: int | None = None,
    account_id: str | None = None,
    email: str | None = None,
    plan_type: str | None = None,
    metadata: dict[str, Any] | None = None,
    previous: StoredAuthSession | None = None,
) -> StoredAuthSession:
    current_iso = datetime.now(timezone.utc).isoformat()
    created_at = previous.created_at if previous is not None else current_iso
    return StoredAuthSession(
        provider_id=provider_id,
        backend=backend,
        access_token=access_token,
        refresh_token=refresh_token,
        expires_at=expires_at,
        account_id=account_id,
        email=email,
        plan_type=plan_type,
        metadata=dict(metadata or {}),
        created_at=created_at,
        updated_at=current_iso,
    )


def redact_auth_session(session: StoredAuthSession | None) -> dict[str, Any] | None:
    if session is None:
        return None
    return {
        "provider_id": session.provider_id,
        "backend": session.backend,
        "has_access_token": bool(session.access_token),
        "has_refresh_token": bool(session.refresh_token),
        "expires_at": session.expires_at,
        "account_id": session.account_id,
        "email": session.email,
        "plan_type": session.plan_type,
        "created_at": session.created_at,
        "updated_at": session.updated_at,
    }


def _session_from_payload(
    provider_id: str,
    payload: dict[str, Any],
) -> StoredAuthSession | None:
    backend = payload.get("backend")
    access_token = payload.get("access_token")
    if not isinstance(backend, str) or not isinstance(access_token, str):
        return None
    refresh_token = payload.get("refresh_token")
    expires_at = payload.get("expires_at")
    account_id = payload.get("account_id")
    email = payload.get("email")
    plan_type = payload.get("plan_type")
    metadata = payload.get("metadata")
    created_at = payload.get("created_at")
    updated_at = payload.get("updated_at")
    return StoredAuthSession(
        provider_id=provider_id,
        backend=backend,
        access_token=access_token,
        refresh_token=refresh_token if isinstance(refresh_token, str) else None,
        expires_at=expires_at if isinstance(expires_at, int) else None,
        account_id=account_id if isinstance(account_id, str) else None,
        email=email if isinstance(email, str) else None,
        plan_type=plan_type if isinstance(plan_type, str) else None,
        metadata=metadata if isinstance(metadata, dict) else {},
        created_at=created_at if isinstance(created_at, str) else "",
        updated_at=updated_at if isinstance(updated_at, str) else "",
    )


def _save_auth_store_payload(payload: dict[str, Any]) -> None:
    path = auth_store_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        "w",
        delete=False,
        dir=path.parent,
        encoding="utf-8",
    ) as handle:
        json.dump(payload, handle, indent=2, sort_keys=True)
        handle.write("\n")
        temp_path = Path(handle.name)
    os.replace(temp_path, path)
