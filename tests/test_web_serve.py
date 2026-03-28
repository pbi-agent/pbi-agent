from __future__ import annotations

import asyncio
from io import StringIO
from unittest.mock import patch

from fastapi.testclient import TestClient
from rich.console import Console

from pbi_agent.branding import PBI_AGENT_NAME, PBI_AGENT_TAGLINE
from pbi_agent.config import Settings
from pbi_agent.web.serve import PBIWebServer, create_app


def _settings() -> Settings:
    return Settings(api_key="test-key", provider="openai", model="gpt-5.4")


def test_web_server_prints_banner_and_starts_uvicorn() -> None:
    server = PBIWebServer(settings=_settings(), port=9001)
    output = StringIO()
    server.console = Console(file=output, width=80, highlight=False)

    with patch("pbi_agent.web.serve.uvicorn.Server.run") as mock_run:
        server.serve(debug=False)

    rendered = output.getvalue()
    assert PBI_AGENT_NAME in rendered
    assert PBI_AGENT_TAGLINE in rendered
    assert "http://127.0.0.1:9001" in rendered
    mock_run.assert_called_once()


def test_bootstrap_endpoint_returns_workspace_metadata() -> None:
    app = create_app(_settings())

    with TestClient(app) as client:
        response = client.get("/api/bootstrap")

    assert response.status_code == 200
    payload = response.json()
    assert payload["provider"] == "openai"
    assert payload["model"] == "gpt-5.4"
    assert "workspace_root" in payload
    assert payload["board_stages"] == ["backlog", "plan", "processing", "review"]


def test_sessions_endpoint_rejects_invalid_limit() -> None:
    app = create_app(_settings())

    with TestClient(app) as client:
        response = client.get("/api/sessions", params={"limit": 0})

    assert response.status_code == 422


def test_task_creation_is_visible_on_app_event_stream() -> None:
    app = create_app(_settings())

    with TestClient(app) as client:
        create_response = client.post(
            "/api/tasks",
            json={"title": "Task A", "prompt": "Investigate the PBIP model"},
        )
        assert create_response.status_code == 200

        with client.websocket_connect("/api/events/app") as websocket:
            event = websocket.receive_json()

    assert event["type"] == "task_updated"
    assert event["payload"]["task"]["title"] == "Task A"


def test_task_creation_rejects_blank_title() -> None:
    app = create_app(_settings())

    with TestClient(app) as client:
        response = client.post(
            "/api/tasks",
            json={"title": "   ", "prompt": "Investigate the PBIP model"},
        )

    assert response.status_code == 422


def test_chat_session_stream_replays_state_events() -> None:
    with patch("pbi_agent.web.session_manager.run_chat_loop", return_value=0):
        app = create_app(_settings())

        with TestClient(app) as client:
            response = client.post("/api/chat/session", json={})
            assert response.status_code == 200
            live_session_id = response.json()["session"]["live_session_id"]

            with client.websocket_connect(
                f"/api/events/{live_session_id}"
            ) as websocket:
                events = [websocket.receive_json(), websocket.receive_json()]

    assert all(event["type"] == "session_state" for event in events)
    assert {event["payload"]["state"] for event in events}.issuperset({"starting"})
    assert {event["payload"]["state"] for event in events} & {"running", "ended"}


def test_event_stream_treats_cancelled_error_as_clean_disconnect() -> None:
    app = create_app(_settings())
    route = next(
        route
        for route in app.routes
        if getattr(route, "path", None) == "/api/events/{stream_id}"
    )
    endpoint = route.endpoint

    class FakeWebSocket:
        def __init__(self) -> None:
            self.accepted = False
            self.app = app
            self.closed_code = None
            self.sent: list[dict[str, object]] = []

        async def accept(self) -> None:
            self.accepted = True

        async def close(self, code: int) -> None:
            self.closed_code = code

        async def send_json(self, payload: dict[str, object]) -> None:
            self.sent.append(payload)

    fake_websocket = FakeWebSocket()
    manager = app.state.manager
    stream = manager.get_event_stream("app")

    class CancellingQueue:
        async def get(self) -> dict[str, object]:
            raise asyncio.CancelledError()

    subscriber_id = "subscriber-1"
    with patch.object(
        stream, "subscribe", return_value=(subscriber_id, CancellingQueue())
    ):
        with patch.object(stream, "unsubscribe") as mock_unsubscribe:
            asyncio.run(endpoint(fake_websocket, "app"))

    assert fake_websocket.accepted is True
    assert fake_websocket.closed_code is None
    mock_unsubscribe.assert_called_once_with(subscriber_id)


def test_lifespan_suppresses_cancelled_error_and_runs_shutdown() -> None:
    app = create_app(_settings())
    manager = app.state.manager

    async def run_lifespan() -> None:
        async with app.router.lifespan_context(app):
            raise asyncio.CancelledError()

    with patch.object(manager, "shutdown") as mock_shutdown:
        asyncio.run(run_lifespan())

    mock_shutdown.assert_called_once_with()
