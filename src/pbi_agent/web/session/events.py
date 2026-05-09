from __future__ import annotations

from copy import deepcopy
from typing import Any, Protocol, cast

from pbi_agent.session_store import RunSessionRecord, SessionRecord, SessionStore
from pbi_agent.web.session.serializers import (
    _deserialize_json_field,
    _persisted_web_run_status,
    _snapshot_item_id,
    _web_event_from_record,
)
from pbi_agent.web.session.state import (
    APP_EVENT_STREAM_ID,
    EventStream,
    LiveSessionSnapshot,
    LiveSessionState,
)

TRANSIENT_WEB_EVENT_KEY = "__pbi_transient"


class _EventsManagerSurface(Protocol):
    _app_stream: EventStream
    _directory_key: str
    _live_sessions: dict[str, LiveSessionState]

    def _find_stream_live_session_for_saved_session(
        self,
        session_id: str,
    ) -> LiveSessionState | None: ...

    def _require_saved_session(self, session_id: str) -> SessionRecord: ...

    def _serialize_live_snapshot(
        self,
        live_session: LiveSessionState,
    ) -> dict[str, Any]: ...


class EventsMixin:
    _app_stream: EventStream
    _directory_key: str
    _live_sessions: dict[str, LiveSessionState]

    def get_event_stream(self, stream_id: str) -> EventStream:
        if stream_id == APP_EVENT_STREAM_ID:
            return self._app_stream
        live_session = self._live_sessions.get(stream_id)
        if live_session is not None:
            return live_session.event_stream
        self._require_persisted_web_event_stream(stream_id)
        stream = EventStream()
        stream.load(self._load_persisted_web_events(stream_id))
        return stream

    def get_event_stream_replay(
        self,
        stream_id: str,
        *,
        since: int = 0,
    ) -> list[dict[str, Any]]:
        if stream_id == APP_EVENT_STREAM_ID:
            return []
        if stream_id not in self._live_sessions:
            self._require_persisted_web_event_stream(stream_id)
        return self._load_persisted_web_events(stream_id, since=since)

    def get_session_event_stream(self, session_id: str) -> EventStream:
        manager = cast(_EventsManagerSurface, self)
        manager._require_saved_session(session_id)
        live_session = manager._find_stream_live_session_for_saved_session(session_id)
        if live_session is None:
            with SessionStore() as store:
                web_run = store.get_latest_web_session_run(session_id)
                run = web_run or store.get_latest_session_run(
                    session_id,
                    include_ended=True,
                )
                if run is None:
                    raise KeyError(session_id)
            stream = EventStream()
            stream.load(self._load_persisted_web_events(run.run_session_id))
            return stream
        return live_session.event_stream

    def get_session_event_stream_replay(
        self,
        session_id: str,
        *,
        since: int = 0,
    ) -> list[dict[str, Any]]:
        manager = cast(_EventsManagerSurface, self)
        manager._require_saved_session(session_id)
        live_session = manager._find_stream_live_session_for_saved_session(session_id)
        if live_session is not None:
            return self._load_persisted_web_events(
                live_session.live_session_id,
                since=since,
            )
        with SessionStore() as store:
            web_run = store.get_latest_web_session_run(session_id)
            run = web_run or store.get_latest_session_run(
                session_id,
                include_ended=True,
            )
        if run is None:
            raise KeyError(session_id)
        return self._load_persisted_web_events(run.run_session_id, since=since)

    def resolve_session_event_since(
        self,
        session_id: str,
        since: int,
        *,
        live_session_id: str | None = None,
    ) -> int:
        if since <= 0:
            return since
        manager = cast(_EventsManagerSurface, self)
        manager._require_saved_session(session_id)
        live_session = manager._find_stream_live_session_for_saved_session(session_id)
        if live_session is not None:
            if (
                live_session_id is not None
                and live_session_id != live_session.live_session_id
            ):
                return 0
            latest_seq = live_session.snapshot.last_event_seq
            if latest_seq <= 0:
                latest_seq = self._latest_persisted_web_event_seq(
                    live_session.live_session_id
                )
            return 0 if latest_seq > 0 and since > latest_seq else since

        with SessionStore() as store:
            web_run = store.get_latest_web_session_run(session_id)
            run = web_run or store.get_latest_session_run(
                session_id,
                include_ended=True,
            )
        if run is None:
            raise KeyError(session_id)
        if live_session_id is not None and live_session_id != run.run_session_id:
            return 0
        latest_seq = run.last_event_seq
        if latest_seq <= 0:
            latest_seq = self._latest_persisted_web_event_seq(run.run_session_id)
        return 0 if latest_seq > 0 and since > latest_seq else since

    def _latest_persisted_web_event_seq(self, run_session_id: str) -> int:
        events = self._load_persisted_web_events(run_session_id)
        return max((int(event["seq"]) for event in events), default=0)

    def _require_persisted_web_event_stream(
        self,
        run_session_id: str,
    ) -> RunSessionRecord:
        with SessionStore() as store:
            record = store.get_run_session(run_session_id)
            if (
                record is None
                or record.agent_type != "web_session"
                or record.kind not in {"session", "task"}
            ):
                raise KeyError(run_session_id)
            if record.session_id is not None:
                session = store.get_session(record.session_id)
                if session is None or session.directory != self._directory_key:
                    raise KeyError(run_session_id)
            else:
                metadata = _deserialize_json_field(record.metadata_json)
                if not isinstance(metadata, dict):
                    raise KeyError(run_session_id)
                if metadata.get("directory") != self._directory_key:
                    raise KeyError(run_session_id)
        return record

    def _load_persisted_web_events(
        self,
        run_session_id: str,
        *,
        since: int = 0,
    ) -> list[dict[str, Any]]:
        with SessionStore() as store:
            records = store.list_observability_events(run_session_id=run_session_id)

        web_events: list[tuple[int, int, dict[str, Any]]] = []
        for record in records:
            event = _web_event_from_record(record)
            if event is None:
                continue
            seq = int(event["seq"])
            if seq <= since:
                continue
            web_events.append((seq, record.id, event))
        return [event for _, _, event in sorted(web_events, key=lambda item: item[:2])]

    def _persist_live_event_record(
        self,
        live_session: LiveSessionState,
        event: dict[str, Any],
    ) -> None:
        with SessionStore() as store:
            store.add_web_observability_event_and_update_run_session(
                run_session_id=live_session.live_session_id,
                session_id=live_session.bound_session_id,
                step_index=-int(event["seq"]),
                metadata={
                    "type": event["type"],
                    "payload": event["payload"],
                    "seq": event["seq"],
                    "created_at": event["created_at"],
                    "live_session_id": live_session.live_session_id,
                    "session_id": live_session.bound_session_id,
                },
                status=_persisted_web_run_status(live_session),
                ended_at=live_session.ended_at,
                last_event_seq=live_session.snapshot.last_event_seq,
                snapshot=cast(_EventsManagerSurface, self)._serialize_live_snapshot(
                    live_session
                ),
                exit_code=live_session.exit_code,
                fatal_error=live_session.fatal_error,
            )

    def _sub_agent_snapshot(
        self,
        live_session: LiveSessionState,
        sub_agent_id: str,
    ) -> dict[str, Any]:
        current = live_session.snapshot.sub_agents.get(sub_agent_id)
        snapshot = dict(current) if isinstance(current, dict) else {}
        snapshot.setdefault("title", sub_agent_id or "sub_agent")
        snapshot.setdefault("status", "running")
        return snapshot

    def _has_active_sub_agent_processing(
        self,
        snapshot: LiveSessionSnapshot,
    ) -> bool:
        return any(
            isinstance((processing := sub_agent.get("processing")), dict)
            and processing.get("active") is True
            for sub_agent in snapshot.sub_agents.values()
        )

    def _sub_agent_aggregate_processing_state(self) -> dict[str, Any]:
        return {
            "active": True,
            "phase": "tool_execution",
            "message": "running sub-agent...",
        }

    def _is_sub_agent_aggregate_processing_state(
        self,
        processing: object,
    ) -> bool:
        return (
            isinstance(processing, dict)
            and processing.get("active") is True
            and processing.get("phase") == "tool_execution"
            and processing.get("message") == "running sub-agent..."
        )

    def _publish_live_event(
        self,
        live_session_id: str,
        event_type: str,
        payload: dict[str, Any],
        *,
        allow_after_end: bool = False,
    ) -> dict[str, Any] | None:
        live_session = self._live_sessions[live_session_id]
        with live_session.event_lock:
            if live_session.ended_at is not None and not allow_after_end:
                return None
            enriched_payload = dict(payload)
            transient = bool(enriched_payload.pop(TRANSIENT_WEB_EVENT_KEY, False))
            enriched_payload["live_session_id"] = live_session.live_session_id
            if live_session.bound_session_id is not None:
                enriched_payload["session_id"] = live_session.bound_session_id
                enriched_payload["resume_session_id"] = live_session.bound_session_id
            if transient:
                return live_session.event_stream.publish_transient(
                    event_type,
                    enriched_payload,
                )
            event = live_session.event_stream.publish(
                event_type,
                enriched_payload,
                deliver=False,
            )
            previous_snapshot = deepcopy(live_session.snapshot)
            try:
                self._apply_live_event(live_session, event)
                self._persist_live_event_record(live_session, event)
            except Exception:
                live_session.snapshot = previous_snapshot
                live_session.event_stream.discard(event)
                raise
            live_session.event_stream.deliver(event)
            return event

    def _apply_live_event(
        self,
        live_session: LiveSessionState,
        event: dict[str, Any],
    ) -> None:
        snapshot = live_session.snapshot
        snapshot.last_event_seq = int(event["seq"])
        payload = event["payload"]
        event_type = event["type"]
        raw_sub_agent_id = payload.get("sub_agent_id")
        sub_agent_id = raw_sub_agent_id if isinstance(raw_sub_agent_id, str) else None

        if event_type == "session_reset":
            snapshot.items = []
            snapshot.sub_agents = {}
            snapshot.wait_message = None
            snapshot.processing = None
            snapshot.turn_usage = None
            snapshot.session_ended = False
            snapshot.fatal_error = None
            snapshot.pending_user_questions = None
            return
        if event_type == "session_identity":
            snapshot.session_id = (
                payload["session_id"]
                if isinstance(payload.get("session_id"), str)
                else None
            )
            return
        if event_type == "input_state":
            if sub_agent_id:
                return
            snapshot.input_enabled = bool(payload.get("enabled"))
            return
        if event_type == "wait_state":
            if sub_agent_id:
                sub_agent = self._sub_agent_snapshot(live_session, sub_agent_id)
                if payload.get("active"):
                    sub_agent["wait_message"] = str(
                        payload.get("message") or "Working..."
                    )
                else:
                    sub_agent.pop("wait_message", None)
                snapshot.sub_agents[sub_agent_id] = sub_agent
                return
            snapshot.wait_message = (
                str(payload.get("message") or "Working...")
                if payload.get("active")
                else None
            )
            return
        if event_type == "processing_state":
            if sub_agent_id:
                sub_agent = self._sub_agent_snapshot(live_session, sub_agent_id)
                if payload.get("active"):
                    sub_agent["processing"] = {
                        "active": bool(payload.get("active")),
                        "phase": payload.get("phase"),
                        "message": payload.get("message"),
                        **(
                            {"active_tool_count": payload.get("active_tool_count")}
                            if "active_tool_count" in payload
                            else {}
                        ),
                    }
                    if not (snapshot.processing or {}).get("active"):
                        snapshot.processing = (
                            self._sub_agent_aggregate_processing_state()
                        )
                else:
                    sub_agent.pop("processing", None)
                snapshot.sub_agents[sub_agent_id] = sub_agent
                if self._is_sub_agent_aggregate_processing_state(
                    snapshot.processing
                ) and not self._has_active_sub_agent_processing(snapshot):
                    snapshot.processing = None
                return
            snapshot.processing = (
                dict(payload)
                if payload.get("active")
                else self._sub_agent_aggregate_processing_state()
                if self._has_active_sub_agent_processing(snapshot)
                else None
            )
            return
        if event_type == "user_questions_requested":
            snapshot.pending_user_questions = dict(payload)
            snapshot.input_enabled = False
            return
        if event_type == "user_questions_resolved":
            if snapshot.pending_user_questions and snapshot.pending_user_questions.get(
                "prompt_id"
            ) == payload.get("prompt_id"):
                snapshot.pending_user_questions = None
            return
        if event_type == "usage_updated":
            if isinstance(payload.get("sub_agent_id"), str):
                return
            if payload.get("scope") == "session":
                snapshot.session_usage = payload.get("usage")
            else:
                snapshot.turn_usage = {
                    "usage": payload.get("usage"),
                    "elapsed_seconds": payload.get("elapsed_seconds"),
                }
            return
        if event_type in {"message_added", "thinking_updated", "tool_group_added"}:
            item = dict(payload)
            item["kind"] = (
                "message"
                if event_type == "message_added"
                else "thinking"
                if event_type == "thinking_updated"
                else "tool_group"
            )
            item["itemId"] = str(payload.get("item_id") or "")
            snapshot.items = self._upsert_snapshot_item(snapshot.items, item)
            return
        if event_type == "message_rekeyed":
            raw_item = payload.get("item")
            if not isinstance(raw_item, dict):
                return
            old_item_id = str(payload.get("old_item_id") or "")
            item = dict(raw_item)
            if sub_agent_id and not isinstance(item.get("sub_agent_id"), str):
                item["sub_agent_id"] = sub_agent_id
            item["kind"] = "message"
            item["itemId"] = str(item.get("item_id") or item.get("itemId") or "")
            if old_item_id and old_item_id != item["itemId"]:
                snapshot.items = [
                    existing
                    for existing in snapshot.items
                    if _snapshot_item_id(existing) != old_item_id
                ]
            snapshot.items = self._upsert_snapshot_item(snapshot.items, item)
            return
        if event_type == "message_removed":
            item_id = str(payload.get("item_id") or "")
            if item_id:
                snapshot.items = [
                    item
                    for item in snapshot.items
                    if _snapshot_item_id(item) != item_id
                ]
            return
        if event_type == "sub_agent_state":
            sub_agent_id = str(payload.get("sub_agent_id") or "")
            sub_agent = self._sub_agent_snapshot(live_session, sub_agent_id)
            sub_agent.update(
                {
                    "title": str(payload.get("title") or "sub_agent"),
                    "status": str(payload.get("status") or "running"),
                }
            )
            if sub_agent["status"] not in {"running", "starting"}:
                sub_agent.pop("wait_message", None)
                sub_agent.pop("processing", None)
            snapshot.sub_agents[sub_agent_id] = sub_agent
            return
        if event_type == "session_state":
            if "session_id" in payload:
                snapshot.session_id = (
                    payload["session_id"]
                    if isinstance(payload.get("session_id"), str)
                    else None
                )
            if payload.get("state") == "ended":
                snapshot.session_ended = True
                snapshot.input_enabled = False
                snapshot.wait_message = None
                snapshot.processing = None
                snapshot.fatal_error = (
                    str(payload["fatal_error"])
                    if isinstance(payload.get("fatal_error"), str)
                    else None
                )
                snapshot.pending_user_questions = None
            else:
                snapshot.session_ended = False
                snapshot.fatal_error = None
            return
        if event_type == "session_runtime_updated":
            snapshot.runtime = {
                "provider": payload.get("provider"),
                "provider_id": payload.get("provider_id"),
                "profile_id": payload.get("profile_id"),
                "model": payload.get("model"),
                "reasoning_effort": payload.get("reasoning_effort"),
                "compact_threshold": payload.get("compact_threshold"),
            }

    def _upsert_snapshot_item(
        self,
        items: list[dict[str, Any]],
        next_item: dict[str, Any],
    ) -> list[dict[str, Any]]:
        item_id = str(next_item.get("itemId") or "")
        for index, item in enumerate(items):
            if str(item.get("itemId") or "") != item_id:
                continue
            updated = list(items)
            updated[index] = next_item
            return updated
        return [*items, next_item]
