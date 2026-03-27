from __future__ import annotations

import sys
from pathlib import Path

from pbi_agent.agent.sub_agent_discovery import discover_project_sub_agents
from pbi_agent.agent.skill_discovery import discover_project_skills

_DEFAULT_SYSTEM_PROMPT = """
You are pbi-agent, a local CLI agent for creating, auditing, and editing Power BI PBIP projects.

<power_bi_rules>
- Use explicit measures in visuals; never rely on implicit aggregations.
- Dedicated measures table must be named `_Measures`, never `Measures`.
- Never modify auto-generated date tables (`DateTableTemplate_*`, `LocalDateTable_*`); skip their descriptions — their TMDL schema is restricted.
- Distribute visuals intentionally across the canvas unless the user specifies a layout.
- Style priority: explicit user instruction > existing project/brand conventions > skill default preset.
</power_bi_rules>
""".strip()

_SUB_AGENT_PROMPT = """
<persona>
- You are a delegated sub-agent operating on behalf of the main agent.
- You are in background mode and will not interact with the user directly. Do not ask the user questions.
</persona>
""".strip()

# Tools that are specific to the default Power BI mode and should be
# excluded when a custom INSTRUCTIONS.md replaces the built-in prompt.
_PBI_ONLY_TOOLS: frozenset[str] = frozenset({"skill_knowledge", "init_report"})

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
Project skills are available for specialized tasks.
- When a task matches a skill description, load that skill's SKILL.md with read_file before proceeding.
- Resolve relative paths in a skill against the skill directory, which is the parent directory of SKILL.md.
- Use read_file, list_files, and search_files to inspect referenced project-local resources as needed.
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
- Project sub-agents run in isolated child-agent contexts and do not inherit the main conversation history.
</sub_agent_loading_rules>
""".strip()

    return f"{base_prompt}\n\n{instructions}\n{catalog}"


def get_system_prompt() -> str:
    prompt = _append_available_skills(_append_project_rules(_resolve_base_prompt()))
    return _append_available_sub_agents(prompt)


def get_sub_agent_system_prompt(agent_prompt_override: str | None = None) -> str:
    base = agent_prompt_override or _resolve_base_prompt()
    prompt = _append_project_rules(f"{base}\n\n{_SUB_AGENT_PROMPT}")
    return _append_available_skills(prompt)


def get_custom_excluded_tools() -> set[str]:
    """Return tool names to exclude when custom instructions are active."""
    if load_instructions() is not None:
        return set(_PBI_ONLY_TOOLS)
    return set()
