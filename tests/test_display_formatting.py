from __future__ import annotations

from pbi_agent.display.formatting import (
    route_function_result,
    tool_group_class,
    tool_item_class,
)


def test_search_workspace_routes_to_dedicated_cli_display() -> None:
    tool_name, text = route_function_result(
        "search_workspace",
        status="[green]done[/green]",
        arguments={
            "pattern": "UserService",
            "root": "src",
            "regex": True,
            "target": "both",
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

    assert tool_name == "search_workspace"
    assert tool_group_class("search_workspace") == "tool-group-search-workspace"
    assert tool_item_class("search_workspace") == "tool-call-search-workspace"
    assert "UserService" in text
    assert "root:" in text
    assert "src" in text
    assert "target:" in text
    assert "both" in text
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
    assert "search_workspace()" not in text


def test_search_workspace_cli_display_shows_error_detail() -> None:
    _, text = route_function_result(
        "search_workspace",
        status="[red]failed[/red]",
        arguments={"pattern": "[", "regex": True},
        result={
            "ok": False,
            "result": {"error": "unterminated character set at position 0"},
        },
    )

    assert "error:" in text
    assert "unterminated character set at position 0" in text
