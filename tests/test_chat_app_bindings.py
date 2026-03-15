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
