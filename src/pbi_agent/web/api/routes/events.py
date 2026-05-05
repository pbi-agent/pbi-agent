from __future__ import annotations

import asyncio
import json
import logging
import time
from collections.abc import AsyncIterator
from typing import Annotated, Any
from typing import cast

from fastapi import (
    APIRouter,
    Header,
    HTTPException,
    Query,
    Request,
)
from fastapi.responses import StreamingResponse

from pbi_agent.web.api.deps import SessionIdPath, StreamIdPath
from pbi_agent.web.session_manager import WebSessionManager

router = APIRouter(prefix="/api/events", tags=["events"])
logger = logging.getLogger(__name__)

_SSE_HEARTBEAT_SECONDS = 10.0


def _cursor_source(since: int, last_event_id: str | None) -> str:
    return "last_event_id" if _resolve_since(since, last_event_id) != since else "query"


def _seq_range(events: list[dict[str, Any]]) -> tuple[int | None, int | None]:
    seqs = [_event_seq(event) for event in events if _event_seq(event) > 0]
    return (min(seqs), max(seqs)) if seqs else (None, None)


def _log_sse(action: str, **fields: Any) -> None:
    payload = {"action": action, **fields}
    logger.info(
        "sse.%s %s",
        action,
        json.dumps(payload, sort_keys=True, separators=(",", ":")),
        extra={"pbi_sse": payload},
    )


@router.get("/{stream_id}")
async def stream_events_sse(
    request: Request,
    stream_id: StreamIdPath,
    last_event_id: Annotated[
        str | None,
        Header(alias="Last-Event-ID"),
    ] = None,
    since: int = Query(default=0, ge=0),
) -> StreamingResponse:
    manager = cast(WebSessionManager, request.app.state.manager)
    resume_since = _resolve_since(since, last_event_id)
    try:
        stream = manager.get_event_stream(stream_id)
        replay_events = manager.get_event_stream_replay(
            stream_id,
            since=resume_since,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Event stream not found.") from exc
    return _sse_response(
        stream,
        since=resume_since,
        requested_since=resume_since,
        replay_events=replay_events,
        log_context={
            "endpoint": "stream",
            "stream_kind": "app" if stream_id == "app" else "live",
            "stream_id": stream_id,
            "requested_since": resume_since,
            "resolved_since": resume_since,
            "cursor_source": _cursor_source(since, last_event_id),
            "cursor_reset": False,
        },
    )


@router.get("/sessions/{session_id}")
async def stream_session_events_sse(
    request: Request,
    session_id: SessionIdPath,
    last_event_id: Annotated[
        str | None,
        Header(alias="Last-Event-ID"),
    ] = None,
    since: int = Query(default=0, ge=0),
    live_session_id: str | None = Query(default=None),
) -> StreamingResponse:
    manager = cast(WebSessionManager, request.app.state.manager)
    requested_since = _resolve_since(since, last_event_id)
    try:
        resume_since = manager.resolve_session_event_since(
            session_id,
            requested_since,
            live_session_id=live_session_id,
        )
        stream = manager.get_session_event_stream(session_id)
        replay_events = manager.get_session_event_stream_replay(
            session_id,
            since=resume_since,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Event stream not found.") from exc
    return _sse_response(
        stream,
        since=resume_since,
        requested_since=requested_since,
        replay_events=replay_events,
        log_context={
            "endpoint": "session",
            "stream_kind": "session",
            "session_id": session_id,
            "requested_since": requested_since,
            "resolved_since": resume_since,
            "cursor_source": _cursor_source(since, last_event_id),
            "cursor_reset": requested_since != resume_since,
        },
    )


def _resolve_since(since: int, last_event_id: str | None) -> int:
    if last_event_id is None:
        return since
    try:
        parsed_last_event_id = int(last_event_id)
    except ValueError:
        return since
    return parsed_last_event_id if parsed_last_event_id >= 0 else since


def _event_seq(event: dict[str, Any]) -> int:
    seq = event.get("seq")
    return seq if isinstance(seq, int) else 0


def _is_transient_event(event: dict[str, Any]) -> bool:
    payload = event.get("payload")
    return isinstance(payload, dict) and payload.get("transient") is True


def _control_event(
    event_type: str,
    seq: int,
    payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "seq": seq,
        "type": event_type,
        "payload": payload or {},
        "created_at": "",
    }


def _replay_incomplete_event(
    *,
    requested_since: int,
    resolved_since: int,
    oldest_available_seq: int | None,
    latest_seq: int,
) -> dict[str, Any] | None:
    if requested_since <= 0:
        return None
    if requested_since != resolved_since or requested_since > latest_seq:
        return _control_event(
            "server.replay_incomplete",
            resolved_since,
            {
                "reason": "cursor_ahead",
                "requested_since": requested_since,
                "resolved_since": resolved_since,
                "oldest_available_seq": oldest_available_seq,
                "latest_seq": latest_seq,
                "snapshot_required": True,
            },
        )
    if latest_seq > requested_since and (
        oldest_available_seq is None or oldest_available_seq > requested_since + 1
    ):
        return _control_event(
            "server.replay_incomplete",
            resolved_since,
            {
                "reason": "cursor_too_old",
                "requested_since": requested_since,
                "resolved_since": resolved_since,
                "oldest_available_seq": oldest_available_seq,
                "latest_seq": latest_seq,
                "snapshot_required": True,
            },
        )
    return None


def _subscriber_queue_overflow_event(
    *,
    cursor: int,
    oldest_available_seq: int | None,
    latest_seq: int,
) -> dict[str, Any]:
    return _control_event(
        "server.replay_incomplete",
        latest_seq,
        {
            "reason": "subscriber_queue_overflow",
            "requested_since": cursor,
            "resolved_since": cursor,
            "oldest_available_seq": oldest_available_seq,
            "latest_seq": latest_seq,
            "snapshot_required": True,
        },
    )


def _oldest_available_seq(
    replay_events: list[dict[str, Any]] | None,
    snapshot_events: list[dict[str, Any]],
    *,
    since: int,
) -> int | None:
    seqs = [
        seq
        for event in [*(replay_events or []), *snapshot_events]
        if (seq := _event_seq(event)) > since
    ]
    return min(seqs, default=None)


def _oldest_available_after_cursor(
    *,
    oldest_retained_seq: int | None,
    latest_seq: int,
    cursor: int,
) -> int | None:
    if latest_seq <= cursor:
        return None
    if oldest_retained_seq is None:
        return None
    return max(oldest_retained_seq, cursor + 1)


def _format_sse(event: dict[str, Any], *, event_id: int | None = None) -> str:
    lines = ["event: message"]
    if event_id is not None:
        lines.append(f"id: {event_id}")
    data = json.dumps(event, separators=(",", ":"))
    for line in data.splitlines() or [""]:
        lines.append(f"data: {line}")
    return "\n".join(lines) + "\n\n"


def _sse_response(
    stream,  # noqa: ANN001
    *,
    since: int,
    requested_since: int | None = None,
    replay_events: list[dict[str, Any]] | None = None,
    log_context: dict[str, Any] | None = None,
) -> StreamingResponse:
    return StreamingResponse(
        _iter_sse_events(
            stream,
            since=since,
            requested_since=requested_since,
            replay_events=replay_events,
            log_context=log_context,
        ),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "X-Accel-Buffering": "no",
            "X-Content-Type-Options": "nosniff",
        },
    )


async def _iter_sse_events(
    stream,  # noqa: ANN001
    *,
    since: int,
    requested_since: int | None = None,
    replay_events: list[dict[str, Any]] | None = None,
    log_context: dict[str, Any] | None = None,
) -> AsyncIterator[str]:
    requested_since = since if requested_since is None else requested_since
    last_sent_seq = since
    started_at = time.monotonic()
    yield _format_sse(_control_event("server.connected", since))

    subscriber_id, queue = stream.subscribe()
    try:
        snapshot_events = stream.replay_snapshot(include_transient_since=since)
        oldest_retained_seq, latest_seq = stream.bounds()
        replay_from_seq, replay_to_seq = _seq_range(replay_events or [])
        snapshot_from_seq, snapshot_to_seq = _seq_range(snapshot_events)
        oldest_available_seq = _oldest_available_seq(
            replay_events,
            snapshot_events,
            since=since,
        )
        base_log_context = {
            **(log_context or {}),
            "subscriber_id": subscriber_id,
            "requested_since": requested_since,
            "resolved_since": since,
            "replay_count": len(replay_events or []),
            "replay_from_seq": replay_from_seq,
            "replay_to_seq": replay_to_seq,
            "snapshot_count": len(snapshot_events),
            "snapshot_from_seq": snapshot_from_seq,
            "snapshot_to_seq": snapshot_to_seq,
            "oldest_retained_seq": oldest_retained_seq,
            "oldest_available_seq": oldest_available_seq,
            "latest_seq": latest_seq,
            "subscriber_count": stream.subscriber_count(),
        }
        _log_sse("subscribe", **base_log_context)
        incomplete_event = _replay_incomplete_event(
            requested_since=requested_since,
            resolved_since=since,
            oldest_available_seq=oldest_available_seq,
            latest_seq=latest_seq,
        )
        if incomplete_event is not None:
            _log_sse(
                "replay_incomplete",
                **base_log_context,
                reason=incomplete_event["payload"].get("reason"),
                snapshot_required=incomplete_event["payload"].get("snapshot_required"),
            )
            yield _format_sse(incomplete_event)

        for event in replay_events or []:
            seq = _event_seq(event)
            if seq <= last_sent_seq:
                continue
            last_sent_seq = max(last_sent_seq, seq)
            yield _format_sse(event, event_id=seq)

        for event in snapshot_events:
            seq = _event_seq(event)
            if _is_transient_event(event):
                yield _format_sse(event)
                continue
            if seq <= last_sent_seq:
                continue
            last_sent_seq = max(last_sent_seq, seq)
            yield _format_sse(event, event_id=seq)

        while True:
            try:
                event = await asyncio.wait_for(
                    queue.get(),
                    timeout=_SSE_HEARTBEAT_SECONDS,
                )
            except TimeoutError:
                yield _format_sse(_control_event("server.heartbeat", last_sent_seq))
                continue

            seq = _event_seq(event)
            if event.get("type") == "server.replay_incomplete":
                _oldest_retained_seq, current_latest_seq = stream.bounds()
                latest_seq = max(seq, current_latest_seq)
                overflow_event = _subscriber_queue_overflow_event(
                    cursor=last_sent_seq,
                    oldest_available_seq=_oldest_available_after_cursor(
                        oldest_retained_seq=_oldest_retained_seq,
                        latest_seq=latest_seq,
                        cursor=last_sent_seq,
                    ),
                    latest_seq=latest_seq,
                )
                _log_sse(
                    "replay_incomplete",
                    **(log_context or {}),
                    subscriber_id=subscriber_id,
                    requested_since=last_sent_seq,
                    resolved_since=last_sent_seq,
                    last_sent_seq=last_sent_seq,
                    latest_seq=latest_seq,
                    oldest_available_seq=overflow_event["payload"].get(
                        "oldest_available_seq"
                    ),
                    reason=overflow_event["payload"].get("reason"),
                    snapshot_required=overflow_event["payload"].get(
                        "snapshot_required"
                    ),
                )
                yield _format_sse(overflow_event, event_id=latest_seq)
                break
            if _is_transient_event(event):
                yield _format_sse(event)
                continue
            if seq <= last_sent_seq:
                continue
            last_sent_seq = max(last_sent_seq, seq)
            yield _format_sse(event, event_id=seq)
    finally:
        stream.unsubscribe(subscriber_id)
        _log_sse(
            "unsubscribe",
            **(log_context or {}),
            subscriber_id=subscriber_id,
            last_sent_seq=last_sent_seq,
            subscriber_count=stream.subscriber_count(),
            duration_ms=round((time.monotonic() - started_at) * 1000),
        )
