from __future__ import annotations

import asyncio
import base64
import json
import logging
import re
import sqlite3
from io import BytesIO, StringIO
from pathlib import Path
import threading
import time
from types import SimpleNamespace
from unittest.mock import patch
import urllib.error
import urllib.request

from fastapi.testclient import TestClient
import pytest
from rich.console import Console

from pbi_agent.auth.browser_callback import (
    BrowserAuthCallbackOutcome,
    BrowserAuthCallbackParams,
)
from pbi_agent.auth.models import (
    AuthFlowPollResult,
    BrowserAuthChallenge,
    DeviceAuthChallenge,
)
from pbi_agent.auth.store import build_auth_session, save_auth_session
from pbi_agent import __version__
from pbi_agent.agent.session import SessionTurnInterrupted
from pbi_agent.branding import PBI_AGENT_TAGLINE
from pbi_agent.cli import build_parser
from pbi_agent.providers.chatgpt_codex_backend import CHATGPT_ORIGINATOR
from pbi_agent.config import (
    ModelProfileConfig,
    ProviderConfig,
    Settings,
    create_model_profile_config,
    create_provider_config,
    delete_model_profile_config,
)
from pbi_agent.display.protocol import PendingUserQuestion
from pbi_agent.session_store import (
    MessageImageAttachment,
    MessageRecord,
    SESSION_DB_PATH_ENV,
    SessionStore,
    WebManagerLeaseBusyError,
)
from pbi_agent.web.display import WebDisplay
from pbi_agent.web.api.routes.events import _iter_sse_events, _resolve_since
from pbi_agent.web.server_runtime import (
    _ExpectedStartupFailureFilter,
    _startup_error_message_from_traceback,
)
from pbi_agent.web.session_manager import (
    WebManagerStartupError,
    WebSessionManager,
)
from pbi_agent.web.session.state import _MAX_SUBSCRIBER_QUEUE_SIZE
from pbi_agent.web.serve import PBIWebServer, create_app


def _settings() -> Settings:
    return Settings(api_key="test-key", provider="openai", model="gpt-5.4")


def _runtime_args(*argv: str):
    return build_parser().parse_args(list(argv))


def _write_command(root: Path, name: str, content: str) -> None:
    commands_dir = root / ".agents" / "commands"
    commands_dir.mkdir(parents=True, exist_ok=True)
    (commands_dir / f"{name}.md").write_text(content, encoding="utf-8")


def _write_default_commands(root: Path) -> None:
    _write_command(
        root, "implement", "# Implementation command\n\nImplement the change."
    )
    _write_command(root, "plan", "# Planning command\n\nPlan before coding.")
    _write_command(root, "review", "# Code review command\n\nReview the change.")


def _put_two_stage_board(client: TestClient) -> None:
    response = client.put(
        "/api/board/stages",
        json={
            "board_stages": [
                {"id": "backlog", "name": "Backlog"},
                {"id": "plan", "name": "Plan"},
            ]
        },
    )
    assert response.status_code == 200


def _start_task_session(
    client: TestClient, *, prompt: str = "Investigate"
) -> tuple[str, str]:
    create_response = client.post(
        "/api/tasks",
        json={"title": "Task A", "prompt": prompt, "stage": "plan"},
    )
    assert create_response.status_code == 200
    task_id = create_response.json()["task"]["task_id"]

    run_response = client.post(f"/api/tasks/{task_id}/run")
    assert run_response.status_code == 200
    session_id = run_response.json()["task"]["session_id"]
    assert isinstance(session_id, str)
    assert session_id
    return task_id, session_id


def _wait_for_first_task_status(client: TestClient, status: str) -> dict:
    deadline = time.monotonic() + 2
    while True:
        task = client.get("/api/tasks").json()["tasks"][0]
        if task["run_status"] == status:
            return task
        if time.monotonic() > deadline:
            raise AssertionError(f"task run did not reach {status!r} in time")
        time.sleep(0.01)


def _wait_for_session_detail_detached(client: TestClient, session_id: str) -> dict:
    deadline = time.monotonic() + 2
    while True:
        detail = client.get(f"/api/sessions/{session_id}").json()
        if (
            detail["live_session"] is None
            and detail["active_live_session"] is None
            and detail["active_run"] is None
        ):
            return detail
        if time.monotonic() > deadline:
            raise AssertionError("session detail did not detach in time")
        time.sleep(0.01)


def _jwt(payload: dict[str, object]) -> str:
    def encode(part: dict[str, object]) -> str:
        raw = json.dumps(part, separators=(",", ":")).encode("utf-8")
        return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")

    return f"{encode({'alg': 'none', 'typ': 'JWT'})}.{encode(payload)}."


class _FakeBrowserAuthCallbackListener:
    def __init__(self, callback_handler) -> None:
        self.callback_handler = callback_handler
        self.callback_url = "http://localhost:1455/auth/callback"
        self.started = False
        self.stopped = False

    def start(self) -> None:
        self.started = True

    def shutdown(self) -> None:
        self.stopped = True

    def complete(
        self,
        *,
        code: str | None = None,
        state: str | None = None,
        error: str | None = None,
        error_description: str | None = None,
    ) -> BrowserAuthCallbackOutcome:
        return self.callback_handler(
            BrowserAuthCallbackParams(
                code=code,
                state=state,
                error=error,
                error_description=error_description,
            )
        )


class _FakeTimer:
    def __init__(self, interval, function, args=None, kwargs=None) -> None:
        self.interval = interval
        self.function = function
        self.args = args or ()
        self.kwargs = kwargs or {}
        self.started = False
        self.cancelled = False

    def start(self) -> None:
        self.started = True

    def cancel(self) -> None:
        self.cancelled = True

    def fire(self) -> None:
        self.function(*self.args, **self.kwargs)


class _FakeHTTPResponse:
    def __init__(
        self, payload: dict[str, object], headers: dict[str, str] | None = None
    ):
        self._payload = payload
        self.headers = headers or {}

    def read(self) -> bytes:
        return json.dumps(self._payload).encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        del exc_type, exc, tb


def test_web_server_prints_banner_and_starts_uvicorn() -> None:
    server = PBIWebServer(settings=_settings(), port=9001)
    output = StringIO()
    server.console = Console(file=output, width=80, highlight=False)

    with patch("pbi_agent.web.server_runtime.uvicorn.Server.run") as mock_run:
        server.serve(debug=False)

    rendered = output.getvalue()
    assert "PPPPPP  BBBBBB  IIIII" in rendered
    assert PBI_AGENT_TAGLINE in rendered
    assert f"v{__version__}" in rendered
    assert "http://127.0.0.1:9001" in rendered
    mock_run.assert_called_once()


def test_built_static_app_serving_smoke() -> None:
    built_index_path = (
        Path(__file__).parents[1]
        / "src"
        / "pbi_agent"
        / "web"
        / "static"
        / "app"
        / "index.html"
    )
    built_index_html = built_index_path.read_text(encoding="utf-8")
    asset_paths = re.findall(
        r"""(?:src|href)=["'](?P<path>/assets/[^"']+)["']""", built_index_html
    )
    assert asset_paths

    client = TestClient(create_app(_settings()))

    root_response = client.get("/")
    assert root_response.status_code == 200
    assert root_response.text == built_index_html
    assert "pbi-agent web assets are missing" not in root_response.text

    asset_response = client.get(asset_paths[0])
    assert asset_response.status_code == 200
    assert asset_response.content

    spa_response = client.get("/sessions/example-session")
    assert spa_response.status_code == 200
    assert spa_response.text == built_index_html

    api_response = client.get("/api/not-a-real-route")
    assert api_response.status_code == 404


def test_web_server_prints_warning_for_expected_startup_failure() -> None:
    server = PBIWebServer(settings=_settings(), port=9001)
    output = StringIO()
    server.console = Console(file=output, width=80, highlight=False)

    def fake_run(_uvicorn_server, sockets=None) -> None:
        del sockets
        _uvicorn_server._record_startup_failure(
            "Another web app instance is already managing this workspace."
        )

    with patch("pbi_agent.web.server_runtime.uvicorn.Server.run", fake_run):
        server.serve(debug=False)

    rendered = output.getvalue()
    assert (
        "Warning: Another web app instance is already managing this workspace."
        in rendered
    )


def test_expected_startup_failure_filter_hides_traceback_and_exit_log() -> None:
    messages: list[str] = []
    log_filter = _ExpectedStartupFailureFilter(messages.append)
    exc = WebManagerStartupError("friendly")
    traceback_record = logging.LogRecord(
        "uvicorn.error",
        logging.ERROR,
        __file__,
        1,
        "Exception in 'lifespan' protocol\n",
        (),
        (type(exc), exc, exc.__traceback__),
    )
    text_traceback_record = logging.LogRecord(
        "uvicorn.error",
        logging.ERROR,
        __file__,
        1,
        "ERROR:    Traceback (most recent call last):\n"
        '  File "src/pbi_agent/web/session_manager.py", line 534, in start\n'
        "    raise WebManagerAlreadyRunningError(\n"
        "pbi_agent.web.session_manager.WebManagerAlreadyRunningError: "
        "Another web app instance is already managing this workspace.",
        (),
        None,
    )
    exit_record = logging.LogRecord(
        "uvicorn.error",
        logging.ERROR,
        __file__,
        1,
        "Application startup failed. Exiting.",
        (),
        None,
    )
    unexpected_record = logging.LogRecord(
        "uvicorn.error",
        logging.ERROR,
        __file__,
        1,
        "Different startup error",
        (),
        None,
    )

    assert not log_filter.filter(traceback_record)
    assert messages == ["friendly"]
    assert not log_filter.filter(text_traceback_record)
    assert messages == [
        "friendly",
        "Another web app instance is already managing this workspace.",
    ]
    assert not log_filter.filter(exit_record)
    assert log_filter.filter(unexpected_record)


def test_startup_error_message_from_traceback_extracts_base_error() -> None:
    message = (
        "Traceback (most recent call last):\n"
        "pbi_agent.web.session_manager.WebManagerStartupError: "
        "Session database is busy. Try starting the web app again."
    )

    assert _startup_error_message_from_traceback(message) == (
        "Session database is busy. Try starting the web app again."
    )


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
    assert [stage["id"] for stage in payload["board_stages"]] == ["backlog", "done"]
    assert payload["board_stages"][0]["command_id"] is None
    assert payload["board_stages"][1]["command_id"] is None


def test_config_bootstrap_and_crud_endpoints_round_trip(
    monkeypatch, tmp_path: Path
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("OPENAI_API_KEY", "env-openai-key")
    _write_default_commands(tmp_path)
    runtime_args = _runtime_args("web")
    app = create_app(_settings(), runtime_args=runtime_args)

    with TestClient(app) as client:
        bootstrap_response = client.get("/api/config/bootstrap")
        assert bootstrap_response.status_code == 200
        bootstrap_payload = bootstrap_response.json()
        assert bootstrap_payload["providers"] == []
        assert bootstrap_payload["model_profiles"] == []
        assert [item["id"] for item in bootstrap_payload["commands"]] == [
            "implement",
            "plan",
            "review",
        ]
        assert bootstrap_payload["commands"][1]["path"] == ".agents/commands/plan.md"
        assert "config_revision" in bootstrap_payload
        revision = bootstrap_payload["config_revision"]

        create_provider_response = client.post(
            "/api/config/providers",
            headers={"If-Match": revision},
            json={
                "name": "OpenAI Main",
                "kind": "openai",
                "api_key_env": "OPENAI_API_KEY",
            },
        )
        assert create_provider_response.status_code == 200
        provider_payload = create_provider_response.json()
        assert provider_payload["provider"]["id"] == "openai-main"
        assert provider_payload["provider"]["auth_mode"] == "api_key"
        assert provider_payload["provider"]["secret_source"] == "env_var"
        assert provider_payload["provider"]["has_secret"] is True
        assert (
            provider_payload["provider"]["auth_status"]["session_status"] == "missing"
        )
        revision = provider_payload["config_revision"]

        create_profile_response = client.post(
            "/api/config/model-profiles",
            headers={"If-Match": revision},
            json={
                "name": "Analysis",
                "provider_id": "openai-main",
                "model": "gpt-5.4-2026-03-05",
                "reasoning_effort": "xhigh",
            },
        )
        assert create_profile_response.status_code == 200
        profile_payload = create_profile_response.json()
        assert profile_payload["model_profile"]["id"] == "analysis"
        assert (
            profile_payload["model_profile"]["resolved_runtime"]["profile_id"]
            == "analysis"
        )
        assert (
            profile_payload["model_profile"]["resolved_runtime"]["model"]
            == "gpt-5.4-2026-03-05"
        )
        assert (
            profile_payload["model_profile"]["resolved_runtime"]["sub_agent_model"]
            == "gpt-5.4-2026-03-05"
        )
        revision = profile_payload["config_revision"]

        select_response = client.put(
            "/api/config/active-model-profile",
            headers={"If-Match": revision},
            json={"profile_id": "analysis"},
        )
        assert select_response.status_code == 200
        revision = select_response.json()["config_revision"]

        refreshed = client.get("/api/config/bootstrap")
        assert refreshed.status_code == 200
        refreshed_payload = refreshed.json()
        assert refreshed_payload["active_profile_id"] == "analysis"
        assert {item["id"] for item in refreshed_payload["providers"]} == {
            "openai-main"
        }
        assert refreshed_payload["providers"][0]["auth_mode"] == "api_key"
        assert (
            refreshed_payload["providers"][0]["auth_status"]["auth_mode"] == "api_key"
        )
        assert (
            refreshed_payload["options"]["provider_metadata"]["openai"]["label"]
            == "OpenAI API"
        )
        assert (
            refreshed_payload["options"]["provider_metadata"]["openai"]["description"]
            == "Uses an OpenAI API key."
        )
        assert refreshed_payload["options"]["provider_metadata"]["openai"][
            "auth_modes"
        ] == ["api_key"]
        assert refreshed_payload["options"]["provider_metadata"]["openai"][
            "auth_mode_metadata"
        ] == {
            "api_key": {
                "label": "API key",
                "account_label": None,
                "supported_methods": [],
            },
        }
        assert refreshed_payload["options"]["provider_metadata"]["chatgpt"] == {
            "label": "ChatGPT (Subscription)",
            "description": "Uses your ChatGPT subscription account.",
            "default_auth_mode": "chatgpt_account",
            "auth_modes": ["chatgpt_account"],
            "auth_mode_metadata": {
                "chatgpt_account": {
                    "label": "ChatGPT account",
                    "account_label": "ChatGPT subscription account",
                    "supported_methods": ["browser", "device"],
                }
            },
            "default_model": "gpt-5.4",
            "default_sub_agent_model": "gpt-5.4-mini",
            "default_responses_url": "https://chatgpt.com/backend-api/codex/responses",
            "default_generic_api_url": None,
            "supports_responses_url": True,
            "supports_generic_api_url": False,
            "supports_service_tier": False,
            "supports_native_web_search": True,
            "supports_image_inputs": True,
        }
        analysis_profile = next(
            item
            for item in refreshed_payload["model_profiles"]
            if item["id"] == "analysis"
        )
        assert {item["id"] for item in refreshed_payload["commands"]} == {
            "implement",
            "plan",
            "review",
        }
        assert analysis_profile["is_active_default"] is True
        assert refreshed_payload["config_revision"] == revision


def test_config_writes_require_current_revision() -> None:
    app = create_app(_settings())

    with TestClient(app) as client:
        stale_revision = client.get("/api/config/bootstrap").json()["config_revision"]
        create_response = client.post(
            "/api/config/providers",
            headers={"If-Match": stale_revision},
            json={"name": "OpenAI Main", "kind": "openai", "api_key": "test-key"},
        )
        assert create_response.status_code == 200

        stale_update = client.post(
            "/api/config/providers",
            headers={"If-Match": stale_revision},
            json={"name": "xAI Main", "kind": "xai", "api_key": "x-key"},
        )
        assert stale_update.status_code == 409


def test_command_list_endpoint_returns_command_files(
    monkeypatch, tmp_path: Path
) -> None:
    monkeypatch.chdir(tmp_path)
    _write_command(
        tmp_path,
        "focus",
        "# Focus command\n\nStay focused on the requested change.",
    )
    app = create_app(_settings())

    with TestClient(app) as client:
        revision = client.get("/api/config/bootstrap").json()["config_revision"]

        list_response = client.get("/api/config/commands")
        assert list_response.status_code == 200
        assert list_response.json()["config_revision"] == revision
        assert list_response.json()["commands"] == [
            {
                "id": "focus",
                "name": "Focus",
                "slash_alias": "/focus",
                "description": "Focus command",
                "instructions": "# Focus command\n\nStay focused on the requested change.",
                "path": ".agents/commands/focus.md",
            }
        ]

        create_response = client.post(
            "/api/config/commands",
            headers={"If-Match": revision},
            json={
                "name": "Focus",
                "slash_alias": "/focus",
                "instructions": "Stay focused.",
            },
        )
        assert create_response.status_code == 405


def test_provider_update_rejects_dual_secret_mutation() -> None:
    app = create_app(_settings())

    with TestClient(app) as client:
        revision = client.get("/api/config/bootstrap").json()["config_revision"]
        create_response = client.post(
            "/api/config/providers",
            headers={"If-Match": revision},
            json={"name": "OpenAI Main", "kind": "openai", "api_key": "test-key"},
        )
        assert create_response.status_code == 200
        revision = create_response.json()["config_revision"]

        update_response = client.patch(
            "/api/config/providers/openai-main",
            headers={"If-Match": revision},
            json={"api_key": "next-key", "api_key_env": "OPENAI_API_KEY"},
        )
        assert update_response.status_code == 400


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


def test_slash_command_search_endpoint_returns_web_commands(
    monkeypatch, tmp_path: Path
) -> None:
    monkeypatch.chdir(tmp_path)
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
            "kind": "local_command",
        },
        {
            "name": "/mcp",
            "description": "Show discovered project MCP servers",
            "kind": "local_command",
        },
        {
            "name": "/agents",
            "description": "Show discovered project sub-agents",
            "kind": "local_command",
        },
        {
            "name": "/reload",
            "description": "Reload workspace instructions and file caches",
            "kind": "local_command",
        },
        {
            "name": "/compact",
            "description": "Summarize the live session to reduce model context",
            "kind": "local_command",
        },
    ]


def test_slash_command_search_endpoint_includes_command_file_commands(
    monkeypatch, tmp_path: Path
) -> None:
    monkeypatch.chdir(tmp_path)
    _write_default_commands(tmp_path)
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
            "kind": "local_command",
        },
        {
            "name": "/mcp",
            "description": "Show discovered project MCP servers",
            "kind": "local_command",
        },
        {
            "name": "/agents",
            "description": "Show discovered project sub-agents",
            "kind": "local_command",
        },
        {
            "name": "/reload",
            "description": "Reload workspace instructions and file caches",
            "kind": "local_command",
        },
        {
            "name": "/compact",
            "description": "Summarize the live session to reduce model context",
            "kind": "local_command",
        },
        {
            "name": "/implement",
            "description": "Implementation command",
            "kind": "command",
        },
        {
            "name": "/plan",
            "description": "Planning command",
            "kind": "command",
        },
        {
            "name": "/review",
            "description": "Code review command",
            "kind": "command",
        },
    ]


def test_slash_command_search_endpoint_filters_command_file_commands(
    monkeypatch, tmp_path: Path
) -> None:
    monkeypatch.chdir(tmp_path)
    _write_command(tmp_path, "plan", "# Planning command\n\nPlan before coding.")
    app = create_app(_settings())

    with TestClient(app) as client:
        response = client.get(
            "/api/slash-commands/search", params={"q": "pla", "limit": 10}
        )

    assert response.status_code == 200
    assert response.json()["items"] == [
        {
            "name": "/plan",
            "description": "Planning command",
            "kind": "command",
        }
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
            "/api/sessions/expand-input",
            json={"text": "Review @notes.md and @mockup.png carefully"},
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["text"] == "Review notes.md and mockup.png carefully"
    assert payload["file_paths"] == ["notes.md", "mockup.png"]
    assert payload["image_paths"] == ["mockup.png"]
    assert payload["warnings"] == []


def test_expand_input_endpoint_handles_path_mention_followed_by_long_prompt(
    tmp_path,
    monkeypatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    commands_dir = tmp_path / ".agents" / "commands"
    commands_dir.mkdir(parents=True)
    (commands_dir / "ship-task.md").write_text("ship it\n", encoding="utf-8")
    app = create_app(_settings())

    with TestClient(app) as client:
        response = client.post(
            "/api/sessions/expand-input",
            json={
                "text": "Update @.agents/commands/ship-task.md "
                "we need to add instruction to wait for github workflow before merging PR"
            },
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["text"] == (
        "Update .agents/commands/ship-task.md "
        "we need to add instruction to wait for github workflow before merging PR"
    )
    assert payload["file_paths"] == [".agents/commands/ship-task.md"]
    assert payload["image_paths"] == []
    assert payload["warnings"] == []


def test_expand_input_endpoint_warns_for_overlong_path_mention(
    tmp_path,
    monkeypatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    app = create_app(_settings())
    overlong_name = "a" * 300 + ".md"

    with TestClient(app) as client:
        response = client.post(
            "/api/sessions/expand-input",
            json={"text": f"Review @{overlong_name}"},
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["text"] == f"Review @{overlong_name}"
    assert payload["file_paths"] == []
    assert payload["image_paths"] == []
    assert payload["warnings"] == ["Referenced file path is too long and was ignored."]


def test_expand_input_endpoint_keeps_image_mentions_for_any_provider(
    tmp_path, monkeypatch
) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / "mockup.png").write_bytes(b"png")
    app = create_app(Settings(api_key="test-key", provider="xai", model="grok-4"))

    with TestClient(app) as client:
        response = client.post(
            "/api/sessions/expand-input",
            json={"text": "Review @mockup.png carefully"},
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["text"] == "Review mockup.png carefully"
    assert payload["file_paths"] == ["mockup.png"]
    assert payload["image_paths"] == ["mockup.png"]
    assert payload["warnings"] == []


def test_sessions_endpoint_rejects_invalid_limit() -> None:
    app = create_app(_settings())

    with TestClient(app) as client:
        response = client.get("/api/sessions", params={"limit": 0})

    assert response.status_code == 422


def test_update_session_title_endpoint_updates_workspace_session(
    tmp_path, monkeypatch
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv(SESSION_DB_PATH_ENV, str(tmp_path / "sessions.db"))
    with SessionStore(db_path=tmp_path / "sessions.db") as store:
        session_id = store.create_session(
            str(tmp_path),
            "openai",
            "gpt-5.4",
            "Original title",
        )
    app = create_app(_settings())

    with TestClient(app) as client:
        response = client.patch(
            f"/api/sessions/{session_id}",
            json={"title": "  Updated title  "},
        )
        event = app.state.manager.get_event_stream("app").snapshot()[-1]

    assert response.status_code == 200
    payload = response.json()
    assert payload["session"]["title"] == "Updated title"
    assert event["type"] == "session_updated"
    assert event["payload"]["session"]["session_id"] == session_id
    assert event["payload"]["session"]["title"] == "Updated title"
    with SessionStore(db_path=tmp_path / "sessions.db") as store:
        stored = store.get_session(session_id)
    assert stored is not None
    assert stored.title == "Updated title"


def test_update_session_title_endpoint_rejects_blank_title(
    tmp_path, monkeypatch
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv(SESSION_DB_PATH_ENV, str(tmp_path / "sessions.db"))
    with SessionStore(db_path=tmp_path / "sessions.db") as store:
        session_id = store.create_session(
            str(tmp_path),
            "openai",
            "gpt-5.4",
            "Original title",
        )
    app = create_app(_settings())

    with TestClient(app) as client:
        response = client.patch(
            f"/api/sessions/{session_id}",
            json={"title": "   "},
        )

    assert response.status_code == 422


def test_update_session_title_endpoint_returns_not_found_for_other_workspace(
    tmp_path, monkeypatch
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv(SESSION_DB_PATH_ENV, str(tmp_path / "sessions.db"))
    with SessionStore(db_path=tmp_path / "sessions.db") as store:
        session_id = store.create_session(
            str(tmp_path / "other"),
            "openai",
            "gpt-5.4",
            "Other title",
        )
    app = create_app(_settings())

    with TestClient(app) as client:
        response = client.patch(
            f"/api/sessions/{session_id}",
            json={"title": "Updated title"},
        )

    assert response.status_code == 404


def test_task_creation_is_visible_on_app_event_stream() -> None:
    app = create_app(_settings())

    with TestClient(app) as client:
        create_response = client.post(
            "/api/tasks",
            json={"title": "Task A", "prompt": "Investigate the workspace layout"},
        )
        assert create_response.status_code == 200
        event = app.state.manager.get_event_stream("app").snapshot()[-1]

    assert event["type"] == "task_updated"
    assert event["payload"]["task"]["title"] == "Task A"


def test_event_stream_since_skips_snapshot_events_at_or_before_cursor() -> None:
    app = create_app(_settings())
    manager = app.state.manager
    stream = manager.get_event_stream("app")
    first = stream.publish("first", {})
    second = stream.publish("second", {})

    async def collect() -> dict[str, object]:
        iterator = _iter_sse_events(stream, since=int(first["seq"]))
        try:
            await anext(iterator)
            return _decode_sse_payload(await anext(iterator))
        finally:
            await iterator.aclose()

    event = asyncio.run(collect())

    assert event["seq"] == second["seq"]
    assert event["type"] == "second"


def _decode_sse_payload(raw: str) -> dict[str, object]:
    data_lines = [
        line.removeprefix("data: ")
        for line in raw.splitlines()
        if line.startswith("data: ")
    ]
    return json.loads("\n".join(data_lines))


def test_sse_event_stream_sends_connected_and_filters_by_cursor() -> None:
    app = create_app(_settings())
    manager = app.state.manager
    stream = manager.get_event_stream("app")
    first = stream.publish("first", {})
    second = stream.publish("second", {})

    async def collect() -> list[str]:
        iterator = _iter_sse_events(stream, since=int(first["seq"]))
        try:
            return [await anext(iterator), await anext(iterator)]
        finally:
            await iterator.aclose()

    connected_raw, event_raw = asyncio.run(collect())

    assert _decode_sse_payload(connected_raw)["type"] == "server.connected"
    event = _decode_sse_payload(event_raw)
    assert event["seq"] == second["seq"]
    assert event["type"] == "second"
    assert f"id: {second['seq']}" in event_raw


def test_event_stream_subscriber_queue_overflow_enqueues_recovery_control() -> None:
    app = create_app(_settings())
    stream = app.state.manager.get_event_stream("app")

    async def fill_slow_subscriber() -> tuple[
        list[dict[str, object]], list[BaseException]
    ]:
        loop = asyncio.get_running_loop()
        loop_errors: list[BaseException] = []

        def capture_loop_error(_loop, context) -> None:  # noqa: ANN001
            exception = context.get("exception")
            if isinstance(exception, BaseException):
                loop_errors.append(exception)

        previous_handler = loop.get_exception_handler()
        loop.set_exception_handler(capture_loop_error)
        subscriber_id, queue = stream.subscribe()
        try:
            assert queue.maxsize == _MAX_SUBSCRIBER_QUEUE_SIZE
            for index in range(_MAX_SUBSCRIBER_QUEUE_SIZE + 5):
                stream.publish("item", {"index": index})
            await asyncio.sleep(0)
            queued = [queue.get_nowait() for _ in range(queue.qsize())]
        finally:
            stream.unsubscribe(subscriber_id)
            loop.set_exception_handler(previous_handler)
        return queued, loop_errors

    queued_events, loop_errors = asyncio.run(fill_slow_subscriber())

    assert loop_errors == []
    assert 0 < len(queued_events) <= _MAX_SUBSCRIBER_QUEUE_SIZE
    assert queued_events[0]["type"] == "server.replay_incomplete"
    assert queued_events[0]["seq"] == _MAX_SUBSCRIBER_QUEUE_SIZE + 1
    assert queued_events[0]["payload"] == {
        "reason": "subscriber_queue_overflow",
        "latest_seq": _MAX_SUBSCRIBER_QUEUE_SIZE + 1,
    }
    assert [int(event["seq"]) for event in queued_events[1:]] == list(
        range(_MAX_SUBSCRIBER_QUEUE_SIZE + 2, _MAX_SUBSCRIBER_QUEUE_SIZE + 6)
    )
    assert [int(event["seq"]) for event in stream.snapshot()] == list(
        range(6, _MAX_SUBSCRIBER_QUEUE_SIZE + 6)
    )


def test_event_stream_publish_ignores_closed_subscriber_loop() -> None:
    app = create_app(_settings())
    stream = app.state.manager.get_event_stream("app")
    loop = asyncio.new_event_loop()

    async def subscribe() -> str:
        subscriber_id, _queue = stream.subscribe()
        return subscriber_id

    subscriber_id = loop.run_until_complete(subscribe())
    loop.close()

    stream.publish("item", {})

    assert stream.subscriber_count() == 0
    stream.unsubscribe(subscriber_id)


def test_sse_event_stream_disconnects_on_subscriber_queue_overflow(monkeypatch) -> None:
    app = create_app(_settings())
    stream = app.state.manager.get_event_stream("app")

    async def collect() -> tuple[str, dict[str, object], str, dict[str, object]]:
        queue: asyncio.Queue = asyncio.Queue(maxsize=_MAX_SUBSCRIBER_QUEUE_SIZE)
        queue.put_nowait(
            {
                "seq": 8,
                "type": "item",
                "payload": {},
                "created_at": "2026-05-05T00:00:00Z",
            }
        )
        queue.put_nowait(
            {
                "seq": 12,
                "type": "server.replay_incomplete",
                "payload": {
                    "reason": "subscriber_queue_overflow",
                    "latest_seq": 12,
                },
                "created_at": "2026-05-05T00:00:01Z",
            }
        )
        queue.put_nowait(
            {
                "seq": 13,
                "type": "item",
                "payload": {},
                "created_at": "2026-05-05T00:00:02Z",
            }
        )
        monkeypatch.setattr(stream, "subscribe", lambda: ("slow", queue))
        monkeypatch.setattr(stream, "unsubscribe", lambda _subscriber_id: None)
        monkeypatch.setattr(stream, "snapshot", lambda: [])
        monkeypatch.setattr(stream, "bounds", lambda: (8, 12))
        iterator = _iter_sse_events(stream, since=0, requested_since=0)
        try:
            connected = _decode_sse_payload(await anext(iterator))
            assert connected["type"] == "server.connected"
            item_raw = await anext(iterator)
            item = _decode_sse_payload(item_raw)
            control_raw = await anext(iterator)
            control = _decode_sse_payload(control_raw)
            with pytest.raises(StopAsyncIteration):
                await anext(iterator)
            return item_raw, item, control_raw, control
        finally:
            await iterator.aclose()

    item_raw, item, control_raw, event = asyncio.run(collect())

    assert item["type"] == "item"
    assert item["seq"] == 8
    assert "id: 8" in item_raw
    assert event["type"] == "server.replay_incomplete"
    assert event["seq"] == 12
    assert event["payload"] == {
        "reason": "subscriber_queue_overflow",
        "requested_since": 8,
        "resolved_since": 8,
        "oldest_available_seq": 9,
        "latest_seq": 12,
        "snapshot_required": True,
    }
    assert "id: 12" in control_raw
    assert _resolve_since(0, "12") == 12


def test_sse_event_stream_logs_subscription_replay_range_and_unsubscribe(
    caplog,
) -> None:
    caplog.set_level(logging.INFO, logger="pbi_agent.web.api.routes.events")
    app = create_app(_settings())
    stream = app.state.manager.get_event_stream("app")
    stream.publish("snapshot", {"index": 2})
    replay_events = [
        {
            "seq": 2,
            "type": "replay",
            "payload": {"index": 1},
            "created_at": "2026-05-04T00:00:00Z",
        }
    ]

    async def collect() -> list[str]:
        iterator = _iter_sse_events(
            stream,
            since=1,
            requested_since=1,
            replay_events=replay_events,
            log_context={"endpoint": "stream", "stream_kind": "app"},
        )
        try:
            return [await anext(iterator), await anext(iterator)]
        finally:
            await iterator.aclose()

    frames = asyncio.run(collect())
    records = [
        record.pbi_sse for record in caplog.records if hasattr(record, "pbi_sse")
    ]

    assert _decode_sse_payload(frames[1])["seq"] == 2
    assert [record["action"] for record in records] == ["subscribe", "unsubscribe"]
    subscribe = records[0]
    assert subscribe["replay_count"] == 1
    assert subscribe["replay_from_seq"] == 2
    assert subscribe["replay_to_seq"] == 2
    assert subscribe["snapshot_count"] == 1
    assert subscribe["latest_seq"] == 1
    assert subscribe["requested_since"] == 1
    assert subscribe["resolved_since"] == 1
    assert isinstance(subscribe["subscriber_id"], str)
    unsubscribe = records[1]
    assert unsubscribe["subscriber_id"] == subscribe["subscriber_id"]
    assert unsubscribe["last_sent_seq"] == 2
    assert unsubscribe["subscriber_count"] == 0


def test_sse_event_stream_uses_last_event_id_as_resume_cursor() -> None:
    assert _resolve_since(1, "5") == 5
    assert _resolve_since(5, "1") == 1
    assert _resolve_since(5, "not-a-number") == 5
    assert _resolve_since(5, "-1") == 5


def test_live_sse_last_event_id_takes_precedence_over_since_for_gap_detection(
    monkeypatch,
) -> None:
    app = create_app(_settings())
    stream = app.state.manager.get_event_stream("app")
    for index in range(1005):
        stream.publish("item", {"index": index})

    captured: dict[str, object] = {}

    def fake_sse_response(  # noqa: ANN001
        stream,
        *,
        since,
        requested_since=None,
        replay_events=None,
        log_context=None,
    ):
        captured["since"] = since
        captured["requested_since"] = requested_since
        captured["oldest_seq"] = stream.snapshot()[0]["seq"]
        captured["log_context"] = log_context
        from fastapi.responses import JSONResponse

        return JSONResponse({"ok": True})

    from pbi_agent.web.api.routes import events as events_route

    monkeypatch.setattr(events_route, "_sse_response", fake_sse_response)

    with TestClient(app) as client:
        response = client.get(
            "/api/events/app",
            params={"since": 1005},
            headers={"Last-Event-ID": "1"},
        )

    assert response.status_code == 200
    assert captured["since"] == 1
    assert captured["requested_since"] == 1
    assert captured["oldest_seq"] == 6


def test_sse_event_stream_reports_cursor_too_old_when_memory_history_has_gap() -> None:
    app = create_app(_settings())
    manager = app.state.manager
    stream = manager.get_event_stream("app")

    for index in range(1005):
        stream.publish("item", {"index": index})

    async def collect() -> dict[str, object]:
        iterator = _iter_sse_events(stream, since=1, requested_since=1)
        try:
            await anext(iterator)
            return _decode_sse_payload(await anext(iterator))
        finally:
            await iterator.aclose()

    event = asyncio.run(collect())

    assert event["type"] == "server.replay_incomplete"
    assert event["payload"]["reason"] == "cursor_too_old"
    assert event["payload"]["requested_since"] == 1
    assert event["payload"]["resolved_since"] == 1
    assert event["payload"]["oldest_available_seq"] == 6
    assert event["payload"]["latest_seq"] == 1005
    assert event["payload"]["snapshot_required"] is True


def test_sse_event_stream_logs_replay_incomplete_once(caplog) -> None:
    caplog.set_level(logging.INFO, logger="pbi_agent.web.api.routes.events")
    app = create_app(_settings())
    stream = app.state.manager.get_event_stream("app")

    for index in range(1005):
        stream.publish("item", {"index": index})

    async def collect() -> dict[str, object]:
        iterator = _iter_sse_events(
            stream,
            since=1,
            requested_since=1,
            log_context={"endpoint": "stream", "stream_kind": "app"},
        )
        try:
            await anext(iterator)
            return _decode_sse_payload(await anext(iterator))
        finally:
            await iterator.aclose()

    event = asyncio.run(collect())
    records = [
        record.pbi_sse for record in caplog.records if hasattr(record, "pbi_sse")
    ]
    incomplete_records = [
        record for record in records if record["action"] == "replay_incomplete"
    ]

    assert event["type"] == "server.replay_incomplete"
    assert len(incomplete_records) == 1
    incomplete = incomplete_records[0]
    assert incomplete["reason"] == "cursor_too_old"
    assert incomplete["snapshot_required"] is True
    assert incomplete["requested_since"] == 1
    assert incomplete["resolved_since"] == 1
    assert incomplete["oldest_available_seq"] == 6
    assert incomplete["latest_seq"] == 1005
    assert {record["action"] for record in records} == {
        "subscribe",
        "replay_incomplete",
        "unsubscribe",
    }


def test_saved_session_sse_replays_persisted_events_beyond_memory_retention_without_gap(
    tmp_path,
    monkeypatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv(SESSION_DB_PATH_ENV, str(tmp_path / "sessions.db"))
    run_id = "long-stream-run"

    with SessionStore(db_path=tmp_path / "sessions.db") as store:
        session_id = store.create_session(
            str(tmp_path),
            "openai",
            "gpt-5.4",
            "Long stream replay",
        )
        store.create_run_session(
            run_session_id=run_id,
            session_id=session_id,
            agent_name="main",
            agent_type="web_session",
            provider="openai",
            provider_id="default",
            profile_id="analysis",
            model="gpt-5.4",
            status="ended",
            kind="session",
            last_event_seq=1005,
            metadata={
                "source": "web",
                "directory": str(tmp_path).lower(),
                "workspace_root": str(tmp_path),
                "live_session_id": run_id,
            },
        )
        for seq in range(1, 1006):
            store.add_observability_event(
                run_session_id=run_id,
                session_id=session_id,
                step_index=-seq,
                event_type="web_event",
                metadata={
                    "type": "message_added",
                    "payload": {
                        "live_session_id": run_id,
                        "session_id": session_id,
                        "item_id": f"item-{seq}",
                        "role": "assistant",
                        "content": f"message {seq}",
                    },
                    "seq": seq,
                    "created_at": f"2026-05-04T00:00:{seq % 60:02d}Z",
                },
            )

    app = create_app(_settings())
    with TestClient(app):
        stream = app.state.manager.get_session_event_stream(session_id)
        replay_events = app.state.manager.get_session_event_stream_replay(
            session_id,
            since=1,
        )
        snapshot_events = stream.snapshot()

        async def collect() -> list[str]:
            iterator = _iter_sse_events(
                stream,
                since=1,
                requested_since=1,
                replay_events=replay_events,
            )
            try:
                frames: list[str] = []
                for _ in range(1 + len(replay_events)):
                    frames.append(await anext(iterator))
                return frames
            finally:
                await iterator.aclose()

        raw_frames = asyncio.run(collect())

    decoded = [_decode_sse_payload(frame) for frame in raw_frames]
    replayed = decoded[1:]

    assert snapshot_events[0]["seq"] == 6
    assert decoded[0]["type"] == "server.connected"
    assert all(event["type"] != "server.replay_incomplete" for event in replayed)
    assert [event["seq"] for event in replayed] == list(range(2, 1006))
    assert [event["payload"]["item_id"] for event in replayed] == [
        f"item-{seq}" for seq in range(2, 1006)
    ]
    assert "id: 2" in raw_frames[1]
    assert "id: 1005" in raw_frames[-1]


def test_sse_event_stream_reports_impossible_cursor_ahead_of_latest() -> None:
    app = create_app(_settings())
    manager = app.state.manager
    stream = manager.get_event_stream("app")
    stream.publish("item", {})

    async def collect() -> dict[str, object]:
        iterator = _iter_sse_events(stream, since=99, requested_since=99)
        try:
            await anext(iterator)
            return _decode_sse_payload(await anext(iterator))
        finally:
            await iterator.aclose()

    event = asyncio.run(collect())

    assert event["type"] == "server.replay_incomplete"
    assert event["payload"]["reason"] == "cursor_ahead"
    assert event["payload"]["requested_since"] == 99
    assert event["payload"]["resolved_since"] == 99
    assert event["payload"]["latest_seq"] == 1
    assert event["payload"]["snapshot_required"] is True


def test_saved_session_sse_reports_cursor_ahead_when_since_resets_for_new_run(
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
            "Cursor ahead",
        )
        run_id = store.create_run_session(
            session_id=session_id,
            agent_name="main",
            agent_type="web_session",
            provider="openai",
            provider_id="default",
            profile_id="analysis",
            model="gpt-5.4",
            status="ended",
            kind="session",
            last_event_seq=1,
        )
        store.add_observability_event(
            run_session_id=run_id,
            session_id=session_id,
            step_index=-1,
            event_type="web_event",
            metadata={
                "type": "message_added",
                "payload": {"item_id": "new-low", "role": "assistant"},
                "seq": 1,
            },
        )

    with TestClient(app):
        requested_since = 99
        resolved_since = app.state.manager.resolve_session_event_since(
            session_id,
            requested_since,
        )
        stream = app.state.manager.get_session_event_stream(session_id)
        replay_events = app.state.manager.get_session_event_stream_replay(
            session_id,
            since=resolved_since,
        )

        async def collect() -> dict[str, object]:
            iterator = _iter_sse_events(
                stream,
                since=resolved_since,
                requested_since=requested_since,
                replay_events=replay_events,
            )
            try:
                await anext(iterator)
                return _decode_sse_payload(await anext(iterator))
            finally:
                await iterator.aclose()

        event = asyncio.run(collect())

    assert resolved_since == 0
    assert event["type"] == "server.replay_incomplete"
    assert event["payload"]["reason"] == "cursor_ahead"
    assert event["payload"]["requested_since"] == 99
    assert event["payload"]["resolved_since"] == 0
    assert event["payload"]["latest_seq"] == 1
    assert event["payload"]["snapshot_required"] is True


def test_live_events_include_canonical_identity_in_stream_and_persistence(
    tmp_path, monkeypatch
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv(SESSION_DB_PATH_ENV, str(tmp_path / "sessions.db"))
    with SessionStore(db_path=tmp_path / "sessions.db") as store:
        session_id = store.create_session(
            str(tmp_path),
            "openai",
            "gpt-5.4",
            "Identity events",
        )
    app = create_app(_settings())

    with TestClient(app):
        created = app.state.manager.create_live_session(session_id=session_id)
        live_session_id = created["live_session_id"]
        event = app.state.manager._publish_live_event(
            live_session_id,
            "wait_state",
            {"active": True, "message": "Working..."},
        )
        stream_event = next(
            snapshot_event
            for snapshot_event in app.state.manager.get_event_stream(
                live_session_id
            ).snapshot()
            if snapshot_event["seq"] == event["seq"]
        )

    assert event["payload"]["live_session_id"] == live_session_id
    assert event["payload"]["session_id"] == session_id
    assert event["payload"]["resume_session_id"] == session_id
    assert stream_event["payload"] == event["payload"]

    with SessionStore(db_path=tmp_path / "sessions.db") as store:
        records = store.list_observability_events(run_session_id=live_session_id)
    persisted = json.loads(records[0].metadata_json)
    for record in records:
        metadata = json.loads(record.metadata_json)
        if metadata.get("type") == "wait_state":
            persisted = metadata
            break

    assert persisted["type"] == "wait_state"
    assert persisted["seq"] == event["seq"]
    assert persisted["created_at"] == event["created_at"]
    assert persisted["live_session_id"] == live_session_id
    assert persisted["session_id"] == session_id
    assert persisted["payload"]["live_session_id"] == live_session_id
    assert persisted["payload"]["session_id"] == session_id
    assert persisted["payload"]["resume_session_id"] == session_id

    with SessionStore(db_path=tmp_path / "sessions.db") as store:
        run = store.get_run_session(live_session_id)
    assert run is not None
    run_metadata = json.loads(run.metadata_json)
    assert run_metadata["source"] == "web"
    assert run_metadata["directory"] == str(tmp_path).lower()
    assert run_metadata["workspace_root"] == str(tmp_path)
    assert run_metadata["live_session_id"] == live_session_id


def test_live_session_creation_rechecks_saved_session_under_registration_lock(
    tmp_path, monkeypatch
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv(SESSION_DB_PATH_ENV, str(tmp_path / "sessions.db"))
    with SessionStore(db_path=tmp_path / "sessions.db") as store:
        session_id = store.create_session(
            str(tmp_path),
            "openai",
            "gpt-5.4",
            "Delete race",
        )
    app = create_app(_settings())

    class DeleteBeforeAcquire:
        def __init__(self) -> None:
            self._lock = threading.Lock()
            self._deleted = False

        def __enter__(self):
            if not self._deleted:
                self._deleted = True
                with SessionStore(db_path=tmp_path / "sessions.db") as store:
                    assert store.delete_session(session_id)
            return self._lock.__enter__()

        def __exit__(self, exc_type, exc_value, traceback):
            return self._lock.__exit__(exc_type, exc_value, traceback)

    with TestClient(app):
        manager = app.state.manager
        manager._lock = DeleteBeforeAcquire()

        with pytest.raises(KeyError):
            manager.create_live_session(session_id=session_id)

        assert manager._live_sessions == {}


def test_live_event_persistence_failure_does_not_deliver_to_subscribers(
    tmp_path, monkeypatch
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv(SESSION_DB_PATH_ENV, str(tmp_path / "sessions.db"))
    app = create_app(_settings())

    class IdleThread:
        def __init__(self, *args, **kwargs) -> None:
            del args, kwargs

        def start(self) -> None:
            return None

        def join(self, timeout: float | None = None) -> None:
            del timeout

        def is_alive(self) -> bool:
            return False

    with TestClient(app):
        with patch("pbi_agent.web.session.live_sessions.threading.Thread", IdleThread):
            created = app.state.manager.create_live_session()
        manager = app.state.manager
        live_session_id = created["live_session_id"]
        live_session = manager._live_sessions[live_session_id]
        original_persist = manager._persist_live_event_record

        def fail_failed_event(live_session, event):  # noqa: ANN001
            if event["payload"].get("message") == "Failed":
                raise RuntimeError("persist failed")
            original_persist(live_session, event)

        monkeypatch.setattr(manager, "_persist_live_event_record", fail_failed_event)

        async def collect() -> dict[str, object]:
            subscriber_id, queue = live_session.event_stream.subscribe()
            try:
                await asyncio.sleep(0)
                while not queue.empty():
                    queue.get_nowait()
                _oldest_seq, latest_seq_before_failure = (
                    live_session.event_stream.bounds()
                )

                with pytest.raises(RuntimeError, match="persist failed"):
                    manager._publish_live_event(
                        live_session_id,
                        "wait_state",
                        {"active": True, "message": "Failed"},
                    )
                await asyncio.sleep(0)
                assert queue.empty()
                assert all(
                    event["payload"].get("message") != "Failed"
                    for event in live_session.event_stream.snapshot()
                )
                assert (
                    live_session.event_stream.bounds()[1] == latest_seq_before_failure
                )

                delivered = manager._publish_live_event(
                    live_session_id,
                    "wait_state",
                    {"active": True, "message": "Delivered"},
                )
                queued = await asyncio.wait_for(queue.get(), timeout=1)
                assert delivered is not None
                assert delivered["seq"] == latest_seq_before_failure + 1
                assert queued == delivered
                return queued
            finally:
                live_session.event_stream.unsubscribe(subscriber_id)

        event = asyncio.run(collect())

    assert event["type"] == "wait_state"
    assert event["payload"]["message"] == "Delivered"


def test_live_event_run_update_failure_rolls_back_persisted_event(
    tmp_path, monkeypatch
) -> None:
    monkeypatch.chdir(tmp_path)
    db_path = tmp_path / "sessions.db"
    monkeypatch.setenv(SESSION_DB_PATH_ENV, str(db_path))
    app = create_app(_settings())

    class IdleThread:
        def __init__(self, *args, **kwargs) -> None:
            del args, kwargs

        def start(self) -> None:
            return None

        def join(self, timeout: float | None = None) -> None:
            del timeout

        def is_alive(self) -> bool:
            return False

    with TestClient(app):
        with patch("pbi_agent.web.session.live_sessions.threading.Thread", IdleThread):
            created = app.state.manager.create_live_session()
        manager = app.state.manager
        live_session_id = created["live_session_id"]
        live_session = manager._live_sessions[live_session_id]
        _oldest_seq, latest_seq_before_failure = live_session.event_stream.bounds()

        escaped_live_session_id = live_session_id.replace("'", "''")
        with sqlite3.connect(db_path) as conn:
            conn.execute(
                "CREATE TRIGGER block_web_run_update "
                "BEFORE UPDATE ON run_sessions "
                f"WHEN OLD.run_session_id = '{escaped_live_session_id}' "
                "BEGIN SELECT RAISE(ABORT, 'run update blocked'); END"
            )

        with pytest.raises(sqlite3.IntegrityError, match="run update blocked"):
            manager._publish_live_event(
                live_session_id,
                "wait_state",
                {"active": True, "message": "Failed"},
            )

        assert live_session.event_stream.bounds()[1] == latest_seq_before_failure
        assert all(
            event["payload"].get("message") != "Failed"
            for event in live_session.event_stream.snapshot()
        )
        with SessionStore(db_path=db_path) as store:
            run = store.get_run_session(live_session_id)
            records = store.list_observability_events(run_session_id=live_session_id)
        assert run is not None
        assert run.last_event_seq == latest_seq_before_failure
        assert all(
            json.loads(record.metadata_json).get("payload", {}).get("message")
            != "Failed"
            for record in records
        )

        with sqlite3.connect(db_path) as conn:
            conn.execute("DROP TRIGGER block_web_run_update")

        delivered = manager._publish_live_event(
            live_session_id,
            "wait_state",
            {"active": True, "message": "Delivered"},
        )
        assert delivered is not None
        assert delivered["seq"] == latest_seq_before_failure + 1

        replay = manager.get_event_stream_replay(
            live_session_id,
            since=latest_seq_before_failure,
        )

    assert [event["payload"].get("message") for event in replay] == ["Delivered"]
    with SessionStore(db_path=db_path) as store:
        run = store.get_run_session(live_session_id)
        records = store.list_observability_events(run_session_id=live_session_id)
    assert run is not None
    assert run.last_event_seq == delivered["seq"]
    assert [
        json.loads(record.metadata_json).get("payload", {}).get("message")
        for record in records
        if json.loads(record.metadata_json).get("type") == "wait_state"
    ] == ["Delivered"]


def test_concurrent_live_events_preserve_snapshot_items_and_persist_latest_snapshot(
    tmp_path, monkeypatch
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv(SESSION_DB_PATH_ENV, str(tmp_path / "sessions.db"))

    class IdleThread:
        def __init__(self, *args, **kwargs) -> None:
            del args, kwargs

        def start(self) -> None:
            return None

        def join(self, timeout: float | None = None) -> None:
            del timeout

        def is_alive(self) -> bool:
            return False

    manager = WebSessionManager(_settings())
    manager.start()
    try:
        with patch("pbi_agent.web.session.live_sessions.threading.Thread", IdleThread):
            created = manager.create_live_session()
        live_session_id = str(created["live_session_id"])

        original_upsert = manager._upsert_snapshot_item
        release_first_upsert = threading.Event()
        first_upsert_entered = threading.Event()
        upsert_guard = threading.Lock()
        upsert_count = 0

        def racing_upsert(
            items: list[dict[str, object]],
            next_item: dict[str, object],
        ) -> list[dict[str, object]]:
            nonlocal upsert_count
            if str(next_item.get("itemId") or "").startswith("concurrent-"):
                with upsert_guard:
                    upsert_count += 1
                    current_upsert = upsert_count
                if current_upsert == 1:
                    first_upsert_entered.set()
                    release_first_upsert.wait(timeout=0.05)
                elif current_upsert == 2:
                    assert first_upsert_entered.is_set()
                    release_first_upsert.set()
            return original_upsert(items, next_item)

        monkeypatch.setattr(manager, "_upsert_snapshot_item", racing_upsert)

        start = threading.Barrier(3)
        events: list[dict[str, object]] = []
        errors: list[BaseException] = []
        events_guard = threading.Lock()

        def publish_message(index: int) -> None:
            try:
                start.wait(timeout=1)
                event = manager._publish_live_event(
                    live_session_id,
                    "message_added",
                    {
                        "item_id": f"concurrent-{index}",
                        "role": "assistant",
                        "content": f"Concurrent {index}",
                        "markdown": False,
                    },
                )
                assert event is not None
                with events_guard:
                    events.append(event)
            except BaseException as exc:  # pragma: no cover - surfaced below
                with events_guard:
                    errors.append(exc)

        threads = [
            threading.Thread(target=publish_message, args=(index,))
            for index in range(2)
        ]
        for thread in threads:
            thread.start()
        start.wait(timeout=1)
        for thread in threads:
            thread.join(timeout=1)

        assert errors == []
        assert len(events) == 2

        live_session = manager._live_sessions[live_session_id]
        memory_item_ids = {
            str(item.get("itemId") or "") for item in live_session.snapshot.items
        }
        expected_item_ids = {"concurrent-0", "concurrent-1"}

        with SessionStore(db_path=tmp_path / "sessions.db") as store:
            run = store.get_run_session(live_session_id)
        assert run is not None
        persisted_snapshot = json.loads(run.snapshot_json)
        persisted_item_ids = {
            str(item.get("itemId") or "") for item in persisted_snapshot["items"]
        }
        latest_seq = max(int(event["seq"]) for event in events)

        assert expected_item_ids <= memory_item_ids
        assert expected_item_ids <= persisted_item_ids
        assert live_session.snapshot.last_event_seq == latest_seq
        assert run.last_event_seq == latest_seq
        assert persisted_snapshot["last_event_seq"] == latest_seq
    finally:
        manager.shutdown()


def test_live_session_bind_none_clears_persisted_run_session_id(
    tmp_path, monkeypatch
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv(SESSION_DB_PATH_ENV, str(tmp_path / "sessions.db"))

    class IdleThread:
        def __init__(self, *args, **kwargs) -> None:
            del args, kwargs

        def start(self) -> None:
            return None

        def join(self, timeout: float | None = None) -> None:
            del timeout

        def is_alive(self) -> bool:
            return False

    with SessionStore(db_path=tmp_path / "sessions.db") as store:
        session_id = store.create_session(
            str(tmp_path),
            "openai",
            "gpt-5.4",
            "Saved session",
        )

    manager = WebSessionManager(_settings())
    manager.start()
    try:
        with patch("pbi_agent.web.session.live_sessions.threading.Thread", IdleThread):
            created = manager.create_live_session(session_id=session_id)
        live_session_id = str(created["live_session_id"])

        with SessionStore(db_path=tmp_path / "sessions.db") as store:
            initial_run = store.get_run_session(live_session_id)
        assert initial_run is not None
        assert initial_run.session_id == session_id

        manager._bind_live_session(live_session_id, None)

        with SessionStore(db_path=tmp_path / "sessions.db") as store:
            rebound_run = store.get_run_session(live_session_id)
        assert rebound_run is not None
        assert rebound_run.session_id is None
        assert json.loads(rebound_run.snapshot_json)["session_id"] is None
    finally:
        manager.shutdown()


def test_late_live_events_after_terminal_finalization_do_not_mutate_run(
    tmp_path, monkeypatch
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv(SESSION_DB_PATH_ENV, str(tmp_path / "sessions.db"))

    class IdleThread:
        def __init__(self, *args, **kwargs) -> None:
            del args, kwargs

        def start(self) -> None:
            return None

        def join(self, timeout: float | None = None) -> None:
            del timeout

        def is_alive(self) -> bool:
            return False

    manager = WebSessionManager(_settings())
    manager.start()
    try:
        with patch("pbi_agent.web.session.live_sessions.threading.Thread", IdleThread):
            created = manager.create_live_session()
        live_session_id = str(created["live_session_id"])
        manager._publish_live_event(
            live_session_id,
            "message_added",
            {
                "item_id": "assistant-before-end",
                "role": "assistant",
                "content": "Before end",
                "markdown": False,
            },
        )

        live_session = manager._live_sessions[live_session_id]
        with manager._lock:
            manager._finalize_live_session_locked(live_session)

        terminal_stream_events = manager.get_event_stream(live_session_id).snapshot()
        with SessionStore(db_path=tmp_path / "sessions.db") as store:
            terminal_run = store.get_run_session(live_session_id)
            terminal_records = store.list_observability_events(
                run_session_id=live_session_id
            )
        assert terminal_run is not None
        terminal_snapshot = json.loads(terminal_run.snapshot_json)
        terminal_metadata = [record.metadata_json for record in terminal_records]
        assert terminal_snapshot["session_ended"] is True
        assert terminal_snapshot["items"][0]["content"] == "Before end"
        assert all(record.event_type == "web_event" for record in terminal_records)
        assert any(
            json.loads(record.metadata_json)["type"] == "session_state"
            and json.loads(record.metadata_json)["payload"]["state"] == "ended"
            for record in terminal_records
        )

        late_event = manager._publish_live_event(
            live_session_id,
            "message_added",
            {
                "item_id": "assistant-after-end",
                "role": "assistant",
                "content": "After end",
                "markdown": False,
            },
        )

        with SessionStore(db_path=tmp_path / "sessions.db") as store:
            late_run = store.get_run_session(live_session_id)
            late_records = store.list_observability_events(
                run_session_id=live_session_id
            )

        assert late_event is None
        assert late_run is not None
        assert late_run.snapshot_json == terminal_run.snapshot_json
        assert late_run.last_event_seq == terminal_run.last_event_seq
        assert (
            manager.get_event_stream(live_session_id).snapshot()
            == terminal_stream_events
        )
        assert [record.metadata_json for record in late_records] == terminal_metadata
    finally:
        manager.shutdown()


def test_live_session_finalization_persistence_failure_rolls_back_terminal_fields(
    tmp_path, monkeypatch
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv(SESSION_DB_PATH_ENV, str(tmp_path / "sessions.db"))

    class IdleThread:
        def __init__(self, *args, **kwargs) -> None:
            del args, kwargs

        def start(self) -> None:
            return None

        def join(self, timeout: float | None = None) -> None:
            del timeout

        def is_alive(self) -> bool:
            return False

    manager = WebSessionManager(_settings())
    manager.start()
    try:
        with patch("pbi_agent.web.session.live_sessions.threading.Thread", IdleThread):
            created = manager.create_live_session()
        live_session_id = str(created["live_session_id"])
        live_session = manager._live_sessions[live_session_id]
        original_status = live_session.status
        original_persist = manager._persist_live_event_record
        failed = False

        def fail_terminal_persist(session, event):
            nonlocal failed
            if (
                not failed
                and event["type"] == "session_state"
                and event["payload"].get("state") == "ended"
            ):
                failed = True
                raise RuntimeError("terminal persist failed")
            original_persist(session, event)

        monkeypatch.setattr(
            manager, "_persist_live_event_record", fail_terminal_persist
        )

        with pytest.raises(RuntimeError, match="terminal persist failed"):
            with manager._lock:
                manager._finalize_live_session_locked(live_session)

        assert live_session.status == original_status
        assert live_session.ended_at is None
        assert live_session.exit_code is None
        assert live_session.snapshot.session_ended is False
        assert not any(
            event["type"] == "live_session_ended"
            for event in manager._app_stream.snapshot()
        )
        assert not any(
            event["type"] == "session_state"
            and event["payload"].get("state") == "ended"
            for event in manager.get_event_stream(live_session_id).snapshot()
        )
        with SessionStore(db_path=tmp_path / "sessions.db") as store:
            failed_run = store.get_run_session(live_session_id)
            failed_records = store.list_observability_events(
                run_session_id=live_session_id
            )
        assert failed_run is not None
        assert failed_run.ended_at is None
        assert json.loads(failed_run.snapshot_json)["session_ended"] is False
        assert not any(
            json.loads(record.metadata_json)["type"] == "session_state"
            and json.loads(record.metadata_json)["payload"].get("state") == "ended"
            for record in failed_records
        )

        with manager._lock:
            manager._finalize_live_session_locked(live_session)

        assert live_session.status == "ended"
        assert live_session.ended_at is not None
        assert live_session.exit_code == 0
        with SessionStore(db_path=tmp_path / "sessions.db") as store:
            retried_run = store.get_run_session(live_session_id)
        assert retried_run is not None
        assert retried_run.ended_at == live_session.ended_at
        assert json.loads(retried_run.snapshot_json)["session_ended"] is True
    finally:
        manager.shutdown()


def test_live_event_sse_replays_persisted_events_when_memory_snapshot_is_empty(
    tmp_path, monkeypatch
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv(SESSION_DB_PATH_ENV, str(tmp_path / "sessions.db"))
    app = create_app(_settings())

    with TestClient(app):
        created = app.state.manager.create_live_session()
        live_session_id = created["live_session_id"]
        first = app.state.manager._publish_live_event(
            live_session_id,
            "wait_state",
            {"active": True, "message": "Persisted"},
        )

        event_stream = app.state.manager._live_sessions[live_session_id].event_stream
        with event_stream._lock:
            event_stream._events = []
        stream = app.state.manager.get_event_stream(live_session_id)
        replay_events = app.state.manager.get_event_stream_replay(
            live_session_id,
            since=int(first["seq"]) - 1,
        )

        async def collect() -> dict[str, object]:
            iterator = _iter_sse_events(
                stream,
                since=int(first["seq"]) - 1,
                replay_events=replay_events,
            )
            try:
                await anext(iterator)
                return _decode_sse_payload(await anext(iterator))
            finally:
                await iterator.aclose()

        event = asyncio.run(collect())

    assert event["seq"] == first["seq"]
    assert event["type"] == "wait_state"
    assert event["payload"]["message"] == "Persisted"


def test_event_stream_by_live_session_id_replays_persisted_web_run_after_restart(
    tmp_path, monkeypatch
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv(SESSION_DB_PATH_ENV, str(tmp_path / "sessions.db"))
    run_id = "ended-live-stream"

    with SessionStore(db_path=tmp_path / "sessions.db") as store:
        session_id = store.create_session(
            str(tmp_path),
            "openai",
            "gpt-5.4",
            "Restart replay",
        )
        store.create_run_session(
            run_session_id=run_id,
            session_id=session_id,
            agent_name="main",
            agent_type="web_session",
            provider="openai",
            provider_id=None,
            profile_id=None,
            model="gpt-5.4",
            status="ended",
            kind="session",
            metadata={
                "source": "web",
                "directory": str(tmp_path).lower(),
                "workspace_root": str(tmp_path),
                "live_session_id": run_id,
            },
        )
        store.add_observability_event(
            run_session_id=run_id,
            session_id=session_id,
            step_index=-1,
            event_type="web_event",
            metadata={
                "type": "message_added",
                "payload": {
                    "live_session_id": run_id,
                    "session_id": session_id,
                    "item_id": "assistant-1",
                    "role": "assistant",
                    "content": "Restored",
                },
                "seq": 1,
                "created_at": "2026-05-04T00:00:00+00:00",
                "live_session_id": run_id,
                "session_id": session_id,
            },
        )

    app = create_app(_settings())

    with TestClient(app):
        stream = app.state.manager.get_event_stream(run_id)
        events = stream.snapshot()

    assert [event["seq"] for event in events] == [1]
    assert events[0]["type"] == "message_added"
    assert events[0]["payload"]["content"] == "Restored"


def test_task_creation_preserves_plain_prompt_content() -> None:
    app = create_app(_settings())

    with TestClient(app) as client:
        response = client.post(
            "/api/tasks",
            json={
                "title": "Investigate Workspace",
                "prompt": "Review the repository and list the broken workflows.",
            },
        )

    assert response.status_code == 200
    task = response.json()["task"]
    assert task["title"] == "Investigate Workspace"
    assert task["prompt"] == "Review the repository and list the broken workflows."


def test_task_creation_preserves_existing_structured_prompt() -> None:
    app = create_app(_settings())
    structured_prompt = (
        "# Task\nInvestigate Workspace\n\n## Goal\nReview the repository."
    )

    with TestClient(app) as client:
        response = client.post(
            "/api/tasks",
            json={"title": "Investigate Workspace", "prompt": structured_prompt},
        )

    assert response.status_code == 200
    assert response.json()["task"]["prompt"] == structured_prompt


def test_task_creation_rejects_blank_title() -> None:
    app = create_app(_settings())

    with TestClient(app) as client:
        response = client.post(
            "/api/tasks",
            json={"title": "   ", "prompt": "Investigate the workspace layout"},
        )

    assert response.status_code == 422


def test_task_contract_includes_model_profile_binding_and_null_patch_semantics(
    monkeypatch, tmp_path
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("OPENAI_API_KEY", "saved-openai-key")
    runtime_args = _runtime_args("web")
    create_provider_config(
        ProviderConfig(
            id="openai-main",
            name="OpenAI Main",
            kind="openai",
            api_key_env="OPENAI_API_KEY",
        )
    )
    create_model_profile_config(
        ModelProfileConfig(
            id="analysis",
            name="Analysis",
            provider_id="openai-main",
            model="gpt-5.4-2026-03-05",
            reasoning_effort="xhigh",
        )
    )
    app = create_app(_settings(), runtime_args=runtime_args)

    with SessionStore(db_path=tmp_path / "sessions.db") as store:
        session_id = store.create_session(
            str(tmp_path),
            "openai",
            "gpt-5.4-2026-03-05",
            "Saved session",
        )

    with TestClient(app) as client:
        create_response = client.post(
            "/api/tasks",
            json={
                "title": "Task A",
                "prompt": "Investigate",
                "session_id": session_id,
                "profile_id": "analysis",
            },
        )
        assert create_response.status_code == 200
        payload = create_response.json()["task"]
        assert payload["profile_id"] == "analysis"
        assert payload["runtime_summary"]["profile_id"] == "analysis"
        assert payload["runtime_summary"]["model"] == "gpt-5.4-2026-03-05"
        task_id = payload["task_id"]

        update_response = client.patch(
            f"/api/tasks/{task_id}",
            json={"session_id": None, "profile_id": None},
        )
        assert update_response.status_code == 200
        updated = update_response.json()["task"]
        assert updated["session_id"] is None
        assert updated["profile_id"] is None


def test_board_stage_endpoints_round_trip(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.chdir(tmp_path)
    _write_default_commands(tmp_path)
    app = create_app(_settings())

    with TestClient(app) as client:
        list_response = client.get("/api/board/stages")
        assert list_response.status_code == 200
        assert [item["id"] for item in list_response.json()["board_stages"]] == [
            "backlog",
            "done",
        ]

        update_response = client.put(
            "/api/board/stages",
            json={
                "board_stages": [
                    {
                        "id": "build",
                        "name": "Build",
                        "command_id": "implement",
                        "auto_start": True,
                    },
                    {"id": "done", "name": "Completed", "command_id": "review"},
                    {"id": "backlog", "name": "Inbox", "auto_start": True},
                    {"id": "review", "name": "Review", "command_id": "review"},
                ]
            },
        )
        assert update_response.status_code == 200
        payload = update_response.json()
        assert [item["id"] for item in payload["board_stages"]] == [
            "backlog",
            "build",
            "review",
            "done",
        ]
        assert payload["board_stages"][0]["name"] == "Backlog"
        assert payload["board_stages"][0]["command_id"] is None
        assert payload["board_stages"][0]["auto_start"] is False
        assert payload["board_stages"][1]["auto_start"] is True
        assert payload["board_stages"][1]["command_id"] == "implement"
        assert payload["board_stages"][3]["name"] == "Done"
        assert payload["board_stages"][3]["command_id"] is None
        assert payload["board_stages"][3]["auto_start"] is False


def test_run_task_advances_to_next_configured_stage(monkeypatch, tmp_path) -> None:
    monkeypatch.chdir(tmp_path)
    _write_default_commands(tmp_path)
    app = create_app(_settings())

    with patch(
        "pbi_agent.web.session.workers.run_single_turn_in_directory",
        return_value=SimpleNamespace(
            tool_errors=[],
            text="Planned.",
            session_id="session-123",
        ),
    ):
        with TestClient(app) as client:
            client.put(
                "/api/board/stages",
                json={
                    "board_stages": [
                        {"id": "backlog", "name": "Backlog"},
                        {"id": "plan", "name": "Plan", "command_id": "plan"},
                        {"id": "review", "name": "Review", "command_id": "review"},
                    ]
                },
            )
            create_response = client.post(
                "/api/tasks",
                json={"title": "Task A", "prompt": "Investigate", "stage": "plan"},
            )
            assert create_response.status_code == 200
            task_id = create_response.json()["task"]["task_id"]

            run_response = client.post(f"/api/tasks/{task_id}/run")
            assert run_response.status_code == 200

            deadline = time.monotonic() + 2
            while True:
                task_response = client.get("/api/tasks")
                task_payload = task_response.json()["tasks"][0]
                if (
                    task_payload["stage"] == "review"
                    and task_payload["run_status"] == "completed"
                ):
                    break
                if time.monotonic() > deadline:
                    raise AssertionError("task run did not finish in time")
                time.sleep(0.01)

    assert task_payload["stage"] == "review"
    assert task_payload["run_status"] == "completed"
    assert task_payload["session_id"] == "session-123"


def test_run_task_exposes_live_session_before_completion(monkeypatch, tmp_path) -> None:
    monkeypatch.chdir(tmp_path)
    app = create_app(_settings())
    run_started = threading.Event()
    release_run = threading.Event()

    def fake_run_single_turn(prompt, runtime, display, **kwargs):
        del prompt, runtime
        assert isinstance(kwargs["persisted_user_message_id"], int)
        run_started.set()
        display.render_markdown("Live progress")
        assert release_run.wait(timeout=2)
        with SessionStore() as store:
            store.add_message(kwargs["resume_session_id"], "assistant", "Done.")
        return SimpleNamespace(
            tool_errors=[],
            text="Done.",
            session_id=kwargs["resume_session_id"],
        )

    def fake_run_session_loop(_runtime, display, **kwargs):
        resume_session_id = kwargs["resume_session_id"]
        queued = display.user_prompt()
        assert getattr(queued, "text", None) == "Follow up"
        with SessionStore() as store:
            store.add_message(resume_session_id, "user", queued.text)
            store.add_message(resume_session_id, "assistant", "Continued.")
        display.render_markdown("Continued.")
        return 0

    with (
        patch(
            "pbi_agent.web.session.workers.run_single_turn_in_directory",
            side_effect=fake_run_single_turn,
        ),
        patch(
            "pbi_agent.web.session.workers.run_session_loop",
            side_effect=fake_run_session_loop,
        ),
    ):
        with TestClient(app) as client:
            client.put(
                "/api/board/stages",
                json={
                    "board_stages": [
                        {"id": "backlog", "name": "Backlog"},
                        {"id": "plan", "name": "Plan"},
                    ]
                },
            )
            create_response = client.post(
                "/api/tasks",
                json={"title": "Task A", "prompt": "Investigate", "stage": "plan"},
            )
            assert create_response.status_code == 200
            task_id = create_response.json()["task"]["task_id"]

            run_response = client.post(f"/api/tasks/{task_id}/run")
            assert run_response.status_code == 200
            running_task = run_response.json()["task"]
            session_id = running_task["session_id"]
            assert running_task["run_status"] == "running"
            assert isinstance(session_id, str)
            assert session_id

            detail_response = client.get(f"/api/sessions/{session_id}")
            assert detail_response.status_code == 200
            detail_payload = detail_response.json()
            assert detail_payload["history_items"] == [
                {
                    "item_id": detail_payload["history_items"][0]["item_id"],
                    "message_id": detail_payload["history_items"][0]["message_id"],
                    "part_ids": detail_payload["history_items"][0]["part_ids"],
                    "role": "user",
                    "content": "Investigate",
                    "file_paths": [],
                    "image_attachments": [],
                    "markdown": False,
                    "historical": True,
                    "created_at": detail_payload["history_items"][0]["created_at"],
                }
            ]
            active_live_session = detail_payload["active_live_session"]
            assert active_live_session["kind"] == "task"
            assert active_live_session["task_id"] == task_id
            assert active_live_session["session_id"] == session_id

            live_session_id = active_live_session["live_session_id"]
            assert detail_payload["live_session"] == active_live_session
            assert detail_payload["active_run"] is None
            assert (
                detail_payload["session"]["active_live_session_id"] == live_session_id
            )
            assert detail_payload["session"]["active_run_id"] is None
            manager = app.state.manager
            assert (
                manager._live_sessions[live_session_id].worker
                is manager._task_workers[task_id]
            )
            assert manager._live_sessions[live_session_id].worker is not None
            events = manager.get_event_stream(live_session_id).snapshot()[:2]
            assert [event["type"] for event in events] == [
                "session_runtime_updated",
                "session_state",
            ]
            assert events[1]["payload"]["state"] in {"starting", "running"}

            assert run_started.wait(timeout=2)
            deadline = time.monotonic() + 2
            while True:
                snapshot = app.state.manager.get_event_stream(
                    live_session_id
                ).snapshot()
                if any(event["type"] == "message_added" for event in snapshot):
                    break
                if time.monotonic() > deadline:
                    raise AssertionError("live event was not published")
                time.sleep(0.01)

            release_run.set()
            deadline = time.monotonic() + 2
            while True:
                final_task = client.get("/api/tasks").json()["tasks"][0]
                if final_task["run_status"] == "completed":
                    break
                if time.monotonic() > deadline:
                    raise AssertionError("task run did not finish in time")
                time.sleep(0.01)

            assert final_task["session_id"] == session_id
            assert final_task["last_result_summary"] == "Done."

            completed_detail_response = client.get(f"/api/sessions/{session_id}")
            assert completed_detail_response.status_code == 200
            completed_detail = completed_detail_response.json()
            assert completed_detail["live_session"] is None
            assert completed_detail["active_live_session"] is None
            assert completed_detail["active_run"] is None
            assert completed_detail["session"]["active_live_session_id"] is None
            assert completed_detail["session"]["active_run_id"] is None
            assert completed_detail["timeline"]["live_session_id"] == live_session_id
            assert [item["content"] for item in completed_detail["history_items"]] == [
                "Investigate",
                "Done.",
            ]

            continuation_response = client.post(
                f"/api/sessions/{session_id}/messages",
                json={"text": "Follow up"},
            )
            assert continuation_response.status_code == 200
            continuation_live_session_id = continuation_response.json()["session"][
                "live_session_id"
            ]
            assert continuation_live_session_id != live_session_id

            manager = app.state.manager
            continuation_worker = manager._live_sessions[
                continuation_live_session_id
            ].worker
            assert continuation_worker is not None
            continuation_worker.join(timeout=2)

            continued_detail_response = client.get(f"/api/sessions/{session_id}")
            assert continued_detail_response.status_code == 200
            continued_detail = continued_detail_response.json()
            assert [item["content"] for item in continued_detail["history_items"]] == [
                "Investigate",
                "Done.",
                "Follow up",
                "Continued.",
            ]


def test_completed_task_terminal_persist_failure_does_not_mark_task_failed(
    monkeypatch, tmp_path
) -> None:
    monkeypatch.chdir(tmp_path)
    app = create_app(_settings())
    run_started = threading.Event()
    release_run = threading.Event()

    def fake_run_single_turn(_prompt, _runtime, _display, **kwargs):
        run_started.set()
        assert release_run.wait(timeout=2)
        return SimpleNamespace(
            tool_errors=[],
            text="Done.",
            session_id=kwargs["resume_session_id"],
        )

    with patch(
        "pbi_agent.web.session.workers.run_single_turn_in_directory",
        side_effect=fake_run_single_turn,
    ):
        with TestClient(app) as client:
            _put_two_stage_board(client)
            create_response = client.post(
                "/api/tasks",
                json={"title": "Task A", "prompt": "Investigate", "stage": "plan"},
            )
            assert create_response.status_code == 200
            task_id = create_response.json()["task"]["task_id"]

            run_response = client.post(f"/api/tasks/{task_id}/run")
            assert run_response.status_code == 200
            session_id = run_response.json()["task"]["session_id"]
            assert run_started.wait(timeout=2)

            detail = client.get(f"/api/sessions/{session_id}").json()
            live_session_id = detail["active_live_session"]["live_session_id"]
            manager = app.state.manager
            live_session = manager._live_sessions[live_session_id]
            worker = manager._task_workers[task_id]
            original_persist = manager._persist_live_event_record
            failed = False

            def fail_terminal_persist(session, event):
                nonlocal failed
                if (
                    not failed
                    and event["type"] == "session_state"
                    and event["payload"].get("state") == "ended"
                ):
                    failed = True
                    raise RuntimeError("terminal persist failed")
                original_persist(session, event)

            monkeypatch.setattr(
                manager,
                "_persist_live_event_record",
                fail_terminal_persist,
            )

            release_run.set()
            worker.join(timeout=2)
            assert not worker.is_alive()

            task = client.get("/api/tasks").json()["tasks"][0]
            assert task["run_status"] == "completed"
            assert task["last_result_summary"] == "Done."
            assert live_session.status == "running"
            assert live_session.ended_at is None
            assert live_session.exit_code is None
            assert live_session.snapshot.session_ended is False
            assert not any(
                event["type"] == "session_state"
                and event["payload"].get("state") == "ended"
                for event in manager.get_event_stream(live_session_id).snapshot()
            )
            with SessionStore() as store:
                failed_run = store.get_run_session(live_session_id)
                failed_records = store.list_observability_events(
                    run_session_id=live_session_id
                )
            assert failed_run is not None
            assert failed_run.ended_at is None
            assert json.loads(failed_run.snapshot_json)["session_ended"] is False
            assert not any(
                json.loads(record.metadata_json)["type"] == "session_state"
                and json.loads(record.metadata_json)["payload"].get("state") == "ended"
                for record in failed_records
            )

            with manager._lock:
                manager._finalize_live_session_locked(live_session)

            retried_task = client.get("/api/tasks").json()["tasks"][0]
            assert retried_task["run_status"] == "completed"
            assert live_session.status == "ended"
            assert live_session.ended_at is not None
            assert live_session.exit_code == 0
            with SessionStore() as store:
                retried_run = store.get_run_session(live_session_id)
            assert retried_run is not None
            assert retried_run.ended_at == live_session.ended_at
            assert json.loads(retried_run.snapshot_json)["session_ended"] is True


def test_delete_session_rejects_task_start_setup_before_live_registration(
    monkeypatch, tmp_path
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv(SESSION_DB_PATH_ENV, str(tmp_path / "sessions.db"))
    app = create_app(_settings())
    delete_rejected = False

    def fake_run_single_turn(_prompt, _runtime, _display, **kwargs):
        return SimpleNamespace(
            tool_errors=[],
            text="Done.",
            session_id=kwargs["resume_session_id"],
        )

    with patch(
        "pbi_agent.web.session.workers.run_single_turn_in_directory",
        side_effect=fake_run_single_turn,
    ):
        with TestClient(app) as client:
            _put_two_stage_board(client)
            create_response = client.post(
                "/api/tasks",
                json={"title": "Task A", "prompt": "Investigate", "stage": "plan"},
            )
            assert create_response.status_code == 200
            task_id = create_response.json()["task"]["task_id"]

            manager = app.state.manager
            original_create_task_live_session = manager._create_task_live_session

            def guarded_create_task_live_session(record, runtime):
                nonlocal delete_rejected
                assert record.session_id is not None
                with pytest.raises(RuntimeError, match="active run"):
                    manager.delete_session(record.session_id)
                delete_rejected = True
                return original_create_task_live_session(record, runtime)

            monkeypatch.setattr(
                manager,
                "_create_task_live_session",
                guarded_create_task_live_session,
            )

            run_response = client.post(f"/api/tasks/{task_id}/run")
            assert run_response.status_code == 200
            session_id = run_response.json()["task"]["session_id"]

            assert delete_rejected is True
            with SessionStore(db_path=tmp_path / "sessions.db") as store:
                saved_session = store.get_session(session_id)
                task = store.get_kanban_task(task_id)

    assert saved_session is not None
    assert task is not None
    assert task.session_id == session_id


def test_startup_retry_of_partial_task_start_does_not_duplicate_prompt(
    monkeypatch, tmp_path
) -> None:
    monkeypatch.chdir(tmp_path)
    db_path = tmp_path / "sessions.db"
    monkeypatch.setenv(SESSION_DB_PATH_ENV, str(db_path))

    first_app = create_app(_settings())
    with TestClient(first_app) as client:
        _put_two_stage_board(client)
        create_response = client.post(
            "/api/tasks",
            json={"title": "Task A", "prompt": "Investigate", "stage": "plan"},
        )
        assert create_response.status_code == 200
        task_id = create_response.json()["task"]["task_id"]

    with SessionStore(db_path=db_path) as store:
        session_id = store.create_session(
            directory=str(tmp_path),
            provider="openai",
            model="gpt-5.4",
            title="Task A",
        )
        store.update_kanban_task(task_id, session_id=session_id)
        initial_message_id = store.add_message(session_id, "user", "Investigate")

    def fake_run_single_turn(prompt, _runtime, _display, **kwargs):
        assert prompt == "Investigate"
        assert kwargs["persisted_user_message_id"] == initial_message_id
        with SessionStore() as store:
            store.add_message(kwargs["resume_session_id"], "assistant", "Done.")
        return SimpleNamespace(
            tool_errors=[],
            text="Done.",
            session_id=kwargs["resume_session_id"],
        )

    second_app = create_app(_settings())
    with patch(
        "pbi_agent.web.session.workers.run_single_turn_in_directory",
        side_effect=fake_run_single_turn,
    ):
        with TestClient(second_app) as client:
            run_response = client.post(f"/api/tasks/{task_id}/run")
            assert run_response.status_code == 200
            completed_task = _wait_for_first_task_status(client, "completed")

    assert completed_task["session_id"] == session_id
    with SessionStore(db_path=db_path) as store:
        messages = store.list_messages(session_id)
    assert [message.content for message in messages] == ["Investigate", "Done."]


def test_startup_marks_running_task_without_live_run_failed(
    monkeypatch, tmp_path
) -> None:
    monkeypatch.chdir(tmp_path)
    db_path = tmp_path / "sessions.db"
    monkeypatch.setenv(SESSION_DB_PATH_ENV, str(db_path))

    first_app = create_app(_settings())
    with TestClient(first_app) as client:
        _put_two_stage_board(client)
        create_response = client.post(
            "/api/tasks",
            json={"title": "Task A", "prompt": "Investigate", "stage": "plan"},
        )
        assert create_response.status_code == 200
        task_id = create_response.json()["task"]["task_id"]

    with SessionStore(db_path=db_path) as store:
        running = store.set_kanban_task_running(task_id)
    assert running is not None
    assert running.run_status == "running"

    second_app = create_app(_settings())
    with TestClient(second_app) as client:
        task = client.get("/api/tasks").json()["tasks"][0]

    assert task["task_id"] == task_id
    assert task["run_status"] == "failed"
    assert task["last_result_summary"] == "Interrupted while the app was not running."


def test_running_task_rejects_unsafe_patch_updates(monkeypatch, tmp_path) -> None:
    monkeypatch.chdir(tmp_path)
    app = create_app(_settings())
    run_started = threading.Event()
    release_run = threading.Event()

    def blocking_run_single_turn(_prompt, _runtime, _display, **kwargs):
        run_started.set()
        assert release_run.wait(timeout=2)
        return SimpleNamespace(
            tool_errors=[],
            text="Done.",
            session_id=kwargs["resume_session_id"],
        )

    with patch(
        "pbi_agent.web.session.workers.run_single_turn_in_directory",
        side_effect=blocking_run_single_turn,
    ):
        with TestClient(app) as client:
            client.put(
                "/api/board/stages",
                json={
                    "board_stages": [
                        {"id": "backlog", "name": "Backlog"},
                        {"id": "plan", "name": "Plan"},
                        {"id": "review", "name": "Review"},
                    ]
                },
            )
            upload_response = client.post(
                "/api/tasks/images",
                files={"files": ("chart.png", b"\x89PNG\r\n\x1a\n", "image/png")},
            )
            assert upload_response.status_code == 200
            upload_id = upload_response.json()["uploads"][0]["upload_id"]

            create_response = client.post(
                "/api/tasks",
                json={
                    "title": "Task A",
                    "prompt": "Investigate",
                    "stage": "plan",
                    "project_dir": ".",
                    "image_upload_ids": [upload_id],
                },
            )
            assert create_response.status_code == 200
            created_task = create_response.json()["task"]
            task_id = created_task["task_id"]

            run_response = client.post(f"/api/tasks/{task_id}/run")
            assert run_response.status_code == 200
            running_task = run_response.json()["task"]
            assert run_started.wait(timeout=2)

            update_response = client.patch(
                f"/api/tasks/{task_id}",
                json={
                    "prompt": "Mutated prompt",
                    "stage": "review",
                    "project_dir": "missing-project",
                    "session_id": "mutated-session",
                    "profile_id": "mutated-profile",
                    "image_upload_ids": [],
                },
            )
            listed_task = client.get("/api/tasks").json()["tasks"][0]
            release_run.set()

            deadline = time.monotonic() + 2
            while True:
                final_task = client.get("/api/tasks").json()["tasks"][0]
                if final_task["run_status"] == "completed":
                    break
                if time.monotonic() > deadline:
                    raise AssertionError("task run did not finish in time")
                time.sleep(0.01)

    assert update_response.status_code == 400
    assert update_response.json()["detail"] == "Cannot update a running task."
    assert listed_task["prompt"] == created_task["prompt"]
    assert listed_task["stage"] == created_task["stage"]
    assert listed_task["project_dir"] == created_task["project_dir"]
    assert listed_task["session_id"] == running_task["session_id"]
    assert listed_task["profile_id"] == created_task["profile_id"]
    assert listed_task["image_attachments"] == created_task["image_attachments"]


def test_completed_task_session_can_be_repeatedly_continued(
    monkeypatch, tmp_path
) -> None:
    monkeypatch.chdir(tmp_path)
    app = create_app(_settings())

    def fake_run_single_turn(_prompt, _runtime, _display, **kwargs):
        with SessionStore() as store:
            store.add_message(kwargs["resume_session_id"], "assistant", "Done.")
        return SimpleNamespace(
            tool_errors=[],
            text="Done.",
            session_id=kwargs["resume_session_id"],
        )

    def fake_run_session_loop(_runtime, display, **kwargs):
        resume_session_id = kwargs["resume_session_id"]
        queued = display.user_prompt()
        responses = {
            "Follow up 1": "Continued 1.",
            "Follow up 2": "Continued 2.",
        }
        response = responses[queued.text]
        with SessionStore() as store:
            store.add_message(resume_session_id, "user", queued.text)
            store.add_message(resume_session_id, "assistant", response)
        display.render_markdown(response)
        return 0

    with (
        patch(
            "pbi_agent.web.session.workers.run_single_turn_in_directory",
            side_effect=fake_run_single_turn,
        ),
        patch(
            "pbi_agent.web.session.workers.run_session_loop",
            side_effect=fake_run_session_loop,
        ),
    ):
        with TestClient(app) as client:
            _put_two_stage_board(client)
            _task_id, session_id = _start_task_session(client)
            completed_task = _wait_for_first_task_status(client, "completed")
            assert completed_task["session_id"] == session_id

            first_response = client.post(
                f"/api/sessions/{session_id}/messages",
                json={"text": "Follow up 1"},
            )
            assert first_response.status_code == 200
            first_live_session_id = first_response.json()["session"]["live_session_id"]
            first_worker = app.state.manager._live_sessions[
                first_live_session_id
            ].worker
            assert first_worker is not None
            first_worker.join(timeout=2)

            first_detail = _wait_for_session_detail_detached(client, session_id)
            assert first_detail["active_live_session"] is None
            assert first_detail["active_run"] is None

            second_response = client.post(
                f"/api/sessions/{session_id}/messages",
                json={"text": "Follow up 2"},
            )
            assert second_response.status_code == 200
            second_live_session_id = second_response.json()["session"][
                "live_session_id"
            ]
            assert second_live_session_id != first_live_session_id
            second_worker = app.state.manager._live_sessions[
                second_live_session_id
            ].worker
            assert second_worker is not None
            second_worker.join(timeout=2)

            final_detail = _wait_for_session_detail_detached(client, session_id)
            assert final_detail["active_live_session"] is None
            assert final_detail["active_run"] is None
            assert [item["content"] for item in final_detail["history_items"]] == [
                "Investigate",
                "Done.",
                "Follow up 1",
                "Continued 1.",
                "Follow up 2",
                "Continued 2.",
            ]


def test_failed_task_run_session_can_be_manually_continued(
    monkeypatch, tmp_path
) -> None:
    monkeypatch.chdir(tmp_path)
    app = create_app(_settings())

    def fake_run_single_turn(_prompt, _runtime, _display, **_kwargs):
        raise RuntimeError("boom")

    def fake_run_session_loop(_runtime, display, **kwargs):
        resume_session_id = kwargs["resume_session_id"]
        queued = display.user_prompt()
        assert queued.text == "Recover"
        with SessionStore() as store:
            store.add_message(resume_session_id, "user", queued.text)
            store.add_message(resume_session_id, "assistant", "Recovered.")
        display.render_markdown("Recovered.")
        return 0

    with (
        patch(
            "pbi_agent.web.session.workers.run_single_turn_in_directory",
            side_effect=fake_run_single_turn,
        ),
        patch(
            "pbi_agent.web.session.workers.run_session_loop",
            side_effect=fake_run_session_loop,
        ),
    ):
        with TestClient(app) as client:
            _put_two_stage_board(client)
            _task_id, session_id = _start_task_session(client)
            failed_task = _wait_for_first_task_status(client, "failed")
            assert failed_task["session_id"] == session_id

            failed_detail = _wait_for_session_detail_detached(client, session_id)
            assert failed_detail["live_session"] is None
            assert failed_detail["active_live_session"] is None
            assert failed_detail["active_run"] is None
            assert failed_detail["status"] == "failed"
            assert failed_detail["timeline"]["fatal_error"]

            continuation_response = client.post(
                f"/api/sessions/{session_id}/messages",
                json={"text": "Recover"},
            )
            assert continuation_response.status_code == 200
            continuation_live_session_id = continuation_response.json()["session"][
                "live_session_id"
            ]
            continuation_worker = app.state.manager._live_sessions[
                continuation_live_session_id
            ].worker
            assert continuation_worker is not None
            continuation_worker.join(timeout=2)

            final_detail = client.get(f"/api/sessions/{session_id}").json()
            assert [item["content"] for item in final_detail["history_items"]] == [
                "Investigate",
                "Recover",
                "Recovered.",
            ]


def test_interrupted_task_run_session_can_be_manually_continued(
    monkeypatch, tmp_path
) -> None:
    monkeypatch.chdir(tmp_path)
    app = create_app(_settings())
    turn_started = threading.Event()

    def fake_run_single_turn(_prompt, _runtime, display, **_kwargs):
        display.assistant_start()
        turn_started.set()
        deadline = time.monotonic() + 2
        while not display.interrupt_requested():
            if time.monotonic() > deadline:
                raise AssertionError("task turn was not interrupted in time")
            time.sleep(0.01)
        raise SessionTurnInterrupted()

    def fake_run_session_loop(_runtime, display, **kwargs):
        resume_session_id = kwargs["resume_session_id"]
        queued = display.user_prompt()
        assert queued.text == "Resume"
        with SessionStore() as store:
            store.add_message(resume_session_id, "user", queued.text)
            store.add_message(resume_session_id, "assistant", "Resumed.")
        display.render_markdown("Resumed.")
        return 0

    with (
        patch(
            "pbi_agent.web.session.workers.run_single_turn_in_directory",
            side_effect=fake_run_single_turn,
        ),
        patch(
            "pbi_agent.web.session.workers.run_session_loop",
            side_effect=fake_run_session_loop,
        ),
    ):
        with TestClient(app) as client:
            _put_two_stage_board(client)
            _task_id, session_id = _start_task_session(client)
            assert turn_started.wait(timeout=2)

            interrupt_response = client.post(f"/api/sessions/{session_id}/interrupt")
            assert interrupt_response.status_code == 200
            interrupted_live_session = interrupt_response.json()["session"]
            interrupted_live_session_id = interrupted_live_session["live_session_id"]
            assert interrupted_live_session["session_id"] == session_id

            interrupted_task = _wait_for_first_task_status(client, "failed")
            assert interrupted_task["session_id"] == session_id

            interrupted_detail = _wait_for_session_detail_detached(client, session_id)
            assert interrupted_detail["live_session"] is None
            assert interrupted_detail["active_live_session"] is None
            assert interrupted_detail["active_run"] is None
            assert interrupted_detail["timeline"]["fatal_error"]
            run_detail_response = client.get(f"/api/runs/{interrupted_live_session_id}")
            assert run_detail_response.status_code == 200
            run_detail = run_detail_response.json()["run"]
            assert run_detail["status"] == "interrupted"
            assert (
                run_detail["fatal_error"]
                == interrupted_detail["timeline"]["fatal_error"]
            )

            continuation_response = client.post(
                f"/api/sessions/{session_id}/messages",
                json={"text": "Resume"},
            )
            assert continuation_response.status_code == 200
            continuation_live_session_id = continuation_response.json()["session"][
                "live_session_id"
            ]
            continuation_worker = app.state.manager._live_sessions[
                continuation_live_session_id
            ].worker
            assert continuation_worker is not None
            continuation_worker.join(timeout=2)

            final_detail = client.get(f"/api/sessions/{session_id}").json()
            assert [item["content"] for item in final_detail["history_items"]] == [
                "Investigate",
                "Resume",
                "Resumed.",
            ]


def test_run_task_precreated_session_is_accessible_from_root_manager(
    monkeypatch, tmp_path
) -> None:
    project_dir = tmp_path / "packages" / "api"
    project_dir.mkdir(parents=True)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv(SESSION_DB_PATH_ENV, str(tmp_path / "sessions.db"))
    app = create_app(_settings())

    def fake_run_single_turn(_prompt, _runtime, _display, **kwargs):
        return SimpleNamespace(
            tool_errors=[],
            text="Done.",
            session_id=kwargs["resume_session_id"],
        )

    with patch(
        "pbi_agent.web.session.workers.run_single_turn_in_directory",
        side_effect=fake_run_single_turn,
    ) as mock_run:
        with TestClient(app) as client:
            client.put(
                "/api/board/stages",
                json={
                    "board_stages": [
                        {"id": "backlog", "name": "Backlog"},
                        {"id": "plan", "name": "Plan"},
                    ]
                },
            )
            create_response = client.post(
                "/api/tasks",
                json={
                    "title": "Task A",
                    "prompt": "Investigate",
                    "stage": "plan",
                    "project_dir": "packages/api",
                },
            )
            assert create_response.status_code == 200
            task_id = create_response.json()["task"]["task_id"]

            run_response = client.post(f"/api/tasks/{task_id}/run")
            assert run_response.status_code == 200
            session_id = run_response.json()["task"]["session_id"]

            deadline = time.monotonic() + 2
            while True:
                task_payload = client.get("/api/tasks").json()["tasks"][0]
                if task_payload["run_status"] == "completed":
                    break
                if time.monotonic() > deadline:
                    raise AssertionError("task run did not finish in time")
                time.sleep(0.01)

            detail_response = client.get(f"/api/sessions/{session_id}")
            assert detail_response.status_code == 200
            detail = detail_response.json()
            assert detail["session"]["session_id"] == session_id
            assert detail["session"]["directory"] == str(tmp_path).lower()
            assert [item["content"] for item in detail["history_items"]] == [
                "Investigate"
            ]

            replay_events = app.state.manager.get_session_event_stream_replay(
                session_id,
                since=0,
            )
            assert replay_events
            assert any(event["type"] == "session_state" for event in replay_events)

    assert mock_run.call_args is not None
    assert mock_run.call_args.kwargs["project_dir"] == "packages/api"
    assert mock_run.call_args.kwargs["workspace_root"] == tmp_path

    with SessionStore(db_path=tmp_path / "sessions.db") as store:
        saved_session = store.get_session(session_id)

    assert saved_session is not None
    assert saved_session.directory == str(tmp_path).lower()


def test_run_task_from_backlog_moves_to_next_stage_before_execution(
    monkeypatch, tmp_path
) -> None:
    monkeypatch.chdir(tmp_path)
    _write_default_commands(tmp_path)
    app = create_app(_settings())

    with patch(
        "pbi_agent.web.session.workers.run_single_turn_in_directory",
        return_value=SimpleNamespace(
            tool_errors=[],
            text="Planned.",
            session_id="session-123",
        ),
    ) as mock_run:
        with TestClient(app) as client:
            client.put(
                "/api/board/stages",
                json={
                    "board_stages": [
                        {"id": "backlog", "name": "Backlog"},
                        {"id": "plan", "name": "Plan", "command_id": "plan"},
                        {"id": "review", "name": "Review", "command_id": "review"},
                    ]
                },
            )
            create_response = client.post(
                "/api/tasks",
                json={"title": "Task A", "prompt": "Investigate", "stage": "backlog"},
            )
            assert create_response.status_code == 200
            task_id = create_response.json()["task"]["task_id"]

            run_response = client.post(f"/api/tasks/{task_id}/run")
            assert run_response.status_code == 200

            deadline = time.monotonic() + 2
            while True:
                task_response = client.get("/api/tasks")
                task_payload = task_response.json()["tasks"][0]
                if (
                    task_payload["stage"] == "review"
                    and task_payload["run_status"] == "completed"
                ):
                    break
                if time.monotonic() > deadline:
                    raise AssertionError("backlog task run did not finish in time")
                time.sleep(0.01)

    assert task_payload["stage"] == "review"
    assert task_payload["run_status"] == "completed"
    assert task_payload["session_id"] == "session-123"
    assert mock_run.call_args is not None
    assert mock_run.call_args.args[0] == (
        "/plan\n# Task\nTask A\n\n## Goal\nInvestigate"
    )


def test_run_task_formats_multiline_prompt_without_altering_content(
    monkeypatch, tmp_path
) -> None:
    monkeypatch.chdir(tmp_path)
    _write_default_commands(tmp_path)
    app = create_app(_settings())
    prompt = "Keep this exactly:\n\n- item 1\n- item 2"

    with patch(
        "pbi_agent.web.session.workers.run_single_turn_in_directory",
        return_value=SimpleNamespace(
            tool_errors=[],
            text="Planned.",
            session_id="session-123",
        ),
    ) as mock_run:
        with TestClient(app) as client:
            client.put(
                "/api/board/stages",
                json={
                    "board_stages": [
                        {"id": "backlog", "name": "Backlog"},
                        {"id": "plan", "name": "Plan", "command_id": "plan"},
                    ]
                },
            )
            create_response = client.post(
                "/api/tasks",
                json={"title": "Task A", "prompt": prompt, "stage": "plan"},
            )
            assert create_response.status_code == 200
            created_task = create_response.json()["task"]
            task_id = created_task["task_id"]
            assert created_task["prompt"] == prompt

            run_response = client.post(f"/api/tasks/{task_id}/run")
            assert run_response.status_code == 200

            deadline = time.monotonic() + 2
            while True:
                task_response = client.get("/api/tasks")
                task_payload = task_response.json()["tasks"][0]
                if (
                    task_payload["stage"] == "done"
                    and task_payload["run_status"] == "completed"
                ):
                    break
                if time.monotonic() > deadline:
                    raise AssertionError("multiline task run did not finish in time")
                time.sleep(0.01)

    assert mock_run.call_args is not None
    assert mock_run.call_args.args[0] == ("/plan\n# Task\nTask A\n\n## Goal\n" + prompt)


def test_run_task_only_prepends_command_for_first_runnable_stage(
    monkeypatch, tmp_path
) -> None:
    monkeypatch.chdir(tmp_path)
    _write_default_commands(tmp_path)
    app = create_app(_settings())

    with patch(
        "pbi_agent.web.session.workers.run_single_turn_in_directory",
        return_value=SimpleNamespace(
            tool_errors=[],
            text="Reviewed.",
            session_id="session-456",
        ),
    ) as mock_run:
        with TestClient(app) as client:
            client.put(
                "/api/board/stages",
                json={
                    "board_stages": [
                        {"id": "backlog", "name": "Backlog"},
                        {"id": "plan", "name": "Plan", "command_id": "plan"},
                        {"id": "review", "name": "Review", "command_id": "review"},
                    ]
                },
            )
            create_response = client.post(
                "/api/tasks",
                json={"title": "Task A", "prompt": "Investigate", "stage": "review"},
            )
            assert create_response.status_code == 200
            task_id = create_response.json()["task"]["task_id"]

            run_response = client.post(f"/api/tasks/{task_id}/run")
            assert run_response.status_code == 200

            deadline = time.monotonic() + 2
            while True:
                task_response = client.get("/api/tasks")
                task_payload = task_response.json()["tasks"][0]
                if (
                    task_payload["stage"] == "done"
                    and task_payload["run_status"] == "completed"
                ):
                    break
                if time.monotonic() > deadline:
                    raise AssertionError("review task run did not finish in time")
                time.sleep(0.01)

    assert mock_run.call_args is not None
    assert mock_run.call_args.args[0] == "/review"


def test_run_task_continuing_existing_session_sends_command_only(
    monkeypatch, tmp_path
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv(SESSION_DB_PATH_ENV, str(tmp_path / "sessions.db"))
    _write_default_commands(tmp_path)
    app = create_app(_settings())

    with SessionStore(db_path=tmp_path / "sessions.db") as store:
        session_id = store.create_session(
            directory=str(tmp_path),
            provider="openai",
            model="gpt-5.4",
            title="Task A",
        )
        store.add_message(
            session_id, "user", "/plan\n# Task\nTask A\n\n## Goal\nInvestigate"
        )
        store.add_message(session_id, "assistant", "Plan ready.")

    with patch(
        "pbi_agent.web.session.workers.run_single_turn_in_directory",
        return_value=SimpleNamespace(
            tool_errors=[],
            text="Replanned.",
            session_id=session_id,
        ),
    ) as mock_run:
        with TestClient(app) as client:
            client.put(
                "/api/board/stages",
                json={
                    "board_stages": [
                        {"id": "backlog", "name": "Backlog"},
                        {"id": "plan", "name": "Plan", "command_id": "plan"},
                    ]
                },
            )
            create_response = client.post(
                "/api/tasks",
                json={
                    "title": "Task A",
                    "prompt": "Investigate",
                    "stage": "plan",
                    "session_id": session_id,
                },
            )
            assert create_response.status_code == 200
            task_id = create_response.json()["task"]["task_id"]

            run_response = client.post(f"/api/tasks/{task_id}/run")
            assert run_response.status_code == 200

            deadline = time.monotonic() + 2
            while True:
                task_response = client.get("/api/tasks")
                task_payload = task_response.json()["tasks"][0]
                if task_payload["run_status"] == "completed":
                    break
                if time.monotonic() > deadline:
                    raise AssertionError("continued task run did not finish in time")
                time.sleep(0.01)

    with SessionStore(db_path=tmp_path / "sessions.db") as store:
        messages = store.list_messages(session_id)

    assert mock_run.call_args is not None
    assert mock_run.call_args.args[0] == "/plan"
    assert mock_run.call_args.kwargs["resume_session_id"] == session_id
    assert [message.content for message in messages] == [
        "/plan\n# Task\nTask A\n\n## Goal\nInvestigate",
        "Plan ready.",
        "/plan",
    ]


def test_task_update_title_preserves_prompt_content() -> None:
    app = create_app(_settings())

    with TestClient(app) as client:
        create_response = client.post(
            "/api/tasks",
            json={"title": "Task A", "prompt": "Investigate"},
        )
        assert create_response.status_code == 200
        task_id = create_response.json()["task"]["task_id"]

        update_response = client.patch(
            f"/api/tasks/{task_id}",
            json={"title": "Task B"},
        )

    assert update_response.status_code == 200
    task = update_response.json()["task"]
    assert task["title"] == "Task B"
    assert task["prompt"] == "Investigate"


def test_task_stage_move_keeps_prompt_content(monkeypatch, tmp_path) -> None:
    monkeypatch.chdir(tmp_path)
    _write_default_commands(tmp_path)
    app = create_app(_settings())

    with TestClient(app) as client:
        response = client.put(
            "/api/board/stages",
            json={
                "board_stages": [
                    {"id": "backlog", "name": "Backlog"},
                    {"id": "plan", "name": "Plan", "command_id": "plan"},
                    {"id": "review", "name": "Review", "command_id": "review"},
                ]
            },
        )
        assert response.status_code == 200

        create_response = client.post(
            "/api/tasks",
            json={"title": "Task A", "prompt": "Investigate", "stage": "plan"},
        )
        assert create_response.status_code == 200
        task = create_response.json()["task"]
        task_id = task["task_id"]
        original_prompt = task["prompt"]

        move_response = client.patch(f"/api/tasks/{task_id}", json={"stage": "review"})

    assert move_response.status_code == 200
    assert move_response.json()["task"]["prompt"] == original_prompt


def test_task_move_into_auto_start_stage_runs(monkeypatch, tmp_path) -> None:
    monkeypatch.chdir(tmp_path)
    _write_default_commands(tmp_path)
    app = create_app(_settings())
    prompts: list[str] = []

    def fake_run_single_turn_in_directory(prompt, _runtime, _display, **kwargs):
        prompts.append(prompt)
        return SimpleNamespace(
            tool_errors=[],
            text="Review complete.",
            session_id=kwargs["resume_session_id"],
        )

    with patch(
        "pbi_agent.web.session.workers.run_single_turn_in_directory",
        side_effect=fake_run_single_turn_in_directory,
    ):
        with TestClient(app) as client:
            response = client.put(
                "/api/board/stages",
                json={
                    "board_stages": [
                        {"id": "backlog", "name": "Backlog"},
                        {"id": "plan", "name": "Plan", "command_id": "plan"},
                        {
                            "id": "review",
                            "name": "Review",
                            "command_id": "review",
                            "auto_start": True,
                        },
                    ]
                },
            )
            assert response.status_code == 200

            create_response = client.post(
                "/api/tasks",
                json={"title": "Task A", "prompt": "Investigate", "stage": "plan"},
            )
            assert create_response.status_code == 200
            task_id = create_response.json()["task"]["task_id"]

            move_response = client.patch(
                f"/api/tasks/{task_id}",
                json={"stage": "review"},
            )
            assert move_response.status_code == 200

            deadline = time.monotonic() + 2
            while True:
                task_payload = client.get("/api/tasks").json()["tasks"][0]
                if (
                    task_payload["stage"] == "done"
                    and task_payload["run_status"] == "completed"
                ):
                    break
                if time.monotonic() > deadline:
                    raise AssertionError("moved auto-start task did not finish in time")
                time.sleep(0.01)

    assert prompts == ["/review"]
    assert task_payload["session_id"]


def test_auto_start_stage_runs_once_before_done(monkeypatch, tmp_path) -> None:
    monkeypatch.chdir(tmp_path)
    _write_default_commands(tmp_path)
    app = create_app(_settings())
    call_count = 0
    replay_history_flags: list[bool | None] = []

    def fake_run_single_turn_in_directory(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        replay_history_flags.append(kwargs.get("replay_history"))
        return SimpleNamespace(
            tool_errors=[],
            text=f"Completed run {call_count}.",
            session_id=f"session-{call_count}",
        )

    with patch(
        "pbi_agent.web.session.workers.run_single_turn_in_directory",
        side_effect=fake_run_single_turn_in_directory,
    ):
        with TestClient(app) as client:
            client.put(
                "/api/board/stages",
                json={
                    "board_stages": [
                        {"id": "backlog", "name": "Backlog"},
                        {"id": "plan", "name": "Plan", "command_id": "plan"},
                        {
                            "id": "fix-review",
                            "name": "Fix Review",
                            "command_id": "implement",
                            "auto_start": True,
                        },
                    ]
                },
            )
            create_response = client.post(
                "/api/tasks",
                json={"title": "Task A", "prompt": "Investigate", "stage": "plan"},
            )
            assert create_response.status_code == 200
            task_id = create_response.json()["task"]["task_id"]

            run_response = client.post(f"/api/tasks/{task_id}/run")
            assert run_response.status_code == 200

            deadline = time.monotonic() + 2
            while True:
                task_response = client.get("/api/tasks")
                task_payload = task_response.json()["tasks"][0]
                if (
                    task_payload["stage"] == "done"
                    and task_payload["run_status"] == "completed"
                ):
                    break
                if time.monotonic() > deadline:
                    raise AssertionError("auto-start task did not finish in time")
                time.sleep(0.01)

            time.sleep(0.1)
            task_payload = client.get("/api/tasks").json()["tasks"][0]

    assert call_count == 2
    assert replay_history_flags == [False, False]
    assert task_payload["stage"] == "done"
    assert task_payload["run_status"] == "completed"
    assert task_payload["session_id"] == "session-2"


def test_auto_started_stage_prompt_is_visible_while_running(
    monkeypatch, tmp_path
) -> None:
    monkeypatch.chdir(tmp_path)
    _write_default_commands(tmp_path)
    app = create_app(_settings())
    second_run_started = threading.Event()
    release_second_run = threading.Event()
    call_count = 0
    replay_history_flags: list[bool | None] = []
    turn_image_counts: list[int] = []

    def fake_run_single_turn_in_directory(prompt, _runtime, _display, **kwargs):
        nonlocal call_count
        call_count += 1
        replay_history_flags.append(kwargs.get("replay_history"))
        turn_image_counts.append(len(kwargs.get("images") or []))
        assert isinstance(kwargs["persisted_user_message_id"], int)
        if call_count == 2:
            assert prompt == "/implement"
            second_run_started.set()
            assert release_second_run.wait(timeout=2)
        return SimpleNamespace(
            tool_errors=[],
            text=f"Completed run {call_count}.",
            session_id=kwargs["resume_session_id"],
        )

    with patch(
        "pbi_agent.web.session.workers.run_single_turn_in_directory",
        side_effect=fake_run_single_turn_in_directory,
    ):
        with TestClient(app) as client:
            client.put(
                "/api/board/stages",
                json={
                    "board_stages": [
                        {"id": "backlog", "name": "Backlog"},
                        {"id": "plan", "name": "Plan", "command_id": "plan"},
                        {
                            "id": "implement",
                            "name": "Implement",
                            "command_id": "implement",
                            "auto_start": True,
                        },
                    ]
                },
            )
            upload_response = client.post(
                "/api/tasks/images",
                files={"files": ("chart.png", b"\x89PNG\r\n\x1a\n", "image/png")},
            )
            assert upload_response.status_code == 200
            upload_id = upload_response.json()["uploads"][0]["upload_id"]

            create_response = client.post(
                "/api/tasks",
                json={
                    "title": "Task A",
                    "prompt": "Investigate",
                    "stage": "plan",
                    "image_upload_ids": [upload_id],
                },
            )
            assert create_response.status_code == 200
            task_id = create_response.json()["task"]["task_id"]

            run_response = client.post(f"/api/tasks/{task_id}/run")
            assert run_response.status_code == 200
            session_id = run_response.json()["task"]["session_id"]

            assert second_run_started.wait(timeout=2)
            detail_response = client.get(f"/api/sessions/{session_id}")
            release_second_run.set()

            deadline = time.monotonic() + 2
            while True:
                task_payload = client.get("/api/tasks").json()["tasks"][0]
                if task_payload["run_status"] == "completed":
                    break
                if time.monotonic() > deadline:
                    raise AssertionError("auto-start task did not finish in time")
                time.sleep(0.01)

    assert detail_response.status_code == 200
    history = detail_response.json()["history_items"]
    assert [item["role"] for item in history] == ["user", "user"]
    assert history[0]["content"] == "/plan\n# Task\nTask A\n\n## Goal\nInvestigate"
    assert history[0]["image_attachments"][0]["upload_id"] == upload_id
    assert history[1]["content"] == "/implement"
    assert history[1]["image_attachments"] == []
    assert replay_history_flags == [False, False]
    assert turn_image_counts == [1, 0]


def test_saved_session_continuation_persists_uploaded_image_attachments(
    tmp_path,
    monkeypatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv(SESSION_DB_PATH_ENV, str(tmp_path / "sessions.db"))
    queued_seen = threading.Event()
    observed_upload_ids: list[str] = []

    with SessionStore(db_path=tmp_path / "sessions.db") as store:
        session_id = store.create_session(
            str(tmp_path),
            "openai",
            "gpt-5.4",
            "Image continuation",
        )

    def fake_run_session_loop(_settings, display, *, resume_session_id=None, **kwargs):
        del _settings, kwargs
        queued = display.user_prompt()
        assert getattr(queued, "text", None) == "Describe this"
        assert len(getattr(queued, "images", [])) == 1
        assert len(getattr(queued, "image_attachments", [])) == 1
        observed_upload_ids.append(queued.image_attachments[0].upload_id)
        queued_seen.set()
        with SessionStore(db_path=tmp_path / "sessions.db") as store:
            store.add_message(
                resume_session_id,
                "user",
                queued.text,
                image_attachments=[
                    MessageImageAttachment(
                        upload_id=attachment.upload_id,
                        name=attachment.name,
                        mime_type=attachment.mime_type,
                        byte_count=attachment.byte_count,
                        preview_url=attachment.preview_url,
                    )
                    for attachment in queued.image_attachments
                ],
            )
            store.add_message(resume_session_id, "assistant", "It is a chart.")
        return 0

    app = create_app(_settings())
    with patch(
        "pbi_agent.web.session.workers.run_session_loop",
        fake_run_session_loop,
    ):
        with TestClient(app) as client:
            upload_response = client.post(
                f"/api/sessions/{session_id}/images",
                files={"files": ("chart.png", b"\x89PNG\r\n\x1a\n", "image/png")},
            )
            assert upload_response.status_code == 200
            upload = upload_response.json()["uploads"][0]

            run_response = client.post(
                f"/api/sessions/{session_id}/runs",
                json={
                    "text": "Describe this",
                    "image_upload_ids": [upload["upload_id"]],
                },
            )
            assert run_response.status_code == 200
            live_session_id = run_response.json()["session"]["live_session_id"]
            assert queued_seen.wait(timeout=2)

            live_session = app.state.manager._live_sessions[live_session_id]
            if live_session.worker is not None:
                live_session.worker.join(timeout=2)
            detail_response = client.get(f"/api/sessions/{session_id}")

    assert observed_upload_ids == [upload["upload_id"]]
    assert detail_response.status_code == 200
    history = detail_response.json()["history_items"]
    assert [item["role"] for item in history] == ["user", "assistant"]
    assert history[0]["content"] == "Describe this"
    assert history[0]["image_attachments"][0]["upload_id"] == upload["upload_id"]
    assert history[0]["image_attachments"][0]["name"] == "chart.png"
    assert history[1]["image_attachments"] == []


def test_second_manager_start_does_not_mark_running_task_failed(
    monkeypatch, tmp_path
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv(SESSION_DB_PATH_ENV, str(tmp_path / "sessions.db"))
    started = threading.Event()
    finish = threading.Event()

    def blocking_run_single_turn_in_directory(*args, **kwargs):
        started.set()
        if not finish.wait(timeout=2):
            raise AssertionError("task worker did not unblock in time")
        return SimpleNamespace(
            tool_errors=[],
            text="Completed.",
            session_id="session-1",
        )

    manager = WebSessionManager(_settings())
    manager.start()
    try:
        manager.replace_board_stages(
            stages=[
                {"id": "backlog", "name": "Backlog"},
                {"id": "implement", "name": "Implement"},
                {"id": "done", "name": "Done"},
            ]
        )
        task = manager.create_task(
            title="Task A",
            prompt="Investigate",
            stage="implement",
        )
        task_id = str(task["task_id"])

        with patch(
            "pbi_agent.web.session.workers.run_single_turn_in_directory",
            side_effect=blocking_run_single_turn_in_directory,
        ):
            manager.run_task(task_id)
            assert started.wait(timeout=1)

            deadline = time.monotonic() + 2
            while True:
                with SessionStore(db_path=tmp_path / "sessions.db") as store:
                    current = store.get_kanban_task(task_id)
                assert current is not None
                if current.run_status == "running":
                    break
                if time.monotonic() > deadline:
                    raise AssertionError("task did not enter running state in time")
                time.sleep(0.01)

            second_manager = WebSessionManager(_settings())
            with pytest.raises(
                RuntimeError,
                match="Another web app instance is already managing this workspace",
            ):
                second_manager.start()

            with SessionStore(db_path=tmp_path / "sessions.db") as store:
                current = store.get_kanban_task(task_id)
            assert current is not None
            assert current.run_status == "running"

            finish.set()

            deadline = time.monotonic() + 2
            while True:
                with SessionStore(db_path=tmp_path / "sessions.db") as store:
                    current = store.get_kanban_task(task_id)
                assert current is not None
                if current.run_status == "completed":
                    break
                if time.monotonic() > deadline:
                    raise AssertionError("task did not finish in time")
                time.sleep(0.01)
    finally:
        finish.set()
        manager.shutdown()


def test_manager_start_retries_busy_lease_then_succeeds(monkeypatch, tmp_path) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv(SESSION_DB_PATH_ENV, str(tmp_path / "sessions.db"))
    manager = WebSessionManager(_settings())

    with (
        patch(
            "pbi_agent.web.session_manager.SessionStore.acquire_web_manager_lease",
            side_effect=[
                WebManagerLeaseBusyError("db busy"),
                True,
            ],
        ) as mock_acquire,
        patch("pbi_agent.web.session_manager.time.sleep") as mock_sleep,
    ):
        manager.start()

    assert mock_acquire.call_count == 2
    mock_sleep.assert_called_once()
    manager.shutdown()


def test_shutdown_keeps_lease_until_noncooperative_live_worker_stops(
    monkeypatch, tmp_path
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv(SESSION_DB_PATH_ENV, str(tmp_path / "sessions.db"))
    started = threading.Event()
    finish = threading.Event()

    def blocking_run_session_loop(*args, **kwargs):
        del args, kwargs
        started.set()
        if not finish.wait(timeout=5):
            raise AssertionError("live worker did not unblock in time")
        return 0

    manager = WebSessionManager(_settings())
    manager.start()
    try:
        with patch(
            "pbi_agent.web.session.workers.run_session_loop",
            side_effect=blocking_run_session_loop,
        ):
            live_session = manager.create_live_session()
            live_session_id = str(live_session["live_session_id"])
            assert started.wait(timeout=2)

            manager.shutdown()

            worker = manager._live_sessions[live_session_id].worker
            assert worker is not None
            assert worker.is_alive()
            assert manager._started is True
            with SessionStore(db_path=tmp_path / "sessions.db") as store:
                assert store.has_active_web_manager_lease(
                    str(tmp_path), stale_after_seconds=30.0
                )
                run = store.get_run_session(live_session_id)
            second_manager = WebSessionManager(_settings())
            with pytest.raises(
                RuntimeError,
                match="Another web app instance is already managing this workspace",
            ):
                second_manager.start()
            assert run is not None
            assert run.status == "interrupted"
            assert run.ended_at is not None
            assert run.exit_code == 130
            snapshot = json.loads(run.snapshot_json)
            assert snapshot["session_ended"] is True
            assert snapshot["processing"] is None
            assert snapshot["wait_message"] is None
            assert snapshot["fatal_error"] == "Interrupted during app shutdown."

            finish.set()
            worker.join(timeout=2)
            assert not worker.is_alive()
            with SessionStore(db_path=tmp_path / "sessions.db") as store:
                assert not store.has_active_web_manager_lease(
                    str(tmp_path), stale_after_seconds=30.0
                )
                completed_run = store.get_run_session(live_session_id)
            second_manager.start()
            second_manager.shutdown()
            assert completed_run is not None
            assert completed_run.status == "interrupted"
            assert completed_run.exit_code == 130
    finally:
        finish.set()
        manager.shutdown()


def test_shutdown_keeps_lease_until_noncooperative_task_worker_stops(
    monkeypatch, tmp_path
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv(SESSION_DB_PATH_ENV, str(tmp_path / "sessions.db"))
    started = threading.Event()
    finish = threading.Event()

    def blocking_run_single_turn(_prompt, _runtime, _display, **kwargs):
        started.set()
        if not finish.wait(timeout=5):
            raise AssertionError("task worker did not unblock in time")
        return SimpleNamespace(
            tool_errors=[],
            text="Done.",
            session_id=kwargs["resume_session_id"],
        )

    manager = WebSessionManager(_settings())
    manager.start()
    try:
        manager.replace_board_stages(
            stages=[
                {"id": "backlog", "name": "Backlog"},
                {"id": "plan", "name": "Plan"},
            ]
        )
        task = manager.create_task(title="Task A", prompt="Investigate", stage="plan")
        task_id = str(task["task_id"])

        with patch(
            "pbi_agent.web.session.workers.run_single_turn_in_directory",
            side_effect=blocking_run_single_turn,
        ):
            manager.run_task(task_id)
            assert started.wait(timeout=2)
            live_session_id = next(
                live_session_id
                for live_session_id, live_session in manager._live_sessions.items()
                if live_session.task_id == task_id
            )

            manager.shutdown()

            worker = manager._task_workers[task_id]
            assert worker.is_alive()
            assert manager._started is True
            with SessionStore(db_path=tmp_path / "sessions.db") as store:
                assert store.has_active_web_manager_lease(
                    str(tmp_path), stale_after_seconds=30.0
                )
                current = store.get_kanban_task(task_id)
                run = store.get_run_session(live_session_id)
            second_manager = WebSessionManager(_settings())
            with pytest.raises(
                RuntimeError,
                match="Another web app instance is already managing this workspace",
            ):
                second_manager.start()
            assert current is not None
            assert current.run_status == "failed"
            assert current.last_result_summary == "Interrupted during app shutdown."
            assert current.last_run_finished_at is not None
            assert run is not None
            assert run.status == "interrupted"
            assert run.ended_at is not None
            assert run.exit_code == 130

            finish.set()
            worker.join(timeout=2)
            assert not worker.is_alive()
            with SessionStore(db_path=tmp_path / "sessions.db") as store:
                assert not store.has_active_web_manager_lease(
                    str(tmp_path), stale_after_seconds=30.0
                )
                completed_task = store.get_kanban_task(task_id)
                completed_run = store.get_run_session(live_session_id)
            second_manager.start()
            second_manager.shutdown()
            assert completed_task is not None
            assert completed_task.run_status == "failed"
            assert completed_run is not None
            assert completed_run.status == "interrupted"
    finally:
        finish.set()
        manager.shutdown()


def test_lost_manager_lease_rejects_new_live_sessions(monkeypatch, tmp_path) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv(SESSION_DB_PATH_ENV, str(tmp_path / "sessions.db"))
    manager = WebSessionManager(_settings())
    try:
        with (
            patch(
                "pbi_agent.web.session.workers._WEB_MANAGER_LEASE_HEARTBEAT_SECS", 0.01
            ),
            patch(
                "pbi_agent.web.session.workers.SessionStore.renew_web_manager_lease",
                return_value=False,
            ),
        ):
            manager.start()
            deadline = time.monotonic() + 2
            while manager._started or manager._lease_thread is not None:
                if time.monotonic() > deadline:
                    raise AssertionError("lost lease shutdown did not finish in time")
                time.sleep(0.01)

        assert manager._shutdown_requested is True
        assert manager._started is False
        with pytest.raises(RuntimeError, match="Manager shutdown is in progress"):
            manager.create_live_session()
        with SessionStore(db_path=tmp_path / "sessions.db") as store:
            assert not store.has_active_web_manager_lease(
                str(tmp_path), stale_after_seconds=30.0
            )
    finally:
        manager.shutdown()


def test_lost_manager_lease_interrupts_active_live_worker(
    monkeypatch, tmp_path
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv(SESSION_DB_PATH_ENV, str(tmp_path / "sessions.db"))
    started = threading.Event()
    finish = threading.Event()

    def blocking_run_session_loop(*args, **kwargs):
        del args, kwargs
        started.set()
        if not finish.wait(timeout=5):
            raise AssertionError("live worker did not unblock in time")
        return 0

    manager = WebSessionManager(_settings())
    manager.start()
    try:
        with patch(
            "pbi_agent.web.session.workers.run_session_loop",
            side_effect=blocking_run_session_loop,
        ):
            live_session = manager.create_live_session()
            live_session_id = str(live_session["live_session_id"])
            assert started.wait(timeout=2)

            with (
                patch(
                    "pbi_agent.web.session.workers.SessionStore.renew_web_manager_lease",
                    return_value=False,
                ),
                patch.object(manager._lease_stop, "wait", return_value=False),
            ):
                manager._renew_manager_lease_loop()

            assert manager._shutdown_requested is True
            with pytest.raises(RuntimeError, match="Manager shutdown is in progress"):
                manager.create_live_session()
            with SessionStore(db_path=tmp_path / "sessions.db") as store:
                run = store.get_run_session(live_session_id)
            assert run is not None
            assert run.status == "interrupted"
            assert run.ended_at is not None
            assert run.exit_code == 130
            assert run.fatal_error == "Interrupted during app shutdown."
    finally:
        finish.set()
        manager.shutdown()


def test_create_live_session_rejects_after_shutdown_requested(
    monkeypatch, tmp_path
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv(SESSION_DB_PATH_ENV, str(tmp_path / "sessions.db"))
    manager = WebSessionManager(_settings())
    manager.start()
    try:
        with manager._lock:
            manager._shutdown_requested = True

        with pytest.raises(RuntimeError, match="Manager shutdown is in progress"):
            manager.create_live_session()

        assert manager._live_sessions == {}
    finally:
        manager.shutdown()


def test_run_task_rejects_after_shutdown_requested(monkeypatch, tmp_path) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv(SESSION_DB_PATH_ENV, str(tmp_path / "sessions.db"))
    manager = WebSessionManager(_settings())
    manager.start()
    try:
        manager.replace_board_stages(
            stages=[
                {"id": "backlog", "name": "Backlog"},
                {"id": "plan", "name": "Plan"},
            ]
        )
        task = manager.create_task(title="Task A", prompt="Investigate", stage="plan")
        task_id = str(task["task_id"])

        with manager._lock:
            manager._shutdown_requested = True

        with pytest.raises(RuntimeError, match="Manager shutdown is in progress"):
            manager.run_task(task_id)

        assert manager._running_task_ids == set()
        assert manager._task_workers == {}
        with SessionStore(db_path=tmp_path / "sessions.db") as store:
            current = store.get_kanban_task(task_id)
        assert current is not None
        assert current.run_status == "idle"
        assert current.session_id is None
    finally:
        manager.shutdown()


def test_run_task_rejects_while_task_update_is_mutating(monkeypatch, tmp_path) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv(SESSION_DB_PATH_ENV, str(tmp_path / "sessions.db"))
    manager = WebSessionManager(_settings())
    manager.start()
    try:
        manager.replace_board_stages(
            stages=[
                {"id": "backlog", "name": "Backlog"},
                {"id": "plan", "name": "Plan"},
            ]
        )
        task = manager.create_task(title="Task A", prompt="Investigate", stage="plan")
        task_id = str(task["task_id"])
        original_get_task = SessionStore.get_kanban_task
        update_entered_store = threading.Event()
        release_update = threading.Event()
        update_errors: list[BaseException] = []

        def blocking_get_task(self, current_task_id):
            if (
                current_task_id == task_id
                and threading.current_thread().name == "task-update-race"
                and not update_entered_store.is_set()
            ):
                update_entered_store.set()
                assert release_update.wait(timeout=2)
            return original_get_task(self, current_task_id)

        def update_task_in_thread() -> None:
            try:
                manager.update_task(task_id, prompt="Changed")
            except BaseException as exc:  # pragma: no cover - re-raised in test thread
                update_errors.append(exc)

        with (
            patch.object(SessionStore, "get_kanban_task", blocking_get_task),
            patch.object(
                manager,
                "_create_task_live_session",
                side_effect=RuntimeError("run setup should not start"),
            ),
        ):
            update_thread = threading.Thread(
                target=update_task_in_thread,
                name="task-update-race",
            )
            update_thread.start()
            assert update_entered_store.wait(timeout=2)
            try:
                with pytest.raises(RuntimeError, match="Task is already running"):
                    manager.run_task(task_id)
            finally:
                release_update.set()
                update_thread.join(timeout=2)

        assert not update_thread.is_alive()
        assert update_errors == []
        assert task_id not in manager._running_task_ids
        with SessionStore(db_path=tmp_path / "sessions.db") as store:
            current = store.get_kanban_task(task_id)
        assert current is not None
        assert current.prompt == "Changed"
    finally:
        manager.shutdown()


def test_run_task_rejects_while_task_delete_is_mutating(monkeypatch, tmp_path) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv(SESSION_DB_PATH_ENV, str(tmp_path / "sessions.db"))
    manager = WebSessionManager(_settings())
    manager.start()
    try:
        manager.replace_board_stages(
            stages=[
                {"id": "backlog", "name": "Backlog"},
                {"id": "plan", "name": "Plan"},
            ]
        )
        task = manager.create_task(title="Task A", prompt="Investigate", stage="plan")
        task_id = str(task["task_id"])
        original_get_task = SessionStore.get_kanban_task
        delete_entered_store = threading.Event()
        release_delete = threading.Event()
        delete_errors: list[BaseException] = []

        def blocking_get_task(self, current_task_id):
            if (
                current_task_id == task_id
                and threading.current_thread().name == "task-delete-race"
                and not delete_entered_store.is_set()
            ):
                delete_entered_store.set()
                assert release_delete.wait(timeout=2)
            return original_get_task(self, current_task_id)

        def delete_task_in_thread() -> None:
            try:
                manager.delete_task(task_id)
            except BaseException as exc:  # pragma: no cover - re-raised in test thread
                delete_errors.append(exc)

        with (
            patch.object(SessionStore, "get_kanban_task", blocking_get_task),
            patch.object(
                manager,
                "_create_task_live_session",
                side_effect=RuntimeError("run setup should not start"),
            ),
        ):
            delete_thread = threading.Thread(
                target=delete_task_in_thread,
                name="task-delete-race",
            )
            delete_thread.start()
            assert delete_entered_store.wait(timeout=2)
            try:
                with pytest.raises(RuntimeError, match="Task is already running"):
                    manager.run_task(task_id)
            finally:
                release_delete.set()
                delete_thread.join(timeout=2)

        assert not delete_thread.is_alive()
        assert delete_errors == []
        assert task_id not in manager._running_task_ids
        with SessionStore(db_path=tmp_path / "sessions.db") as store:
            current = store.get_kanban_task(task_id)
        assert current is None
    finally:
        manager.shutdown()


def test_run_task_setup_failure_clears_running_task_id(monkeypatch, tmp_path) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv(SESSION_DB_PATH_ENV, str(tmp_path / "sessions.db"))
    manager = WebSessionManager(_settings())
    manager.start()
    try:
        manager.replace_board_stages(
            stages=[
                {"id": "backlog", "name": "Backlog"},
                {"id": "plan", "name": "Plan"},
            ]
        )
        task = manager.create_task(title="Task A", prompt="Investigate", stage="plan")
        task_id = str(task["task_id"])
        original_resolve_task_runtime = manager._resolve_task_runtime
        resolve_calls = 0

        def fail_first_resolve_task_runtime(*args, **kwargs):
            nonlocal resolve_calls
            resolve_calls += 1
            if resolve_calls == 1:
                raise RuntimeError("setup failed")
            return original_resolve_task_runtime(*args, **kwargs)

        def fake_run_single_turn(_prompt, _runtime, _display, **kwargs):
            return SimpleNamespace(
                tool_errors=[],
                text="Done.",
                session_id=kwargs["resume_session_id"],
            )

        with patch.object(
            manager,
            "_resolve_task_runtime",
            side_effect=fail_first_resolve_task_runtime,
        ):
            with pytest.raises(RuntimeError, match="setup failed"):
                manager.run_task(task_id)

            assert task_id not in manager._running_task_ids

            with patch(
                "pbi_agent.web.session.workers.run_single_turn_in_directory",
                side_effect=fake_run_single_turn,
            ):
                rerun_task = manager.run_task(task_id)

        assert rerun_task["task_id"] == task_id
        assert resolve_calls >= 2
        deadline = time.monotonic() + 2
        while True:
            with manager._lock:
                running = task_id in manager._running_task_ids
            if not running:
                break
            if time.monotonic() > deadline:
                raise AssertionError("task worker did not finish in time")
            time.sleep(0.01)
    finally:
        manager.shutdown()


def test_run_task_live_session_creation_failure_marks_task_failed(
    monkeypatch, tmp_path
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv(SESSION_DB_PATH_ENV, str(tmp_path / "sessions.db"))
    manager = WebSessionManager(_settings())
    manager.start()
    try:
        manager.replace_board_stages(
            stages=[
                {"id": "backlog", "name": "Backlog"},
                {"id": "plan", "name": "Plan"},
            ]
        )
        task = manager.create_task(title="Task A", prompt="Investigate", stage="plan")
        task_id = str(task["task_id"])

        with patch.object(
            manager,
            "_publish_live_session_runtime",
            side_effect=RuntimeError("live setup failed"),
        ):
            with pytest.raises(RuntimeError, match="live setup failed"):
                manager.run_task(task_id)

        assert task_id not in manager._running_task_ids
        assert manager._task_workers == {}
        assert len(manager._live_sessions) == 1
        live_session = next(iter(manager._live_sessions.values()))
        assert live_session.task_id == task_id
        assert live_session.worker is None
        assert live_session.status == "ended"
        assert live_session.exit_code == 1
        assert live_session.fatal_error == "live setup failed"
        with SessionStore(db_path=tmp_path / "sessions.db") as store:
            current = store.get_kanban_task(task_id)
            run = store.get_run_session(live_session.live_session_id)
        assert current is not None
        assert current.run_status == "failed"
        assert current.last_result_summary == "live setup failed"
        assert run is not None
        assert run.status == "failed"
        assert run.ended_at is not None
        assert run.exit_code == 1
        assert run.fatal_error == "live setup failed"
    finally:
        manager.shutdown()


def test_run_task_worker_start_failure_finalizes_live_projection(
    monkeypatch, tmp_path
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv(SESSION_DB_PATH_ENV, str(tmp_path / "sessions.db"))
    manager = WebSessionManager(_settings())
    manager.start()

    class FailingThread:
        def __init__(self, *args, **kwargs) -> None:
            del args, kwargs

        def start(self) -> None:
            raise RuntimeError("thread start failed")

        def join(self, timeout: float | None = None) -> None:
            del timeout

        def is_alive(self) -> bool:
            return False

    try:
        manager.replace_board_stages(
            stages=[
                {"id": "backlog", "name": "Backlog"},
                {"id": "plan", "name": "Plan"},
            ]
        )
        task = manager.create_task(title="Task A", prompt="Investigate", stage="plan")
        task_id = str(task["task_id"])

        with patch("pbi_agent.web.session.tasks.threading.Thread", FailingThread):
            with pytest.raises(RuntimeError, match="thread start failed"):
                manager.run_task(task_id)

        assert task_id not in manager._running_task_ids
        assert manager._task_workers == {}
        assert len(manager._live_sessions) == 1
        live_session = next(iter(manager._live_sessions.values()))
        assert live_session.task_id == task_id
        assert live_session.worker is None
        assert live_session.status == "ended"
        assert live_session.exit_code == 1
        assert live_session.fatal_error == "thread start failed"

        with SessionStore(db_path=tmp_path / "sessions.db") as store:
            current = store.get_kanban_task(task_id)
            run = store.get_run_session(live_session.live_session_id)
        assert current is not None
        assert current.run_status == "failed"
        assert current.last_result_summary == "thread start failed"
        assert run is not None
        assert run.status == "failed"
        assert run.ended_at is not None
        assert run.exit_code == 1
        assert run.fatal_error == "thread start failed"
    finally:
        manager.shutdown()


def test_create_live_session_worker_start_failure_finalizes_live_projection(
    monkeypatch, tmp_path
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv(SESSION_DB_PATH_ENV, str(tmp_path / "sessions.db"))
    with SessionStore(db_path=tmp_path / "sessions.db") as store:
        session_id = store.create_session(
            str(tmp_path),
            "openai",
            "gpt-5.4",
            "Saved session",
        )
    manager = WebSessionManager(_settings())
    manager.start()

    class FailingThread:
        def __init__(self, *args, **kwargs) -> None:
            del args, kwargs

        def start(self) -> None:
            raise RuntimeError("thread start failed")

        def join(self, timeout: float | None = None) -> None:
            del timeout

        def is_alive(self) -> bool:
            return False

    try:
        with patch(
            "pbi_agent.web.session.live_sessions.threading.Thread", FailingThread
        ):
            with pytest.raises(RuntimeError, match="thread start failed"):
                manager.create_live_session(session_id=session_id)

        assert len(manager._live_sessions) == 1
        live_session = next(iter(manager._live_sessions.values()))
        assert live_session.worker is None
        assert live_session.status == "ended"
        assert live_session.exit_code == 1
        assert live_session.fatal_error == "thread start failed"
        assert manager._find_live_session_for_saved_session(session_id) is None

        detail = manager.get_session_detail(session_id)
        run_detail = manager.get_run_detail(live_session.live_session_id)
        with SessionStore(db_path=tmp_path / "sessions.db") as store:
            run = store.get_run_session(live_session.live_session_id)
        assert detail["active_live_session"] is None
        assert detail["active_run"] is None
        assert detail["status"] == "failed"
        assert detail["session"]["active_live_session_id"] is None
        assert run is not None
        assert run.status == "failed"
        assert run.ended_at is not None
        assert run.exit_code == 1
        assert run.fatal_error == "thread start failed"
        assert run_detail["run"]["status"] == "failed"
        assert run_detail["run"]["fatal_error"] == "thread start failed"
    finally:
        manager.shutdown()


def test_shutdown_waits_for_run_task_setup_before_releasing_lease(
    monkeypatch, tmp_path
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv(SESSION_DB_PATH_ENV, str(tmp_path / "sessions.db"))
    setup_entered = threading.Event()
    release_setup = threading.Event()
    worker_started = threading.Event()
    release_worker = threading.Event()
    run_result: dict[str, object] = {}

    manager = WebSessionManager(_settings())
    manager.start()
    try:
        manager.replace_board_stages(
            stages=[
                {"id": "backlog", "name": "Backlog"},
                {"id": "plan", "name": "Plan"},
            ]
        )
        task = manager.create_task(title="Task A", prompt="Investigate", stage="plan")
        task_id = str(task["task_id"])
        original_resolve_task_runtime = manager._resolve_task_runtime

        def blocking_resolve_task_runtime(*args, **kwargs):
            setup_entered.set()
            if not release_setup.wait(timeout=5):
                raise AssertionError("run_task setup did not unblock in time")
            return original_resolve_task_runtime(*args, **kwargs)

        def blocking_run_single_turn(prompt, runtime, display, **kwargs):
            del prompt, runtime, display
            worker_started.set()
            if not release_worker.wait(timeout=5):
                raise AssertionError("task worker did not unblock in time")
            return SimpleNamespace(
                tool_errors=[],
                text="Done.",
                session_id=kwargs["resume_session_id"],
            )

        def run_task_in_thread() -> None:
            try:
                run_result["task"] = manager.run_task(task_id)
            except Exception as exc:  # pragma: no cover - surfaced by assertion below
                run_result["error"] = exc

        with (
            patch.object(
                manager,
                "_resolve_task_runtime",
                side_effect=blocking_resolve_task_runtime,
            ),
            patch(
                "pbi_agent.web.session.workers.run_single_turn_in_directory",
                side_effect=blocking_run_single_turn,
            ),
        ):
            run_thread = threading.Thread(target=run_task_in_thread)
            run_thread.start()
            assert setup_entered.wait(timeout=2)
            with manager._lock:
                assert task_id in manager._running_task_ids
                assert manager._task_workers == {}

            manager.shutdown()

            with SessionStore(db_path=tmp_path / "sessions.db") as store:
                assert store.has_active_web_manager_lease(
                    str(tmp_path), stale_after_seconds=30.0
                )

            release_setup.set()
            run_thread.join(timeout=2)
            assert not run_thread.is_alive()
            assert "task" not in run_result
            error = run_result["error"]
            assert isinstance(error, RuntimeError)
            assert str(error) == "Manager shutdown is in progress."
            assert not worker_started.wait(timeout=0.1)
            live_session_id = next(
                live_session_id
                for live_session_id, live_session in manager._live_sessions.items()
                if live_session.task_id == task_id
            )
            assert manager._task_workers == {}
            assert manager._live_sessions[live_session_id].worker is None

            deadline = time.monotonic() + 2
            while True:
                with manager._lock:
                    running_task_ids = set(manager._running_task_ids)
                    task_workers = dict(manager._task_workers)
                with SessionStore(db_path=tmp_path / "sessions.db") as store:
                    active = store.has_active_web_manager_lease(
                        str(tmp_path), stale_after_seconds=30.0
                    )
                    current = store.get_kanban_task(task_id)
                    run = store.get_run_session(live_session_id)
                if not active and not running_task_ids:
                    break
                if time.monotonic() > deadline:
                    raise AssertionError("manager lease was not released")
                time.sleep(0.01)
            assert task_workers == {}
            assert current is not None
            assert current.run_status == "failed"
            assert current.last_result_summary == "Manager shutdown is in progress."
            assert current.last_run_finished_at is not None
            assert run is not None
            assert run.status == "failed"
            assert run.ended_at is not None
            assert run.exit_code == 1
            assert run.fatal_error == "Manager shutdown is in progress."
    finally:
        release_setup.set()
        release_worker.set()
        manager.shutdown()


def test_manager_start_reports_busy_database_after_retry_window(
    monkeypatch, tmp_path
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv(SESSION_DB_PATH_ENV, str(tmp_path / "sessions.db"))
    manager = WebSessionManager(_settings())

    with (
        patch(
            "pbi_agent.web.session_manager.SessionStore.acquire_web_manager_lease",
            side_effect=WebManagerLeaseBusyError("db busy"),
        ),
        patch(
            "pbi_agent.web.session_manager._WEB_MANAGER_LEASE_BUSY_RETRY_SECS",
            0.0,
        ),
        patch("pbi_agent.web.session_manager.time.sleep") as mock_sleep,
    ):
        with pytest.raises(
            RuntimeError,
            match="Session database is busy. Try starting the web app again.",
        ):
            manager.start()

    mock_sleep.assert_not_called()


def test_run_task_rejects_backlog_when_no_next_stage(monkeypatch, tmp_path) -> None:
    monkeypatch.chdir(tmp_path)
    app = create_app(_settings())

    with TestClient(app) as client:
        response = client.put(
            "/api/board/stages",
            json={
                "board_stages": [
                    {"id": "backlog", "name": "Backlog"},
                    {"id": "done", "name": "Done"},
                ]
            },
        )
        assert response.status_code == 200

        create_response = client.post(
            "/api/tasks",
            json={"title": "Task A", "prompt": "Investigate", "stage": "backlog"},
        )
        assert create_response.status_code == 200
        task_id = create_response.json()["task"]["task_id"]

        run_response = client.post(f"/api/tasks/{task_id}/run")

    assert run_response.status_code == 400
    assert (
        run_response.json()["detail"]
        == "Backlog tasks require a runnable board stage before they can run."
    )


def test_run_task_rejects_done_stage(monkeypatch, tmp_path) -> None:
    monkeypatch.chdir(tmp_path)
    app = create_app(_settings())

    with TestClient(app) as client:
        create_response = client.post(
            "/api/tasks",
            json={"title": "Task A", "prompt": "Investigate", "stage": "done"},
        )
        assert create_response.status_code == 200
        task_id = create_response.json()["task"]["task_id"]

        run_response = client.post(f"/api/tasks/{task_id}/run")

    assert run_response.status_code == 400
    assert run_response.json()["detail"] == "Done tasks cannot run."


def test_run_task_rejects_orphaned_task_profile(monkeypatch, tmp_path) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("OPENAI_API_KEY", "saved-openai-key")
    runtime_args = _runtime_args("web")
    create_provider_config(
        ProviderConfig(
            id="openai-main",
            name="OpenAI Main",
            kind="openai",
            api_key_env="OPENAI_API_KEY",
        )
    )
    create_model_profile_config(
        ModelProfileConfig(
            id="analysis",
            name="Analysis",
            provider_id="openai-main",
            model="gpt-5.4-2026-03-05",
        )
    )
    app = create_app(_settings(), runtime_args=runtime_args)

    with TestClient(app) as client:
        update_response = client.put(
            "/api/board/stages",
            json={
                "board_stages": [
                    {"id": "backlog", "name": "Backlog"},
                    {"id": "plan", "name": "Plan"},
                    {"id": "done", "name": "Done"},
                ]
            },
        )
        assert update_response.status_code == 200

        create_response = client.post(
            "/api/tasks",
            json={
                "title": "Task A",
                "prompt": "Investigate",
                "stage": "plan",
                "profile_id": "analysis",
            },
        )
        assert create_response.status_code == 200
        task_id = create_response.json()["task"]["task_id"]

        delete_model_profile_config("analysis")

        run_response = client.post(f"/api/tasks/{task_id}/run")

    assert run_response.status_code == 404
    assert run_response.json()["detail"] == "Unknown profile ID 'analysis'."


def test_run_task_rejects_orphaned_stage_profile(monkeypatch, tmp_path) -> None:
    monkeypatch.chdir(tmp_path)
    _write_default_commands(tmp_path)
    monkeypatch.setenv("OPENAI_API_KEY", "saved-openai-key")
    runtime_args = _runtime_args("web")
    create_provider_config(
        ProviderConfig(
            id="openai-main",
            name="OpenAI Main",
            kind="openai",
            api_key_env="OPENAI_API_KEY",
        )
    )
    create_model_profile_config(
        ModelProfileConfig(
            id="analysis",
            name="Analysis",
            provider_id="openai-main",
            model="gpt-5.4-2026-03-05",
        )
    )
    app = create_app(_settings(), runtime_args=runtime_args)

    with TestClient(app) as client:
        update_response = client.put(
            "/api/board/stages",
            json={
                "board_stages": [
                    {"id": "backlog", "name": "Backlog"},
                    {
                        "id": "plan",
                        "name": "Plan",
                        "command_id": "plan",
                        "profile_id": "analysis",
                    },
                    {"id": "review", "name": "Review", "command_id": "review"},
                ]
            },
        )
        assert update_response.status_code == 200

        create_response = client.post(
            "/api/tasks",
            json={"title": "Task A", "prompt": "Investigate", "stage": "plan"},
        )
        assert create_response.status_code == 200
        task_id = create_response.json()["task"]["task_id"]

        delete_model_profile_config("analysis")

        run_response = client.post(f"/api/tasks/{task_id}/run")

    assert run_response.status_code == 404
    assert run_response.json()["detail"] == "Unknown profile ID 'analysis'."


def test_run_task_backlog_setup_failure_marks_moved_task_failed(
    monkeypatch, tmp_path
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("OPENAI_API_KEY", "saved-openai-key")
    runtime_args = _runtime_args("web")
    create_provider_config(
        ProviderConfig(
            id="openai-main",
            name="OpenAI Main",
            kind="openai",
            api_key_env="OPENAI_API_KEY",
        )
    )
    create_model_profile_config(
        ModelProfileConfig(
            id="analysis",
            name="Analysis",
            provider_id="openai-main",
            model="gpt-5.4-2026-03-05",
        )
    )
    app = create_app(_settings(), runtime_args=runtime_args)

    with TestClient(app) as client:
        update_response = client.put(
            "/api/board/stages",
            json={
                "board_stages": [
                    {"id": "backlog", "name": "Backlog"},
                    {"id": "plan", "name": "Plan", "profile_id": "analysis"},
                    {"id": "done", "name": "Done"},
                ]
            },
        )
        assert update_response.status_code == 200

        create_response = client.post(
            "/api/tasks",
            json={"title": "Task A", "prompt": "Investigate", "stage": "backlog"},
        )
        assert create_response.status_code == 200
        task_id = create_response.json()["task"]["task_id"]

        delete_model_profile_config("analysis")

        run_response = client.post(f"/api/tasks/{task_id}/run")
        tasks_response = client.get("/api/tasks")
        event = app.state.manager.get_event_stream("app").snapshot()[-1]

    assert run_response.status_code == 404
    assert run_response.json()["detail"] == "Unknown profile ID 'analysis'."
    assert task_id not in app.state.manager._running_task_ids

    assert tasks_response.status_code == 200
    task_payload = tasks_response.json()["tasks"][0]
    assert task_payload["task_id"] == task_id
    assert task_payload["stage"] == "plan"
    assert task_payload["run_status"] == "failed"
    assert task_payload["last_result_summary"] == "Unknown profile ID 'analysis'."

    assert event["type"] == "task_updated"
    assert event["payload"]["task"]["task_id"] == task_id
    assert event["payload"]["task"]["stage"] == "plan"
    assert event["payload"]["task"]["run_status"] == "failed"


def test_web_display_wait_stop_clears_model_wait_processing() -> None:
    published: list[tuple[str, dict]] = []
    display = WebDisplay(
        publish_event=lambda event_type, payload: published.append(
            (event_type, payload)
        )
    )

    display.wait_start("analyzing your request...")
    display.wait_stop()

    assert published[-2:] == [
        ("wait_state", {"active": False}),
        ("processing_state", {"active": False, "phase": None, "message": None}),
    ]


def test_web_display_rekeys_persisted_assistant_message() -> None:
    published: list[tuple[str, dict]] = []
    display = WebDisplay(
        publish_event=lambda event_type, payload: published.append(
            (event_type, payload)
        )
    )

    display.render_markdown("final answer")
    display.persisted_message(
        MessageRecord(
            id=42,
            session_id="session-1",
            role="assistant",
            content="final answer",
            created_at="2026-05-03T00:00:00Z",
        )
    )

    assert published[-1] == (
        "message_rekeyed",
        {
            "old_item_id": "message-1",
            "item": {
                "item_id": "msg-42",
                "message_id": "msg-42",
                "part_ids": {
                    "content": "msg-42:content",
                    "file_paths": [],
                    "image_attachments": [],
                },
                "role": "assistant",
                "content": "final answer",
                "file_paths": [],
                "image_attachments": [],
                "markdown": True,
                "historical": True,
                "created_at": "2026-05-03T00:00:00Z",
            },
        },
    )


def test_live_session_worker_refreshes_mentions_on_reload_and_end() -> None:
    observed: dict[str, object] = {}

    def fake_run_session_loop(
        _settings, _display, *, resume_session_id=None, on_reload=None
    ):
        del _settings, _display, resume_session_id
        observed["on_reload_callable"] = callable(on_reload)
        if on_reload is not None:
            on_reload()
        return 0

    manager = WebSessionManager(_settings())
    refresh_calls = 0

    def fake_refresh_file_mentions_cache() -> None:
        nonlocal refresh_calls
        refresh_calls += 1

    manager.refresh_file_mentions_cache = fake_refresh_file_mentions_cache  # type: ignore[method-assign]

    manager.start()
    try:
        with patch(
            "pbi_agent.web.session.workers.run_session_loop", fake_run_session_loop
        ):
            live_session = manager.create_live_session()
            worker = manager._live_sessions[live_session["live_session_id"]].worker
            assert worker is not None
            worker.join(timeout=2)
    finally:
        manager.shutdown()

    assert observed["on_reload_callable"] is True
    assert refresh_calls == 2


def test_web_session_worker_records_turn_run_separately_from_live_projection(
    tmp_path, monkeypatch
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv(SESSION_DB_PATH_ENV, str(tmp_path / "sessions.db"))
    observed_run_session_ids: list[str | None] = []

    with SessionStore(db_path=tmp_path / "sessions.db") as store:
        session_id = store.create_session(
            str(tmp_path),
            "openai",
            "gpt-5.4",
            "Saved session",
        )

    def fake_run_session_loop(
        _settings,
        _display,
        *,
        resume_session_id=None,
        on_reload=None,
        run_session_id=None,
    ):
        del _settings, _display, on_reload
        observed_run_session_ids.append(run_session_id)
        with SessionStore(db_path=tmp_path / "sessions.db") as store:
            turn_run_id = store.create_run_session(
                session_id=resume_session_id,
                agent_name="main",
                agent_type="session_turn",
                provider="openai",
                provider_id="default",
                profile_id="analysis",
                model="gpt-5.4",
            )
            store.update_run_session(turn_run_id, status="completed")
        return 0

    manager = WebSessionManager(_settings())
    try:
        manager.start()
        with patch(
            "pbi_agent.web.session.workers.run_session_loop", fake_run_session_loop
        ):
            live_session = manager.create_live_session(session_id=session_id)
            live_session_id = live_session["live_session_id"]
            worker = manager._live_sessions[live_session_id].worker
            assert worker is not None
            worker.join(timeout=2)

        runs = manager.list_session_runs(session_id)
        all_runs = manager.list_all_runs()
        stats = manager.get_dashboard_stats()
        with SessionStore(db_path=tmp_path / "sessions.db") as store:
            live_projection = store.get_run_session(live_session_id)
    finally:
        manager.shutdown()

    assert observed_run_session_ids == [None]
    assert live_projection is not None
    assert live_projection.agent_type == "web_session"
    assert live_projection.status == "completed"
    assert [run["agent_type"] for run in runs] == ["session_turn"]
    assert runs[0]["run_session_id"] != live_session_id
    assert runs[0]["status"] == "completed"
    assert all_runs["total_count"] == 1
    assert all_runs["runs"][0]["run_session_id"] == runs[0]["run_session_id"]
    assert stats["overview"]["total_runs"] == 1


def test_web_session_worker_persists_failed_projection_on_fatal_error(
    tmp_path, monkeypatch
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv(SESSION_DB_PATH_ENV, str(tmp_path / "sessions.db"))
    with SessionStore(db_path=tmp_path / "sessions.db") as store:
        session_id = store.create_session(
            str(tmp_path),
            "openai",
            "gpt-5.4",
            "Fatal saved session",
        )

    def fake_run_session_loop(
        _settings,
        _display,
        *,
        resume_session_id=None,
        on_reload=None,
    ):
        del _settings, _display, resume_session_id, on_reload
        raise RuntimeError("boom")

    manager = WebSessionManager(_settings())
    try:
        manager.start()
        with patch(
            "pbi_agent.web.session.workers.run_session_loop", fake_run_session_loop
        ):
            live_session = manager.create_live_session(session_id=session_id)
            live_session_id = live_session["live_session_id"]
            worker = manager._live_sessions[live_session_id].worker
            assert worker is not None
            worker.join(timeout=2)
        detail = manager.get_session_detail(session_id)
        run_detail = manager.get_run_detail(live_session_id)
        with SessionStore(db_path=tmp_path / "sessions.db") as store:
            live_projection = store.get_run_session(live_session_id)
    finally:
        manager.shutdown()

    assert live_projection is not None
    assert live_projection.status == "failed"
    assert live_projection.exit_code == 1
    assert live_projection.fatal_error
    assert detail["status"] == "failed"
    assert run_detail["run"]["status"] == "failed"
    assert run_detail["run"]["fatal_error"] == live_projection.fatal_error


def test_saved_session_first_message_sets_blank_title(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv(SESSION_DB_PATH_ENV, str(tmp_path / "sessions.db"))

    def fake_run_session_loop(
        _settings, display, *, resume_session_id=None, on_reload=None
    ):
        del _settings, resume_session_id, on_reload
        display.user_prompt()
        return 0

    with SessionStore(db_path=tmp_path / "sessions.db") as store:
        session_id = store.create_session(
            str(tmp_path),
            "openai",
            "gpt-5.4",
            "",
        )

    manager = WebSessionManager(_settings())
    try:
        manager.start()
        with patch(
            "pbi_agent.web.session.workers.run_session_loop", fake_run_session_loop
        ):
            manager.submit_saved_session_input(
                session_id,
                text="Summarize the first part of this request and keep going.",
            )
            live_session = manager._find_stream_live_session_for_saved_session(
                session_id
            )
            if live_session is not None and live_session.worker is not None:
                live_session.worker.join(timeout=2)
        with SessionStore(db_path=tmp_path / "sessions.db") as store:
            updated = store.get_session(session_id)
    finally:
        manager.shutdown()

    assert updated is not None
    assert updated.title == "Summarize the first part of this request and keep going."


def test_saved_session_first_message_keeps_existing_title(
    tmp_path, monkeypatch
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv(SESSION_DB_PATH_ENV, str(tmp_path / "sessions.db"))

    def fake_run_session_loop(
        _settings, display, *, resume_session_id=None, on_reload=None
    ):
        del _settings, resume_session_id, on_reload
        display.user_prompt()
        return 0

    with SessionStore(db_path=tmp_path / "sessions.db") as store:
        session_id = store.create_session(
            str(tmp_path),
            "openai",
            "gpt-5.4",
            "Manual title",
        )

    manager = WebSessionManager(_settings())
    try:
        manager.start()
        with patch(
            "pbi_agent.web.session.workers.run_session_loop", fake_run_session_loop
        ):
            manager.submit_saved_session_input(
                session_id,
                text="This should not replace an existing title.",
            )
            live_session = manager._find_stream_live_session_for_saved_session(
                session_id
            )
            if live_session is not None and live_session.worker is not None:
                live_session.worker.join(timeout=2)
        with SessionStore(db_path=tmp_path / "sessions.db") as store:
            updated = store.get_session(session_id)
    finally:
        manager.shutdown()

    assert updated is not None
    assert updated.title == "Manual title"


def test_get_session_detail_returns_saved_history(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv(SESSION_DB_PATH_ENV, str(tmp_path / "sessions.db"))
    app = create_app(_settings())

    with SessionStore(db_path=tmp_path / "sessions.db") as store:
        session_id = store.create_session(
            str(tmp_path),
            "openai",
            "gpt-5.4",
            "Saved session",
        )
        store.add_message(session_id, "user", "Hello", file_paths=["notes.md"])
        store.add_message(session_id, "assistant", "Hi there")

    with TestClient(app) as client:
        response = client.get(f"/api/sessions/{session_id}")

    assert response.status_code == 200
    payload = response.json()
    assert payload["session"]["session_id"] == session_id
    assert payload["history_items"] == [
        {
            "item_id": "msg-1",
            "message_id": "msg-1",
            "part_ids": {
                "content": "msg-1:content",
                "file_paths": ["msg-1:file-path:0"],
                "image_attachments": [],
            },
            "role": "user",
            "content": "Hello",
            "file_paths": ["notes.md"],
            "image_attachments": [],
            "markdown": False,
            "historical": True,
            "created_at": payload["history_items"][0]["created_at"],
        },
        {
            "item_id": "msg-2",
            "message_id": "msg-2",
            "part_ids": {
                "content": "msg-2:content",
                "file_paths": [],
                "image_attachments": [],
            },
            "role": "assistant",
            "content": "Hi there",
            "file_paths": [],
            "image_attachments": [],
            "markdown": True,
            "historical": True,
            "created_at": payload["history_items"][1]["created_at"],
        },
    ]
    assert payload["live_session"] is None
    assert payload["active_run"] is None
    assert payload["timeline"] is None
    assert payload["status"] == "idle"


def test_saved_session_pending_questions_survive_refresh_and_answer_submission(
    tmp_path,
    monkeypatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv(SESSION_DB_PATH_ENV, str(tmp_path / "sessions.db"))
    answer_received = threading.Event()
    observed_answers: list[str] = []

    with SessionStore(db_path=tmp_path / "sessions.db") as store:
        session_id = store.create_session(
            str(tmp_path),
            "openai",
            "gpt-5.4",
            "Ask user",
        )

    def fake_run_session_loop(_settings, display, *, resume_session_id=None, **kwargs):
        del _settings, resume_session_id, kwargs
        queued = display.user_prompt()
        assert getattr(queued, "text", None) == "Need a choice"
        answers = display.ask_user_questions(
            [
                PendingUserQuestion(
                    question_id="q-1",
                    question="Which API style should I use?",
                    suggestions=["REST", "GraphQL", "SSE"],
                )
            ]
        )
        observed_answers.extend(answer.answer for answer in answers)
        answer_received.set()
        return 0

    app = create_app(_settings())
    with patch(
        "pbi_agent.web.session.workers.run_session_loop",
        fake_run_session_loop,
    ):
        with TestClient(app) as client:
            run_response = client.post(
                f"/api/sessions/{session_id}/runs",
                json={"text": "Need a choice"},
            )
            assert run_response.status_code == 200
            live_session_id = run_response.json()["session"]["live_session_id"]

            pending_detail: dict[str, object] | None = None
            deadline = time.monotonic() + 2
            while time.monotonic() <= deadline:
                detail_response = client.get(f"/api/sessions/{session_id}")
                assert detail_response.status_code == 200
                detail_payload = detail_response.json()
                pending = detail_payload["timeline"]["pending_user_questions"]
                if pending is not None:
                    pending_detail = detail_payload
                    break
                time.sleep(0.01)
            if pending_detail is None:
                raise AssertionError("pending user questions were not exposed")

            pending_questions = pending_detail["timeline"]["pending_user_questions"]
            assert pending_questions["prompt_id"] == "ask-1"
            assert pending_questions["questions"][0]["question_id"] == "q-1"
            assert (
                pending_detail["active_live_session"]["live_session_id"]
                == live_session_id
            )

            with SessionStore(db_path=tmp_path / "sessions.db") as store:
                run = store.get_run_session(live_session_id)
            assert run is not None
            snapshot = json.loads(run.snapshot_json or "{}")
            persisted_pending = snapshot["pending_user_questions"]
            assert persisted_pending["prompt_id"] == pending_questions["prompt_id"]
            assert persisted_pending["questions"] == pending_questions["questions"]
            assert persisted_pending["live_session_id"] == live_session_id
            assert persisted_pending["session_id"] == session_id

            answer_response = client.post(
                f"/api/sessions/{session_id}/question-response",
                json={
                    "prompt_id": "ask-1",
                    "answers": [
                        {
                            "question_id": "q-1",
                            "answer": "REST",
                            "selected_suggestion_index": 0,
                            "custom": False,
                        }
                    ],
                },
            )
            assert answer_response.status_code == 200
            assert answer_received.wait(timeout=2)

            live_session = app.state.manager._live_sessions[live_session_id]
            if live_session.worker is not None:
                live_session.worker.join(timeout=2)

            cleared_response = client.get(f"/api/sessions/{session_id}")
            assert cleared_response.status_code == 200
            cleared_payload = cleared_response.json()

    assert observed_answers == ["REST"]
    assert cleared_payload["timeline"]["pending_user_questions"] is None
    with SessionStore(db_path=tmp_path / "sessions.db") as store:
        records = store.list_observability_events(run_session_id=live_session_id)
    persisted_events = [json.loads(record.metadata_json) for record in records]
    assert any(
        event.get("type") == "user_questions_resolved"
        and event.get("payload", {}).get("prompt_id") == "ask-1"
        for event in persisted_events
    )


def test_get_session_detail_does_not_attach_ended_web_run(
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
            "Completed task",
        )
        store.add_message(session_id, "user", "/execute")
        store.add_message(session_id, "assistant", "Done")
        store.create_run_session(
            run_session_id="completed-turn-run",
            session_id=session_id,
            agent_name="main",
            agent_type="single_turn",
            provider="openai",
            provider_id="default",
            profile_id="analysis",
            model="gpt-5.4",
            status="completed",
            kind="session",
            project_dir=str(tmp_path),
        )
        run_id = store.create_run_session(
            run_session_id="ended-web-session",
            session_id=session_id,
            agent_name="web",
            agent_type="web_session",
            provider="openai",
            provider_id="default",
            profile_id="analysis",
            model="gpt-5.4",
            status="ended",
            kind="task",
            task_id="task-1",
            project_dir=str(tmp_path),
            last_event_seq=2,
            snapshot={
                "live_session_id": "ended-web-session",
                "session_id": session_id,
                "runtime": None,
                "input_enabled": False,
                "wait_message": None,
                "processing": None,
                "session_usage": None,
                "turn_usage": None,
                "session_ended": True,
                "fatal_error": None,
                "pending_user_questions": None,
                "items": [
                    {
                        "kind": "message",
                        "itemId": "message-1",
                        "role": "assistant",
                        "content": "Done",
                        "markdown": True,
                    }
                ],
                "sub_agents": {},
                "last_event_seq": 2,
            },
            exit_code=0,
        )
        store.add_observability_event(
            run_session_id=run_id,
            session_id=session_id,
            step_index=-1,
            event_type="web_event",
            metadata={
                "type": "message_added",
                "payload": {
                    "item_id": "message-1",
                    "role": "assistant",
                    "content": "Done",
                    "markdown": True,
                },
                "seq": 1,
            },
        )

    with TestClient(app) as client:
        response = client.get(f"/api/sessions/{session_id}")

    assert response.status_code == 200
    payload = response.json()
    assert [item["content"] for item in payload["history_items"]] == [
        "/execute",
        "Done",
    ]
    assert payload["status"] == "ended"
    assert payload["session"]["status"] == "ended"
    assert payload["live_session"] is None
    assert payload["active_live_session"] is None
    assert payload["active_run"] is None
    assert payload["session"]["active_live_session_id"] is None
    assert payload["session"]["active_run_id"] is None
    assert payload["timeline"]["live_session_id"] == "ended-web-session"
    assert payload["timeline"]["processing"] is None
    assert payload["timeline"]["pending_user_questions"] is None
    assert payload["timeline"]["session_ended"] is True
    assert payload["timeline"]["items"][0]["content"] == "Done"


def test_get_session_detail_combines_completed_web_run_timelines(
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
            "Multi-run session",
        )
        user_1 = store.add_message(session_id, "user", "/plan")
        assistant_1 = store.add_message(session_id, "assistant", "Plan done")
        user_2 = store.add_message(session_id, "user", "/review")
        assistant_2 = store.add_message(session_id, "assistant", "No findings")
        store.create_run_session(
            run_session_id="first-web-run",
            session_id=session_id,
            agent_name="web",
            agent_type="web_session",
            provider="openai",
            provider_id="default",
            profile_id="analysis",
            model="gpt-5.4",
            status="completed",
            kind="task",
            project_dir=str(tmp_path),
            last_event_seq=10,
            snapshot={
                "live_session_id": "first-web-run",
                "session_id": session_id,
                "runtime": None,
                "input_enabled": False,
                "wait_message": None,
                "processing": None,
                "session_usage": None,
                "turn_usage": None,
                "session_ended": True,
                "fatal_error": None,
                "pending_user_questions": None,
                "items": [
                    {
                        "kind": "message",
                        "itemId": f"msg-{user_1}",
                        "messageId": f"msg-{user_1}",
                        "role": "user",
                        "content": "/plan",
                        "markdown": False,
                    },
                    {
                        "kind": "thinking",
                        "itemId": "thinking-1",
                        "title": "Thinking",
                        "content": "planning",
                    },
                    {
                        "kind": "tool_group",
                        "itemId": "tool-group-2",
                        "label": "shell",
                        "status": "completed",
                        "items": [{"text": "output"}],
                    },
                    {
                        "kind": "message",
                        "itemId": f"msg-{assistant_1}",
                        "messageId": f"msg-{assistant_1}",
                        "role": "assistant",
                        "content": "Plan done",
                        "markdown": True,
                    },
                ],
                "sub_agents": {},
                "last_event_seq": 10,
            },
        )
        store.create_run_session(
            run_session_id="second-web-run",
            session_id=session_id,
            agent_name="web",
            agent_type="web_session",
            provider="openai",
            provider_id="default",
            profile_id="analysis",
            model="gpt-5.4",
            status="completed",
            kind="task",
            project_dir=str(tmp_path),
            last_event_seq=12,
            snapshot={
                "live_session_id": "second-web-run",
                "session_id": session_id,
                "runtime": None,
                "input_enabled": True,
                "wait_message": None,
                "processing": None,
                "session_usage": None,
                "turn_usage": None,
                "session_ended": True,
                "fatal_error": None,
                "pending_user_questions": None,
                "items": [
                    {
                        "kind": "message",
                        "itemId": f"msg-{user_2}",
                        "messageId": f"msg-{user_2}",
                        "role": "user",
                        "content": "/review",
                        "markdown": False,
                    },
                    {
                        "kind": "thinking",
                        "itemId": "thinking-1",
                        "title": "Thinking",
                        "content": "reviewing",
                    },
                    {
                        "kind": "message",
                        "itemId": f"msg-{assistant_2}",
                        "messageId": f"msg-{assistant_2}",
                        "role": "assistant",
                        "content": "No findings",
                        "markdown": True,
                    },
                ],
                "sub_agents": {},
                "last_event_seq": 12,
            },
        )

    with TestClient(app) as client:
        response = client.get(f"/api/sessions/{session_id}")

    assert response.status_code == 200
    payload = response.json()
    assert payload["timeline"]["live_session_id"] == "second-web-run"
    assert payload["timeline"]["last_event_seq"] == 12
    assert [item["kind"] for item in payload["timeline"]["items"]] == [
        "message",
        "thinking",
        "tool_group",
        "message",
        "message",
        "thinking",
        "message",
    ]
    assert payload["timeline"]["items"][1]["itemId"] == "first-web-run:thinking-1"
    assert payload["timeline"]["items"][2]["itemId"] == "first-web-run:tool-group-2"
    assert payload["timeline"]["items"][5]["itemId"] == "second-web-run:thinking-1"


def test_set_saved_session_profile_updates_dormant_session_without_starting_run(
    tmp_path, monkeypatch
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv(SESSION_DB_PATH_ENV, str(tmp_path / "sessions.db"))
    monkeypatch.setenv("OPENAI_API_KEY", "saved-openai-key")
    create_provider_config(
        ProviderConfig(
            id="openai-main",
            name="OpenAI Main",
            kind="openai",
            api_key_env="OPENAI_API_KEY",
        )
    )
    create_model_profile_config(
        ModelProfileConfig(
            id="review",
            name="Review",
            provider_id="openai-main",
            model="gpt-5.4-mini",
            reasoning_effort="low",
        )
    )
    app = create_app(_settings(), runtime_args=_runtime_args("web"))

    with SessionStore(db_path=tmp_path / "sessions.db") as store:
        session_id = store.create_session(
            str(tmp_path),
            "openai",
            "gpt-5.4",
            "Old session",
        )
        store.add_message(session_id, "user", "hello")
        store.create_run_session(
            run_session_id="ended-web-run",
            session_id=session_id,
            agent_name="web",
            agent_type="web_session",
            provider="openai",
            provider_id="default",
            profile_id=None,
            model="gpt-5.4",
            status="completed",
            kind="session",
            project_dir=str(tmp_path),
        )

    with TestClient(app) as client:
        response = client.put(
            f"/api/sessions/{session_id}/profile",
            json={"profile_id": "review"},
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["session"]["session_id"] == session_id
    assert payload["session"]["profile_id"] == "review"
    assert payload["session"]["model"] == "gpt-5.4-mini"
    assert payload["session"]["status"] == "idle"
    with SessionStore(db_path=tmp_path / "sessions.db") as store:
        saved = store.get_session(session_id)
        web_runs = store.list_web_session_runs(session_id)
    assert saved is not None
    assert saved.profile_id == "review"
    assert saved.model == "gpt-5.4-mini"
    assert [run.run_session_id for run in web_runs] == ["ended-web-run"]


def test_manager_start_marks_active_web_runs_stale_and_preserves_session_history(
    tmp_path, monkeypatch
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv(SESSION_DB_PATH_ENV, str(tmp_path / "sessions.db"))
    snapshot = {
        "live_session_id": "stale-live-run",
        "session_id": None,
        "runtime": None,
        "input_enabled": False,
        "wait_message": "waiting",
        "processing": {"active": True, "phase": "model_wait", "message": "waiting"},
        "session_usage": None,
        "turn_usage": None,
        "session_ended": False,
        "fatal_error": None,
        "pending_user_questions": None,
        "items": [
            {
                "kind": "message",
                "itemId": "message-1",
                "role": "assistant",
                "content": "Working",
                "markdown": True,
            }
        ],
        "sub_agents": {},
        "last_event_seq": 2,
    }
    event_1 = {
        "type": "session_state",
        "payload": {"state": "running", "session_id": None},
        "seq": 1,
        "created_at": "2026-04-16T12:00:00Z",
        "live_session_id": "stale-live-run",
        "session_id": None,
    }
    event_2 = {
        "type": "message_added",
        "payload": {
            "item_id": "message-1",
            "role": "assistant",
            "content": "Working",
            "markdown": True,
        },
        "seq": 2,
        "created_at": "2026-04-16T12:00:01Z",
        "live_session_id": "stale-live-run",
        "session_id": None,
    }

    with SessionStore(db_path=tmp_path / "sessions.db") as store:
        session_id = store.create_session(
            str(tmp_path),
            "openai",
            "gpt-5.4",
            "Stale session",
        )
        snapshot["session_id"] = session_id
        event_1["payload"]["session_id"] = session_id
        event_1["session_id"] = session_id
        event_2["session_id"] = session_id
        store.add_message(session_id, "user", "Hello")
        store.add_message(session_id, "assistant", "Saved answer")
        store.create_run_session(
            run_session_id="stale-live-run",
            session_id=session_id,
            agent_name="web",
            agent_type="web_session",
            provider="openai",
            provider_id="default",
            profile_id="analysis",
            model="gpt-5.4",
            status="running",
            kind="session",
            project_dir=str(tmp_path),
            last_event_seq=2,
            snapshot=snapshot,
        )
        store.add_observability_event(
            run_session_id="stale-live-run",
            session_id=session_id,
            step_index=-1,
            event_type="web_event",
            metadata=event_1,
        )
        store.add_observability_event(
            run_session_id="stale-live-run",
            session_id=session_id,
            step_index=-2,
            event_type="web_event",
            metadata=event_2,
        )
        other_session_id = store.create_session(
            str(tmp_path),
            "openai",
            "gpt-5.4",
            "Non-web active session",
        )
        store.create_run_session(
            run_session_id="non-web-active-run",
            session_id=other_session_id,
            agent_name="main",
            agent_type="session_turn",
            provider="openai",
            provider_id="default",
            profile_id="analysis",
            model="gpt-5.4",
            status="running",
            kind="session",
            project_dir=str(tmp_path),
        )
        store.create_run_session(
            run_session_id="unbound-web-run",
            session_id=None,
            agent_name="main",
            agent_type="web_session",
            provider="openai",
            provider_id="default",
            profile_id="analysis",
            model="gpt-5.4",
            status="waiting_for_input",
            kind="session",
            project_dir=str(tmp_path),
            metadata={"source": "web", "directory": str(tmp_path)},
        )
        store.create_run_session(
            run_session_id="other-directory-unbound-web-run",
            session_id=None,
            agent_name="main",
            agent_type="web_session",
            provider="openai",
            provider_id="default",
            profile_id="analysis",
            model="gpt-5.4",
            status="running",
            kind="session",
            project_dir=str(tmp_path / "other"),
            metadata={"source": "web", "directory": str(tmp_path / "other")},
        )
        store.create_run_session(
            run_session_id="malformed-metadata-unbound-web-run",
            session_id=None,
            agent_name="main",
            agent_type="web_session",
            provider="openai",
            provider_id="default",
            profile_id="analysis",
            model="gpt-5.4",
            status="running",
            kind="session",
            project_dir=str(tmp_path),
        )
        store.create_run_session(
            run_session_id="other-malformed-metadata-unbound-web-run",
            session_id=None,
            agent_name="main",
            agent_type="web_session",
            provider="openai",
            provider_id="default",
            profile_id="analysis",
            model="gpt-5.4",
            status="running",
            kind="session",
            project_dir=str(tmp_path / "other"),
        )
        store._conn.execute(
            "UPDATE run_sessions SET metadata_json = ? WHERE run_session_id IN (?, ?)",
            (
                "{malformed",
                "malformed-metadata-unbound-web-run",
                "other-malformed-metadata-unbound-web-run",
            ),
        )
        store._conn.commit()

    manager = WebSessionManager(_settings())
    try:
        manager.start()
        detail = manager.get_session_detail(session_id)
        listed_session = next(
            session
            for session in manager.list_sessions(limit=10)
            if session["session_id"] == session_id
        )
        direct_events = manager.get_event_stream("stale-live-run").snapshot()
        session_events = manager.get_session_event_stream(session_id).snapshot()
        with SessionStore(db_path=tmp_path / "sessions.db") as store:
            stale_run = store.get_run_session("stale-live-run")
            non_web_run = store.get_run_session("non-web-active-run")
            unbound_web_run = store.get_run_session("unbound-web-run")
            other_directory_unbound_web_run = store.get_run_session(
                "other-directory-unbound-web-run"
            )
            malformed_metadata_unbound_web_run = store.get_run_session(
                "malformed-metadata-unbound-web-run"
            )
            other_malformed_metadata_unbound_web_run = store.get_run_session(
                "other-malformed-metadata-unbound-web-run"
            )
            persisted_events = store.list_observability_events(
                run_session_id="stale-live-run"
            )
    finally:
        manager.shutdown()

    assert stale_run is not None
    assert stale_run.status == "stale"
    assert stale_run.ended_at is not None
    assert stale_run.last_event_seq == 2
    assert json.loads(stale_run.snapshot_json)["items"][0]["content"] == "Working"
    assert non_web_run is not None
    assert non_web_run.status == "running"
    assert unbound_web_run is not None
    assert unbound_web_run.status == "stale"
    assert unbound_web_run.ended_at is not None
    assert other_directory_unbound_web_run is not None
    assert other_directory_unbound_web_run.status == "running"
    assert other_directory_unbound_web_run.ended_at is None
    assert malformed_metadata_unbound_web_run is not None
    assert malformed_metadata_unbound_web_run.status == "stale"
    assert malformed_metadata_unbound_web_run.ended_at is not None
    assert other_malformed_metadata_unbound_web_run is not None
    assert other_malformed_metadata_unbound_web_run.status == "running"
    assert other_malformed_metadata_unbound_web_run.ended_at is None
    assert [record.event_type for record in persisted_events] == [
        "web_event",
        "web_event",
    ]
    assert detail["status"] == "stale"
    assert detail["session"]["status"] == "stale"
    assert detail["live_session"] is None
    assert detail["active_live_session"] is None
    assert detail["active_run"] is None
    assert detail["session"]["active_live_session_id"] is None
    assert detail["session"]["active_run_id"] is None
    assert [item["content"] for item in detail["history_items"]] == [
        "Hello",
        "Saved answer",
    ]
    assert detail["timeline"]["live_session_id"] == "stale-live-run"
    assert detail["timeline"]["items"][0]["content"] == "Working"
    assert listed_session["status"] == "stale"
    assert listed_session["active_live_session_id"] is None
    assert listed_session["active_run_id"] is None
    assert [event["seq"] for event in direct_events] == [1, 2]
    assert [event["type"] for event in session_events] == [
        "session_state",
        "message_added",
    ]


def test_get_session_detail_matches_legacy_mixed_case_directory(
    tmp_path, monkeypatch
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv(SESSION_DB_PATH_ENV, str(tmp_path / "sessions.db"))

    with SessionStore(db_path=tmp_path / "sessions.db") as store:
        session_id = store.create_session(
            str(tmp_path),
            "openai",
            "gpt-5.4",
            "Saved session",
        )
        legacy_directory = str(tmp_path).replace("/tmp/", "/TMP/", 1)
        store._conn.execute(
            "UPDATE sessions SET directory = ? WHERE session_id = ?",
            (legacy_directory, session_id),
        )
        store._conn.commit()

    app = create_app(_settings())

    with TestClient(app) as client:
        sessions_response = client.get("/api/sessions")
        detail_response = client.get(f"/api/sessions/{session_id}")

    assert sessions_response.status_code == 200
    assert [item["session_id"] for item in sessions_response.json()["sessions"]] == [
        session_id
    ]
    assert detail_response.status_code == 200
    assert detail_response.json()["session"]["session_id"] == session_id


def test_list_session_runs_returns_observability_runs(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv(SESSION_DB_PATH_ENV, str(tmp_path / "sessions.db"))
    app = create_app(_settings())

    with SessionStore(db_path=tmp_path / "sessions.db") as store:
        session_id = store.create_session(
            str(tmp_path),
            "openai",
            "gpt-5.4",
            "Saved session",
        )
        parent_run_id = store.create_run_session(
            session_id=session_id,
            agent_name="main",
            agent_type="session_turn",
            provider="openai",
            provider_id="default",
            profile_id="analysis",
            model="gpt-5.4",
            metadata={"origin": "test"},
        )
        child_run_id = store.create_run_session(
            session_id=session_id,
            parent_run_session_id=parent_run_id,
            agent_name="athena",
            agent_type="reviewer",
            provider="openai",
            provider_id="default",
            profile_id="analysis",
            model="gpt-5.4-mini",
        )
        store.update_run_session(
            child_run_id,
            status="completed",
            total_duration_ms=42,
            total_tool_calls=1,
            total_api_calls=2,
            error_count=0,
        )

    with TestClient(app) as client:
        response = client.get(f"/api/sessions/{session_id}/runs")

    assert response.status_code == 200
    payload = response.json()
    assert [run["run_session_id"] for run in payload["runs"]] == [
        parent_run_id,
        child_run_id,
    ]
    assert payload["runs"][0]["metadata"] == {"origin": "test"}
    assert payload["runs"][1]["parent_run_session_id"] == parent_run_id
    assert payload["runs"][1]["status"] == "completed"
    assert payload["runs"][1]["total_duration_ms"] == 42
    assert payload["runs"][1]["total_tool_calls"] == 1
    assert payload["runs"][1]["total_api_calls"] == 2


def test_list_session_runs_returns_not_found_for_unknown_session() -> None:
    app = create_app(_settings())

    with TestClient(app) as client:
        response = client.get("/api/sessions/missing-session/runs")

    assert response.status_code == 404


def test_get_run_detail_returns_observability_events(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv(SESSION_DB_PATH_ENV, str(tmp_path / "sessions.db"))
    app = create_app(_settings())

    with SessionStore(db_path=tmp_path / "sessions.db") as store:
        session_id = store.create_session(
            str(tmp_path),
            "openai",
            "gpt-5.4",
            "Saved session",
        )
        run_session_id = store.create_run_session(
            session_id=session_id,
            agent_name="main",
            agent_type="session_turn",
            provider="openai",
            provider_id="default",
            profile_id="analysis",
            model="gpt-5.4",
        )
        store.add_observability_event(
            run_session_id=run_session_id,
            session_id=session_id,
            step_index=0,
            event_type="run_start",
            request_config={"provider": "openai"},
            metadata={"origin": "test"},
        )
        store.add_observability_event(
            run_session_id=run_session_id,
            session_id=session_id,
            step_index=1,
            event_type="model_call",
            provider="openai",
            model="gpt-5.4",
            request_payload={"input": "Hello"},
            response_payload={"output": "Hi"},
            prompt_tokens=12,
            completion_tokens=8,
            total_tokens=20,
            status_code=200,
            success=True,
        )
        store.add_observability_event(
            run_session_id=run_session_id,
            session_id=session_id,
            step_index=-1,
            event_type="web_event",
            metadata={
                "type": "input_state",
                "payload": {"enabled": True},
                "seq": 1,
            },
        )
        store.update_run_session(
            run_session_id,
            status="completed",
            total_api_calls=1,
        )

    with TestClient(app) as client:
        response = client.get(f"/api/runs/{run_session_id}")

    assert response.status_code == 200
    payload = response.json()
    assert payload["run"]["run_session_id"] == run_session_id
    assert payload["run"]["status"] == "completed"
    assert [event["event_type"] for event in payload["events"]] == [
        "run_start",
        "model_call",
    ]
    assert payload["events"][0]["request_config"] == {"provider": "openai"}
    assert payload["events"][0]["metadata"] == {"origin": "test"}
    assert payload["events"][1]["request_payload"] == {"input": "Hello"}
    assert payload["events"][1]["response_payload"] == {"output": "Hi"}
    assert payload["events"][1]["success"] is True
    assert payload["events"][1]["status_code"] == 200
    assert payload["events"][1]["total_tokens"] == 20


def test_get_run_detail_returns_not_found_for_unknown_run() -> None:
    app = create_app(_settings())

    with TestClient(app) as client:
        response = client.get("/api/runs/missing-run")

    assert response.status_code == 404


def test_get_session_detail_returns_not_found_for_unknown_session() -> None:
    app = create_app(_settings())

    with TestClient(app) as client:
        response = client.get("/api/sessions/missing-session")

    assert response.status_code == 404


def test_create_task_accepts_uploaded_image_ids(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv(SESSION_DB_PATH_ENV, str(tmp_path / "sessions.db"))
    app = create_app(_settings())

    with TestClient(app) as client:
        upload_response = client.post(
            "/api/tasks/images",
            files={"files": ("chart.png", b"\x89PNG\r\n\x1a\n", "image/png")},
        )
        assert upload_response.status_code == 200
        upload_id = upload_response.json()["uploads"][0]["upload_id"]

        create_response = client.post(
            "/api/tasks",
            json={
                "title": "Review chart",
                "prompt": "Describe the chart",
                "image_upload_ids": [upload_id],
            },
        )

    assert create_response.status_code == 200
    task = create_response.json()["task"]
    assert task["image_attachments"][0]["upload_id"] == upload_id
    assert task["image_attachments"][0]["name"] == "chart.png"


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
            "Saved session",
        )

    with TestClient(app) as client:
        task_response = client.post(
            "/api/tasks",
            json={
                "title": "Task with session",
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


def test_delete_session_endpoint_rejects_active_bound_live_session(
    tmp_path, monkeypatch
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv(SESSION_DB_PATH_ENV, str(tmp_path / "sessions.db"))
    app = create_app(_settings())
    run_started = threading.Event()
    release_run = threading.Event()

    def fake_run_single_turn(prompt, runtime, display, **kwargs):
        del prompt, runtime, display
        assert isinstance(kwargs["persisted_user_message_id"], int)
        run_started.set()
        assert release_run.wait(timeout=2)
        return SimpleNamespace(
            tool_errors=[],
            text="Done.",
            session_id=kwargs["resume_session_id"],
        )

    with patch(
        "pbi_agent.web.session.workers.run_single_turn_in_directory",
        side_effect=fake_run_single_turn,
    ):
        with TestClient(app) as client:
            _put_two_stage_board(client)
            task_id, session_id = _start_task_session(client)
            assert run_started.wait(timeout=2)

            delete_response = client.delete(f"/api/sessions/{session_id}")

            with SessionStore(db_path=tmp_path / "sessions.db") as store:
                persisted_session = store.get_session(session_id)
                persisted_task = store.get_kanban_task(task_id)
                persisted_messages = store.list_messages(session_id)
                persisted_run = store.get_latest_web_session_run(session_id)

            release_run.set()
            _wait_for_first_task_status(client, "completed")

    assert delete_response.status_code == 400
    assert "active run" in delete_response.json()["detail"]
    assert persisted_session is not None
    assert persisted_task is not None
    assert persisted_task.session_id == session_id
    assert [message.content for message in persisted_messages] == ["Investigate"]
    assert persisted_run is not None
    assert persisted_run.session_id == session_id


def test_delete_session_endpoint_accepts_saved_sessions_from_any_provider(
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
            "Other provider session",
        )

    with TestClient(app) as client:
        response = client.delete(f"/api/sessions/{session_id}")

    assert response.status_code == 204


def test_sse_event_stream_unsubscribes_when_closed() -> None:
    app = create_app(_settings())
    manager = app.state.manager
    stream = manager.get_event_stream("app")
    stream.publish("test", {})

    async def open_and_close() -> None:
        iterator = _iter_sse_events(stream, since=0)
        await anext(iterator)
        await anext(iterator)
        await iterator.aclose()

    with patch.object(stream, "unsubscribe") as mock_unsubscribe:
        asyncio.run(open_and_close())

    mock_unsubscribe.assert_called_once()


def test_lifespan_suppresses_cancelled_error_and_runs_shutdown() -> None:
    app = create_app(_settings())
    manager = app.state.manager

    async def run_lifespan() -> None:
        async with app.router.lifespan_context(app):
            raise asyncio.CancelledError()

    with patch.object(manager, "shutdown") as mock_shutdown:
        asyncio.run(run_lifespan())

    mock_shutdown.assert_called_once_with()


def test_config_provider_and_profile_list_update_delete_endpoints(
    monkeypatch, tmp_path: Path
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("OPENAI_API_KEY", "env-openai-key")
    app = create_app(_settings(), runtime_args=_runtime_args("web"))

    with TestClient(app) as client:
        bootstrap = client.get("/api/config/bootstrap")
        assert bootstrap.status_code == 200
        revision = bootstrap.json()["config_revision"]

        providers_response = client.get("/api/config/providers")
        assert providers_response.status_code == 200
        assert providers_response.json()["providers"] == []

        create_provider_response = client.post(
            "/api/config/providers",
            headers={"If-Match": revision},
            json={
                "name": "OpenAI Main",
                "kind": "openai",
                "api_key_env": "OPENAI_API_KEY",
            },
        )
        assert create_provider_response.status_code == 200
        revision = create_provider_response.json()["config_revision"]

        providers_response = client.get("/api/config/providers")
        assert providers_response.status_code == 200
        assert providers_response.json()["providers"] == [
            {
                "id": "openai-main",
                "name": "OpenAI Main",
                "kind": "openai",
                "auth_mode": "api_key",
                "responses_url": None,
                "generic_api_url": None,
                "secret_source": "env_var",
                "secret_env_var": "OPENAI_API_KEY",
                "has_secret": True,
                "auth_status": {
                    "auth_mode": "api_key",
                    "backend": None,
                    "session_status": "missing",
                    "has_session": False,
                    "can_refresh": False,
                    "account_id": None,
                    "email": None,
                    "plan_type": None,
                    "expires_at": None,
                },
            }
        ]

        update_provider_response = client.patch(
            "/api/config/providers/openai-main",
            headers={"If-Match": revision},
            json={
                "name": "OpenAI Updated",
                "responses_url": "https://example.test/v1/responses",
            },
        )
        assert update_provider_response.status_code == 200
        assert update_provider_response.json()["provider"]["name"] == "OpenAI Updated"
        assert (
            update_provider_response.json()["provider"]["responses_url"]
            == "https://example.test/v1/responses"
        )
        revision = update_provider_response.json()["config_revision"]

        profiles_response = client.get("/api/config/model-profiles")
        assert profiles_response.status_code == 200
        assert profiles_response.json()["model_profiles"] == []

        create_profile_response = client.post(
            "/api/config/model-profiles",
            headers={"If-Match": revision},
            json={
                "name": "Analysis",
                "provider_id": "openai-main",
                "model": "gpt-5.4-2026-03-05",
                "reasoning_effort": "xhigh",
                "max_tool_workers": 6,
            },
        )
        assert create_profile_response.status_code == 200
        revision = create_profile_response.json()["config_revision"]

        profiles_response = client.get("/api/config/model-profiles")
        assert profiles_response.status_code == 200
        assert [item["id"] for item in profiles_response.json()["model_profiles"]] == [
            "analysis"
        ]
        assert (
            profiles_response.json()["model_profiles"][0]["resolved_runtime"]["model"]
            == "gpt-5.4-2026-03-05"
        )

        update_profile_response = client.patch(
            "/api/config/model-profiles/analysis",
            headers={"If-Match": revision},
            json={
                "name": "Analysis Updated",
                "model": "gpt-5.4",
                "reasoning_effort": "high",
                "web_search": False,
            },
        )
        assert update_profile_response.status_code == 200
        updated_profile = update_profile_response.json()["model_profile"]
        assert updated_profile["name"] == "Analysis Updated"
        assert updated_profile["resolved_runtime"]["model"] == "gpt-5.4"
        assert updated_profile["resolved_runtime"]["web_search"] is False
        revision = update_profile_response.json()["config_revision"]

        delete_profile_response = client.delete(
            "/api/config/model-profiles/analysis",
            headers={"If-Match": revision},
        )
        assert delete_profile_response.status_code == 204

        profiles_response = client.get("/api/config/model-profiles")
        assert profiles_response.status_code == 200
        assert profiles_response.json()["model_profiles"] == []
        revision = profiles_response.json()["config_revision"]

        delete_provider_response = client.delete(
            "/api/config/providers/openai-main",
            headers={"If-Match": revision},
        )
        assert delete_provider_response.status_code == 204

        providers_response = client.get("/api/config/providers")
        assert providers_response.status_code == 200
        assert providers_response.json()["providers"] == []


def test_provider_auth_endpoints_round_trip(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("PBI_AGENT_AUTH_STORE_PATH", str(tmp_path / "auth.json"))
    app = create_app(_settings(), runtime_args=_runtime_args("web"))

    with TestClient(app) as client:
        revision = client.get("/api/config/bootstrap").json()["config_revision"]
        create_provider_response = client.post(
            "/api/config/providers",
            headers={"If-Match": revision},
            json={
                "name": "OpenAI ChatGPT",
                "kind": "chatgpt",
            },
        )
        assert create_provider_response.status_code == 200

        status_response = client.get("/api/provider-auth/openai-chatgpt")
        assert status_response.status_code == 200
        assert status_response.json()["auth_status"]["session_status"] == "missing"

        import_response = client.post(
            "/api/provider-auth/openai-chatgpt/import",
            json={
                "access_token": _jwt(
                    {
                        "exp": 4102444800,
                        "chatgpt_account_id": "acct_123",
                        "email": "user@example.com",
                    }
                ),
                "refresh_token": "refresh-token",
                "plan_type": "chatgpt_plus",
            },
        )
        assert import_response.status_code == 200
        import_payload = import_response.json()
        assert import_payload["provider"]["auth_mode"] == "chatgpt_account"
        assert import_payload["auth_status"]["session_status"] == "connected"
        assert import_payload["auth_status"]["can_refresh"] is True
        assert import_payload["auth_status"]["email"] == "user@example.com"
        assert import_payload["session"]["account_id"] == "acct_123"
        assert import_payload["session"]["plan_type"] == "chatgpt_plus"

        logout_response = client.delete("/api/provider-auth/openai-chatgpt")
        assert logout_response.status_code == 200
        logout_payload = logout_response.json()
        assert logout_payload["removed"] is True
        assert logout_payload["auth_status"]["session_status"] == "missing"


def test_provider_auth_browser_flow_endpoints_round_trip(
    monkeypatch, tmp_path: Path
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("PBI_AGENT_AUTH_STORE_PATH", str(tmp_path / "auth.json"))
    app = create_app(_settings(), runtime_args=_runtime_args("web"))

    browser_auth_holder: dict[str, BrowserAuthChallenge] = {}
    listener_holder: dict[str, _FakeBrowserAuthCallbackListener] = {}
    timer_holder: dict[str, _FakeTimer] = {}

    def fake_create_browser_auth_callback_listener(**kwargs):
        listener = _FakeBrowserAuthCallbackListener(kwargs["callback_handler"])
        listener_holder["listener"] = listener
        return listener

    def fake_timer(*args, **kwargs):
        timer = _FakeTimer(*args, **kwargs)
        timer_holder["timer"] = timer
        return timer

    def fake_start_browser_auth(**kwargs) -> BrowserAuthChallenge:
        browser_auth = BrowserAuthChallenge(
            authorization_url="https://auth.openai.com/oauth/authorize?state=state-123",
            redirect_uri=kwargs["redirect_uri"],
            state="state-123",
            code_verifier="verifier-123",
        )
        browser_auth_holder["auth"] = browser_auth
        return browser_auth

    def fake_complete_browser_auth(**kwargs):
        session = build_auth_session(
            provider_id=kwargs["provider_id"],
            backend="openai_chatgpt",
            access_token=_jwt(
                {
                    "exp": 4102444800,
                    "chatgpt_account_id": "acct_browser",
                    "email": "browser@example.com",
                }
            ),
            refresh_token="refresh-browser",
            account_id="acct_browser",
            email="browser@example.com",
        )
        save_auth_session(session)
        return session

    with (
        patch(
            "pbi_agent.web.session.provider_auth.create_browser_auth_callback_listener",
            side_effect=fake_create_browser_auth_callback_listener,
        ),
        patch(
            "pbi_agent.web.session.provider_auth.threading.Timer",
            side_effect=fake_timer,
        ),
        patch(
            "pbi_agent.web.session.provider_auth.start_provider_browser_auth",
            side_effect=fake_start_browser_auth,
        ),
        patch(
            "pbi_agent.web.session.provider_auth.complete_provider_browser_auth",
            side_effect=fake_complete_browser_auth,
        ),
        TestClient(app) as client,
    ):
        revision = client.get("/api/config/bootstrap").json()["config_revision"]
        create_provider_response = client.post(
            "/api/config/providers",
            headers={"If-Match": revision},
            json={
                "name": "OpenAI ChatGPT",
                "kind": "chatgpt",
            },
        )
        assert create_provider_response.status_code == 200

        start_response = client.post(
            "/api/provider-auth/openai-chatgpt/flows",
            json={"method": "browser"},
        )
        assert start_response.status_code == 200
        start_payload = start_response.json()
        flow_id = start_payload["flow"]["flow_id"]
        assert start_payload["flow"]["status"] == "pending"
        assert start_payload["flow"]["authorization_url"].startswith(
            "https://auth.openai.com/oauth/authorize"
        )
        assert (
            browser_auth_holder["auth"].redirect_uri
            == "http://localhost:1455/auth/callback"
        )
        assert listener_holder["listener"].started is True
        assert timer_holder["timer"].started is True

        callback_outcome = listener_holder["listener"].complete(
            code="auth-code-123",
            state="state-123",
        )
        assert callback_outcome.completed is True

        flow_response = client.get(f"/api/provider-auth/openai-chatgpt/flows/{flow_id}")
        assert flow_response.status_code == 200
        flow_payload = flow_response.json()
        assert flow_payload["flow"]["status"] == "completed"
        assert flow_payload["auth_status"]["session_status"] == "connected"
        assert flow_payload["session"]["email"] == "browser@example.com"
        assert listener_holder["listener"].stopped is True
        assert timer_holder["timer"].cancelled is True


def test_provider_auth_browser_flow_uses_dedicated_local_callback_listener(
    monkeypatch, tmp_path: Path
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("PBI_AGENT_AUTH_STORE_PATH", str(tmp_path / "auth.json"))
    app = create_app(_settings(), runtime_args=_runtime_args("web"))
    listener_holder: dict[str, _FakeBrowserAuthCallbackListener] = {}
    captured_redirect_uris: list[str] = []
    timer_holder: dict[str, _FakeTimer] = {}

    def fake_create_browser_auth_callback_listener(**kwargs):
        listener = _FakeBrowserAuthCallbackListener(kwargs["callback_handler"])
        listener_holder["listener"] = listener
        return listener

    def fake_timer(*args, **kwargs):
        timer = _FakeTimer(*args, **kwargs)
        timer_holder["timer"] = timer
        return timer

    def fake_start_browser_auth(**kwargs) -> BrowserAuthChallenge:
        captured_redirect_uris.append(kwargs["redirect_uri"])
        return BrowserAuthChallenge(
            authorization_url="https://auth.openai.com/oauth/authorize?state=state-123",
            redirect_uri=kwargs["redirect_uri"],
            state="state-123",
            code_verifier="verifier-123",
        )

    with (
        patch(
            "pbi_agent.web.session.provider_auth.create_browser_auth_callback_listener",
            side_effect=fake_create_browser_auth_callback_listener,
        ),
        patch(
            "pbi_agent.web.session.provider_auth.threading.Timer",
            side_effect=fake_timer,
        ),
        patch(
            "pbi_agent.web.session.provider_auth.start_provider_browser_auth",
            side_effect=fake_start_browser_auth,
        ),
        TestClient(app, base_url="http://127.0.0.1:8000") as client,
    ):
        revision = client.get("/api/config/bootstrap").json()["config_revision"]
        create_provider_response = client.post(
            "/api/config/providers",
            headers={"If-Match": revision},
            json={
                "name": "OpenAI ChatGPT",
                "kind": "chatgpt",
            },
        )
        assert create_provider_response.status_code == 200

        start_response = client.post(
            "/api/provider-auth/openai-chatgpt/flows",
            json={"method": "browser"},
        )
        assert start_response.status_code == 200

    assert captured_redirect_uris == ["http://localhost:1455/auth/callback"]
    assert listener_holder["listener"].started is True
    assert timer_holder["timer"].started is True


def test_provider_auth_browser_flow_registers_before_listener_start(
    monkeypatch, tmp_path: Path
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("PBI_AGENT_AUTH_STORE_PATH", str(tmp_path / "auth.json"))
    app = create_app(_settings(), runtime_args=_runtime_args("web"))

    timer_holder: dict[str, _FakeTimer] = {}

    class _EagerListener(_FakeBrowserAuthCallbackListener):
        def start(self) -> None:
            super().start()
            outcome = self.complete(code="auth-code-123", state="state-123")
            assert outcome.completed is True

    def fake_create_browser_auth_callback_listener(**kwargs):
        return _EagerListener(kwargs["callback_handler"])

    def fake_timer(*args, **kwargs):
        timer = _FakeTimer(*args, **kwargs)
        timer_holder["timer"] = timer
        return timer

    def fake_start_browser_auth(**kwargs) -> BrowserAuthChallenge:
        return BrowserAuthChallenge(
            authorization_url="https://auth.openai.com/oauth/authorize?state=state-123",
            redirect_uri=kwargs["redirect_uri"],
            state="state-123",
            code_verifier="verifier-123",
        )

    def fake_complete_browser_auth(**kwargs):
        session = build_auth_session(
            provider_id=kwargs["provider_id"],
            backend="openai_chatgpt",
            access_token=_jwt(
                {
                    "exp": 4102444800,
                    "chatgpt_account_id": "acct_browser",
                    "email": "browser@example.com",
                }
            ),
            refresh_token="refresh-browser",
            account_id="acct_browser",
            email="browser@example.com",
        )
        save_auth_session(session)
        return session

    with (
        patch(
            "pbi_agent.web.session.provider_auth.create_browser_auth_callback_listener",
            side_effect=fake_create_browser_auth_callback_listener,
        ),
        patch(
            "pbi_agent.web.session.provider_auth.threading.Timer",
            side_effect=fake_timer,
        ),
        patch(
            "pbi_agent.web.session.provider_auth.start_provider_browser_auth",
            side_effect=fake_start_browser_auth,
        ),
        patch(
            "pbi_agent.web.session.provider_auth.complete_provider_browser_auth",
            side_effect=fake_complete_browser_auth,
        ),
        TestClient(app) as client,
    ):
        revision = client.get("/api/config/bootstrap").json()["config_revision"]
        create_provider_response = client.post(
            "/api/config/providers",
            headers={"If-Match": revision},
            json={
                "name": "OpenAI ChatGPT",
                "kind": "chatgpt",
            },
        )
        assert create_provider_response.status_code == 200

        start_response = client.post(
            "/api/provider-auth/openai-chatgpt/flows",
            json={"method": "browser"},
        )
        assert start_response.status_code == 200
        assert start_response.json()["flow"]["status"] == "completed"
        assert timer_holder["timer"].cancelled is True


def test_provider_auth_browser_flow_timeout_stops_listener(
    monkeypatch, tmp_path: Path
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("PBI_AGENT_AUTH_STORE_PATH", str(tmp_path / "auth.json"))
    app = create_app(_settings(), runtime_args=_runtime_args("web"))

    listener_holder: dict[str, _FakeBrowserAuthCallbackListener] = {}
    timer_holder: dict[str, _FakeTimer] = {}

    def fake_create_browser_auth_callback_listener(**kwargs):
        listener = _FakeBrowserAuthCallbackListener(kwargs["callback_handler"])
        listener_holder["listener"] = listener
        return listener

    def fake_timer(*args, **kwargs):
        timer = _FakeTimer(*args, **kwargs)
        timer_holder["timer"] = timer
        return timer

    def fake_start_browser_auth(**kwargs) -> BrowserAuthChallenge:
        return BrowserAuthChallenge(
            authorization_url="https://auth.openai.com/oauth/authorize?state=state-123",
            redirect_uri=kwargs["redirect_uri"],
            state="state-123",
            code_verifier="verifier-123",
        )

    with (
        patch(
            "pbi_agent.web.session.provider_auth.create_browser_auth_callback_listener",
            side_effect=fake_create_browser_auth_callback_listener,
        ),
        patch(
            "pbi_agent.web.session.provider_auth.threading.Timer",
            side_effect=fake_timer,
        ),
        patch(
            "pbi_agent.web.session.provider_auth.start_provider_browser_auth",
            side_effect=fake_start_browser_auth,
        ),
        TestClient(app) as client,
    ):
        revision = client.get("/api/config/bootstrap").json()["config_revision"]
        create_provider_response = client.post(
            "/api/config/providers",
            headers={"If-Match": revision},
            json={
                "name": "OpenAI ChatGPT",
                "kind": "chatgpt",
            },
        )
        assert create_provider_response.status_code == 200

        start_response = client.post(
            "/api/provider-auth/openai-chatgpt/flows",
            json={"method": "browser"},
        )
        assert start_response.status_code == 200
        flow_id = start_response.json()["flow"]["flow_id"]

        timer_holder["timer"].fire()

        flow_response = client.get(f"/api/provider-auth/openai-chatgpt/flows/{flow_id}")
        assert flow_response.status_code == 200
        flow_payload = flow_response.json()
        assert flow_payload["flow"]["status"] == "failed"
        assert flow_payload["flow"]["error_message"] == "Authorization timed out."
        assert listener_holder["listener"].stopped is True
        assert timer_holder["timer"].cancelled is True


def test_provider_auth_device_flow_endpoints_round_trip(
    monkeypatch, tmp_path: Path
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("PBI_AGENT_AUTH_STORE_PATH", str(tmp_path / "auth.json"))
    app = create_app(_settings(), runtime_args=_runtime_args("web"))

    def fake_start_device_auth(**kwargs) -> DeviceAuthChallenge:
        del kwargs
        return DeviceAuthChallenge(
            verification_url="https://auth.openai.com/codex/device",
            user_code="ABCD-EFGH",
            device_auth_id="device-auth-123",
            interval_seconds=5,
        )

    def fake_poll_device_auth(**kwargs) -> AuthFlowPollResult:
        session = build_auth_session(
            provider_id=kwargs["provider_id"],
            backend="openai_chatgpt",
            access_token=_jwt(
                {
                    "exp": 4102444800,
                    "chatgpt_account_id": "acct_device",
                    "email": "device@example.com",
                }
            ),
            refresh_token="refresh-device",
            account_id="acct_device",
            email="device@example.com",
        )
        save_auth_session(session)
        return AuthFlowPollResult(status="completed", session=session)

    with (
        patch(
            "pbi_agent.web.session.provider_auth.start_provider_device_auth",
            side_effect=fake_start_device_auth,
        ),
        patch(
            "pbi_agent.web.session.provider_auth.poll_provider_device_auth",
            side_effect=fake_poll_device_auth,
        ),
        TestClient(app) as client,
    ):
        revision = client.get("/api/config/bootstrap").json()["config_revision"]
        create_provider_response = client.post(
            "/api/config/providers",
            headers={"If-Match": revision},
            json={
                "name": "OpenAI ChatGPT",
                "kind": "chatgpt",
            },
        )
        assert create_provider_response.status_code == 200

        start_response = client.post(
            "/api/provider-auth/openai-chatgpt/flows",
            json={"method": "device"},
        )
        assert start_response.status_code == 200
        start_payload = start_response.json()
        flow_id = start_payload["flow"]["flow_id"]
        assert start_payload["flow"]["status"] == "pending"
        assert start_payload["flow"]["user_code"] == "ABCD-EFGH"

        poll_response = client.post(
            f"/api/provider-auth/openai-chatgpt/flows/{flow_id}/poll"
        )
        assert poll_response.status_code == 200
        poll_payload = poll_response.json()
        assert poll_payload["flow"]["status"] == "completed"
        assert poll_payload["auth_status"]["session_status"] == "connected"
        assert poll_payload["session"]["email"] == "device@example.com"


def test_provider_model_discovery_endpoint_returns_openai_models(
    monkeypatch, tmp_path: Path
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("OPENAI_API_KEY", "env-openai-key")
    app = create_app(_settings(), runtime_args=_runtime_args("web"))

    requests_seen: list[urllib.request.Request] = []

    def fake_urlopen(request: urllib.request.Request, timeout: float = 0.0):
        del timeout
        requests_seen.append(request)
        return _FakeHTTPResponse(
            {
                "data": [
                    {
                        "id": "gpt-5.4",
                        "created": 1_713_000_000,
                        "owned_by": "openai",
                    },
                    {
                        "id": "gpt-5.4-mini",
                        "created": 1_713_000_100,
                        "owned_by": "openai",
                    },
                ]
            }
        )

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)

    with TestClient(app) as client:
        revision = client.get("/api/config/bootstrap").json()["config_revision"]
        create_provider_response = client.post(
            "/api/config/providers",
            headers={"If-Match": revision},
            json={
                "name": "OpenAI Main",
                "kind": "openai",
                "api_key_env": "OPENAI_API_KEY",
            },
        )
        assert create_provider_response.status_code == 200

        response = client.get("/api/config/providers/openai-main/models")

    assert response.status_code == 200
    payload = response.json()
    assert payload["provider_id"] == "openai-main"
    assert payload["provider_kind"] == "openai"
    assert payload["discovery_supported"] is True
    assert payload["manual_entry_required"] is False
    assert [item["id"] for item in payload["models"]] == ["gpt-5.4", "gpt-5.4-mini"]
    assert payload["models"][0]["owned_by"] == "openai"
    assert payload["models"][0]["supports_reasoning_effort"] is True
    assert payload["error"] is None
    assert requests_seen[0].full_url == "https://api.openai.com/v1/models"
    assert requests_seen[0].headers["Authorization"] == "Bearer env-openai-key"


def test_azure_provider_model_discovery_returns_manual_entry_required(
    monkeypatch, tmp_path: Path
) -> None:
    """Azure requires deployment names — discovery is disabled."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("AZURE_API_KEY", raising=False)
    app = create_app(_settings(), runtime_args=_runtime_args("web"))

    with TestClient(app) as client:
        revision = client.get("/api/config/bootstrap").json()["config_revision"]
        create_response = client.post(
            "/api/config/providers",
            headers={"If-Match": revision},
            json={
                "name": "Azure Chat",
                "kind": "azure",
                "api_key_env": "AZURE_API_KEY",
                "responses_url": "https://mca-resource.openai.azure.com/openai/v1",
            },
        )
        assert create_response.status_code == 200
        response = client.get("/api/config/providers/azure-chat/models")

    assert response.status_code == 200
    payload = response.json()
    assert payload["provider_kind"] == "azure"
    assert payload["discovery_supported"] is False
    assert payload["manual_entry_required"] is True
    assert payload["models"] == []


def test_provider_model_discovery_endpoint_lists_chatgpt_openai_models(
    monkeypatch, tmp_path: Path
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("PBI_AGENT_AUTH_STORE_PATH", str(tmp_path / "auth.json"))
    app = create_app(_settings(), runtime_args=_runtime_args("web"))

    requests_seen: list[urllib.request.Request] = []

    def fake_urlopen(request: urllib.request.Request, timeout: float = 0.0):
        del timeout
        requests_seen.append(request)
        return _FakeHTTPResponse(
            {
                "models": [
                    {
                        "slug": "gpt-5.4",
                        "display_name": "GPT-5.4",
                        "input_modalities": ["text", "image"],
                        "supported_reasoning_levels": [
                            {"effort": "medium", "description": "balanced"}
                        ],
                        "visibility": "list",
                        "supported_in_api": True,
                    },
                    {
                        "slug": "gpt-hidden",
                        "display_name": "Hidden",
                        "visibility": "hide",
                        "supported_in_api": True,
                    },
                    {
                        "slug": "gpt-not-supported",
                        "display_name": "Not Supported",
                        "visibility": "list",
                        "supported_in_api": False,
                    },
                ]
            }
        )

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)

    with TestClient(app) as client:
        revision = client.get("/api/config/bootstrap").json()["config_revision"]
        create_provider_response = client.post(
            "/api/config/providers",
            headers={"If-Match": revision},
            json={
                "name": "OpenAI ChatGPT",
                "kind": "chatgpt",
            },
        )
        assert create_provider_response.status_code == 200
        save_auth_session(
            build_auth_session(
                provider_id="openai-chatgpt",
                backend="openai_chatgpt",
                access_token=_jwt(
                    {
                        "exp": 4102444800,
                        "chatgpt_account_id": "acct_chatgpt",
                        "email": "chatgpt@example.com",
                    }
                ),
                refresh_token="refresh-chatgpt",
                account_id="acct_chatgpt",
                email="chatgpt@example.com",
            )
        )

        response = client.get("/api/config/providers/openai-chatgpt/models")

    assert response.status_code == 200
    payload = response.json()
    assert payload["provider_id"] == "openai-chatgpt"
    assert payload["provider_kind"] == "chatgpt"
    assert payload["discovery_supported"] is True
    assert payload["manual_entry_required"] is False
    assert payload["models"] == [
        {
            "id": "gpt-5.4",
            "display_name": "GPT-5.4",
            "created": None,
            "owned_by": "openai",
            "input_modalities": ["text", "image"],
            "output_modalities": ["text"],
            "aliases": [],
            "supports_reasoning_effort": True,
        }
    ]
    assert payload["error"] is None
    assert len(requests_seen) == 1
    assert (
        requests_seen[0].full_url
        == "https://chatgpt.com/backend-api/codex/models?client_version=0.124.0"
    )
    headers = {key.lower(): value for key, value in requests_seen[0].header_items()}
    assert headers["authorization"].startswith("Bearer ")
    assert headers["chatgpt-account-id"] == "acct_chatgpt"
    assert headers["originator"] == CHATGPT_ORIGINATOR
    assert headers["user-agent"].startswith(f"{CHATGPT_ORIGINATOR}/")


def test_provider_model_discovery_endpoint_returns_auth_required_error(
    monkeypatch, tmp_path: Path
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("PBI_AGENT_AUTH_STORE_PATH", str(tmp_path / "auth.json"))
    app = create_app(_settings(), runtime_args=_runtime_args("web"))

    with TestClient(app) as client:
        revision = client.get("/api/config/bootstrap").json()["config_revision"]
        create_provider_response = client.post(
            "/api/config/providers",
            headers={"If-Match": revision},
            json={
                "name": "OpenAI ChatGPT",
                "kind": "chatgpt",
            },
        )
        assert create_provider_response.status_code == 200

        response = client.get("/api/config/providers/openai-chatgpt/models")

    assert response.status_code == 200
    payload = response.json()
    assert payload["discovery_supported"] is True
    assert payload["manual_entry_required"] is True
    assert payload["models"] == []
    assert payload["error"]["code"] == "auth_required"
    assert "Missing authentication" in payload["error"]["message"]


def test_provider_model_discovery_endpoint_discovers_github_copilot_models(
    monkeypatch, tmp_path: Path
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("PBI_AGENT_AUTH_STORE_PATH", str(tmp_path / "auth.json"))
    app = create_app(_settings(), runtime_args=_runtime_args("web"))

    requests_seen: list[urllib.request.Request] = []

    def fake_urlopen(request: urllib.request.Request, timeout: float = 0.0):
        del timeout
        requests_seen.append(request)
        return _FakeHTTPResponse(
            {
                "data": [
                    {
                        "id": "gpt-5.4",
                        "name": "GPT-5.4",
                        "vendor": "openai",
                        "version": "2026-04-01",
                        "model_picker_enabled": True,
                        "policy": {"state": "enabled"},
                        "capabilities": {
                            "type": "chat",
                            "family": "gpt-5.4",
                            "supports": {
                                "vision": True,
                                "reasoning_effort": ["low", "medium", "high"],
                            },
                        },
                    },
                    {
                        "id": "claude-sonnet-4",
                        "name": "Claude Sonnet 4",
                        "vendor": "anthropic",
                        "version": "2026-04-01",
                        "model_picker_enabled": True,
                        "policy": {"state": "enabled"},
                        "capabilities": {
                            "type": "chat",
                            "family": "claude-sonnet-4",
                            "supports": {
                                "vision": True,
                            },
                        },
                    },
                    {
                        "id": "gpt-hidden",
                        "name": "Hidden",
                        "vendor": "openai",
                        "model_picker_enabled": False,
                        "capabilities": {
                            "type": "chat",
                            "family": "gpt-hidden",
                            "supports": {},
                        },
                    },
                    {
                        "id": "gemini-disabled",
                        "name": "Gemini Disabled",
                        "vendor": "google",
                        "model_picker_enabled": True,
                        "policy": {"state": "disabled"},
                        "capabilities": {
                            "type": "chat",
                            "family": "gemini-disabled",
                            "supports": {},
                        },
                    },
                ]
            }
        )

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)

    with TestClient(app) as client:
        revision = client.get("/api/config/bootstrap").json()["config_revision"]
        create_provider_response = client.post(
            "/api/config/providers",
            headers={"If-Match": revision},
            json={
                "name": "Copilot",
                "kind": "github_copilot",
            },
        )
        assert create_provider_response.status_code == 200
        save_auth_session(
            build_auth_session(
                provider_id="copilot",
                backend="github_copilot",
                access_token="gho_test_token",
                plan_type="github_copilot",
            )
        )

        response = client.get("/api/config/providers/copilot/models")

    assert response.status_code == 200
    payload = response.json()
    assert payload["provider_kind"] == "github_copilot"
    assert payload["discovery_supported"] is True
    assert payload["manual_entry_required"] is False
    assert payload["models"] == [
        {
            "id": "claude-sonnet-4",
            "display_name": "Claude Sonnet 4",
            "created": None,
            "owned_by": "anthropic",
            "input_modalities": ["text", "image"],
            "output_modalities": ["text"],
            "aliases": ["2026-04-01"],
            "supports_reasoning_effort": None,
        },
        {
            "id": "gpt-5.4",
            "display_name": "GPT-5.4",
            "created": None,
            "owned_by": "openai",
            "input_modalities": ["text", "image"],
            "output_modalities": ["text"],
            "aliases": ["2026-04-01"],
            "supports_reasoning_effort": True,
        },
    ]
    assert requests_seen[0].full_url == "https://api.githubcopilot.com/models"
    assert requests_seen[0].headers["Authorization"] == "Bearer gho_test_token"


def test_provider_model_discovery_endpoint_discovers_generic_provider_models(
    monkeypatch, tmp_path: Path
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("GENERIC_API_KEY", "generic-key")
    app = create_app(_settings(), runtime_args=_runtime_args("web"))

    requests_seen: list[urllib.request.Request] = []

    def fake_urlopen(request: urllib.request.Request, timeout: float = 0.0):
        del timeout
        requests_seen.append(request)
        return _FakeHTTPResponse(
            {
                "data": [
                    {
                        "id": "openrouter/auto",
                        "created": 1_713_000_000,
                        "owned_by": "openrouter",
                    },
                    {
                        "id": "anthropic/claude-sonnet-4",
                        "created": 1_713_000_100,
                        "owned_by": "anthropic",
                    },
                ]
            }
        )

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)

    with TestClient(app) as client:
        revision = client.get("/api/config/bootstrap").json()["config_revision"]
        create_provider_response = client.post(
            "/api/config/providers",
            headers={"If-Match": revision},
            json={
                "name": "Gateway",
                "kind": "generic",
                "api_key_env": "GENERIC_API_KEY",
                "generic_api_url": "https://gateway.example.test/v1/chat/completions",
            },
        )
        assert create_provider_response.status_code == 200

        response = client.get("/api/config/providers/gateway/models")

    assert response.status_code == 200
    payload = response.json()
    assert payload["provider_kind"] == "generic"
    assert payload["discovery_supported"] is True
    assert payload["manual_entry_required"] is False
    assert [item["id"] for item in payload["models"]] == [
        "anthropic/claude-sonnet-4",
        "openrouter/auto",
    ]
    assert payload["error"] is None
    assert requests_seen[0].full_url == "https://gateway.example.test/v1/models"
    assert requests_seen[0].headers["Authorization"] == "Bearer generic-key"


def test_provider_model_discovery_endpoint_falls_back_for_generic_provider_error(
    monkeypatch, tmp_path: Path
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("GENERIC_API_KEY", "generic-key")
    app = create_app(_settings(), runtime_args=_runtime_args("web"))

    def fake_urlopen(request: urllib.request.Request, timeout: float = 0.0):
        del timeout, request
        raise urllib.error.HTTPError(
            url="https://gateway.example.test/v1/models",
            code=404,
            msg="Not Found",
            hdrs=None,
            fp=BytesIO(b'{"error":{"message":"No models endpoint"}}'),
        )

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)

    with TestClient(app) as client:
        revision = client.get("/api/config/bootstrap").json()["config_revision"]
        create_provider_response = client.post(
            "/api/config/providers",
            headers={"If-Match": revision},
            json={
                "name": "Gateway",
                "kind": "generic",
                "api_key_env": "GENERIC_API_KEY",
                "generic_api_url": "https://gateway.example.test/v1/chat/completions",
            },
        )
        assert create_provider_response.status_code == 200

        response = client.get("/api/config/providers/gateway/models")

    assert response.status_code == 200
    payload = response.json()
    assert payload["provider_kind"] == "generic"
    assert payload["discovery_supported"] is True
    assert payload["manual_entry_required"] is True
    assert payload["models"] == []
    assert payload["error"]["code"] == "http_error"
    assert payload["error"]["message"] == "No models endpoint"


def test_provider_model_discovery_normalizes_google_payload(
    monkeypatch, tmp_path: Path
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("GEMINI_API_KEY", "gemini-key")
    app = create_app(_settings(), runtime_args=_runtime_args("web"))

    requests_seen: list[urllib.request.Request] = []

    def fake_urlopen(request: urllib.request.Request, timeout: float = 0.0):
        del timeout
        requests_seen.append(request)
        assert (
            request.full_url
            == "https://generativelanguage.googleapis.com/v1beta/models?pageSize=1000"
        )
        assert request.headers["X-goog-api-key"] == "gemini-key"
        return _FakeHTTPResponse(
            {
                "models": [
                    {
                        "name": "models/gemini-2.5-flash-preview-001",
                        "baseModelId": "gemini-2.5-flash-preview",
                        "version": "2.5",
                        "displayName": "Gemini 2.5 Flash Preview",
                        "supportedGenerationMethods": ["generateContent"],
                        "thinking": True,
                    },
                    {
                        "name": "models/text-embedding-004",
                        "baseModelId": "text-embedding-004",
                        "version": "004",
                        "displayName": "Text Embedding 004",
                        "supportedGenerationMethods": ["embedContent"],
                    },
                ]
            }
        )

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)

    with TestClient(app) as client:
        revision = client.get("/api/config/bootstrap").json()["config_revision"]
        create_provider_response = client.post(
            "/api/config/providers",
            headers={"If-Match": revision},
            json={
                "name": "Gemini",
                "kind": "google",
                "api_key_env": "GEMINI_API_KEY",
            },
        )
        assert create_provider_response.status_code == 200

        response = client.get("/api/config/providers/gemini/models")

    assert response.status_code == 200
    payload = response.json()
    assert payload["provider_kind"] == "google"
    assert payload["discovery_supported"] is True
    assert payload["manual_entry_required"] is False
    assert payload["models"] == [
        {
            "id": "gemini-2.5-flash-preview",
            "display_name": "Gemini 2.5 Flash Preview",
            "created": None,
            "owned_by": "google",
            "input_modalities": [],
            "output_modalities": ["text"],
            "aliases": ["gemini-2.5-flash-preview-001", "2.5"],
            "supports_reasoning_effort": True,
        }
    ]
    assert payload["error"] is None
    assert len(requests_seen) == 1


def test_provider_model_discovery_normalizes_xai_and_anthropic_payloads(
    monkeypatch, tmp_path: Path
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("XAI_API_KEY", "xai-key")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "anthropic-key")
    app = create_app(_settings(), runtime_args=_runtime_args("web"))

    requests_seen: list[str] = []

    def fake_urlopen(request: urllib.request.Request, timeout: float = 0.0):
        del timeout
        requests_seen.append(request.full_url)
        if request.full_url == "https://api.x.ai/v1/language-models":
            return _FakeHTTPResponse(
                {
                    "models": [
                        {
                            "id": "grok-4.20-reasoning",
                            "created": 1_713_000_200,
                            "owned_by": "xai",
                            "input_modalities": ["text", "image"],
                            "output_modalities": ["text"],
                            "aliases": ["grok-4.20"],
                        }
                    ]
                }
            )
        if request.full_url == "https://api.anthropic.com/v1/models?limit=1000":
            return _FakeHTTPResponse(
                {
                    "data": [
                        {
                            "id": "claude-sonnet-4-20250514",
                            "display_name": "Claude Sonnet 4",
                            "created_at": "2025-02-19T00:00:00Z",
                            "capabilities": {
                                "effort": {"supported": True},
                                "image_input": {"supported": True},
                                "pdf_input": {"supported": False},
                            },
                        }
                    ],
                    "has_more": True,
                    "last_id": "claude-sonnet-4-20250514",
                }
            )
        if (
            request.full_url
            == "https://api.anthropic.com/v1/models?limit=1000&after_id=claude-sonnet-4-20250514"
        ):
            return _FakeHTTPResponse(
                {
                    "data": [
                        {
                            "id": "claude-opus-4-20250514",
                            "display_name": "Claude Opus 4",
                            "created_at": "2025-02-19T00:00:00Z",
                            "capabilities": {
                                "effort": {"supported": False},
                                "image_input": {"supported": True},
                                "pdf_input": {"supported": True},
                            },
                        }
                    ],
                    "has_more": False,
                    "last_id": "claude-opus-4-20250514",
                }
            )
        raise AssertionError(f"Unexpected request URL: {request.full_url}")

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)

    with TestClient(app) as client:
        revision = client.get("/api/config/bootstrap").json()["config_revision"]
        xai_provider_response = client.post(
            "/api/config/providers",
            headers={"If-Match": revision},
            json={
                "name": "xAI",
                "kind": "xai",
                "api_key_env": "XAI_API_KEY",
            },
        )
        assert xai_provider_response.status_code == 200
        revision = xai_provider_response.json()["config_revision"]
        anthropic_provider_response = client.post(
            "/api/config/providers",
            headers={"If-Match": revision},
            json={
                "name": "Anthropic",
                "kind": "anthropic",
                "api_key_env": "ANTHROPIC_API_KEY",
            },
        )
        assert anthropic_provider_response.status_code == 200

        xai_response = client.get("/api/config/providers/xai/models")
        anthropic_response = client.get("/api/config/providers/anthropic/models")

    assert xai_response.status_code == 200
    xai_payload = xai_response.json()
    assert xai_payload["models"] == [
        {
            "id": "grok-4.20-reasoning",
            "display_name": "grok-4.20-reasoning",
            "created": 1713000200,
            "owned_by": "xai",
            "input_modalities": ["text", "image"],
            "output_modalities": ["text"],
            "aliases": ["grok-4.20"],
            "supports_reasoning_effort": True,
        }
    ]

    assert anthropic_response.status_code == 200
    anthropic_payload = anthropic_response.json()
    assert [item["id"] for item in anthropic_payload["models"]] == [
        "claude-opus-4-20250514",
        "claude-sonnet-4-20250514",
    ]
    assert anthropic_payload["models"][0]["display_name"] == "Claude Opus 4"
    assert anthropic_payload["models"][0]["created"] == "2025-02-19T00:00:00Z"
    assert anthropic_payload["models"][0]["owned_by"] == "anthropic"
    assert anthropic_payload["models"][0]["input_modalities"] == [
        "text",
        "image",
        "pdf",
    ]
    assert anthropic_payload["models"][0]["output_modalities"] == ["text"]
    assert anthropic_payload["models"][0]["supports_reasoning_effort"] is False
    assert anthropic_payload["models"][1]["input_modalities"] == ["text", "image"]
    assert anthropic_payload["models"][1]["supports_reasoning_effort"] is True
    assert requests_seen == [
        "https://api.x.ai/v1/language-models",
        "https://api.anthropic.com/v1/models?limit=1000",
        "https://api.anthropic.com/v1/models?limit=1000&after_id=claude-sonnet-4-20250514",
    ]


def test_sessions_endpoint_lists_saved_sessions(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv(SESSION_DB_PATH_ENV, str(tmp_path / "sessions.db"))
    app = create_app(_settings())

    with SessionStore(db_path=tmp_path / "sessions.db") as store:
        first_session_id = store.create_session(
            str(tmp_path),
            "openai",
            "gpt-5.4",
            "First session",
        )
        second_session_id = store.create_session(
            str(tmp_path),
            "xai",
            "grok-4",
            "Second session",
        )

    with TestClient(app) as client:
        response = client.get("/api/sessions", params={"limit": 10})

    assert response.status_code == 200
    payload = response.json()["sessions"]
    assert [item["session_id"] for item in payload] == [
        second_session_id,
        first_session_id,
    ]
    assert payload[0]["provider"] == "xai"
    assert payload[1]["provider"] == "openai"


def test_sessions_endpoint_maps_completed_run_status_to_ended(
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
            "Completed run session",
        )
        store.create_run_session(
            session_id=session_id,
            agent_name="main",
            agent_type="session_turn",
            provider="openai",
            provider_id="default",
            profile_id="analysis",
            model="gpt-5.4",
            status="completed",
        )

    with TestClient(app) as client:
        list_response = client.get("/api/sessions", params={"limit": 10})
        detail_response = client.get(f"/api/sessions/{session_id}")

    assert list_response.status_code == 200
    assert list_response.json()["sessions"][0]["status"] == "ended"
    assert list_response.json()["sessions"][0]["active_run_id"] is None
    assert detail_response.status_code == 200
    assert detail_response.json()["status"] == "ended"
    assert detail_response.json()["live_session"] is None
    assert detail_response.json()["active_run"] is None


def test_saved_session_event_stream_replays_persisted_events_in_sequence(
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
            "Persisted events",
        )
        run_id = store.create_run_session(
            session_id=session_id,
            agent_name="main",
            agent_type="web_session",
            provider="openai",
            provider_id="default",
            profile_id="analysis",
            model="gpt-5.4",
            status="ended",
            kind="session",
        )
        store.add_observability_event(
            run_session_id=run_id,
            session_id=session_id,
            step_index=1,
            event_type="run_step",
            metadata={"name": "ordinary observability event"},
        )
        store.add_observability_event(
            run_session_id=run_id,
            session_id=session_id,
            step_index=-2,
            event_type="web_event",
            metadata={
                "type": "message_added",
                "payload": {"item_id": "second", "role": "assistant"},
                "seq": 2,
            },
        )
        store.add_observability_event(
            run_session_id=run_id,
            session_id=session_id,
            step_index=-1,
            event_type="web_event",
            metadata={
                "type": "message_added",
                "payload": {"item_id": "first", "role": "user"},
                "seq": 1,
            },
        )

    with TestClient(app):
        stream = app.state.manager.get_session_event_stream(session_id)
        events = stream.snapshot()

    assert [event["seq"] for event in events] == [1, 2]
    assert [event["payload"]["item_id"] for event in events] == ["first", "second"]

    async def collect() -> list[str]:
        iterator = _iter_sse_events(stream, since=1)
        try:
            return [await anext(iterator), await anext(iterator)]
        finally:
            await iterator.aclose()

    _connected_raw, event_raw = asyncio.run(collect())
    event = _decode_sse_payload(event_raw)
    assert event["seq"] == 2
    assert event["payload"]["item_id"] == "second"
    assert "id: 2" in event_raw


def test_saved_session_sse_replays_latest_web_run_when_prior_cursor_is_high(
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
            "Persisted events across runs",
        )
        old_run_id = store.create_run_session(
            session_id=session_id,
            agent_name="main",
            agent_type="web_session",
            provider="openai",
            provider_id="default",
            profile_id="analysis",
            model="gpt-5.4",
            status="ended",
            kind="session",
            last_event_seq=99,
        )
        new_run_id = store.create_run_session(
            session_id=session_id,
            agent_name="main",
            agent_type="web_session",
            provider="openai",
            provider_id="default",
            profile_id="analysis",
            model="gpt-5.4",
            status="ended",
            kind="session",
            last_event_seq=1,
        )
        same_started_at = "2026-05-04T00:00:00+00:00"
        store._conn.execute(
            "UPDATE run_sessions SET started_at = ? WHERE run_session_id IN (?, ?)",
            (same_started_at, old_run_id, new_run_id),
        )
        store._conn.commit()
        store.add_observability_event(
            run_session_id=old_run_id,
            session_id=session_id,
            step_index=-99,
            event_type="web_event",
            metadata={
                "type": "message_added",
                "payload": {"item_id": "old-high", "role": "assistant"},
                "seq": 99,
            },
        )
        store.add_observability_event(
            run_session_id=new_run_id,
            session_id=session_id,
            step_index=-1,
            event_type="web_event",
            metadata={
                "type": "message_added",
                "payload": {"item_id": "new-low", "role": "assistant"},
                "seq": 1,
            },
        )

    captured: dict[str, object] = {}

    def fake_sse_response(  # noqa: ANN001
        stream,
        *,
        since,
        requested_since=None,
        replay_events=None,
        log_context=None,
    ):
        captured["since"] = since
        captured["requested_since"] = requested_since
        captured["snapshot"] = stream.snapshot()
        captured["replay_events"] = replay_events
        captured["log_context"] = log_context
        from fastapi.responses import JSONResponse

        return JSONResponse({"ok": True})

    from pbi_agent.web.api.routes import events as events_route

    monkeypatch.setattr(events_route, "_sse_response", fake_sse_response)

    with TestClient(app) as client:
        response = client.get(
            f"/api/events/sessions/{session_id}",
            params={"since": 99},
        )

    assert response.status_code == 200
    snapshot = captured["snapshot"]
    replay_events = captured["replay_events"]
    assert [event["payload"]["item_id"] for event in snapshot] == ["new-low"]
    assert [event["payload"]["item_id"] for event in replay_events] == ["new-low"]
    assert captured["since"] == 0
    assert captured["log_context"] == {
        "endpoint": "session",
        "stream_kind": "session",
        "session_id": session_id,
        "requested_since": 99,
        "resolved_since": 0,
        "cursor_source": "query",
        "cursor_reset": True,
    }


def test_saved_session_sse_replays_latest_web_run_when_prior_cursor_is_low(
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
            "Persisted events across low cursor runs",
        )
        old_run_id = store.create_run_session(
            session_id=session_id,
            agent_name="main",
            agent_type="web_session",
            provider="openai",
            provider_id="default",
            profile_id="analysis",
            model="gpt-5.4",
            status="ended",
            kind="session",
            last_event_seq=1,
        )
        new_run_id = store.create_run_session(
            session_id=session_id,
            agent_name="main",
            agent_type="web_session",
            provider="openai",
            provider_id="default",
            profile_id="analysis",
            model="gpt-5.4",
            status="ended",
            kind="session",
            last_event_seq=5,
        )
        same_started_at = "2026-05-04T00:00:00+00:00"
        store._conn.execute(
            "UPDATE run_sessions SET started_at = ? WHERE run_session_id IN (?, ?)",
            (same_started_at, old_run_id, new_run_id),
        )
        store._conn.commit()
        store.add_observability_event(
            run_session_id=old_run_id,
            session_id=session_id,
            step_index=-1,
            event_type="web_event",
            metadata={
                "type": "message_added",
                "payload": {"item_id": "old-1", "role": "assistant"},
                "seq": 1,
            },
        )
        for seq in range(1, 6):
            store.add_observability_event(
                run_session_id=new_run_id,
                session_id=session_id,
                step_index=-seq,
                event_type="web_event",
                metadata={
                    "type": "message_added",
                    "payload": {"item_id": f"new-{seq}", "role": "assistant"},
                    "seq": seq,
                },
            )

    captured: dict[str, object] = {}

    def fake_sse_response(  # noqa: ANN001
        stream,
        *,
        since,
        requested_since=None,
        replay_events=None,
        log_context=None,
    ):
        captured["since"] = since
        captured["requested_since"] = requested_since
        captured["snapshot"] = stream.snapshot()
        captured["replay_events"] = replay_events
        captured["log_context"] = log_context
        from fastapi.responses import JSONResponse

        return JSONResponse({"ok": True})

    from pbi_agent.web.api.routes import events as events_route

    monkeypatch.setattr(events_route, "_sse_response", fake_sse_response)

    with TestClient(app) as client:
        response = client.get(
            f"/api/events/sessions/{session_id}",
            params={"since": 1, "live_session_id": old_run_id},
        )

    assert response.status_code == 200
    replay_events = captured["replay_events"]
    assert [event["seq"] for event in captured["snapshot"]] == [1, 2, 3, 4, 5]
    assert [event["seq"] for event in replay_events] == [1, 2, 3, 4, 5]
    assert [event["payload"]["item_id"] for event in replay_events][0] == "new-1"
    assert captured["since"] == 0
    assert captured["requested_since"] == 1
    assert captured["log_context"] == {
        "endpoint": "session",
        "stream_kind": "session",
        "session_id": session_id,
        "requested_since": 1,
        "resolved_since": 0,
        "cursor_source": "query",
        "cursor_reset": True,
    }


def test_saved_session_sse_continues_when_cursor_matches_current_run(
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
            "Persisted events same run cursor",
        )
        run_id = store.create_run_session(
            session_id=session_id,
            agent_name="main",
            agent_type="web_session",
            provider="openai",
            provider_id="default",
            profile_id="analysis",
            model="gpt-5.4",
            status="ended",
            kind="session",
            last_event_seq=5,
        )
        for seq in range(1, 6):
            store.add_observability_event(
                run_session_id=run_id,
                session_id=session_id,
                step_index=-seq,
                event_type="web_event",
                metadata={
                    "type": "message_added",
                    "payload": {"item_id": f"current-{seq}", "role": "assistant"},
                    "seq": seq,
                },
            )

    captured: dict[str, object] = {}

    def fake_sse_response(  # noqa: ANN001
        stream,
        *,
        since,
        requested_since=None,
        replay_events=None,
        log_context=None,
    ):
        captured["since"] = since
        captured["requested_since"] = requested_since
        captured["replay_events"] = replay_events
        captured["log_context"] = log_context
        from fastapi.responses import JSONResponse

        return JSONResponse({"ok": True})

    from pbi_agent.web.api.routes import events as events_route

    monkeypatch.setattr(events_route, "_sse_response", fake_sse_response)

    with TestClient(app) as client:
        response = client.get(
            f"/api/events/sessions/{session_id}",
            params={"since": 1, "live_session_id": run_id},
        )

    assert response.status_code == 200
    replay_events = captured["replay_events"]
    assert [event["seq"] for event in replay_events] == [2, 3, 4, 5]
    assert captured["since"] == 1
    assert captured["requested_since"] == 1
    assert captured["log_context"] == {
        "endpoint": "session",
        "stream_kind": "session",
        "session_id": session_id,
        "requested_since": 1,
        "resolved_since": 1,
        "cursor_source": "query",
        "cursor_reset": False,
    }


def test_saved_session_sse_last_event_id_overrides_stale_since_for_new_run(
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
            "Last event precedence",
        )
        run_id = store.create_run_session(
            session_id=session_id,
            agent_name="main",
            agent_type="web_session",
            provider="openai",
            provider_id="default",
            profile_id="analysis",
            model="gpt-5.4",
            status="ended",
            kind="session",
            last_event_seq=1,
        )
        store.add_observability_event(
            run_session_id=run_id,
            session_id=session_id,
            step_index=-1,
            event_type="web_event",
            metadata={
                "type": "message_added",
                "payload": {"item_id": "new-low", "role": "assistant"},
                "seq": 1,
            },
        )

    captured: dict[str, object] = {}

    def fake_sse_response(  # noqa: ANN001
        stream,
        *,
        since,
        requested_since=None,
        replay_events=None,
        log_context=None,
    ):
        captured["since"] = since
        captured["requested_since"] = requested_since
        captured["replay_events"] = replay_events
        captured["log_context"] = log_context
        from fastapi.responses import JSONResponse

        return JSONResponse({"ok": True})

    from pbi_agent.web.api.routes import events as events_route

    monkeypatch.setattr(events_route, "_sse_response", fake_sse_response)

    with TestClient(app) as client:
        response = client.get(
            f"/api/events/sessions/{session_id}",
            params={"since": 99},
            headers={"Last-Event-ID": "1"},
        )

    assert response.status_code == 200
    assert captured["requested_since"] == 1
    assert captured["since"] == 1
    assert captured["replay_events"] == []
    assert captured["log_context"] == {
        "endpoint": "session",
        "stream_kind": "session",
        "session_id": session_id,
        "requested_since": 1,
        "resolved_since": 1,
        "cursor_source": "last_event_id",
        "cursor_reset": False,
    }


def test_delete_task_endpoint_removes_task() -> None:
    app = create_app(_settings())

    with TestClient(app) as client:
        create_response = client.post(
            "/api/tasks",
            json={"title": "Task A", "prompt": "Investigate"},
        )
        assert create_response.status_code == 200
        task_id = create_response.json()["task"]["task_id"]

        delete_response = client.delete(f"/api/tasks/{task_id}")
        assert delete_response.status_code == 204

        list_response = client.get("/api/tasks")

    assert list_response.status_code == 200
    assert list_response.json()["tasks"] == []


def test_static_and_spa_routes_return_expected_responses() -> None:
    app = create_app(_settings())

    with TestClient(app) as client:
        index_response = client.get("/")
        fallback_response = client.get("/plan")
        favicon_ico_response = client.get("/favicon.ico")
        favicon_png_response = client.get("/favicon.png")
        logo_response = client.get("/logo.png")
        logo_jpg_response = client.get("/logo.jpg")
        api_not_found_response = client.get("/api/not-found")
        stream_guard_response = client.get("/app")

    assert index_response.status_code == 200
    assert "text/html" in index_response.headers["content-type"]
    assert fallback_response.status_code == 200
    assert "text/html" in fallback_response.headers["content-type"]
    assert favicon_ico_response.status_code == 200
    assert favicon_ico_response.headers["content-type"] == "image/jpeg"
    assert favicon_png_response.status_code == 200
    assert favicon_png_response.headers["content-type"] == "image/jpeg"
    assert logo_response.status_code == 200
    assert logo_response.headers["content-type"] == "image/jpeg"
    assert logo_jpg_response.status_code == 200
    assert logo_jpg_response.headers["content-type"] == "image/jpeg"
    assert api_not_found_response.status_code == 404
    assert stream_guard_response.status_code == 404


def test_dashboard_stats_returns_aggregated_overview(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv(SESSION_DB_PATH_ENV, str(tmp_path / "sessions.db"))
    app = create_app(_settings())

    with SessionStore(db_path=tmp_path / "sessions.db") as store:
        session_id = store.create_session(
            str(tmp_path),
            "openai",
            "gpt-5.4",
            "Dashboard test",
        )
        run_id = store.create_run_session(
            session_id=session_id,
            agent_name="main",
            agent_type="session_turn",
            provider="openai",
            provider_id="default",
            profile_id="analysis",
            model="gpt-5.4",
        )
        store.update_run_session(
            run_id,
            status="completed",
            total_duration_ms=1000,
            input_tokens=100,
            output_tokens=50,
            estimated_cost_usd=0.01,
            total_tool_calls=3,
            total_api_calls=2,
            error_count=0,
        )

    with TestClient(app) as client:
        response = client.get("/api/dashboard/stats")

    assert response.status_code == 200
    payload = response.json()
    overview = payload["overview"]
    assert overview["total_sessions"] == 1
    assert overview["total_runs"] == 1
    assert overview["total_input_tokens"] == 100
    assert overview["total_output_tokens"] == 50
    assert overview["total_cost"] == 0.01
    assert overview["total_tool_calls"] == 3
    assert overview["total_api_calls"] == 2
    assert overview["completed_runs"] == 1
    assert overview["failed_runs"] == 0

    assert len(payload["breakdown"]) == 1
    assert payload["breakdown"][0]["provider"] == "openai"
    assert payload["breakdown"][0]["model"] == "gpt-5.4"
    assert payload["breakdown"][0]["run_count"] == 1

    assert len(payload["daily"]) >= 1


def test_dashboard_stats_global_scope_includes_other_workspaces(
    tmp_path, monkeypatch
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv(SESSION_DB_PATH_ENV, str(tmp_path / "sessions.db"))
    app = create_app(_settings())

    with SessionStore(db_path=tmp_path / "sessions.db") as store:
        # Create a session in a *different* directory than the workspace.
        session_id = store.create_session(
            "/other/workspace",
            "anthropic",
            "claude-4",
            "Other workspace",
        )
        store.create_run_session(
            session_id=session_id,
            agent_name="main",
            agent_type="session_turn",
            provider="anthropic",
            provider_id=None,
            profile_id=None,
            model="claude-4",
        )

    with TestClient(app) as client:
        # Workspace scope should NOT see the other workspace's run.
        ws_response = client.get("/api/dashboard/stats?scope=workspace")
        assert ws_response.status_code == 200
        assert ws_response.json()["overview"]["total_runs"] == 0

        # Global scope SHOULD see it.
        global_response = client.get("/api/dashboard/stats?scope=global")
        assert global_response.status_code == 200
        assert global_response.json()["overview"]["total_runs"] == 1


def test_list_all_runs_returns_paginated_runs(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv(SESSION_DB_PATH_ENV, str(tmp_path / "sessions.db"))
    app = create_app(_settings())

    with SessionStore(db_path=tmp_path / "sessions.db") as store:
        session_id = store.create_session(
            str(tmp_path),
            "openai",
            "gpt-5.4",
            "Paginated test",
        )
        for i in range(5):
            run_id = store.create_run_session(
                session_id=session_id,
                agent_name="main",
                agent_type="session_turn",
                provider="openai",
                provider_id="default",
                profile_id="analysis",
                model="gpt-5.4",
                status="completed" if i % 2 == 0 else "failed",
            )
            store.update_run_session(
                run_id,
                input_tokens=(i + 1) * 100,
                output_tokens=(i + 1) * 50,
            )

    with TestClient(app) as client:
        response = client.get("/api/runs?limit=2&offset=0")
        assert response.status_code == 200
        payload = response.json()
        assert payload["total_count"] == 5
        assert len(payload["runs"]) == 2
        assert payload["runs"][0]["session_title"] == "Paginated test"

        response = client.get("/api/runs?status=completed")
        assert response.status_code == 200
        payload = response.json()
        assert payload["total_count"] == 3
        assert all(run["status"] == "completed" for run in payload["runs"])

        response = client.get("/api/runs?status=failed")
        assert response.status_code == 200
        payload = response.json()
        assert payload["total_count"] == 2
        assert all(run["status"] == "failed" for run in payload["runs"])
