"""Tests for the SQLite session store."""

from __future__ import annotations

import time

import pytest

from pbi_agent.session_store import SessionStore


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
