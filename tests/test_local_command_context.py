from unittest.mock import Mock

import pytest

from pbi_agent.agent.conversation_context import model_context_messages
from pbi_agent.agent.session.compaction import (
    _rewrite_compacted_context,
    _split_messages_for_compaction,
    active_context_messages,
)
from pbi_agent.agent.session.history import (
    refresh_provider_history_from_store,
    resume_session,
)
from pbi_agent.agent.session.subagents import build_parent_context_snapshot
from pbi_agent.agent.session.shared import (
    COMPACTION_MARKER,
    COMPACTION_SUMMARY_PREFIX,
)
from pbi_agent.config import ResolvedRuntime, Settings
from pbi_agent.models.messages import TokenUsage
from pbi_agent.providers.base import Provider
from pbi_agent.session_store import MessageRecord, SessionStore
from pbi_agent.web.session.prompt_enhancement import _prompt_enhancement_user_input


def _messages(
    *turns: tuple[str, str], local_indexes: tuple[int, ...] = ()
) -> list[MessageRecord]:
    return [
        MessageRecord(
            id=index,
            session_id="session",
            role=role,
            content=content,
            created_at="2026-09-10T00:00:00Z",
            is_local_command=index in local_indexes,
        )
        for index, (role, content) in enumerate(turns)
    ]


@pytest.mark.parametrize(
    ("turns", "local_indexes", "expected"),
    [
        ([("user", "!ls"), ("assistant", "local output")], (0, 1), []),
        ([("user", "  !pwd"), ("assistant", "local output")], (0, 1), []),
        (
            [("user", "!ls"), ("user", "real request"), ("assistant", "answer")],
            (0,),
            ["real request", "answer"],
        ),
        (
            [
                ("user", "!ls"),
                ("user", "!pwd"),
                ("assistant", "local output"),
                ("user", "real request"),
            ],
            (0, 1, 2),
            ["real request"],
        ),
        (
            [
                ("user", "Explain !ls"),
                ("assistant", "## Shell command output\n\nAn explanation"),
                ("user", "!pwd"),
            ],
            (2,),
            ["Explain !ls", "## Shell command output\n\nAn explanation"],
        ),
        (
            [
                ("user", "![diagram](architecture.png)"),
                ("assistant", "An architecture diagram"),
            ],
            (),
            ["![diagram](architecture.png)", "An architecture diagram"],
        ),
        (
            [("user", "!important: fix this"), ("assistant", "Fixed")],
            (),
            ["!important: fix this", "Fixed"],
        ),
        (
            [("user", "!ls"), ("assistant", COMPACTION_MARKER)],
            (0,),
            [COMPACTION_MARKER],
        ),
        (
            [("assistant", "local output"), ("assistant", "real answer")],
            (0,),
            ["real answer"],
        ),
    ],
)
def test_model_context_excludes_only_local_interactions(
    turns, local_indexes, expected
) -> None:
    messages = _messages(*turns, local_indexes=local_indexes)
    assert [m.content for m in model_context_messages(messages)] == expected
    assert len(messages) == len(turns)


@pytest.mark.parametrize(
    "provider_name",
    [
        "openai",
        "azure",
        "chatgpt",
        "github_copilot",
        "xai",
        "google",
        "google_gcp",
        "anthropic",
        "generic",
    ],
)
@pytest.mark.parametrize("include_tool_history", [False, True])
@pytest.mark.parametrize("refresh", [False, True])
def test_shared_provider_restore_keeps_local_shell_in_ui_only(
    tmp_path, provider_name, include_tool_history, refresh
) -> None:
    provider = Mock(spec=Provider)
    provider.settings = Settings(
        provider=provider_name, api_key="test", model="gpt-5.4"
    )
    display = Mock()
    with SessionStore(db_path=tmp_path / "sessions.db") as store:
        session_id = store.create_session(str(tmp_path), provider_name, "gpt-5.4")
        for role, content, is_local_command in [
            ("user", "!ls", True),
            ("assistant", "## Shell command output\n\nprivate local output", True),
            ("user", "![diagram](architecture.png)", False),
            ("assistant", "real answer", False),
            ("user", "!pwd", True),
            ("assistant", "## Shell command output\n\nprivate local path", True),
        ]:
            store.add_message(
                session_id, role, content, is_local_command=is_local_command
            )
        if refresh:
            refresh_provider_history_from_store(
                provider,
                store,
                session_id,
                reason="test",
                include_tool_history=include_tool_history,
            )
            provider.reset_conversation.assert_called_once()
        else:
            resume_session(
                provider=provider,
                store=store,
                session_id=session_id,
                session_usage=TokenUsage(model="gpt-5.4"),
                display=display,
                include_tool_history=include_tool_history,
            )
            assert len(display.replay_history.call_args.args[0]) == 6
        if include_tool_history:
            items = provider.restore_history_items.call_args.args[0]
            restored = [item["message"] for item in items]
        else:
            restored = provider.restore_messages.call_args.args[0]
        assert [message.content for message in restored] == [
            "![diagram](architecture.png)",
            "real answer",
        ]
        assert len(store.list_messages(session_id)) == 6


def test_local_shell_is_excluded_from_auxiliary_model_context(tmp_path) -> None:
    messages = _messages(
        ("user", "![diagram](architecture.png)"),
        ("assistant", "real answer"),
        ("user", "!ls"),
        ("assistant", "private local output"),
        local_indexes=(2, 3),
    )
    settings = Settings(api_key="test", compact_tail_turns=0)
    assert active_context_messages(messages) == messages[:2]
    compact = _split_messages_for_compaction(messages, settings)
    assert compact.head_messages == messages[:2]
    assert compact.tail_messages == []
    prompt = _prompt_enhancement_user_input("draft", messages)
    assert "![diagram](architecture.png)" in prompt
    assert "real answer" in prompt
    assert "!ls" not in prompt
    assert "private local output" not in prompt

    provider = Mock(spec=Provider)
    provider.settings = settings
    provider.get_conversation_checkpoint.return_value = None
    with SessionStore(db_path=tmp_path / "sessions.db") as store:
        session_id = store.create_session(str(tmp_path), "openai", "gpt-5.4")
        for message in messages:
            store.add_message(
                session_id,
                message.role,
                message.content,
                is_local_command=message.is_local_command,
            )
        context = build_parent_context_snapshot(
            provider=provider,
            store=store,
            session_id=session_id,
            current_user_turn_text=None,
        )
    assert context is not None
    assert [m.content for m in context.messages] == [
        "![diagram](architecture.png)",
        "real answer",
    ]


@pytest.mark.parametrize("tail_turns", [0, 1])
def test_compaction_after_unfinished_local_command_keeps_latest_boundary(
    tmp_path, tail_turns
) -> None:
    settings = Settings(api_key="test", compact_tail_turns=tail_turns)
    runtime = ResolvedRuntime(settings=settings, provider_id=None, profile_id=None)
    old_summary = f"{COMPACTION_SUMMARY_PREFIX}\n\nDeployment is failing."
    new_summary = f"{COMPACTION_SUMMARY_PREFIX}\n\nDeployment is now fixed."
    provider = Mock(spec=Provider)
    provider.settings = settings

    with SessionStore(db_path=tmp_path / "sessions.db") as store:
        session_id = store.create_session(str(tmp_path), "openai", settings.model)
        for role, content in [
            ("assistant", COMPACTION_MARKER),
            ("assistant", old_summary),
            ("user", "Fix deployment"),
            ("assistant", "Fixed deployment"),
        ]:
            store.add_message(session_id, role, content)
        command_id = store.add_message(session_id, "user", "!ls", is_local_command=True)
        context = _split_messages_for_compaction(
            store.list_messages(session_id), settings
        )
        _rewrite_compacted_context(
            store,
            session_id,
            runtime,
            compaction_context=context,
            summary_content=new_summary,
        )
        messages = store.list_messages(session_id)
        expected = [new_summary, *(m.content for m in context.tail_messages)]
        assert [m.content for m in active_context_messages(messages)] == expected
        assert any(m.id == command_id and m.is_local_command for m in messages)

        refresh_provider_history_from_store(
            provider, store, session_id, reason="compaction"
        )
        restored = provider.restore_messages.call_args.args[0]
        assert [m.content for m in restored] == expected
