from pbi_agent.ui.styles import CHAT_APP_CSS


def test_web_search_tool_group_has_dedicated_color() -> None:
    assert "ToolGroup.tool-group-web-search" in CHAT_APP_CSS
    assert "border-left: thick #10B981;" in CHAT_APP_CSS


def test_web_search_tool_item_has_dedicated_background() -> None:
    assert "ToolItem.tool-call-web-search" in CHAT_APP_CSS
    assert "background: #10B981 14%;" in CHAT_APP_CSS
