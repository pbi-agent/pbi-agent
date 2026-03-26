from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class SlashCommand:
    """Slash-command metadata used by autocomplete and app dispatch."""

    name: str
    description: str
    hidden_keywords: str = ""
    local_only: bool = False


COMMANDS: tuple[SlashCommand, ...] = (
    SlashCommand(
        name="/help",
        description="Show chat shortcuts and local commands",
        hidden_keywords="shortcuts commands",
        local_only=True,
    ),
    SlashCommand(
        name="/clear",
        description="Clear chat and start a new session",
        hidden_keywords="reset new chat",
        local_only=True,
    ),
    SlashCommand(
        name="/skills",
        description="Show discovered project skills",
        hidden_keywords="skill catalog list loaded skills",
    ),
    SlashCommand(
        name="/quit",
        description="Quit the app",
        hidden_keywords="exit close",
        local_only=True,
    ),
)


SLASH_COMMANDS: list[tuple[str, str, str]] = [
    (command.name, command.description, command.hidden_keywords) for command in COMMANDS
]

LOCAL_COMMANDS: frozenset[str] = frozenset(
    command.name for command in COMMANDS if command.local_only
)


def normalize_command_name(value: str) -> str:
    """Return the normalized slash command token for *value*."""

    return value.strip().split(maxsplit=1)[0].lower() if value.strip() else ""


__all__ = [
    "COMMANDS",
    "LOCAL_COMMANDS",
    "SLASH_COMMANDS",
    "SlashCommand",
    "normalize_command_name",
]
