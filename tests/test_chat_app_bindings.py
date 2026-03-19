from pbi_agent.session_store import SessionRecord
from pbi_agent.config import Settings
from pbi_agent.ui.app import ChatApp


def test_chat_app_exposes_new_chat_binding() -> None:
    keys_to_actions = {binding.key: binding.action for binding in ChatApp.BINDINGS}
    assert keys_to_actions["ctrl+r"] == "new_chat"


def test_chat_app_initializes_header_with_model_and_effort() -> None:
    app = ChatApp(
        settings=Settings(
            api_key="test-key",
            model="gpt-5.4-2026-03-05",
            reasoning_effort="xhigh",
        )
    )

    assert "gpt-5.4-2026-03-05 (xhigh)" in app.sub_title


def test_populate_sidebar_filters_sessions_to_active_provider(monkeypatch) -> None:
    app = ChatApp(
        settings=Settings(
            api_key="test-key",
            provider="openai",
            model="gpt-5.4-2026-03-05",
        )
    )
    sessions = [
        SessionRecord(
            session_id="openai-session",
            directory="/workspace",
            provider="openai",
            model="gpt-5.4-2026-03-05",
            previous_id="resp_1",
            title="OpenAI chat",
            total_tokens=10,
            input_tokens=6,
            output_tokens=4,
            cost_usd=0.01,
            created_at="2026-03-19T10:00:00+00:00",
            updated_at="2026-03-19T10:00:00+00:00",
        ),
        SessionRecord(
            session_id="xai-session",
            directory="/workspace",
            provider="xai",
            model="grok-4",
            previous_id="resp_2",
            title="xAI chat",
            total_tokens=10,
            input_tokens=6,
            output_tokens=4,
            cost_usd=0.01,
            created_at="2026-03-19T10:00:00+00:00",
            updated_at="2026-03-19T10:00:00+00:00",
        ),
        SessionRecord(
            session_id="other-openai-model",
            directory="/workspace",
            provider="openai",
            model="gpt-4.1",
            previous_id="resp_3",
            title="Older OpenAI chat",
            total_tokens=10,
            input_tokens=6,
            output_tokens=4,
            cost_usd=0.01,
            created_at="2026-03-19T10:00:00+00:00",
            updated_at="2026-03-19T10:00:00+00:00",
        ),
    ]

    class FakeStore:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def list_sessions(
            self, directory: str, limit: int = 30, provider: str | None = None
        ):
            assert directory == "/workspace"
            assert limit == 30
            assert provider == "openai"
            return [s for s in sessions if s.provider == provider]

    class FakeSidebar:
        def __init__(self) -> None:
            self.items = None

        def refresh_sessions(self, items):
            self.items = items

    monkeypatch.setattr("pbi_agent.session_store.SessionStore", FakeStore)
    monkeypatch.setattr("pbi_agent.ui.app.os.getcwd", lambda: "/workspace")

    sidebar = FakeSidebar()
    app._populate_sidebar(sidebar)

    assert sidebar.items == [
        ("openai-session", "OpenAI chat\n[dim]openai · 2026-03-19[/dim]"),
        ("other-openai-model", "Older OpenAI chat\n[dim]openai · 2026-03-19[/dim]"),
    ]
