from __future__ import annotations

from pbi_agent.display.formatting import (
    route_function_result,
    tool_group_class,
    tool_item_class,
)


def test_explore_workspace_routes_to_dedicated_cli_display() -> None:
    tool_name, text = route_function_result(
        "explore_workspace",
        status="[green]done[/green]",
        arguments={
            "pattern": "UserService",
            "root": "src",
            "regex": True,
            "target": "path",
            "path_scope": "basename",
            "mode": "snippets",
            "context_lines": 1,
            "glob": ["*.py"],
            "exclude": "tests/**",
            "cursor": 20,
        },
        result={
            "result": "src/service.py\n 12:class UserService:\nsrc/user_service.py"
        },
    )

    assert tool_name == "explore_workspace"
    assert tool_group_class("explore_workspace") == "tool-group-explore-workspace"
    assert tool_item_class("explore_workspace") == "tool-call-explore-workspace"
    assert "UserService" in text
    assert "root:" in text
    assert "src" in text
    assert "target:" in text
    assert "path search" in text
    assert "pattern:" in text
    assert "regex" in text
    assert "options:" in text
    assert "mode=snippets" in text
    assert "context=1" in text
    assert "path_scope=basename" in text
    assert "cursor=20" in text
    assert "glob:" in text
    assert "*.py" in text
    assert "exclude:" in text
    assert "tests/**" in text
    assert "output:" in text
    assert "src/service.py" in text
    assert "class UserService" in text
    assert "explore_workspace()" not in text


def test_explore_workspace_cli_display_shows_error_detail() -> None:
    _, text = route_function_result(
        "explore_workspace",
        status="[red]failed[/red]",
        arguments={"pattern": "[", "regex": True},
        result={
            "ok": False,
            "result": {"error": "unterminated character set at position 0"},
        },
    )

    assert "error:" in text
    assert "unterminated character set at position 0" in text


def test_web_search_routes_unwrap_wrapped_result_sources() -> None:
    tool_name, text = route_function_result(
        "web_search",
        status="[green]done[/green]",
        arguments={"query": "btc live price"},
        result={
            "ok": True,
            "result": {
                "sources": [
                    {
                        "title": "BTC USD — Bitcoin Price and Chart",
                        "url": "https://www.tradingview.com/symbols/BTCUSD/",
                        "snippet": "Live Bitcoin price information.",
                    },
                ],
            },
        },
    )

    assert tool_name == "web_search"
    assert "1 source" in text
    assert "BTC USD" in text
    assert "https://www.tradingview.com/symbols/BTCUSD/" in text
    assert "no sources" not in text
