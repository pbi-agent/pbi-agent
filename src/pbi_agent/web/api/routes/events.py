from __future__ import annotations

import asyncio
from typing import cast

from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect

from pbi_agent.web.api.deps import SessionIdPath, StreamIdPath
from pbi_agent.web.session_manager import WebSessionManager

router = APIRouter(prefix="/api/events", tags=["events"])


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


async def _stream_event_stream(
    websocket: WebSocket,
    stream,  # noqa: ANN001
    *,
    since: int = 0,
) -> None:
    await websocket.accept()
    try:
        for event in stream.snapshot():
            if int(event.get("seq") or 0) <= since:
                continue
            await websocket.send_json(event)
    except WebSocketDisconnect:
        return
    except asyncio.CancelledError:
        return
    subscriber_id, queue = stream.subscribe()
    try:
        while True:
            event = await queue.get()
            await websocket.send_json(event)
    except WebSocketDisconnect:
        return
    except asyncio.CancelledError:
        return
    finally:
        stream.unsubscribe(subscriber_id)
