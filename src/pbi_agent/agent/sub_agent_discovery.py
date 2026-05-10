from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path
import re

from pbi_agent.frontmatter import FrontmatterParseError, parse_simple_frontmatter

from rich.console import Console
from rich.table import Table

_DISCOVERY_ROOT = Path(".agents") / "agents"


@dataclass(slots=True, frozen=True)
class ProjectSubAgent:
    name: str
    description: str
    system_prompt: str
    location: Path
    model_profile_id: str | None = None


def format_project_sub_agents_markdown(workspace: Path | None = None) -> str:
    agents = discover_project_sub_agents(workspace)
    lines = ["### Sub-Agents", ""]
    lines.append(
        "Default: use `sub_agent` without `agent_type` for the built-in generalist sub-agent."
    )
    if not agents:
        lines.extend(
            ["", "No project sub-agents discovered under `.agents/agents/*.md`."]
        )
        return "\n".join(lines)

    lines.append("")
    for agent in agents:
        lines.append(f"- `{agent.name}`: {agent.description}")
    return "\n".join(lines)


def render_installed_project_sub_agents(
    workspace: Path | None = None,
    *,
    console: Console | None = None,
) -> int:
    agents = discover_project_sub_agents(workspace=workspace)
    active_console = console or Console()

    if not agents:
        active_console.print(
            "[dim]No project agents discovered under[/dim] .agents/agents/"
        )
        return 0

    table = Table(title="Project Agents", title_style="bold cyan")
    table.add_column("Name", style="green")
    table.add_column("Description")
    table.add_column("Location", style="dim")
    for agent in agents:
        description = agent.description
        if agent.model_profile_id:
            description = f"{description} [profile: {agent.model_profile_id}]"
        table.add_row(agent.name, description, str(agent.location))
    active_console.print(table)
    return 0


def _warn(message: str) -> None:
    print(message, file=sys.stderr)


def discover_project_sub_agents(workspace: Path | None = None) -> list[ProjectSubAgent]:
    root = (workspace or Path.cwd()).resolve()
    agents_root = root / _DISCOVERY_ROOT
    if not agents_root.is_dir():
        return []

    discovered: list[ProjectSubAgent] = []
    seen_names: dict[str, Path] = {}
    for agent_path in sorted(
        agents_root.iterdir(), key=lambda item: item.name.casefold()
    ):
        if not agent_path.is_file() or agent_path.suffix != ".md":
            continue

        agent = _load_project_sub_agent(agent_path)
        if agent is None:
            continue
        if agent.name in seen_names:
            _warn(
                f"Skipping sub-agent at {agent_path}: duplicate name {agent.name!r}; "
                f"first loaded from {seen_names[agent.name]}."
            )
            continue
        seen_names[agent.name] = agent.location
        discovered.append(agent)

    return discovered


def get_project_sub_agent_by_name(
    name: str, workspace: Path | None = None
) -> ProjectSubAgent | None:
    for agent in discover_project_sub_agents(workspace):
        if agent.name == name:
            return agent
    return None


def _load_project_sub_agent(agent_path: Path) -> ProjectSubAgent | None:
    try:
        content = agent_path.read_text(encoding="utf-8")
    except OSError:
        _warn(f"Skipping sub-agent at {agent_path}: file is unreadable.")
        return None

    frontmatter = _extract_frontmatter(content, agent_path)
    if frontmatter is None:
        return None

    metadata = _parse_frontmatter(frontmatter, agent_path)
    if metadata is None:
        return None

    name = metadata.get("name")
    description = metadata.get("description")
    if not isinstance(name, str) or not name.strip():
        _warn(f"Skipping sub-agent at {agent_path}: missing non-empty 'name'.")
        return None
    if not isinstance(description, str) or not description.strip():
        _warn(f"Skipping sub-agent at {agent_path}: missing non-empty 'description'.")
        return None
    unsupported_keys = sorted(
        set(metadata) - {"name", "description", "model_profile_id"}
    )
    if unsupported_keys:
        _warn(
            f"Skipping sub-agent at {agent_path}: unsupported frontmatter keys: "
            f"{', '.join(repr(key) for key in unsupported_keys)}."
        )
        return None

    model_profile_id = metadata.get("model_profile_id")
    normalized_model_profile_id: str | None = None
    if isinstance(model_profile_id, str) and model_profile_id.strip():
        from pbi_agent.config import ConfigError, slugify

        try:
            normalized_model_profile_id = slugify(model_profile_id.strip())
        except ConfigError:
            _warn(f"Skipping sub-agent at {agent_path}: invalid 'model_profile_id'.")
            return None

    normalized_name = name.strip()
    return ProjectSubAgent(
        name=normalized_name,
        description=description.strip(),
        system_prompt=_extract_body(content).strip(),
        location=agent_path.resolve(),
        model_profile_id=normalized_model_profile_id,
    )


def _extract_body(content: str) -> str:
    match = re.match(
        r"\A---\s*\r?\n.*?\r?\n---[ \t]*(?:\r?\n|\Z)",
        content,
        re.DOTALL,
    )
    if match is None:
        return content
    return content[match.end() :]


def _extract_frontmatter(content: str, agent_path: Path) -> str | None:
    match = re.match(
        r"\A---\s*\r?\n(.*?)\r?\n---(?:\s*\r?\n|\s*\Z)",
        content,
        re.DOTALL,
    )
    if match is None:
        _warn(f"Skipping sub-agent at {agent_path}: missing YAML frontmatter.")
        return None
    return match.group(1)


def _parse_frontmatter(frontmatter: str, agent_path: Path) -> dict[str, str] | None:
    try:
        return parse_simple_frontmatter(
            frontmatter,
            block_scalar_keys=frozenset({"description"}),
        )
    except FrontmatterParseError as exc:
        _warn(f"Skipping sub-agent at {agent_path}: {exc}")
        return None
