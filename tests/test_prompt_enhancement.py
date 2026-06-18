from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

from fastapi.testclient import TestClient
import pytest

from pbi_agent.config import ResolvedRuntime, Settings
from pbi_agent.models.messages import CompletedResponse, TokenUsage
from pbi_agent.observability import RunTracer
from pbi_agent.session_store import SESSION_DB_PATH_ENV, SessionStore
from pbi_agent.web.serve import create_app
import pbi_agent.web.session.prompt_enhancement as prompt_enhancement_module


def _settings() -> Settings:
    return Settings(api_key="test-key", provider="openai", model="gpt-5.4")


class _FakeProvider:
    def __init__(self, settings: Settings, calls: dict[str, Any]) -> None:
        self.settings = settings
        self._calls = calls

    def request_turn(
        self,
        *,
        user_input: Any = None,
        instructions: str | None = None,
        session_id: str | None = None,
        display: Any,
        session_usage: TokenUsage,
        turn_usage: TokenUsage,
        tracer: RunTracer | None = None,
        **_: Any,
    ) -> CompletedResponse:
        self._calls["request"] = {
            "user_input": user_input,
            "instructions": instructions,
            "session_id": session_id,
        }
        usage = TokenUsage(
            input_tokens=7,
            output_tokens=3,
            model=self.settings.model,
        )
        session_usage.add(usage)
        turn_usage.add(usage)
        display.session_usage(session_usage)
        if tracer is not None:
            tracer.log_model_call(
                provider=self.settings.provider,
                model=self.settings.model,
                url="https://example.test/model",
                request_config={},
                request_payload={},
                response_payload={},
                duration_ms=1,
                prompt_tokens=7,
                completion_tokens=3,
                total_tokens=10,
                status_code=200,
                success=True,
            )
        return CompletedResponse(
            response_id="resp-enhance",
            text="Improved prompt with @file and $skill",
            usage=usage,
        )


def _install_fake_provider(
    monkeypatch: pytest.MonkeyPatch,
) -> dict[str, Any]:
    calls: dict[str, Any] = {}

    @contextmanager
    def fake_open_runtime_provider(
        runtime: ResolvedRuntime,
        **kwargs: Any,
    ) -> Iterator[_FakeProvider]:
        calls["open"] = {"runtime": runtime, **kwargs}
        yield _FakeProvider(runtime.settings, calls)

    monkeypatch.setattr(
        prompt_enhancement_module,
        "open_runtime_provider",
        fake_open_runtime_provider,
    )
    return calls


@pytest.mark.parametrize("text", ["", "   ", "/refine this", "  /cmd", "!ls", " !pwd"])
def test_prompt_enhancement_rejects_empty_command_and_shell_drafts(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
    text: str,
) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    monkeypatch.chdir(workspace)
    monkeypatch.setenv(SESSION_DB_PATH_ENV, str(tmp_path / "sessions.db"))
    calls = _install_fake_provider(monkeypatch)

    app = create_app(_settings())
    with TestClient(app) as client:
        response = client.post("/api/prompt/enhance", json={"text": text})

    assert response.status_code == 400
    assert calls == {}


def test_prompt_enhancement_uses_session_runtime_without_tools_and_records_usage(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    monkeypatch.chdir(workspace)
    monkeypatch.setenv(SESSION_DB_PATH_ENV, str(tmp_path / "sessions.db"))
    calls = _install_fake_provider(monkeypatch)

    with SessionStore() as store:
        session_id = store.create_session(
            str(workspace),
            "xai",
            "grok-4",
            "Saved session",
            provider_id="xai-main",
        )
        store.add_message(session_id, "user", "Last user with @file")
        store.add_message(session_id, "assistant", "Last assistant with $skill")

    app = create_app(_settings())
    with TestClient(app) as client:
        response = client.post(
            "/api/prompt/enhance",
            json={
                "session_id": session_id,
                "text": "rough draft using @file and $skill",
            },
        )
        detail = client.get(f"/api/sessions/{session_id}").json()
        search = client.get("/api/sessions", params={"q": "rough draft using"}).json()
        sessions = client.get("/api/sessions").json()["sessions"]

    assert response.status_code == 200
    payload = response.json()
    assert payload["text"] == "Improved prompt with @file and $skill"
    assert payload["session"]["total_tokens"] == 10
    assert payload["session"]["input_tokens"] == 7
    assert payload["session"]["output_tokens"] == 3

    open_call = calls["open"]
    runtime = open_call["runtime"]
    assert runtime.settings.provider == "xai"
    assert runtime.settings.model == "grok-4"
    assert runtime.settings.allowed_tools == ()
    assert runtime.tool_availability_overridden is True
    assert open_call["tool_catalog"].names() == []
    assert open_call["tool_availability_overridden"] is True
    assert "concise, actionable instruction" in open_call["system_prompt"]
    assert "Ensure all composer tokens" in open_call["system_prompt"]

    request = calls["request"]
    assert request["instructions"] is None
    assert request["session_id"] == session_id
    prompt_input = request["user_input"].text
    assert "Turn the current composer draft" in prompt_input
    assert "Last user with @file" in prompt_input
    assert "Last assistant with $skill" in prompt_input
    assert "rough draft using @file and $skill" in prompt_input

    with SessionStore() as store:
        record = store.get_session(session_id)
        assert record is not None
        assert record.total_tokens == 10
        assert record.input_tokens == 7
        assert record.output_tokens == 3
        messages = store.list_messages(session_id)
        runs = store.list_run_sessions(session_id)

    assert [message.content for message in messages] == [
        "Last user with @file",
        "Last assistant with $skill",
    ]
    assert detail["history_items"][0]["content"] == "Last user with @file"
    assert detail["history_items"][1]["content"] == "Last assistant with $skill"
    assert search["sessions"] == []
    assert sessions[0]["status"] == "idle"
    assert len(runs) == 1
    assert runs[0].agent_type == "prompt_enhancement"
    assert runs[0].input_tokens == 7
    assert runs[0].output_tokens == 3
    assert runs[0].total_api_calls == 1
    assert runs[0].total_tool_calls == 0


def test_prompt_enhancement_without_session_uses_default_runtime(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    monkeypatch.chdir(workspace)
    monkeypatch.setenv(SESSION_DB_PATH_ENV, str(tmp_path / "sessions.db"))
    calls = _install_fake_provider(monkeypatch)

    app = create_app(_settings())
    with TestClient(app) as client:
        response = client.post(
            "/api/prompt/enhance",
            json={"text": "please make this clearer"},
        )

    assert response.status_code == 200
    assert response.json()["session"] is None
    runtime = calls["open"]["runtime"]
    assert runtime.settings.provider == "openai"
    assert runtime.settings.model == "gpt-5.4"
    with SessionStore() as store:
        assert store.list_all_sessions() == []
