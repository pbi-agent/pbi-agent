from __future__ import annotations

import asyncio
from io import StringIO
from pathlib import Path
import time
from types import SimpleNamespace
from unittest.mock import patch

from fastapi.testclient import TestClient
from rich.console import Console

from pbi_agent.agent.session import NEW_CHAT_SENTINEL
from pbi_agent.branding import PBI_AGENT_NAME, PBI_AGENT_TAGLINE
from pbi_agent.cli import build_parser
from pbi_agent.config import (
    ModelProfileConfig,
    ProviderConfig,
    Settings,
    create_model_profile_config,
    create_provider_config,
    delete_model_profile_config,
)
from pbi_agent.session_store import SESSION_DB_PATH_ENV, SessionStore
from pbi_agent.display.protocol import QueuedInput, QueuedRuntimeChange
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


def test_web_server_prints_banner_and_starts_uvicorn() -> None:
    server = PBIWebServer(settings=_settings(), port=9001)
    output = StringIO()
    server.console = Console(file=output, width=80, highlight=False)

    with patch("pbi_agent.web.server_runtime.uvicorn.Server.run") as mock_run:
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
        assert provider_payload["provider"]["secret_source"] == "env_var"
        assert provider_payload["provider"]["has_secret"] is True
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
            "Saved chat",
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
    assert mock_run.call_args.args[0] == "/plan Investigate"


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
                events = [websocket.receive_json() for _ in range(3)]

    state_events = [event for event in events if event["type"] == "session_state"]
    assert state_events
    assert {event["payload"]["state"] for event in state_events}.issuperset(
        {"starting"}
    )
    assert {event["payload"]["state"] for event in state_events} & {"running", "ended"}


def test_chat_session_creation_with_model_profile_exposes_runtime_binding(
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
    with patch("pbi_agent.web.session_manager.run_chat_loop", return_value=0):
        app = create_app(_settings())

        with TestClient(app) as client:
            response = client.post(
                "/api/chat/session",
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


def test_chat_input_profile_override_emits_runtime_update(monkeypatch) -> None:
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

    def fake_run_chat_loop(_settings, display, *, resume_session_id=None):
        del _settings, resume_session_id
        queued_values.append(display.user_prompt())
        queued_values.append(display.user_prompt())
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


def test_set_chat_session_profile_emits_runtime_update(monkeypatch) -> None:
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

    def fake_run_chat_loop(_settings, display, *, resume_session_id=None):
        del _settings, resume_session_id
        queued_values.append(display.user_prompt())
        queued_values.append(display.user_prompt())
        return 0

    with patch("pbi_agent.web.session_manager.run_chat_loop", fake_run_chat_loop):
        app = create_app(_settings())

        with TestClient(app) as client:
            response = client.post("/api/chat/session", json={})
            assert response.status_code == 200
            live_session_id = response.json()["session"]["live_session_id"]

            update_response = client.put(
                f"/api/chat/session/{live_session_id}/profile",
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


def test_chat_session_resume_uses_saved_session_runtime(monkeypatch, tmp_path) -> None:
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

    def fake_run_chat_loop(_settings, display, *, resume_session_id=None):
        nonlocal observed_runtime
        del display, resume_session_id
        observed_runtime = _settings
        return 0

    with SessionStore(db_path=tmp_path / "sessions.db") as store:
        session_id = store.create_session(
            str(tmp_path),
            "openai",
            "gpt-5.4-2026-03-05",
            "saved chat",
            provider_id="openai-main",
            profile_id="analysis",
        )

    with patch("pbi_agent.web.session_manager.run_chat_loop", fake_run_chat_loop):
        app = create_app(_settings())

        with TestClient(app) as client:
            response = client.post(
                "/api/chat/session",
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
            "Saved chat",
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


def test_get_session_detail_returns_not_found_for_unknown_session() -> None:
    app = create_app(_settings())

    with TestClient(app) as client:
        response = client.get("/api/sessions/missing-session")

    assert response.status_code == 404


def test_create_chat_session_rejects_unknown_resume_session() -> None:
    app = create_app(_settings())

    with TestClient(app) as client:
        response = client.post(
            "/api/chat/session",
            json={"resume_session_id": "missing-session"},
        )

    assert response.status_code == 404


def test_create_chat_session_reuses_active_live_session_for_saved_chat(
    tmp_path, monkeypatch
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv(SESSION_DB_PATH_ENV, str(tmp_path / "sessions.db"))

    def fake_run_chat_loop(_settings, display, *, resume_session_id=None):
        del _settings, resume_session_id
        display.user_prompt()
        return 0

    with SessionStore(db_path=tmp_path / "sessions.db") as store:
        session_id = store.create_session(
            str(tmp_path),
            "openai",
            "gpt-5.4",
            "Saved chat",
        )

    with patch("pbi_agent.web.session_manager.run_chat_loop", fake_run_chat_loop):
        app = create_app(_settings())

        with TestClient(app) as client:
            first_response = client.post(
                "/api/chat/session",
                json={"resume_session_id": session_id},
            )
            second_response = client.post(
                "/api/chat/session",
                json={"resume_session_id": session_id},
            )

    assert first_response.status_code == 200
    assert second_response.status_code == 200
    assert (
        first_response.json()["session"]["live_session_id"]
        == second_response.json()["session"]["live_session_id"]
    )


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
            "Other provider chat",
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
                "responses_url": None,
                "generic_api_url": None,
                "secret_source": "env_var",
                "secret_env_var": "OPENAI_API_KEY",
                "has_secret": True,
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


def test_sessions_endpoint_lists_saved_sessions(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv(SESSION_DB_PATH_ENV, str(tmp_path / "sessions.db"))
    app = create_app(_settings())

    with SessionStore(db_path=tmp_path / "sessions.db") as store:
        first_session_id = store.create_session(
            str(tmp_path),
            "openai",
            "gpt-5.4",
            "First chat",
        )
        second_session_id = store.create_session(
            str(tmp_path),
            "xai",
            "grok-4",
            "Second chat",
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
    def fake_run_chat_loop(_settings, display, *, resume_session_id=None):
        del _settings, resume_session_id
        display.user_prompt()
        return 0

    with patch("pbi_agent.web.session_manager.run_chat_loop", fake_run_chat_loop):
        app = create_app(_settings())

        with TestClient(app) as client:
            create_response = client.post("/api/chat/session", json={})
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


def test_request_new_chat_endpoint_queues_new_chat() -> None:
    queued_values: list[object] = []

    def fake_run_chat_loop(_settings, display, *, resume_session_id=None):
        del _settings, resume_session_id
        queued_values.append(display.user_prompt())
        queued_values.append(display.user_prompt())
        return 0

    with patch("pbi_agent.web.session_manager.run_chat_loop", fake_run_chat_loop):
        app = create_app(_settings())

        with TestClient(app) as client:
            response = client.post("/api/chat/session", json={})
            assert response.status_code == 200
            live_session_id = response.json()["session"]["live_session_id"]

            new_chat_response = client.post(
                f"/api/chat/session/{live_session_id}/new-chat",
                json={},
            )

    assert new_chat_response.status_code == 200
    assert queued_values[0] == NEW_CHAT_SENTINEL


def test_uploaded_chat_image_route_returns_image_bytes() -> None:
    image_bytes = b"\x89PNG\r\n\x1a\n"

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
        api_not_found_response = client.get("/api/not-found")
        stream_guard_response = client.get("/app")

    assert index_response.status_code == 200
    assert "text/html" in index_response.headers["content-type"]
    assert fallback_response.status_code == 200
    assert "text/html" in fallback_response.headers["content-type"]
    assert favicon_ico_response.status_code == 200
    assert favicon_ico_response.headers["content-type"] == "image/png"
    assert favicon_png_response.status_code == 200
    assert favicon_png_response.headers["content-type"] == "image/png"
    assert logo_response.status_code == 200
    assert logo_response.headers["content-type"] == "image/png"
    assert api_not_found_response.status_code == 404
    assert stream_guard_response.status_code == 404
