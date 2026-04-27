from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from difflib import SequenceMatcher
from typing import TypeVar


@dataclass(frozen=True, slots=True)
class SlashCommand:
    """Slash-command metadata used by the browser composer."""

    name: str
    description: str
    hidden_keywords: str = ""
    kind: str = "local_command"


COMMANDS: tuple[SlashCommand, ...] = (
    SlashCommand(
        name="/skills",
        description="Show discovered project skills",
        hidden_keywords="skill catalog list loaded skills",
    ),
    SlashCommand(
        name="/mcp",
        description="Show discovered project MCP servers",
        hidden_keywords="mcp server servers tools catalog list",
    ),
    SlashCommand(
        name="/agents",
        description="Show discovered project sub-agents",
        hidden_keywords="sub-agent subagent agent agents reload list",
    ),
    SlashCommand(
        name="/compact",
        description="Summarize the live session to reduce model context",
        hidden_keywords="compact context summarize summary token tokens",
    ),
)

SlashCommandTuple = tuple[str, str, str, str]
_MIN_SLASH_FUZZY_SCORE = 25
_MIN_DESC_SEARCH_LEN = 2
_T = TypeVar("_T")


def list_slash_commands() -> list[SlashCommand]:
    """Return slash commands exposed by the browser UI."""

    return list(COMMANDS)


def _command_tuple(command: SlashCommand) -> SlashCommandTuple:
    return (
        command.name,
        command.description,
        command.hidden_keywords,
        command.kind,
    )


def list_slash_command_tuples() -> list[SlashCommandTuple]:
    """Return slash command tuples for autocomplete consumers."""

    return [_command_tuple(command) for command in list_slash_commands()]


def _score_command(search: str, cmd: str, desc: str, keywords: str = "") -> float:
    if not search:
        return 0.0

    name = cmd.lstrip("/").lower()
    lower_desc = desc.lower()
    if name.startswith(search):
        return 200.0
    if search in name:
        return 150.0
    if keywords and len(search) >= _MIN_DESC_SEARCH_LEN:
        for keyword in keywords.lower().split():
            if keyword.startswith(search) or search in keyword:
                return 120.0
    if len(search) >= _MIN_DESC_SEARCH_LEN and search in lower_desc:
        idx = lower_desc.find(search)
        return 110.0 if idx == 0 or lower_desc[idx - 1] == " " else 90.0
    name_ratio = SequenceMatcher(None, search, name).ratio()
    desc_ratio = SequenceMatcher(None, search, lower_desc).ratio()
    best = max(name_ratio * 60, desc_ratio * 30)
    return best if best >= _MIN_SLASH_FUZZY_SCORE else 0.0


def _rank_commands(
    search: str,
    items: Sequence[tuple[_T, SlashCommandTuple]],
    *,
    limit: int,
) -> list[_T]:
    if not search:
        return [item for item, _parts in items[:limit]]

    scored: list[tuple[float, int, _T]] = []
    for index, (item, (cmd, desc, keywords, _kind)) in enumerate(items):
        score = _score_command(search, cmd, desc, keywords)
        if score > 0:
            scored.append((score, index, item))
    scored.sort(key=lambda item: (-item[0], item[1]))
    return [item for _score, _index, item in scored[:limit]]


def search_slash_commands(
    search: str,
    *,
    limit: int = 10,
) -> list[SlashCommand]:
    """Return ranked slash commands for the browser UI."""

    commands = list_slash_commands()
    return _rank_commands(
        search.lower(),
        [(command, _command_tuple(command)) for command in commands],
        limit=limit,
    )


def search_slash_command_tuples(
    search: str,
    commands: Sequence[SlashCommandTuple],
    *,
    limit: int = 10,
) -> list[SlashCommandTuple]:
    """Return ranked autocomplete tuples from an arbitrary command list."""

    return _rank_commands(
        search.lower(),
        [(command, command) for command in commands],
        limit=limit,
    )


SLASH_COMMANDS: list[SlashCommandTuple] = list_slash_command_tuples()


def normalize_command_name(value: str) -> str:
    """Return the normalized slash command token for *value*."""

    return value.strip().split(maxsplit=1)[0].lower() if value.strip() else ""


__all__ = [
    "COMMANDS",
    "SLASH_COMMANDS",
    "SlashCommand",
    "SlashCommandTuple",
    "list_slash_command_tuples",
    "list_slash_commands",
    "normalize_command_name",
    "search_slash_command_tuples",
    "search_slash_commands",
]
