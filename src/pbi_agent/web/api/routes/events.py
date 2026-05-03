from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator
from typing import Annotated, Any
from typing import cast

from fastapi import (
    APIRouter,
    Header,
    HTTPException,
    Query,
    Request,
    WebSocket,
    WebSocketDisconnect,
)
from fastapi.responses import StreamingResponse

from pbi_agent.web.api.deps import SessionIdPath, StreamIdPath
from pbi_agent.web.session_manager import WebSessionManager

router = APIRouter(prefix="/api/events", tags=["events"])

_SSE_HEARTBEAT_SECONDS = 10.0


@router.websocket("/{stream_id}")
async def stream_events(
    websocket: WebSocket,
    stream_id: StreamIdPath,
    since: int = Query(default=0, ge=0),
) -> None:
    manager = cast(WebSessionManager, websocket.app.state.manager)
    try:
        stream = manager.get_event_stream(stream_id)
    except KeyError:
        await websocket.close(code=4404)
        return
    await _stream_event_stream(websocket, stream, since=since)


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
    try:
        stream = manager.get_event_stream(stream_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Event stream not found.") from exc
    return _sse_response(stream, since=_resolve_since(since, last_event_id))


@router.websocket("/sessions/{session_id}")
async def stream_session_events(
    websocket: WebSocket,
    session_id: SessionIdPath,
    since: int = Query(default=0, ge=0),
) -> None:
    manager = cast(WebSessionManager, websocket.app.state.manager)
    try:
        stream = manager.get_session_event_stream(session_id)
    except KeyError:
        await websocket.close(code=4404)
        return
    await _stream_event_stream(websocket, stream, since=since)


@router.get("/sessions/{session_id}")
async def stream_session_events_sse(
    request: Request,
    session_id: SessionIdPath,
    last_event_id: Annotated[
        str | None,
        Header(alias="Last-Event-ID"),
    ] = None,
    since: int = Query(default=0, ge=0),
) -> StreamingResponse:
    manager = cast(WebSessionManager, request.app.state.manager)
    try:
        stream = manager.get_session_event_stream(session_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Event stream not found.") from exc
    return _sse_response(stream, since=_resolve_since(since, last_event_id))


async def _stream_event_stream(
    websocket: WebSocket,
    stream,  # noqa: ANN001
    *,
    since: int = 0,
) -> None:
    await websocket.accept()
    subscriber_id, queue = stream.subscribe()
    last_sent_seq = since
    try:
        for event in stream.snapshot():
            seq = _event_seq(event)
            if seq <= since:
                continue
            await websocket.send_json(event)
            last_sent_seq = max(last_sent_seq, seq)
        while True:
            event = await queue.get()
            seq = _event_seq(event)
            if seq <= last_sent_seq:
                continue
            await websocket.send_json(event)
            last_sent_seq = max(last_sent_seq, seq)
    except WebSocketDisconnect:
        return
    except asyncio.CancelledError:
        return
    finally:
        stream.unsubscribe(subscriber_id)


def _resolve_since(since: int, last_event_id: str | None) -> int:
    if last_event_id is None:
        return since
    try:
        return max(since, int(last_event_id))
    except ValueError:
        return since


def _event_seq(event: dict[str, Any]) -> int:
    seq = event.get("seq")
    return seq if isinstance(seq, int) else 0


def _control_event(event_type: str, seq: int) -> dict[str, Any]:
    return {
        "seq": seq,
        "type": event_type,
        "payload": {},
        "created_at": "",
    }


def _format_sse(event: dict[str, Any], *, event_id: int | None = None) -> str:
    lines = ["event: message"]
    if event_id is not None:
        lines.append(f"id: {event_id}")
    data = json.dumps(event, separators=(",", ":"))
    for line in data.splitlines() or [""]:
        lines.append(f"data: {line}")
    return "\n".join(lines) + "\n\n"


def _sse_response(stream, *, since: int) -> StreamingResponse:  # noqa: ANN001
    return StreamingResponse(
        _iter_sse_events(stream, since=since),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "X-Accel-Buffering": "no",
            "X-Content-Type-Options": "nosniff",
        },
    )


async def _iter_sse_events(stream, *, since: int) -> AsyncIterator[str]:  # noqa: ANN001
    last_sent_seq = since
    yield _format_sse(_control_event("server.connected", since))

    subscriber_id, queue = stream.subscribe()
    try:
        for event in stream.snapshot():
            seq = _event_seq(event)
            if seq <= since:
                continue
            yield _format_sse(event, event_id=seq)
            last_sent_seq = max(last_sent_seq, seq)

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
            if seq <= last_sent_seq:
                continue
            yield _format_sse(event, event_id=seq)
            last_sent_seq = max(last_sent_seq, seq)
    finally:
        stream.unsubscribe(subscriber_id)
