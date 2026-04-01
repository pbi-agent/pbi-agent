from __future__ import annotations

from pbi_agent.web.command_registry import (
    list_slash_commands,
    search_slash_command_tuples,
    search_slash_commands,
)


def test_list_slash_commands_for_web_excludes_local_only_commands() -> None:
    assert [command.name for command in list_slash_commands()] == [
        "/skills",
        "/mcp",
        "/agents",
    ]


def test_search_slash_commands_ranks_matches_by_name_and_keywords() -> None:
    assert [command.name for command in search_slash_commands("ag")] == ["/agents"]
    assert [command.name for command in search_slash_commands("serv")] == ["/mcp"]


def test_search_slash_command_tuples_preserves_registry_order_on_empty_query() -> None:
    commands = [
        ("/skills", "Show discovered project skills", "skill catalog", "local_command"),
        ("/mcp", "Show discovered project MCP servers", "mcp server", "local_command"),
        (
            "/agents",
            "Show discovered project sub-agents",
            "sub-agent agents",
            "local_command",
        ),
    ]

    assert search_slash_command_tuples("", commands, limit=2) == commands[:2]
