from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path
import re

_DISCOVERY_ROOT = Path(".agents/skills")


@dataclass(slots=True, frozen=True)
class ProjectSkill:
    name: str
    description: str
    location: Path


def format_project_skills_markdown(workspace: Path | None = None) -> str:
    skills = discover_project_skills(workspace)
    if not skills:
        return (
            "### Project Skills\n\n"
            "No project skills discovered under `.agents/skills/`."
        )

    lines = ["### Project Skills", ""]
    for skill in skills:
        lines.append(f"- `{skill.name}`: {skill.description}")
        lines.append(f"  `{skill.location}`")
    return "\n".join(lines)


def _warn(message: str) -> None:
    print(message, file=sys.stderr)


def discover_project_skills(workspace: Path | None = None) -> list[ProjectSkill]:
    root = (workspace or Path.cwd()).resolve()
    skills_root = root / _DISCOVERY_ROOT
    if not skills_root.is_dir():
        return []

    discovered: list[ProjectSkill] = []
    for skill_dir in sorted(
        skills_root.iterdir(), key=lambda item: item.name.casefold()
    ):
        if not skill_dir.is_dir():
            continue

        skill_path = skill_dir / "SKILL.md"
        if not skill_path.is_file():
            continue

        skill = _load_project_skill(skill_path)
        if skill is not None:
            discovered.append(skill)

    return discovered


def _load_project_skill(skill_path: Path) -> ProjectSkill | None:
    try:
        content = skill_path.read_text(encoding="utf-8")
    except OSError:
        _warn(f"Skipping skill at {skill_path}: file is unreadable.")
        return None

    frontmatter = _extract_frontmatter(content, skill_path)
    if frontmatter is None:
        return None

    metadata = _parse_frontmatter(frontmatter, skill_path)
    if metadata is None:
        return None

    name = metadata.get("name")
    description = metadata.get("description")
    if not isinstance(name, str) or not name.strip():
        _warn(f"Skipping skill at {skill_path}: missing non-empty 'name'.")
        return None
    if not isinstance(description, str) or not description.strip():
        _warn(f"Skipping skill at {skill_path}: missing non-empty 'description'.")
        return None

    normalized_name = name.strip()
    if skill_path.parent.name != normalized_name:
        _warn(
            f"Skill '{normalized_name}' does not match parent directory "
            f"'{skill_path.parent.name}'; loading anyway."
        )

    return ProjectSkill(
        name=normalized_name,
        description=description.strip(),
        location=skill_path.resolve(),
    )


def _extract_frontmatter(content: str, skill_path: Path) -> str | None:
    match = re.match(
        r"\A---\s*\r?\n(.*?)\r?\n---(?:\s*\r?\n|\s*\Z)",
        content,
        re.DOTALL,
    )
    if match is None:
        _warn(f"Skipping skill at {skill_path}: missing YAML frontmatter.")
        return None
    return match.group(1)


def _parse_frontmatter(frontmatter: str, skill_path: Path) -> dict[str, str] | None:
    """Parse simple ``key: value`` frontmatter without external dependencies."""
    result: dict[str, str] = {}
    for line in frontmatter.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        colon_idx = stripped.find(":")
        if colon_idx < 0:
            _warn(
                f"Skipping skill at {skill_path}: "
                f"frontmatter line is not a key-value pair: {stripped!r}."
            )
            return None
        key = stripped[:colon_idx].strip()
        value = stripped[colon_idx + 1 :].strip()
        if not key:
            _warn(f"Skipping skill at {skill_path}: frontmatter contains an empty key.")
            return None
        result[key] = value
    if not result:
        _warn(f"Skipping skill at {skill_path}: frontmatter is empty.")
        return None
    return result
