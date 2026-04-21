from __future__ import annotations

import sys
from pathlib import Path

from pbi_agent.agent.sub_agent_discovery import discover_project_sub_agents
from pbi_agent.agent.skill_discovery import discover_project_skills

_DEFAULT_SYSTEM_PROMPT = """
You are an expert coding assistant. You help users with coding tasks by reading files, executing commands, editing code, and writing new files.
""".strip()

_SUB_AGENT_PROMPT = """
<persona>
- You are a delegated sub-agent operating on behalf of the main agent.
- You are in background mode and will not interact with the user directly. Do not ask the user questions.
</persona>
""".strip()

_MAX_FILE_BYTES = 1_000_000  # 1 MB


def _warn(message: str) -> None:
    print(message, file=sys.stderr)


def _load_file(name: str, cwd: Path | None = None) -> str | None:
    """Read an optional Markdown file from *cwd* (default: CWD).

    Returns the file content, or ``None`` when the file is absent, empty,
    or unreadable.
    """
    target = (cwd or Path.cwd()) / name

    try:
        size = target.stat().st_size
    except FileNotFoundError:
        return None
    except OSError:
        _warn(f"{name} found but unreadable due to permissions.")
        return None

    if size > _MAX_FILE_BYTES:
        _warn(f"{name} exceeds 1 MB; content will be truncated.")

    try:
        with target.open("rb") as fh:
            raw_content = fh.read(_MAX_FILE_BYTES)
    except OSError:
        _warn(f"{name} found but unreadable due to permissions.")
        return None

    content = raw_content.decode("utf-8", errors="replace").strip()
    if not content:
        return None

    return content


def load_instructions(cwd: Path | None = None) -> str | None:
    """Read an optional ``INSTRUCTIONS.md`` from *cwd* (default: CWD)."""
    return _load_file("INSTRUCTIONS.md", cwd)


def load_project_rules(cwd: Path | None = None) -> str | None:
    """Read an optional ``AGENTS.md`` file from *cwd* (default: CWD).

    Returns the file content, or ``None`` when the file is absent, empty,
    or unreadable.
    """
    return _load_file("AGENTS.md", cwd)


def _resolve_base_prompt() -> str:
    """Return the base system prompt — custom instructions or the built-in default."""
    custom = load_instructions()
    if custom is not None:
        return custom
    return _DEFAULT_SYSTEM_PROMPT


def _append_project_rules(base_prompt: str) -> str:
    """Append ``<project_rules>`` section if ``AGENTS.md`` is present."""
    rules = load_project_rules()
    if rules is None:
        return base_prompt
    return f"{base_prompt}\n\n<project_rules>\n{rules}\n</project_rules>"


def _append_available_skills(base_prompt: str) -> str:
    skills = discover_project_skills()
    if not skills:
        return base_prompt

    catalog_lines = ["<available_skills>"]
    for skill in skills:
        catalog_lines.extend(
            [
                "  <skill>",
                f"    <name>{skill.name}</name>",
                f"    <description>{skill.description}</description>",
                f"    <location>{skill.location}</location>",
                "  </skill>",
            ]
        )
    catalog_lines.append("</available_skills>")
    catalog = "\n".join(catalog_lines)

    instructions = """
<skill_loading_rules>
Project skills use progressive disclosure: the catalog contains only each skill's name, description, and SKILL.md location.
- Use a skill when the user's task matches its description or the user explicitly names it.
- Before applying a matched skill, load its SKILL.md with read_file using the listed location.
- Treat loaded skill instructions as task guidance for the current session.
- Resolve relative paths against the skill directory, which is the parent directory of SKILL.md.
- Load referenced resources only when needed with read_file, list_files, or search_files.
</skill_loading_rules>
""".strip()

    return f"{base_prompt}\n\n{instructions}\n{catalog}"


def _append_available_sub_agents(base_prompt: str) -> str:
    agents = discover_project_sub_agents()
    if not agents:
        return base_prompt

    catalog_lines = ["<available_sub_agents>"]
    for agent in agents:
        catalog_lines.extend(
            [
                "  <sub_agent>",
                f"    <name>{agent.name}</name>",
                f"    <description>{agent.description}</description>",
                "  </sub_agent>",
            ]
        )
    catalog_lines.append("</available_sub_agents>")
    catalog = "\n".join(catalog_lines)

    instructions = """
<sub_agent_loading_rules>
The `sub_agent` tool is available for delegated work.
- Use `sub_agent` without `agent_type` for the default generalist sub-agent.
- When a task matches one of the available project sub-agents below, call `sub_agent` with `agent_type` set to that sub-agent's `name`.
- Project sub-agents are isolated by default. Set `include_context` to `true` when the child should inherit the parent conversation context.
</sub_agent_loading_rules>
""".strip()

    return f"{base_prompt}\n\n{instructions}\n{catalog}"


def _append_active_command(
    base_prompt: str,
    active_command_instructions: str | None = None,
) -> str:
    if active_command_instructions is None:
        return base_prompt
    instructions = active_command_instructions.strip()
    if not instructions:
        return base_prompt
    return f"{base_prompt}\n\n<active_command>\n{instructions}\n</active_command>"


def get_system_prompt(active_command_instructions: str | None = None) -> str:
    prompt = _append_available_skills(_append_project_rules(_resolve_base_prompt()))
    prompt = _append_available_sub_agents(prompt)
    return _append_active_command(prompt, active_command_instructions)


def get_sub_agent_system_prompt(agent_prompt_override: str | None = None) -> str:
    base = agent_prompt_override or _resolve_base_prompt()
    prompt = _append_project_rules(f"{base}\n\n{_SUB_AGENT_PROMPT}")
    return _append_available_skills(prompt)


def get_custom_excluded_tools() -> set[str]:
    """Return tool names to exclude when custom instructions are active."""
    return set()
