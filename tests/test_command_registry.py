from __future__ import annotations

from pbi_agent.config import RESERVED_COMMAND_ALIASES
from pbi_agent.web.command_registry import (
    list_slash_commands,
    search_slash_command_tuples,
    search_slash_commands,
)


def test_list_slash_commands_for_web_excludes_local_only_commands() -> None:
    assert [command.name for command in list_slash_commands()] == [
        "/status",
        "/new",
        "/skills",
        "/mcp",
        "/agents",
        "/extensions",
        "/hooks",
        "/init",
        "/reload",
        "/compact",
    ]


def test_search_slash_commands_ranks_matches_by_name_and_keywords() -> None:
    assert [command.name for command in search_slash_commands("ag", limit=1)] == [
        "/agents"
    ]
    assert [command.name for command in search_slash_commands("serv")] == ["/mcp"]
    assert [command.name for command in search_slash_commands("setup", limit=1)] == [
        "/init"
    ]
    assert [command.name for command in search_slash_commands("refresh")] == ["/reload"]
    assert [command.name for command in search_slash_commands("fresh")] == ["/new"]
    assert [command.name for command in search_slash_commands("trust", limit=1)] == [
        "/hooks"
    ]


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


def test_status_command_is_discoverable_by_usage_keywords() -> None:
    assert search_slash_commands("usage", limit=1)[0].name == "/status"


def test_status_alias_is_reserved_against_project_command_collisions() -> None:
    assert "/status" in RESERVED_COMMAND_ALIASES
