from pbi_agent.ui.app import ChatApp


def test_chat_app_exposes_new_chat_binding() -> None:
    keys_to_actions = {binding.key: binding.action for binding in ChatApp.BINDINGS}
    assert keys_to_actions["ctrl+r"] == "new_chat"
