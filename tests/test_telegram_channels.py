from __future__ import annotations

import queue
from pathlib import Path
from types import SimpleNamespace
import threading

from fastapi.testclient import TestClient

from pbi_agent.channels.telegram import (
    TelegramInboundMessage,
    TelegramChannelRunner,
    parse_telegram_update,
    split_telegram_text,
)
from pbi_agent.channels.types import TelegramChannelConfig
from pbi_agent.config import ResolvedRuntime, Settings
from pbi_agent.session_store import SessionStore
from pbi_agent.web.serve import create_app


class _FakeTelegramClient:
    def __init__(self) -> None:
        self.reactions: list[tuple[str, int]] = []
        self.messages: list[tuple[str, str]] = []

    def set_reaction(self, *, chat_id: str, message_id: int) -> None:
        self.reactions.append((chat_id, message_id))

    def send_chat_action(self, *, chat_id: str, thread_id: int | None = None) -> None:
        return

    def send_message(
        self,
        *,
        chat_id: str,
        text: str,
        thread_id: int | None = None,
    ) -> None:
        self.messages.append((chat_id, text))


def test_parse_private_text_requires_allowed_user() -> None:
    config = TelegramChannelConfig(enabled=True, allowed_users=["123"])
    update = {
        "update_id": 10,
        "message": {
            "message_id": 5,
            "chat": {"id": 123, "type": "private"},
            "from": {"id": 123, "is_bot": False},
            "text": "hello",
        },
    }

    message = parse_telegram_update(update, config)

    assert message is not None
    assert message.source_key == "dm:123"
    assert message.text == "hello"
    assert (
        parse_telegram_update(
            update,
            TelegramChannelConfig(enabled=True, allowed_users=["999"]),
        )
        is None
    )


def test_parse_group_topic_and_channel_photo() -> None:
    config = TelegramChannelConfig(enabled=True, allowed_chats=["-1001"])
    topic_update = {
        "update_id": 11,
        "message": {
            "message_id": 6,
            "message_thread_id": 44,
            "chat": {"id": -1001, "type": "supergroup"},
            "from": {"id": 123, "is_bot": False},
            "text": "follow up",
        },
    }
    channel_update = {
        "update_id": 12,
        "channel_post": {
            "message_id": 7,
            "chat": {"id": -1001, "type": "channel"},
            "caption": "look",
            "photo": [
                {"file_id": "small", "file_size": 1},
                {"file_id": "large", "file_size": 100},
            ],
        },
    }

    topic = parse_telegram_update(topic_update, config)
    channel = parse_telegram_update(channel_update, config)

    assert topic is not None
    assert topic.source_key == "chat:-1001:topic:44"
    assert channel is not None
    assert channel.source_key == "channel:-1001"
    assert channel.attachments[0].file_id == "large"


def test_split_telegram_text_counts_utf16_units() -> None:
    chunks = split_telegram_text("a" * 4095 + "🙂")

    assert chunks == ["a" * 4095, "🙂"]


def test_channel_session_mapping_reuses_existing_session() -> None:
    with SessionStore() as store:
        first = store.get_or_create_channel_session_mapping(
            directory="WORKSPACE",
            platform="telegram",
            source_key="dm:123",
            provider="openai",
            model="gpt-5.4",
            title="Telegram dm:123",
        )
        second = store.get_or_create_channel_session_mapping(
            directory="workspace",
            platform="telegram",
            source_key="dm:123",
            provider="openai",
            model="gpt-5.4",
            title="ignored",
        )

    assert second == first


def test_channel_session_mapping_can_replace_default_session() -> None:
    with SessionStore() as store:
        first = store.get_or_create_channel_session_mapping(
            directory="workspace",
            platform="telegram",
            source_key="dm:123",
            provider="openai",
            model="gpt-5.4",
            title="Telegram dm:123",
        )
        fresh = store.create_channel_session_mapping(
            directory="workspace",
            platform="telegram",
            source_key="dm:123",
            provider="openai",
            model="gpt-5.4",
            title="Telegram dm:123",
        )
        reused = store.get_or_create_channel_session_mapping(
            directory="workspace",
            platform="telegram",
            source_key="dm:123",
            provider="openai",
            model="gpt-5.4",
            title="ignored",
        )

    assert fresh != first
    assert reused == fresh


def test_telegram_new_command_remaps_source_without_agent_run(
    tmp_path, monkeypatch
) -> None:
    config = TelegramChannelConfig(
        enabled=True,
        token_source="secret",
        token_secret="123:abc",
        allowed_users=["123"],
    )
    runtime = ResolvedRuntime(
        settings=Settings(api_key="test-key", provider="openai"),
        provider_id=None,
        profile_id=None,
    )
    directory_key = f"telegram-new-{tmp_path.name}"
    runner = TelegramChannelRunner(
        runtime=runtime,
        workspace_root=Path.cwd(),
        directory_key=directory_key,
        config=config,
        owner_id="owner-new",
    )
    fake_client = _FakeTelegramClient()
    runner._client = fake_client  # type: ignore[assignment]

    with SessionStore() as store:
        old_session_id = store.get_or_create_channel_session_mapping(
            directory=directory_key,
            platform="telegram",
            source_key="dm:123",
            provider="openai",
            model="gpt-5.4",
            title="Telegram dm:123",
        )

    def fail_run_single_turn(*args, **kwargs):
        raise AssertionError("agent turn should not run for /new")

    monkeypatch.setattr(
        "pbi_agent.channels.telegram.run_single_turn_in_directory",
        fail_run_single_turn,
    )

    runner._run_turn(
        TelegramInboundMessage(
            update_id=1,
            chat_id="123",
            message_id=1,
            source_key="dm:123",
            title="Telegram dm:123",
            text="/new",
        )
    )

    with SessionStore() as store:
        new_session_id = store.get_or_create_channel_session_mapping(
            directory=directory_key,
            platform="telegram",
            source_key="dm:123",
            provider="openai",
            model="gpt-5.4",
            title="ignored",
        )

    assert new_session_id != old_session_id
    assert fake_client.messages == [
        (
            "123",
            "Started a new conversation. Send your next message to continue here.",
        )
    ]


def test_token_lease_blocks_same_token_in_second_workspace() -> None:
    config = TelegramChannelConfig(
        enabled=True,
        token_source="secret",
        token_secret="123:abc",
        allowed_users=["123"],
    )
    runtime = ResolvedRuntime(
        settings=Settings(api_key="test-key", provider="openai"),
        provider_id=None,
        profile_id=None,
    )
    first = TelegramChannelRunner(
        runtime=runtime,
        workspace_root=Path.cwd(),
        directory_key="one",
        config=config,
        owner_id="owner-one",
    )
    second = TelegramChannelRunner(
        runtime=runtime,
        workspace_root=Path.cwd(),
        directory_key="two",
        config=config,
        owner_id="owner-two",
    )

    assert first._acquire_token_lease() is True
    try:
        assert second._acquire_token_lease() is False
    finally:
        first._release_token_lease()


def test_token_lease_blocks_reentrant_same_owner_and_ignores_stale_release() -> None:
    config = TelegramChannelConfig(
        enabled=True,
        token_source="secret",
        token_secret="123:abc",
        allowed_users=["123"],
    )
    runtime = ResolvedRuntime(
        settings=Settings(api_key="test-key", provider="openai"),
        provider_id=None,
        profile_id=None,
    )
    first = TelegramChannelRunner(
        runtime=runtime,
        workspace_root=Path.cwd(),
        directory_key="one",
        config=config,
        owner_id="same-owner",
    )
    replacement = TelegramChannelRunner(
        runtime=runtime,
        workspace_root=Path.cwd(),
        directory_key="one",
        config=config,
        owner_id="same-owner",
    )
    other = TelegramChannelRunner(
        runtime=runtime,
        workspace_root=Path.cwd(),
        directory_key="two",
        config=config,
        owner_id="other-owner",
    )

    assert first._acquire_token_lease() is True
    try:
        assert replacement._acquire_token_lease() is False
        first._release_token_lease()
        assert replacement._acquire_token_lease() is True

        first._lease_released = False
        first._release_token_lease()
        assert other._acquire_token_lease() is False
    finally:
        first._release_token_lease()
        replacement._release_token_lease()


def test_handle_update_dispatches_turn_after_reaction(monkeypatch) -> None:
    config = TelegramChannelConfig(
        enabled=True,
        token_source="secret",
        token_secret="123:abc",
        allowed_users=["123"],
    )
    runtime = ResolvedRuntime(
        settings=Settings(api_key="test-key", provider="openai"),
        provider_id=None,
        profile_id=None,
    )
    runner = TelegramChannelRunner(
        runtime=runtime,
        workspace_root=Path.cwd(),
        directory_key="telegram-dispatch-test",
        config=config,
        owner_id="owner-dispatch",
    )
    fake_client = _FakeTelegramClient()
    runner._client = fake_client  # type: ignore[assignment]
    turn_started = threading.Event()
    release_turn = threading.Event()

    def fake_run_single_turn(*args, **kwargs):
        turn_started.set()
        assert release_turn.wait(timeout=2.0)
        return SimpleNamespace(text="done")

    monkeypatch.setattr(
        "pbi_agent.channels.telegram.run_single_turn_in_directory",
        fake_run_single_turn,
    )

    runner._handle_update(
        {
            "update_id": 20,
            "message": {
                "message_id": 9,
                "chat": {"id": 123, "type": "private"},
                "from": {"id": 123, "is_bot": False},
                "text": "hello",
            },
        }
    )

    assert fake_client.reactions == [("123", 9)]
    assert turn_started.wait(timeout=2.0)
    assert fake_client.messages == []

    release_turn.set()
    runner.stop()
    assert fake_client.messages == [("123", "done")]


def test_poll_loop_does_not_ack_or_persist_batch_update_skipped_by_stop(
    tmp_path,
    monkeypatch,
) -> None:
    config = TelegramChannelConfig(
        enabled=True,
        token_source="secret",
        token_secret="123:abc",
        allowed_users=["123"],
    )
    runtime = ResolvedRuntime(
        settings=Settings(api_key="test-key", provider="openai"),
        provider_id=None,
        profile_id=None,
    )
    directory_key = f"telegram-stop-batch-{tmp_path.name}"
    runner = TelegramChannelRunner(
        runtime=runtime,
        workspace_root=Path.cwd(),
        directory_key=directory_key,
        config=config,
        owner_id="owner-stop-batch",
    )
    fake_client = _FakeTelegramClient()

    def get_updates(*, offset: int | None, timeout: int = 20):
        return [
            {
                "update_id": 100,
                "message": {
                    "message_id": 1,
                    "chat": {"id": 123, "type": "private"},
                    "from": {"id": 123, "is_bot": False},
                    "text": "first",
                },
            },
            {
                "update_id": 101,
                "message": {
                    "message_id": 2,
                    "chat": {"id": 123, "type": "private"},
                    "from": {"id": 123, "is_bot": False},
                    "text": "second",
                },
            },
        ]

    def set_reaction(*, chat_id: str, message_id: int) -> None:
        fake_client.reactions.append((chat_id, message_id))
        runner._stop.set()

    enqueued: list[int] = []

    def enqueue_turn(message: TelegramInboundMessage) -> bool:
        if runner._stop.is_set():
            return False
        enqueued.append(message.update_id)
        return True

    fake_client.get_updates = get_updates  # type: ignore[attr-defined]
    fake_client.set_reaction = set_reaction  # type: ignore[method-assign]
    runner._client = fake_client  # type: ignore[assignment]
    monkeypatch.setattr(runner, "_enqueue_turn", enqueue_turn)

    runner._poll_loop()

    with SessionStore() as store:
        record = store.get_channel_config(directory_key, "telegram")

    assert enqueued == [100]
    assert fake_client.reactions == [("123", 1)]
    assert record is not None
    assert record.config["last_update_id"] == 100


def test_source_worker_reports_failed_turn_and_continues() -> None:
    config = TelegramChannelConfig(
        enabled=True,
        token_source="secret",
        token_secret="123:abc",
        allowed_users=["123"],
    )
    runtime = ResolvedRuntime(
        settings=Settings(api_key="test-key", provider="openai"),
        provider_id=None,
        profile_id=None,
    )
    runner = TelegramChannelRunner(
        runtime=runtime,
        workspace_root=Path.cwd(),
        directory_key="telegram-worker-test",
        config=config,
        owner_id="owner-worker",
    )
    fake_client = _FakeTelegramClient()
    runner._client = fake_client  # type: ignore[assignment]
    calls: list[str] = []

    def fake_run_turn(message: TelegramInboundMessage) -> None:
        calls.append(message.text)
        if message.text == "first":
            raise RuntimeError("boom")
        fake_client.send_message(chat_id=message.chat_id, text="second-ok")

    runner._run_turn = fake_run_turn  # type: ignore[method-assign]
    source_queue: queue.Queue[TelegramInboundMessage | None] = queue.Queue()
    first = TelegramInboundMessage(
        update_id=1,
        chat_id="123",
        message_id=1,
        source_key="dm:123",
        title="Telegram dm:123",
        text="first",
    )
    second = TelegramInboundMessage(
        update_id=2,
        chat_id="123",
        message_id=2,
        source_key="dm:123",
        title="Telegram dm:123",
        text="second",
    )

    worker = threading.Thread(
        target=runner._source_worker,
        args=("dm:123", source_queue),
    )
    worker.start()
    source_queue.put(first)
    source_queue.put(second)
    source_queue.put(None)
    worker.join(timeout=2.0)

    assert not worker.is_alive()
    assert calls == ["first", "second"]
    assert fake_client.messages == [
        (
            "123",
            "Sorry, I couldn't process that Telegram message. Please try again.",
        ),
        ("123", "second-ok"),
    ]


def test_stop_keeps_token_lease_while_worker_is_alive(monkeypatch) -> None:
    config = TelegramChannelConfig(
        enabled=True,
        token_source="secret",
        token_secret="123:abc",
        allowed_users=["123"],
    )
    runtime = ResolvedRuntime(
        settings=Settings(api_key="test-key", provider="openai"),
        provider_id=None,
        profile_id=None,
    )
    first = TelegramChannelRunner(
        runtime=runtime,
        workspace_root=Path.cwd(),
        directory_key="one",
        config=config,
        owner_id="owner-one",
    )
    second = TelegramChannelRunner(
        runtime=runtime,
        workspace_root=Path.cwd(),
        directory_key="two",
        config=config,
        owner_id="owner-two",
    )
    worker_can_exit = threading.Event()
    worker = threading.Thread(target=worker_can_exit.wait)
    worker.start()
    first._workers["dm:123"] = worker
    monkeypatch.setattr(first, "_join_workers", lambda *, timeout: None)

    assert first._acquire_token_lease() is True
    try:
        first.stop()
        assert second._acquire_token_lease() is False
    finally:
        worker_can_exit.set()
        worker.join(timeout=2.0)
        first._release_token_lease()


def test_poll_thread_releases_token_lease_after_timed_out_stop(monkeypatch) -> None:
    config = TelegramChannelConfig(
        enabled=True,
        token_source="secret",
        token_secret="123:abc",
        allowed_users=["123"],
    )
    runtime = ResolvedRuntime(
        settings=Settings(api_key="test-key", provider="openai"),
        provider_id=None,
        profile_id=None,
    )
    first = TelegramChannelRunner(
        runtime=runtime,
        workspace_root=Path.cwd(),
        directory_key="one",
        config=config,
        owner_id="owner-one",
    )
    second = TelegramChannelRunner(
        runtime=runtime,
        workspace_root=Path.cwd(),
        directory_key="two",
        config=config,
        owner_id="owner-two",
    )
    poll_can_exit = threading.Event()
    poll_exited = threading.Event()

    def delayed_poll_finally() -> None:
        first._stop.wait(timeout=2.0)
        poll_can_exit.wait(timeout=2.0)
        first._release_token_lease_if_stopped(current_thread_stopping=True)
        poll_exited.set()

    poll_thread = threading.Thread(target=delayed_poll_finally)
    poll_thread.start()
    first._thread = poll_thread
    original_join = threading.Thread.join

    def fake_join(
        self: threading.Thread,
        timeout: float | None = None,
    ) -> None:
        if self is poll_thread:
            return
        original_join(self, timeout=timeout)

    monkeypatch.setattr(threading.Thread, "join", fake_join)

    assert first._acquire_token_lease() is True
    try:
        first.stop()
        assert poll_thread.is_alive()
        assert second._acquire_token_lease() is False

        poll_can_exit.set()
        assert poll_exited.wait(timeout=2.0)
        assert second._acquire_token_lease() is True
    finally:
        first._release_token_lease()
        second._release_token_lease()


def test_channels_api_updates_workspace_config(tmp_path, monkeypatch) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    monkeypatch.chdir(workspace)
    app = create_app(Settings(api_key="test-key", provider="openai"))

    with TestClient(app) as client:
        response = client.put(
            "/api/channels/telegram",
            json={
                "enabled": True,
                "token_source": "env",
                "token_env_var": "PBI_AGENT_TELEGRAM_BOT_TOKEN",
                "allowed_users": ["123"],
                "allowed_chats": [],
            },
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["telegram"]["enabled"] is True
    assert payload["telegram"]["allowed_users"] == ["123"]
