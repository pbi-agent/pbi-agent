from __future__ import annotations

import asyncio
import base64
import json
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

from pbi_agent.agent.session import NEW_SESSION_SENTINEL
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
from pbi_agent.branding import PBI_AGENT_TAGLINE
from pbi_agent.cli import build_parser
from pbi_agent.config import (
    ModelProfileConfig,
    ProviderConfig,
    Settings,
    create_model_profile_config,
    create_provider_config,
    delete_model_profile_config,
)
from pbi_agent.session_store import (
    SESSION_DB_PATH_ENV,
    SessionStore,
    WebManagerLeaseBusyError,
)
from pbi_agent.display.protocol import QueuedInput, QueuedRuntimeChange
from pbi_agent.web.session_manager import WebSessionManager
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
            "/api/live-sessions/expand-input",
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
            "/api/live-sessions/expand-input",
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
            json={"title": "Task A", "prompt": "Investigate the workspace layout"},
        )
        assert create_response.status_code == 200

        with client.websocket_connect("/api/events/app") as websocket:
            event = websocket.receive_json()

    assert event["type"] == "task_updated"
    assert event["payload"]["task"]["title"] == "Task A"


def test_task_creation_structures_plain_prompt_content() -> None:
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
    assert task["prompt"] == (
        "# Task\nInvestigate Workspace\n\n## Goal\n"
        "Review the repository and list the broken workflows."
    )


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
        "pbi_agent.web.session_manager.run_single_turn_in_directory",
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


def test_run_task_from_backlog_moves_to_next_stage_before_execution(
    monkeypatch, tmp_path
) -> None:
    monkeypatch.chdir(tmp_path)
    _write_default_commands(tmp_path)
    app = create_app(_settings())

    with patch(
        "pbi_agent.web.session_manager.run_single_turn_in_directory",
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
        "/plan # Task\nTask A\n\n## Goal\nInvestigate"
    )


def test_run_task_only_prepends_command_for_first_runnable_stage(
    monkeypatch, tmp_path
) -> None:
    monkeypatch.chdir(tmp_path)
    _write_default_commands(tmp_path)
    app = create_app(_settings())

    with patch(
        "pbi_agent.web.session_manager.run_single_turn_in_directory",
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


def test_task_update_title_refreshes_structured_prompt_heading() -> None:
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
    assert task["prompt"] == "# Task\nTask B\n\n## Goal\nInvestigate"


def test_task_stage_move_keeps_structured_prompt_canonical(
    monkeypatch, tmp_path
) -> None:
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


def test_auto_start_stage_runs_once_before_done(monkeypatch, tmp_path) -> None:
    monkeypatch.chdir(tmp_path)
    _write_default_commands(tmp_path)
    app = create_app(_settings())
    call_count = 0

    def fake_run_single_turn_in_directory(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        return SimpleNamespace(
            tool_errors=[],
            text=f"Completed run {call_count}.",
            session_id=f"session-{call_count}",
        )

    with patch(
        "pbi_agent.web.session_manager.run_single_turn_in_directory",
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
    assert task_payload["stage"] == "done"
    assert task_payload["run_status"] == "completed"
    assert task_payload["session_id"] == "session-2"


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
            "pbi_agent.web.session_manager.run_single_turn_in_directory",
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


def test_session_stream_replays_state_events() -> None:
    with patch("pbi_agent.web.session_manager.run_session_loop", return_value=0):
        app = create_app(_settings())

        with TestClient(app) as client:
            response = client.post("/api/live-sessions", json={})
            assert response.status_code == 200
            live_session_id = response.json()["session"]["live_session_id"]

            with client.websocket_connect(
                f"/api/events/{live_session_id}"
            ) as websocket:
                events = [websocket.receive_json() for _ in range(3)]

    state_events = [event for event in events if event["type"] == "session_state"]
    assert state_events
    assert {event["payload"]["state"] for event in state_events}.issuperset(
        {"starting"}
    )
    assert {event["payload"]["state"] for event in state_events} & {"running", "ended"}


def test_session_creation_with_model_profile_exposes_runtime_binding(
    monkeypatch,
) -> None:
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
            id="analysis",
            name="Analysis",
            provider_id="openai-main",
            model="gpt-5.4-2026-03-05",
            reasoning_effort="xhigh",
        )
    )
    with patch("pbi_agent.web.session_manager.run_session_loop", return_value=0):
        app = create_app(_settings())

        with TestClient(app) as client:
            response = client.post(
                "/api/live-sessions",
                json={"profile_id": "analysis"},
            )
            assert response.status_code == 200
            payload = response.json()["session"]
            assert payload["profile_id"] == "analysis"
            assert payload["model"] == "gpt-5.4-2026-03-05"

            live_session_id = payload["live_session_id"]
            events = app.state.manager.get_event_stream(live_session_id).snapshot()

    runtime_events = [
        event for event in events if event["type"] == "session_runtime_updated"
    ]
    assert runtime_events
    assert runtime_events[0]["payload"]["profile_id"] == "analysis"
    assert runtime_events[0]["payload"]["model"] == "gpt-5.4-2026-03-05"


def test_session_input_profile_override_emits_runtime_update(monkeypatch) -> None:
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
            id="analysis",
            name="Analysis",
            provider_id="openai-main",
            model="gpt-5.4-2026-03-05",
            reasoning_effort="xhigh",
        )
    )
    queued_values: list[object] = []

    def fake_run_session_loop(_settings, display, *, resume_session_id=None):
        del _settings, resume_session_id
        queued_values.append(display.user_prompt())
        queued_values.append(display.user_prompt())
        return 0

    with patch("pbi_agent.web.session_manager.run_session_loop", fake_run_session_loop):
        app = create_app(_settings())

        with TestClient(app) as client:
            response = client.post("/api/live-sessions", json={})
            assert response.status_code == 200
            live_session_id = response.json()["session"]["live_session_id"]

            submit_response = client.post(
                f"/api/live-sessions/{live_session_id}/input",
                json={
                    "text": "hello",
                    "file_paths": [],
                    "image_paths": [],
                    "image_upload_ids": [],
                    "profile_id": "analysis",
                },
            )
            assert submit_response.status_code == 200
            events = app.state.manager.get_event_stream(live_session_id).snapshot()

    assert isinstance(queued_values[0], QueuedRuntimeChange)
    assert queued_values[1] == "hello"
    runtime_events = [
        event for event in events if event["type"] == "session_runtime_updated"
    ]
    assert runtime_events[-1]["payload"]["profile_id"] == "analysis"


def test_set_live_session_profile_emits_runtime_update(monkeypatch) -> None:
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
            id="analysis",
            name="Analysis",
            provider_id="openai-main",
            model="gpt-5.4-2026-03-05",
            reasoning_effort="xhigh",
        )
    )
    queued_values: list[object] = []

    def fake_run_session_loop(_settings, display, *, resume_session_id=None):
        del _settings, resume_session_id
        queued_values.append(display.user_prompt())
        queued_values.append(display.user_prompt())
        return 0

    with patch("pbi_agent.web.session_manager.run_session_loop", fake_run_session_loop):
        app = create_app(_settings())

        with TestClient(app) as client:
            response = client.post("/api/live-sessions", json={})
            assert response.status_code == 200
            live_session_id = response.json()["session"]["live_session_id"]

            update_response = client.put(
                f"/api/live-sessions/{live_session_id}/profile",
                json={"profile_id": "analysis"},
            )
            assert update_response.status_code == 200
            payload = update_response.json()["session"]
            assert payload["profile_id"] == "analysis"
            assert payload["model"] == "gpt-5.4-2026-03-05"

            events = app.state.manager.get_event_stream(live_session_id).snapshot()

    assert isinstance(queued_values[0], QueuedRuntimeChange)
    runtime_events = [
        event for event in events if event["type"] == "session_runtime_updated"
    ]
    assert runtime_events[-1]["payload"]["profile_id"] == "analysis"


def test_session_resume_uses_saved_session_runtime(monkeypatch, tmp_path) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv(SESSION_DB_PATH_ENV, str(tmp_path / "sessions.db"))
    monkeypatch.setenv("OPENAI_API_KEY", "env-openai-key")
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
    observed_runtime = None

    def fake_run_session_loop(_settings, display, *, resume_session_id=None):
        nonlocal observed_runtime
        del display, resume_session_id
        observed_runtime = _settings
        return 0

    with SessionStore(db_path=tmp_path / "sessions.db") as store:
        session_id = store.create_session(
            str(tmp_path),
            "openai",
            "gpt-5.4-2026-03-05",
            "saved session",
            provider_id="openai-main",
            profile_id="analysis",
        )

    with patch("pbi_agent.web.session_manager.run_session_loop", fake_run_session_loop):
        app = create_app(_settings())

        with TestClient(app) as client:
            response = client.post(
                "/api/live-sessions",
                json={"resume_session_id": session_id},
            )

    assert response.status_code == 200
    assert observed_runtime is not None
    assert observed_runtime.profile_id == "analysis"
    assert observed_runtime.provider_id == "openai-main"
    assert observed_runtime.settings.model == "gpt-5.4-2026-03-05"


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
            "item_id": "history-1",
            "role": "user",
            "content": "Hello",
            "file_paths": ["notes.md"],
            "image_attachments": [],
            "markdown": False,
            "historical": True,
            "created_at": payload["history_items"][0]["created_at"],
        },
        {
            "item_id": "history-2",
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


def test_create_live_session_rejects_unknown_resume_session() -> None:
    app = create_app(_settings())

    with TestClient(app) as client:
        response = client.post(
            "/api/live-sessions",
            json={"resume_session_id": "missing-session"},
        )

    assert response.status_code == 404


def test_create_live_session_reuses_active_live_session_for_saved_chat(
    tmp_path, monkeypatch
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv(SESSION_DB_PATH_ENV, str(tmp_path / "sessions.db"))

    def fake_run_session_loop(_settings, display, *, resume_session_id=None):
        del _settings, resume_session_id
        display.user_prompt()
        return 0

    with SessionStore(db_path=tmp_path / "sessions.db") as store:
        session_id = store.create_session(
            str(tmp_path),
            "openai",
            "gpt-5.4",
            "Saved session",
        )

    with patch("pbi_agent.web.session_manager.run_session_loop", fake_run_session_loop):
        app = create_app(_settings())

        with TestClient(app) as client:
            first_response = client.post(
                "/api/live-sessions",
                json={"resume_session_id": session_id},
            )
            second_response = client.post(
                "/api/live-sessions",
                json={"resume_session_id": session_id},
            )

    assert first_response.status_code == 200
    assert second_response.status_code == 200
    assert (
        first_response.json()["session"]["live_session_id"]
        == second_response.json()["session"]["live_session_id"]
    )


def test_session_stream_replays_session_identity_event() -> None:
    def fake_run_session_loop(_settings, display, *, resume_session_id=None):
        del _settings, resume_session_id
        display.bind_session("saved-session-1")
        return 0

    with patch("pbi_agent.web.session_manager.run_session_loop", fake_run_session_loop):
        app = create_app(_settings())

        with TestClient(app) as client:
            response = client.post("/api/live-sessions", json={})
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
    def fake_run_session_loop(_settings, display, *, resume_session_id=None):
        del _settings, resume_session_id
        display.user_prompt()
        return 0

    with patch("pbi_agent.web.session_manager.run_session_loop", fake_run_session_loop):
        app = create_app(_settings())

        with TestClient(app) as client:
            response = client.post("/api/live-sessions", json={})
            assert response.status_code == 200
            live_session_id = response.json()["session"]["live_session_id"]

            upload_response = client.post(
                f"/api/live-sessions/{live_session_id}/images",
                files={"files": ("chart.png", b"\x89PNG\r\n\x1a\n", "image/png")},
            )

    assert upload_response.status_code == 200
    payload = upload_response.json()
    assert len(payload["uploads"]) == 1
    assert payload["uploads"][0]["name"] == "chart.png"
    assert payload["uploads"][0]["mime_type"] == "image/png"
    assert payload["uploads"][0]["preview_url"].startswith(
        "/api/live-sessions/uploads/"
    )


def test_submit_session_input_accepts_uploaded_image_ids() -> None:
    def fake_run_session_loop(_settings, display, *, resume_session_id=None):
        del _settings, resume_session_id
        queued = display.user_prompt()
        assert isinstance(queued, QueuedInput)
        assert queued.text == ""
        assert len(queued.images) == 1
        assert queued.images[0].path == "chart.png"
        assert len(queued.image_attachments) == 1
        return 0

    with patch("pbi_agent.web.session_manager.run_session_loop", fake_run_session_loop):
        app = create_app(_settings())

        with TestClient(app) as client:
            response = client.post("/api/live-sessions", json={})
            assert response.status_code == 200
            live_session_id = response.json()["session"]["live_session_id"]

            upload_response = client.post(
                f"/api/live-sessions/{live_session_id}/images",
                files={"files": ("chart.png", b"\x89PNG\r\n\x1a\n", "image/png")},
            )
            assert upload_response.status_code == 200
            upload_id = upload_response.json()["uploads"][0]["upload_id"]

            submit_response = client.post(
                f"/api/live-sessions/{live_session_id}/input",
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


def test_submit_session_input_does_not_duplicate_workspace_image_mentions(
    tmp_path, monkeypatch
) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / "chart.png").write_bytes(b"\x89PNG\r\n\x1a\n")

    def fake_run_session_loop(_settings, display, *, resume_session_id=None):
        del _settings, resume_session_id
        queued = display.user_prompt()
        assert isinstance(queued, QueuedInput)
        assert queued.text == "Describe chart.png"
        assert queued.image_paths == []
        assert len(queued.images) == 1
        assert queued.images[0].path == "chart.png"
        assert len(queued.image_attachments) == 1
        return 0

    with patch("pbi_agent.web.session_manager.run_session_loop", fake_run_session_loop):
        app = create_app(_settings())

        with TestClient(app) as client:
            response = client.post("/api/live-sessions", json={})
            assert response.status_code == 200
            live_session_id = response.json()["session"]["live_session_id"]

            submit_response = client.post(
                f"/api/live-sessions/{live_session_id}/input",
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
            "pbi_agent.web.session_manager.create_browser_auth_callback_listener",
            side_effect=fake_create_browser_auth_callback_listener,
        ),
        patch("pbi_agent.web.session_manager.threading.Timer", side_effect=fake_timer),
        patch(
            "pbi_agent.web.session_manager.start_provider_browser_auth",
            side_effect=fake_start_browser_auth,
        ),
        patch(
            "pbi_agent.web.session_manager.complete_provider_browser_auth",
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
            "pbi_agent.web.session_manager.create_browser_auth_callback_listener",
            side_effect=fake_create_browser_auth_callback_listener,
        ),
        patch("pbi_agent.web.session_manager.threading.Timer", side_effect=fake_timer),
        patch(
            "pbi_agent.web.session_manager.start_provider_browser_auth",
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
            "pbi_agent.web.session_manager.create_browser_auth_callback_listener",
            side_effect=fake_create_browser_auth_callback_listener,
        ),
        patch("pbi_agent.web.session_manager.threading.Timer", side_effect=fake_timer),
        patch(
            "pbi_agent.web.session_manager.start_provider_browser_auth",
            side_effect=fake_start_browser_auth,
        ),
        patch(
            "pbi_agent.web.session_manager.complete_provider_browser_auth",
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
            "pbi_agent.web.session_manager.create_browser_auth_callback_listener",
            side_effect=fake_create_browser_auth_callback_listener,
        ),
        patch("pbi_agent.web.session_manager.threading.Timer", side_effect=fake_timer),
        patch(
            "pbi_agent.web.session_manager.start_provider_browser_auth",
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
            "pbi_agent.web.session_manager.start_provider_device_auth",
            side_effect=fake_start_device_auth,
        ),
        patch(
            "pbi_agent.web.session_manager.poll_provider_device_auth",
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
        == "https://chatgpt.com/backend-api/codex/models?client_version=0.99.0"
    )
    headers = {key.lower(): value for key, value in requests_seen[0].header_items()}
    assert headers["authorization"].startswith("Bearer ")
    assert headers["chatgpt-account-id"] == "acct_chatgpt"
    assert headers["originator"] == "opencode"
    assert headers["user-agent"].startswith("opencode/")


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


def test_live_session_list_and_detail_endpoints() -> None:
    def fake_run_session_loop(_settings, display, *, resume_session_id=None):
        del _settings, resume_session_id
        display.user_prompt()
        return 0

    with patch("pbi_agent.web.session_manager.run_session_loop", fake_run_session_loop):
        app = create_app(_settings())

        with TestClient(app) as client:
            create_response = client.post("/api/live-sessions", json={})
            assert create_response.status_code == 200
            live_session_id = create_response.json()["session"]["live_session_id"]

            list_response = client.get("/api/live-sessions")
            detail_response = client.get(f"/api/live-sessions/{live_session_id}")

    assert list_response.status_code == 200
    live_sessions = list_response.json()["live_sessions"]
    assert [item["live_session_id"] for item in live_sessions] == [live_session_id]
    assert detail_response.status_code == 200
    detail_payload = detail_response.json()
    assert detail_payload["live_session"]["live_session_id"] == live_session_id
    assert detail_payload["snapshot"]["live_session_id"] == live_session_id
    assert detail_payload["snapshot"]["last_event_seq"] >= 0


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


def test_request_new_session_endpoint_queues_new_session() -> None:
    queued_values: list[object] = []

    def fake_run_session_loop(_settings, display, *, resume_session_id=None):
        del _settings, resume_session_id
        queued_values.append(display.user_prompt())
        queued_values.append(display.user_prompt())
        return 0

    with patch("pbi_agent.web.session_manager.run_session_loop", fake_run_session_loop):
        app = create_app(_settings())

        with TestClient(app) as client:
            response = client.post("/api/live-sessions", json={})
            assert response.status_code == 200
            live_session_id = response.json()["session"]["live_session_id"]

            new_session_response = client.post(
                f"/api/live-sessions/{live_session_id}/new-session",
                json={},
            )

    assert new_session_response.status_code == 200
    assert queued_values[0] == NEW_SESSION_SENTINEL


def test_uploaded_session_image_route_returns_image_bytes() -> None:
    image_bytes = b"\x89PNG\r\n\x1a\n"

    def fake_run_session_loop(_settings, display, *, resume_session_id=None):
        del _settings, resume_session_id
        display.user_prompt()
        return 0

    with patch("pbi_agent.web.session_manager.run_session_loop", fake_run_session_loop):
        app = create_app(_settings())

        with TestClient(app) as client:
            response = client.post("/api/live-sessions", json={})
            assert response.status_code == 200
            live_session_id = response.json()["session"]["live_session_id"]

            upload_response = client.post(
                f"/api/live-sessions/{live_session_id}/images",
                files={"files": ("chart.png", image_bytes, "image/png")},
            )
            assert upload_response.status_code == 200
            preview_url = upload_response.json()["uploads"][0]["preview_url"]

            image_response = client.get(preview_url)

    assert image_response.status_code == 200
    assert image_response.headers["content-type"] == "image/png"
    assert image_response.content == image_bytes


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
