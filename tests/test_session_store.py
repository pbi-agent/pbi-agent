"""Tests for the SQLite session store."""

from __future__ import annotations

import time

import pytest

from pbi_agent.session_store import (
    KANBAN_RUN_STATUS_COMPLETED,
    KANBAN_STAGE_BACKLOG,
    KANBAN_STAGE_DONE,
    KANBAN_STAGE_PLAN,
    KANBAN_STAGE_REVIEW,
    KanbanStageConfigSpec,
    MessageImageAttachment,
    SessionStore,
)


def test_create_and_get_session(tmp_path) -> None:
    db = tmp_path / "sessions.db"
    with SessionStore(db_path=db) as store:
        sid = store.create_session("/home/user/project", "openai", "gpt-5", "hello")
        rec = store.get_session(sid)

    assert rec is not None
    assert rec.session_id == sid
    assert rec.directory == "/home/user/project"
    assert rec.provider == "openai"
    assert rec.model == "gpt-5"
    assert rec.title == "hello"
    assert rec.previous_id is None
    assert rec.total_tokens == 0
    assert rec.input_tokens == 0
    assert rec.output_tokens == 0
    assert rec.cost_usd == 0.0
    assert rec.created_at == rec.updated_at


def test_update_previous_id_and_title(tmp_path) -> None:
    db = tmp_path / "sessions.db"
    with SessionStore(db_path=db) as store:
        sid = store.create_session("/w", "xai", "grok-4", "")
        store.update_session(sid, previous_id="resp_42")
        rec = store.get_session(sid)
        assert rec is not None
        assert rec.previous_id == "resp_42"

        store.update_session(sid, title="My chat")
        rec = store.get_session(sid)
        assert rec is not None
        assert rec.title == "My chat"


def test_directory_scoped_listing(tmp_path) -> None:
    db = tmp_path / "sessions.db"
    with SessionStore(db_path=db) as store:
        store.create_session("/project-a", "openai", "gpt-5", "a1")
        store.create_session("/project-b", "xai", "grok-4", "b1")
        store.create_session("/project-a", "openai", "gpt-5", "a2")

        a_sessions = store.list_sessions("/project-a")
        b_sessions = store.list_sessions("/project-b")

    assert len(a_sessions) == 2
    assert len(b_sessions) == 1
    assert all(s.directory == "/project-a" for s in a_sessions)
    assert b_sessions[0].directory == "/project-b"


def test_directory_keys_are_lowercased_and_case_insensitive(tmp_path) -> None:
    db = tmp_path / "sessions.db"
    with SessionStore(db_path=db) as store:
        session_id = store.create_session("/Project-A/Subdir", "openai", "gpt-5", "a1")
        record = store.get_session(session_id)
        sessions = store.list_sessions("/PROJECT-A/SUBDIR")

    assert record is not None
    assert record.directory == "/project-a/subdir"
    assert [session.session_id for session in sessions] == [session_id]


def test_ordering_by_updated_at(tmp_path) -> None:
    db = tmp_path / "sessions.db"
    with SessionStore(db_path=db) as store:
        s1 = store.create_session("/w", "openai", "gpt-5", "first")
        time.sleep(0.01)
        s2 = store.create_session("/w", "openai", "gpt-5", "second")
        time.sleep(0.01)

        # Update s1 so it becomes most recent
        store.update_session(s1, title="updated first")

        sessions = store.list_sessions("/w")

    assert sessions[0].session_id == s1
    assert sessions[1].session_id == s2


def test_limit_respected(tmp_path) -> None:
    db = tmp_path / "sessions.db"
    with SessionStore(db_path=db) as store:
        for i in range(10):
            store.create_session("/w", "openai", "gpt-5", f"session-{i}")

        sessions = store.list_sessions("/w", limit=3)

    assert len(sessions) == 3


def test_nonexistent_session_returns_none(tmp_path) -> None:
    db = tmp_path / "sessions.db"
    with SessionStore(db_path=db) as store:
        result = store.get_session("does-not-exist")

    assert result is None


def test_list_all_sessions(tmp_path) -> None:
    db = tmp_path / "sessions.db"
    with SessionStore(db_path=db) as store:
        store.create_session("/a", "openai", "gpt-5", "a1")
        store.create_session("/b", "xai", "grok-4", "b1")

        all_sessions = store.list_all_sessions()

    assert len(all_sessions) == 2


def test_update_usage_fields(tmp_path) -> None:
    db = tmp_path / "sessions.db"
    with SessionStore(db_path=db) as store:
        sid = store.create_session("/w", "openai", "gpt-5", "usage test")
        store.update_session(
            sid,
            total_tokens=1500,
            input_tokens=1000,
            output_tokens=500,
            cost_usd=0.0375,
        )
        rec = store.get_session(sid)

    assert rec is not None
    assert rec.total_tokens == 1500
    assert rec.input_tokens == 1000
    assert rec.output_tokens == 500
    assert rec.cost_usd == pytest.approx(0.0375)


def test_usage_accumulates_across_updates(tmp_path) -> None:
    db = tmp_path / "sessions.db"
    with SessionStore(db_path=db) as store:
        sid = store.create_session("/w", "openai", "gpt-5", "accum")
        store.update_session(
            sid, total_tokens=100, input_tokens=60, output_tokens=40, cost_usd=0.01
        )
        store.update_session(
            sid, total_tokens=300, input_tokens=180, output_tokens=120, cost_usd=0.03
        )
        rec = store.get_session(sid)

    assert rec is not None
    # The store overwrites (not accumulates) — session.py passes cumulative session_usage
    assert rec.total_tokens == 300
    assert rec.cost_usd == pytest.approx(0.03)


def test_add_and_list_messages(tmp_path) -> None:
    db = tmp_path / "sessions.db"
    with SessionStore(db_path=db) as store:
        sid = store.create_session("/w", "openai", "gpt-5", "msg test")
        store.add_message(sid, "user", "Hello")
        store.add_message(sid, "assistant", "Hi there!")
        store.add_message(sid, "user", "How are you?")

        msgs = store.list_messages(sid)

    assert len(msgs) == 3
    assert msgs[0].role == "user"
    assert msgs[0].content == "Hello"
    assert msgs[1].role == "assistant"
    assert msgs[1].content == "Hi there!"
    assert msgs[2].role == "user"
    assert msgs[2].content == "How are you?"
    # Ordered by id ASC
    assert msgs[0].id < msgs[1].id < msgs[2].id


def test_add_and_list_messages_preserve_image_attachments(tmp_path) -> None:
    db = tmp_path / "sessions.db"
    attachment = MessageImageAttachment(
        upload_id="upload-1",
        name="chart.png",
        mime_type="image/png",
        byte_count=8,
        preview_url="/api/chat/uploads/upload-1",
    )

    with SessionStore(db_path=db) as store:
        sid = store.create_session("/w", "openai", "gpt-5", "msg test")
        store.add_message(
            sid, "user", "Here is a chart", image_attachments=[attachment]
        )
        msgs = store.list_messages(sid)

    assert len(msgs) == 1
    assert msgs[0].image_attachments == [attachment]


def test_add_and_list_messages_preserve_file_paths(tmp_path) -> None:
    db = tmp_path / "sessions.db"

    with SessionStore(db_path=db) as store:
        sid = store.create_session("/w", "openai", "gpt-5", "msg test")
        store.add_message(
            sid,
            "user",
            "Check these files",
            file_paths=["notes.md", "docs/spec.md"],
        )
        msgs = store.list_messages(sid)

    assert len(msgs) == 1
    assert msgs[0].file_paths == ["notes.md", "docs/spec.md"]


def test_messages_scoped_to_session(tmp_path) -> None:
    db = tmp_path / "sessions.db"
    with SessionStore(db_path=db) as store:
        s1 = store.create_session("/w", "openai", "gpt-5", "s1")
        s2 = store.create_session("/w", "openai", "gpt-5", "s2")
        store.add_message(s1, "user", "msg for s1")
        store.add_message(s2, "user", "msg for s2")
        store.add_message(s2, "assistant", "reply for s2")

        msgs1 = store.list_messages(s1)
        msgs2 = store.list_messages(s2)

    assert len(msgs1) == 1
    assert msgs1[0].content == "msg for s1"
    assert len(msgs2) == 2


def test_list_messages_empty_session(tmp_path) -> None:
    db = tmp_path / "sessions.db"
    with SessionStore(db_path=db) as store:
        sid = store.create_session("/w", "openai", "gpt-5", "empty")
        msgs = store.list_messages(sid)

    assert msgs == []


def test_delete_session_removes_session_and_messages(tmp_path) -> None:
    db = tmp_path / "sessions.db"
    with SessionStore(db_path=db) as store:
        sid = store.create_session("/w", "openai", "gpt-5", "delete me")
        store.add_message(sid, "user", "hello")
        store.add_message(sid, "assistant", "hi")

        deleted = store.delete_session(sid)

        rec = store.get_session(sid)
        msgs = store.list_messages(sid)

    assert deleted is True
    assert rec is None
    assert msgs == []


def test_create_and_list_run_sessions(tmp_path) -> None:
    db = tmp_path / "sessions.db"
    with SessionStore(db_path=db) as store:
        session_id = store.create_session("/w", "openai", "gpt-5", "trace me")
        parent_run_id = store.create_run_session(
            session_id=session_id,
            agent_name="main",
            agent_type="chat_turn",
            provider="openai",
            provider_id="default",
            profile_id="analysis",
            model="gpt-5",
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
            model="gpt-5-mini",
        )
        store.update_run_session(
            child_run_id,
            status="completed",
            total_duration_ms=42,
            total_tool_calls=1,
            total_api_calls=2,
            error_count=0,
        )

        runs = store.list_run_sessions(session_id)

    assert [run.run_session_id for run in runs] == [parent_run_id, child_run_id]
    assert runs[1].parent_run_session_id == parent_run_id
    assert runs[1].status == "completed"
    assert runs[1].total_duration_ms == 42


def test_add_and_list_observability_events(tmp_path) -> None:
    db = tmp_path / "sessions.db"
    with SessionStore(db_path=db) as store:
        session_id = store.create_session("/w", "openai", "gpt-5", "trace me")
        run_session_id = store.create_run_session(
            session_id=session_id,
            agent_name="main",
            agent_type="single_turn",
            provider="openai",
            provider_id=None,
            profile_id=None,
            model="gpt-5",
        )
        store.add_observability_event(
            run_session_id=run_session_id,
            session_id=session_id,
            step_index=0,
            event_type="run_start",
            request_config={"provider": "openai"},
        )
        store.add_observability_event(
            run_session_id=run_session_id,
            session_id=session_id,
            step_index=1,
            event_type="tool_call",
            tool_name="shell",
            tool_call_id="call_1",
            tool_input={"command": "pwd"},
            tool_output={"ok": True},
            success=True,
        )

        events = store.list_observability_events(run_session_id=run_session_id)

    assert [event.event_type for event in events] == ["run_start", "tool_call"]
    assert events[1].tool_name == "shell"
    assert events[1].tool_call_id == "call_1"
    assert events[1].tool_input_json == '{"command": "pwd"}'


def test_delete_session_removes_observability_records(tmp_path) -> None:
    db = tmp_path / "sessions.db"
    with SessionStore(db_path=db) as store:
        session_id = store.create_session("/w", "openai", "gpt-5", "trace me")
        run_session_id = store.create_run_session(
            session_id=session_id,
            agent_name="main",
            agent_type="single_turn",
            provider="openai",
            provider_id=None,
            profile_id=None,
            model="gpt-5",
        )
        store.add_observability_event(
            run_session_id=run_session_id,
            session_id=session_id,
            step_index=0,
            event_type="run_start",
        )

        assert store.delete_session(session_id) is True

        assert store.get_run_session(run_session_id) is None
        assert store.list_observability_events(run_session_id=run_session_id) == []


def test_create_and_list_kanban_tasks(tmp_path) -> None:
    db = tmp_path / "sessions.db"
    with SessionStore(db_path=db) as store:
        task = store.create_kanban_task(
            directory="/w",
            title="Task A",
            prompt="Investigate report layout",
        )
        tasks = store.list_kanban_tasks("/w")

    assert len(tasks) == 1
    assert tasks[0].task_id == task.task_id
    assert tasks[0].stage == KANBAN_STAGE_BACKLOG


def test_default_kanban_stage_configs_are_neutral(tmp_path) -> None:
    db = tmp_path / "sessions.db"
    with SessionStore(db_path=db) as store:
        stages = store.list_kanban_stage_configs("/w")

    assert [stage.stage_id for stage in stages] == [
        KANBAN_STAGE_BACKLOG,
        KANBAN_STAGE_DONE,
    ]
    assert [stage.name for stage in stages] == ["Backlog", "Done"]
    assert all(stage.command_id is None for stage in stages)
    assert all(stage.auto_start is False for stage in stages)


def test_move_kanban_task_reorders_within_stage(tmp_path) -> None:
    db = tmp_path / "sessions.db"
    with SessionStore(db_path=db) as store:
        first = store.create_kanban_task(directory="/w", title="A", prompt="One")
        second = store.create_kanban_task(directory="/w", title="B", prompt="Two")
        third = store.create_kanban_task(directory="/w", title="C", prompt="Three")

        moved = store.move_kanban_task(
            first.task_id, stage=KANBAN_STAGE_BACKLOG, position=2
        )
        tasks = [
            task
            for task in store.list_kanban_tasks("/w")
            if task.stage == KANBAN_STAGE_BACKLOG
        ]

    assert moved is not None
    assert [task.title for task in tasks] == ["B", "C", "A"]
    assert [task.position for task in tasks] == [0, 1, 2]
    assert second.task_id != third.task_id


def test_set_kanban_task_result_preserves_stage(tmp_path) -> None:
    db = tmp_path / "sessions.db"
    with SessionStore(db_path=db) as store:
        store.replace_kanban_stage_configs(
            "/w",
            stages=[
                KanbanStageConfigSpec(stage_id="backlog", name="Backlog"),
                KanbanStageConfigSpec(stage_id="plan", name="Plan"),
                KanbanStageConfigSpec(stage_id="done", name="Done"),
            ],
        )
        task = store.create_kanban_task(
            directory="/w",
            title="Planning",
            prompt="Draft the task",
            stage=KANBAN_STAGE_PLAN,
        )
        store.set_kanban_task_running(task.task_id)
        updated = store.set_kanban_task_result(
            task.task_id,
            run_status=KANBAN_RUN_STATUS_COMPLETED,
            summary="Finished successfully.",
            session_id="session-123",
        )

    assert updated is not None
    assert updated.stage == KANBAN_STAGE_PLAN
    assert updated.run_status == KANBAN_RUN_STATUS_COMPLETED
    assert updated.session_id == "session-123"


def test_replace_kanban_stage_configs_reorders_task_listing(tmp_path) -> None:
    db = tmp_path / "sessions.db"
    with SessionStore(db_path=db) as store:
        store.replace_kanban_stage_configs(
            "/w",
            stages=[
                KanbanStageConfigSpec(stage_id="backlog", name="Backlog"),
                KanbanStageConfigSpec(stage_id="plan", name="Plan"),
                KanbanStageConfigSpec(stage_id="review", name="Review"),
                KanbanStageConfigSpec(stage_id="done", name="Done"),
            ],
        )
        store.create_kanban_task(
            directory="/w",
            title="Backlog Task",
            prompt="Backlog",
            stage=KANBAN_STAGE_BACKLOG,
        )
        store.create_kanban_task(
            directory="/w",
            title="Plan Task",
            prompt="Plan",
            stage=KANBAN_STAGE_PLAN,
        )
        store.create_kanban_task(
            directory="/w",
            title="Review Task",
            prompt="Review",
            stage=KANBAN_STAGE_REVIEW,
        )
        store.replace_kanban_stage_configs(
            "/w",
            stages=[
                KanbanStageConfigSpec(stage_id="review", name="Review"),
                KanbanStageConfigSpec(stage_id="backlog", name="Backlog"),
                KanbanStageConfigSpec(stage_id="plan", name="Plan"),
            ],
        )
        tasks = store.list_kanban_tasks("/w")

    assert [task.title for task in tasks] == [
        "Backlog Task",
        "Review Task",
        "Plan Task",
    ]


def test_get_dashboard_stats_returns_aggregated_data(tmp_path) -> None:
    db = tmp_path / "sessions.db"
    with SessionStore(db_path=db) as store:
        session_id = store.create_session("/w", "openai", "gpt-5", "dashboard")
        run_id_1 = store.create_run_session(
            session_id=session_id,
            agent_name="main",
            agent_type="chat_turn",
            provider="openai",
            provider_id=None,
            profile_id=None,
            model="gpt-5",
        )
        store.update_run_session(
            run_id_1,
            status="completed",
            input_tokens=200,
            output_tokens=100,
            estimated_cost_usd=0.02,
            total_tool_calls=5,
            total_api_calls=3,
            error_count=0,
            total_duration_ms=500,
        )
        run_id_2 = store.create_run_session(
            session_id=session_id,
            agent_name="sub",
            agent_type="reviewer",
            provider="anthropic",
            provider_id=None,
            profile_id=None,
            model="claude-4",
        )
        store.update_run_session(
            run_id_2,
            status="failed",
            input_tokens=50,
            output_tokens=10,
            estimated_cost_usd=0.005,
            error_count=1,
            total_duration_ms=100,
        )

        stats = store.get_dashboard_stats(directory="/w")

    overview = stats["overview"]
    assert overview["total_sessions"] == 1
    assert overview["total_runs"] == 2
    assert overview["total_input_tokens"] == 250
    assert overview["total_output_tokens"] == 110
    assert overview["completed_runs"] == 1
    assert overview["failed_runs"] == 1

    breakdown = stats["breakdown"]
    assert len(breakdown) == 2
    providers = {row["provider"] for row in breakdown}
    assert providers == {"openai", "anthropic"}

    daily = stats["daily"]
    assert len(daily) >= 1


def test_list_all_run_sessions_with_filters(tmp_path) -> None:
    db = tmp_path / "sessions.db"
    with SessionStore(db_path=db) as store:
        session_id = store.create_session("/w", "openai", "gpt-5", "filter test")
        for i in range(4):
            run_id = store.create_run_session(
                session_id=session_id,
                agent_name="main",
                agent_type="chat_turn",
                provider="openai" if i < 3 else "anthropic",
                provider_id=None,
                profile_id=None,
                model="gpt-5" if i < 3 else "claude-4",
                status="completed" if i % 2 == 0 else "failed",
            )
            store.update_run_session(run_id, input_tokens=(i + 1) * 100)

        # All runs
        all_runs, total = store.list_all_run_sessions(directory="/w")
        assert total == 4

        # Paginated
        page, total = store.list_all_run_sessions(directory="/w", limit=2, offset=0)
        assert len(page) == 2
        assert total == 4

        # Filter by status
        completed, total = store.list_all_run_sessions(
            directory="/w", status="completed"
        )
        assert total == 2

        # Filter by provider
        anthropic_runs, total = store.list_all_run_sessions(
            directory="/w", provider="anthropic"
        )
        assert total == 1
        assert anthropic_runs[0]["model"] == "claude-4"

        # Session title is included
        assert all_runs[0]["session_title"] == "filter test"
