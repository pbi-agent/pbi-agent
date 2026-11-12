from __future__ import annotations

from types import SimpleNamespace
from typing import Any
from unittest.mock import Mock

from pbi_agent.agent.session.history import _create_session
from pbi_agent.config import ResolvedRuntime
from pbi_agent.session_store import SessionStore
from pbi_agent.web.session.headless import HeadlessSessionChannel
from pbi_agent.web.session.saved_sessions import SavedSessionsMixin
from pbi_agent.web.session.serializers import _web_event_from_record


def _runtime() -> ResolvedRuntime:
    settings = Mock(
        verbose=False,
        provider="openai",
        model="gpt-5",
        reasoning_effort="medium",
        compact_threshold=200000,
    )
    return ResolvedRuntime(settings=settings, provider_id="p", profile_id="m")


def _fake_turn(runtime: ResolvedRuntime):
    def turn(display: Any) -> Any:
        with SessionStore() as store:
            session_id = _create_session(store, runtime, title="t")
        display.bind_session(session_id)
        display.render_user_message("hello")
        display.function_start(1)
        display.function_result(
            "read_web_url", True, call_id="c1", arguments={"url": "x"}, result="ok"
        )
        display.tool_group_end()
        display.render_markdown("done")
        return SimpleNamespace(session_id=session_id, tool_errors=False)

    return turn


def test_cli_channel_persists_web_session_structure() -> None:
    runtime = _runtime()
    renderer = Mock()
    channel = HeadlessSessionChannel(runtime, renderer=renderer)

    outcome = channel.run(_fake_turn(runtime))

    with SessionStore() as store:
        runs = store.list_web_session_runs(outcome.session_id)
        assert len(runs) == 1
        run = runs[0]
        assert run.status == "completed"
        events = store.list_observability_events(run_session_id=run.run_session_id)
    web_events = sorted(
        (
            event
            for record in events
            if (event := _web_event_from_record(record)) is not None
        ),
        key=lambda event: int(event["seq"]),
    )
    web_types = [event["type"] for event in web_events]
    assert "tool_group_added" in web_types
    assert web_types[-1] == "session_state"
    renderer.function_result.assert_called_once()

    manager = SavedSessionsMixin.__new__(SavedSessionsMixin)
    vars(manager).update(
        _directory_key=channel._directory_key,
        _find_live_session_for_saved_session=lambda _sid: None,
    )
    detail: dict[str, Any] = manager.get_session_detail(outcome.session_id)
    kinds = [item.get("kind") for item in detail["timeline"]["items"]]
    assert "tool_group" in kinds
