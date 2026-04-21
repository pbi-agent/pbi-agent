from __future__ import annotations

import sys
import re

from dataclasses import dataclass
from pathlib import Path

from pbi_agent.frontmatter import FrontmatterParseError, parse_simple_frontmatter

from rich.console import Console
from rich.table import Table

_DISCOVERY_ROOT = Path(".agents/skills")


class SkillManifestError(ValueError):
    """Raised when a project skill manifest does not match the supported shape."""


@dataclass(slots=True, frozen=True)
class ProjectSkillManifest:
    name: str
    description: str
    location: Path


def render_installed_project_skills(
    workspace: Path | None = None,
    *,
    console: Console | None = None,
) -> int:
    project_skills = discover_installed_project_skills(workspace=workspace)
    active_console = console or Console()

    if not project_skills:
        active_console.print(
            "[dim]No project skills discovered under[/dim] .agents/skills/"
        )
        return 0

    table = Table(title="Project Skills", title_style="bold cyan")
    table.add_column("Name", style="green")
    table.add_column("Description")
    for skill in project_skills:
        table.add_row(skill.name, skill.description)
    active_console.print(table)
    return 0


def discover_installed_project_skills(
    workspace: Path | None = None,
) -> list[ProjectSkillManifest]:
    root = (workspace or Path.cwd()).resolve()
    skills_root = root / _DISCOVERY_ROOT
    if not skills_root.is_dir():
        return []

    discovered: list[ProjectSkillManifest] = []
    for skill_dir in sorted(
        skills_root.iterdir(), key=lambda item: item.name.casefold()
    ):
        if not skill_dir.is_dir():
            continue

        skill_path = skill_dir / "SKILL.md"
        if not skill_path.is_file():
            continue

        try:
            skill = load_project_skill_manifest(skill_path)
        except SkillManifestError as exc:
            _warn(f"Skipping skill at {skill_path}: {exc}")
            continue

        if skill_dir.name != skill.name:
            _warn(
                f"Skill '{skill.name}' does not match parent directory "
                f"'{skill_dir.name}'; loading anyway."
            )
        discovered.append(skill)

    return discovered


def load_project_skill_manifest(skill_path: Path) -> ProjectSkillManifest:
    try:
        content = skill_path.read_text(encoding="utf-8")
    except OSError as exc:
        raise SkillManifestError("file is unreadable.") from exc

    frontmatter = _extract_frontmatter(content)
    metadata = _parse_frontmatter(frontmatter)

    name = metadata.get("name")
    description = metadata.get("description")
    if not isinstance(name, str) or not name.strip():
        raise SkillManifestError("missing non-empty 'name'.")
    if not isinstance(description, str) or not description.strip():
        raise SkillManifestError("missing non-empty 'description'.")

    return ProjectSkillManifest(
        name=name.strip(),
        description=description.strip(),
        location=skill_path.resolve(),
    )


def _warn(message: str) -> None:
    print(message, file=sys.stderr)


def _extract_frontmatter(content: str) -> str:
    match = re.match(
        r"\A---\s*\r?\n(.*?)\r?\n---(?:\s*\r?\n|\s*\Z)",
        content,
        re.DOTALL,
    )
    if match is None:
        raise SkillManifestError("missing YAML frontmatter.")
    return match.group(1)


def _parse_frontmatter(frontmatter: str) -> dict[str, str]:
    try:
        return parse_simple_frontmatter(
            frontmatter,
            block_scalar_keys=frozenset({"description"}),
            include_keys=frozenset({"name", "description"}),
        )
    except FrontmatterParseError as exc:
        raise SkillManifestError(str(exc)) from exc
