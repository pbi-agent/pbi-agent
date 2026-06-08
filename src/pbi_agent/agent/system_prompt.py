from __future__ import annotations

from collections.abc import Iterable
import sys
from pathlib import Path
from typing import TYPE_CHECKING

from pbi_agent.agent.reference_resolution import (
    resolve_skill_references,
    resolve_sub_agent_references,
)
from pbi_agent.agent.sub_agent_discovery import discover_project_sub_agents
from pbi_agent.agent.skill_discovery import discover_project_skills
from pbi_agent.tools.availability import (
    default_excluded_tool_names,
    effective_excluded_tool_names,
    native_web_search_enabled,
)
from pbi_agent.tools.registry import get_tool_specs

if TYPE_CHECKING:
    from pbi_agent.config import CommandConfig, Settings

_DEFAULT_SYSTEM_PROMPT_PREAMBLE = """
You are task assistant. Treat every user task/question as workspace-related: inspect context and use available tools to achieve the outcome.
Run through Python CLI as `pbi-agent`; check help with `pbi-agent -h` when needed.
""".strip()

_READ_TOOL_NAMES = frozenset({"explore_workspace"})
_WRITE_TOOL_NAMES = frozenset({"apply_patch", "replace_in_file", "write_file"})

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


def _active_tool_excluded_names(
    settings: "Settings | None",
    excluded_tools: Iterable[str] | None,
) -> set[str]:
    if settings is None:
        return default_excluded_tool_names(excluded_tools)
    return effective_excluded_tool_names(settings, excluded_tools)


def _tool_usage_rules(
    *,
    settings: "Settings | None" = None,
    excluded_tools: Iterable[str] | None = None,
) -> str:
    excluded_names = _active_tool_excluded_names(settings, excluded_tools)
    specs = get_tool_specs(excluded_names=excluded_names)
    active_names = {spec.name for spec in specs}

    lines = [
        "<tool_usage_rules>",
    ]
    if "shell" in active_names and (
        active_names & _READ_TOOL_NAMES or active_names & _WRITE_TOOL_NAMES
    ):
        lines.append(
            "Prefer file tools for file operations; use `shell` only for "
            "command execution."
        )

    usage_lines = [
        f"- {spec.prompt_usage}" for spec in specs if spec.prompt_usage is not None
    ]
    if settings is not None and native_web_search_enabled(settings):
        usage_lines.append(
            "- Use provider-native web search when supported by the active "
            "provider and current web information is needed."
        )

    if usage_lines:
        lines.extend(usage_lines)
    else:
        lines.append(
            "No built-in workspace tools are available in this turn. Do not call "
            "disabled built-in tools."
        )
    lines.append("</tool_usage_rules>")
    return "\n".join(lines)


def _inject_tool_usage_rules(base_prompt: str, tool_usage_rules: str) -> str:
    start_tag = "<tool_usage_rules>"
    end_tag = "</tool_usage_rules>"
    start_index = base_prompt.find(start_tag)
    if start_index < 0:
        return f"{base_prompt}\n\n{tool_usage_rules}"
    end_index = base_prompt.find(end_tag, start_index)
    if end_index < 0:
        return f"{base_prompt}\n\n{tool_usage_rules}"
    return (
        f"{base_prompt[:start_index].rstrip()}\n\n"
        f"{tool_usage_rules}"
        f"{base_prompt[end_index + len(end_tag) :]}"
    )


def load_instructions(cwd: Path | None = None) -> str | None:
    """Read an optional ``INSTRUCTIONS.md`` from *cwd* (default: CWD)."""
    return _load_file("INSTRUCTIONS.md", cwd)


def load_project_rules(cwd: Path | None = None) -> str | None:
    """Read an optional ``AGENTS.md`` file from *cwd* (default: CWD).

    Returns the file content, or ``None`` when the file is absent, empty,
    or unreadable.
    """
    return _load_file("AGENTS.md", cwd)


def load_workspace_memory(cwd: Path | None = None) -> str | None:
    """Read an optional ``MEMORY.md`` file from *cwd* (default: CWD).

    Returns the file content, or ``None`` when the file is absent, empty,
    or unreadable.
    """
    return _load_file("MEMORY.md", cwd)


def _resolve_base_prompt(
    *,
    settings: "Settings | None" = None,
    excluded_tools: Iterable[str] | None = None,
    cwd: Path | None = None,
) -> str:
    """Return the base system prompt — custom instructions or the built-in default."""
    tool_usage_rules = _tool_usage_rules(
        settings=settings,
        excluded_tools=excluded_tools,
    )
    custom = load_instructions(cwd)
    if custom is not None:
        return _inject_tool_usage_rules(custom, tool_usage_rules)
    return f"{_DEFAULT_SYSTEM_PROMPT_PREAMBLE}\n\n{tool_usage_rules}"


def _append_project_rules(base_prompt: str, cwd: Path | None = None) -> str:
    """Append ``<project_rules>`` section if ``AGENTS.md`` is present."""
    rules = load_project_rules(cwd)
    if rules is None:
        return base_prompt
    return f"{base_prompt}\n\n<project_rules>\n{rules}\n</project_rules>"


def _append_workspace_memory(base_prompt: str, cwd: Path | None = None) -> str:
    """Append ``<workspace_memory>`` section if ``MEMORY.md`` is present."""
    memory = load_workspace_memory(cwd)
    if memory is None:
        return base_prompt
    return f"{base_prompt}\n\n<workspace_memory>\n{memory}\n</workspace_memory>"


def _append_available_skills(
    base_prompt: str,
    cwd: Path | None = None,
    *,
    explicit_skill_names: set[str] | None = None,
    visible_skill_names: tuple[str, ...] | None = None,
    source_label: str = "Command frontmatter",
    workspace_directory_key: str | None = None,
) -> str:
    if visible_skill_names is None:
        skills = discover_project_skills(
            cwd,
            explicit_skill_names=explicit_skill_names,
            directory_key=workspace_directory_key,
        )
    else:
        skills = list(
            resolve_skill_references(
                visible_skill_names,
                cwd,
                directory_key=workspace_directory_key,
                source_label=source_label,
            )
            or ()
        )
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
- Treat `$<skill-name>` in user input as an explicit request to use that skill; strip the `$` and match `<skill-name>` against catalogued skill names.
- Before applying a matched skill, load its SKILL.md with `explore_workspace` target="read" using the listed location.
- Treat loaded skill instructions as task guidance for the current session.
- Resolve relative paths against the skill directory, which is the parent directory of SKILL.md.
- Load referenced resources only when needed.
</skill_loading_rules>
""".strip()

    return f"{base_prompt}\n\n{instructions}\n{catalog}"


def _append_available_sub_agents(
    base_prompt: str,
    cwd: Path | None = None,
    *,
    explicit_agent_names: set[str] | None = None,
    visible_agent_names: tuple[str, ...] | None = None,
    source_label: str = "Command frontmatter",
    workspace_directory_key: str | None = None,
) -> str:
    if visible_agent_names is None:
        agents = discover_project_sub_agents(
            cwd,
            explicit_agent_names=explicit_agent_names,
            directory_key=workspace_directory_key,
        )
    else:
        agents = list(
            resolve_sub_agent_references(
                visible_agent_names,
                cwd,
                directory_key=workspace_directory_key,
                strict=True,
                source_label=source_label,
            )
            or ()
        )
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

    default_rule = (
        "- Use `sub_agent` without `agent_type` for the default generalist sub-agent."
        if visible_agent_names is None
        else "- Use `sub_agent` with `agent_type` set to one of the available project sub-agent names below."
    )
    instructions = f"""
<sub_agent_loading_rules>
The `sub_agent` tool is available for delegated work.
{default_rule}
- When a task matches one of the available project sub-agents below, call `sub_agent` with `agent_type` set to that sub-agent's `name`.
- Treat `@<agent-name> (agent)` and `@<agent-name>` in user input as explicit requests to call that named sub-agent.
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


def _append_component_commands(
    base_prompt: str,
    commands: Iterable["CommandConfig"] | None = None,
) -> str:
    if commands is None:
        return base_prompt
    sections: list[str] = []
    for command in commands:
        instructions = command.instructions.strip()
        if not instructions:
            continue
        sections.extend(
            [
                f'<component_command name="{command.name}" alias="{command.slash_alias}">',
                instructions,
                "</component_command>",
            ]
        )
    if not sections:
        return base_prompt
    command_sections = "\n\n".join(sections)
    return (
        f"{base_prompt}\n\n"
        "<component_commands>\n"
        f"{command_sections}\n"
        "</component_commands>"
    )


def get_system_prompt(
    active_command_instructions: str | None = None,
    *,
    settings: "Settings | None" = None,
    excluded_tools: Iterable[str] | None = None,
    cwd: Path | None = None,
    explicit_skill_names: set[str] | None = None,
    visible_skill_names: tuple[str, ...] | None = None,
    visible_agent_names: tuple[str, ...] | None = None,
    explicit_agent_names: set[str] | None = None,
    workspace_directory_key: str | None = None,
) -> str:
    excluded_names = _active_tool_excluded_names(settings, excluded_tools)
    active_names = {spec.name for spec in get_tool_specs(excluded_names=excluded_names)}
    prompt = _append_workspace_memory(
        _append_project_rules(
            _resolve_base_prompt(
                settings=settings,
                excluded_tools=excluded_tools,
                cwd=cwd,
            ),
            cwd,
        ),
        cwd,
    )
    if "explore_workspace" in active_names:
        prompt = _append_available_skills(
            prompt,
            cwd,
            explicit_skill_names=explicit_skill_names,
            visible_skill_names=visible_skill_names,
            workspace_directory_key=workspace_directory_key,
        )
    if "sub_agent" in active_names:
        prompt = _append_available_sub_agents(
            prompt,
            cwd,
            explicit_agent_names=explicit_agent_names,
            visible_agent_names=visible_agent_names,
            workspace_directory_key=workspace_directory_key,
        )
    return _append_active_command(prompt, active_command_instructions)


def get_sub_agent_system_prompt(
    agent_prompt_override: str | None = None,
    *,
    settings: "Settings | None" = None,
    excluded_tools: Iterable[str] | None = None,
    cwd: Path | None = None,
    explicit_skill_names: set[str] | None = None,
    visible_skill_names: tuple[str, ...] | None = None,
    skill_source_label: str = "Sub-agent frontmatter",
    visible_agent_names: tuple[str, ...] | None = None,
    agent_source_label: str = "Sub-agent frontmatter",
    component_commands: Iterable["CommandConfig"] | None = None,
    workspace_directory_key: str | None = None,
) -> str:
    if agent_prompt_override is not None:
        agent_prompt_override = _append_component_commands(
            agent_prompt_override,
            component_commands,
        )
        base = _inject_tool_usage_rules(
            agent_prompt_override,
            _tool_usage_rules(settings=settings, excluded_tools=excluded_tools),
        )
    else:
        base = _resolve_base_prompt(
            settings=settings,
            excluded_tools=excluded_tools,
            cwd=cwd,
        )
    prompt = _append_workspace_memory(
        _append_project_rules(f"{base}\n\n{_SUB_AGENT_PROMPT}", cwd),
        cwd,
    )
    excluded_names = _active_tool_excluded_names(settings, excluded_tools)
    active_names = {spec.name for spec in get_tool_specs(excluded_names=excluded_names)}
    if "explore_workspace" in active_names:
        prompt = _append_available_skills(
            prompt,
            cwd,
            explicit_skill_names=explicit_skill_names,
            visible_skill_names=visible_skill_names,
            source_label=skill_source_label,
            workspace_directory_key=workspace_directory_key,
        )
    if "sub_agent" in active_names:
        prompt = _append_available_sub_agents(
            prompt,
            cwd,
            visible_agent_names=visible_agent_names,
            source_label=agent_source_label,
            workspace_directory_key=workspace_directory_key,
        )
    return prompt
