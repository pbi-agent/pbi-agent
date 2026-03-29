from __future__ import annotations

import asyncio
from io import StringIO
from unittest.mock import patch

from fastapi.testclient import TestClient
from rich.console import Console

from pbi_agent.branding import PBI_AGENT_NAME, PBI_AGENT_TAGLINE
from pbi_agent.config import Settings
from pbi_agent.session_store import SESSION_DB_PATH_ENV, SessionStore
from pbi_agent.ui.display_protocol import QueuedInput
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
    assert payload["supports_image_inputs"] is True
    assert "workspace_root" in payload
    assert payload["board_stages"] == ["backlog", "plan", "processing", "review"]


def test_file_search_endpoint_returns_workspace_matches(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / "docs").mkdir()
    (tmp_path / "main.py").write_text("print('hi')\n", encoding="utf-8")
    (tmp_path / "docs" / "maintainer.md").write_text("owner\n", encoding="utf-8")
    (tmp_path / "node_modules").mkdir()
    (tmp_path / "node_modules" / "main.js").write_text("ignored\n", encoding="utf-8")

    app = create_app(_settings())

    with TestClient(app) as client:
        response = client.get("/api/files/search", params={"q": "ma", "limit": 10})

    assert response.status_code == 200
    assert response.json()["items"] == [
        {"path": "main.py", "kind": "file"},
        {"path": "docs/maintainer.md", "kind": "file"},
    ]


def test_slash_command_search_endpoint_returns_web_commands() -> None:
    app = create_app(_settings())

    with TestClient(app) as client:
        response = client.get(
            "/api/slash-commands/search", params={"q": "", "limit": 10}
        )

    assert response.status_code == 200
    assert response.json()["items"] == [
        {
            "name": "/skills",
            "description": "Show discovered project skills",
        },
        {
            "name": "/mcp",
            "description": "Show discovered project MCP servers",
        },
        {
            "name": "/agents",
            "description": "Show discovered project sub-agents",
        },
    ]


def test_expand_input_endpoint_expands_mentions_and_extracts_images(
    tmp_path, monkeypatch
) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / "notes.md").write_text("hello notes\n", encoding="utf-8")
    (tmp_path / "mockup.png").write_bytes(b"png")

    app = create_app(_settings())

    with TestClient(app) as client:
        response = client.post(
            "/api/chat/expand-input",
            json={"text": "Review @notes.md and @mockup.png carefully"},
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["text"] == "Review notes.md and mockup.png carefully"
    assert payload["file_paths"] == ["notes.md", "mockup.png"]
    assert payload["image_paths"] == ["mockup.png"]
    assert payload["warnings"] == []


def test_expand_input_endpoint_warns_when_image_mentions_are_unsupported(
    tmp_path, monkeypatch
) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / "mockup.png").write_bytes(b"png")
    app = create_app(Settings(api_key="test-key", provider="xai", model="grok-4"))

    with TestClient(app) as client:
        response = client.post(
            "/api/chat/expand-input",
            json={"text": "Review @mockup.png carefully"},
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["text"] == "Review mockup.png carefully"
    assert payload["file_paths"] == ["mockup.png"]
    assert payload["image_paths"] == []
    assert payload["warnings"] == [
        "Image mentions are not supported by the current provider."
    ]


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


def test_chat_session_stream_replays_session_identity_event() -> None:
    def fake_run_chat_loop(_settings, display, *, resume_session_id=None):
        del _settings, resume_session_id
        display.bind_session("saved-session-1")
        return 0

    with patch("pbi_agent.web.session_manager.run_chat_loop", fake_run_chat_loop):
        app = create_app(_settings())

        with TestClient(app) as client:
            response = client.post("/api/chat/session", json={})
            assert response.status_code == 200
            live_session_id = response.json()["session"]["live_session_id"]

            with client.websocket_connect(
                f"/api/events/{live_session_id}"
            ) as websocket:
                events = [websocket.receive_json() for _ in range(4)]

    identity_events = [event for event in events if event["type"] == "session_identity"]
    assert identity_events
    assert identity_events[0]["payload"]["resume_session_id"] == "saved-session-1"


def test_upload_endpoint_returns_uploaded_image_metadata() -> None:
    def fake_run_chat_loop(_settings, display, *, resume_session_id=None):
        del _settings, resume_session_id
        display.user_prompt()
        return 0

    with patch("pbi_agent.web.session_manager.run_chat_loop", fake_run_chat_loop):
        app = create_app(_settings())

        with TestClient(app) as client:
            response = client.post("/api/chat/session", json={})
            assert response.status_code == 200
            live_session_id = response.json()["session"]["live_session_id"]

            upload_response = client.post(
                f"/api/chat/session/{live_session_id}/images",
                files={"files": ("chart.png", b"\x89PNG\r\n\x1a\n", "image/png")},
            )

    assert upload_response.status_code == 200
    payload = upload_response.json()
    assert len(payload["uploads"]) == 1
    assert payload["uploads"][0]["name"] == "chart.png"
    assert payload["uploads"][0]["mime_type"] == "image/png"
    assert payload["uploads"][0]["preview_url"].startswith("/api/chat/uploads/")


def test_submit_chat_input_accepts_uploaded_image_ids() -> None:
    def fake_run_chat_loop(_settings, display, *, resume_session_id=None):
        del _settings, resume_session_id
        queued = display.user_prompt()
        assert isinstance(queued, QueuedInput)
        assert queued.text == ""
        assert len(queued.images) == 1
        assert queued.images[0].path == "chart.png"
        assert len(queued.image_attachments) == 1
        return 0

    with patch("pbi_agent.web.session_manager.run_chat_loop", fake_run_chat_loop):
        app = create_app(_settings())

        with TestClient(app) as client:
            response = client.post("/api/chat/session", json={})
            assert response.status_code == 200
            live_session_id = response.json()["session"]["live_session_id"]

            upload_response = client.post(
                f"/api/chat/session/{live_session_id}/images",
                files={"files": ("chart.png", b"\x89PNG\r\n\x1a\n", "image/png")},
            )
            assert upload_response.status_code == 200
            upload_id = upload_response.json()["uploads"][0]["upload_id"]

            submit_response = client.post(
                f"/api/chat/session/{live_session_id}/input",
                json={
                    "text": "",
                    "file_paths": [],
                    "image_paths": [],
                    "image_upload_ids": [upload_id],
                },
            )
            assert submit_response.status_code == 200

            events = app.state.manager.get_event_stream(live_session_id).snapshot()

    message_events = [event for event in events if event["type"] == "message_added"]
    assert message_events
    assert (
        message_events[0]["payload"]["image_attachments"][0]["upload_id"] == upload_id
    )


def test_submit_chat_input_does_not_duplicate_workspace_image_mentions(
    tmp_path, monkeypatch
) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / "chart.png").write_bytes(b"\x89PNG\r\n\x1a\n")

    def fake_run_chat_loop(_settings, display, *, resume_session_id=None):
        del _settings, resume_session_id
        queued = display.user_prompt()
        assert isinstance(queued, QueuedInput)
        assert queued.text == "Describe chart.png"
        assert queued.image_paths == []
        assert len(queued.images) == 1
        assert queued.images[0].path == "chart.png"
        assert len(queued.image_attachments) == 1
        return 0

    with patch("pbi_agent.web.session_manager.run_chat_loop", fake_run_chat_loop):
        app = create_app(_settings())

        with TestClient(app) as client:
            response = client.post("/api/chat/session", json={})
            assert response.status_code == 200
            live_session_id = response.json()["session"]["live_session_id"]

            submit_response = client.post(
                f"/api/chat/session/{live_session_id}/input",
                json={
                    "text": "Describe chart.png",
                    "file_paths": ["chart.png"],
                    "image_paths": ["chart.png"],
                    "image_upload_ids": [],
                },
            )
            assert submit_response.status_code == 200


def test_delete_session_endpoint_removes_session_and_clears_task_links(
    tmp_path, monkeypatch
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv(SESSION_DB_PATH_ENV, str(tmp_path / "sessions.db"))
    app = create_app(_settings())

    with SessionStore(db_path=tmp_path / "sessions.db") as store:
        session_id = store.create_session(
            str(tmp_path),
            "openai",
            "gpt-5.4",
            "Saved chat",
        )

    with TestClient(app) as client:
        task_response = client.post(
            "/api/tasks",
            json={
                "title": "Task with chat",
                "prompt": "Investigate",
                "session_id": session_id,
            },
        )
        assert task_response.status_code == 200

        delete_response = client.delete(f"/api/sessions/{session_id}")
        assert delete_response.status_code == 204

        sessions_response = client.get("/api/sessions")
        tasks_response = client.get("/api/tasks")

    assert sessions_response.json()["sessions"] == []
    assert tasks_response.json()["tasks"][0]["session_id"] is None


def test_delete_session_endpoint_rejects_provider_mismatch(
    tmp_path, monkeypatch
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv(SESSION_DB_PATH_ENV, str(tmp_path / "sessions.db"))
    app = create_app(_settings())

    with SessionStore(db_path=tmp_path / "sessions.db") as store:
        session_id = store.create_session(
            str(tmp_path),
            "xai",
            "grok-4",
            "Other provider chat",
        )

    with TestClient(app) as client:
        response = client.delete(f"/api/sessions/{session_id}")

    assert response.status_code == 404


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
