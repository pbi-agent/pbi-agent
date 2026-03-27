from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path
import re

_DISCOVERY_ROOT = Path(".agents")


@dataclass(slots=True, frozen=True)
class ProjectSubAgent:
    name: str
    description: str
    system_prompt: str
    location: Path
    model: str | None = None
    reasoning_effort: str | None = None


def format_project_sub_agents_markdown(
    workspace: Path | None = None,
    *,
    reloaded: bool = False,
) -> str:
    agents = discover_project_sub_agents(workspace)
    lines = ["### Sub-Agents", ""]
    if reloaded:
        lines.append("Reloaded project sub-agent definitions from `.agents/*.md`.")
        lines.append("")
    lines.append(
        "Default: use `sub_agent` without `agent_type` for the built-in generalist sub-agent."
    )
    if not agents:
        lines.extend(["", "No project sub-agents discovered under `.agents/*.md`."])
        return "\n".join(lines)

    lines.append("")
    for agent in agents:
        lines.append(f"- `{agent.name}`: {agent.description}")
    return "\n".join(lines)


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
    model = metadata.get("model")
    reasoning_effort = metadata.get("reasoning_effort")
    if not isinstance(name, str) or not name.strip():
        _warn(f"Skipping sub-agent at {agent_path}: missing non-empty 'name'.")
        return None
    if not isinstance(description, str) or not description.strip():
        _warn(f"Skipping sub-agent at {agent_path}: missing non-empty 'description'.")
        return None
    if model is not None and not isinstance(model, str):
        _warn(f"Skipping sub-agent at {agent_path}: 'model' must be a string.")
        return None
    if reasoning_effort is not None and not isinstance(reasoning_effort, str):
        _warn(
            f"Skipping sub-agent at {agent_path}: 'reasoning_effort' must be a string."
        )
        return None
    if reasoning_effort is not None and reasoning_effort not in {
        "low",
        "medium",
        "high",
        "xhigh",
    }:
        _warn(
            f"Skipping sub-agent at {agent_path}: 'reasoning_effort' must be one of: "
            "low, medium, high, xhigh."
        )
        return None

    normalized_name = name.strip()
    return ProjectSubAgent(
        name=normalized_name,
        description=description.strip(),
        system_prompt=_extract_body(content).strip(),
        location=agent_path.resolve(),
        model=model.strip() if isinstance(model, str) and model.strip() else None,
        reasoning_effort=(
            reasoning_effort.strip()
            if isinstance(reasoning_effort, str) and reasoning_effort.strip()
            else None
        ),
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
    """Parse a limited frontmatter subset.

    Supported syntax:
    - ``key: value`` scalar pairs
    - blank lines and ``#`` comments
    - ``|`` and ``>`` block scalars with indented content
    - optional ``model`` and ``reasoning_effort`` scalar keys used for runtime
      child-agent configuration

    This is intentionally not a general YAML parser. Unsupported YAML constructs
    such as lists, nested mappings, and anchors are rejected.
    """
    result: dict[str, str] = {}
    lines = frontmatter.splitlines()
    index = 0
    while index < len(lines):
        line = lines[index]
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            index += 1
            continue

        indent = len(line) - len(line.lstrip(" "))
        colon_idx = stripped.find(":")
        if colon_idx < 0:
            _warn(
                f"Skipping sub-agent at {agent_path}: "
                f"frontmatter line is not a key-value pair: {stripped!r}."
            )
            return None

        key = stripped[:colon_idx].strip()
        value = stripped[colon_idx + 1 :].strip()
        if not key:
            _warn(
                f"Skipping sub-agent at {agent_path}: frontmatter contains an empty key."
            )
            return None

        if not value:
            next_index = index + 1
            while next_index < len(lines):
                next_line = lines[next_index]
                next_stripped = next_line.strip()
                if not next_stripped or next_stripped.startswith("#"):
                    next_index += 1
                    continue
                next_indent = len(next_line) - len(next_line.lstrip(" "))
                if next_indent > indent:
                    _warn(
                        f"Skipping sub-agent at {agent_path}: unsupported YAML "
                        f"structure for key {key!r}; only scalar values and block "
                        "scalars are supported."
                    )
                    return None
                break

        if value in {"|", ">"}:
            block_lines: list[str] = []
            index += 1
            while index < len(lines):
                next_line = lines[index]
                next_stripped = next_line.strip()
                next_indent = len(next_line) - len(next_line.lstrip(" "))
                if next_stripped and next_indent <= indent:
                    break
                if not next_stripped:
                    block_lines.append("")
                else:
                    block_lines.append(next_line[indent + 1 :])
                index += 1
            if value == "|":
                result[key] = "\n".join(block_lines)
            else:
                result[key] = " ".join(
                    part.strip() for part in block_lines if part.strip()
                )
            continue

        result[key] = _parse_scalar(value)
        index += 1

    if not result:
        _warn(f"Skipping sub-agent at {agent_path}: frontmatter is empty.")
        return None
    return result


def _parse_scalar(value: str) -> str:
    if len(value) >= 2 and value[:1] == value[-1:] and value[0] in {"'", '"'}:
        return value[1:-1]
    return value
