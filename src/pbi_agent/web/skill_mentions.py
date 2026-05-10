"""Project skill mention search for web composer `$skill` completions."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from pbi_agent.skills.project_catalog import discover_installed_project_skills


@dataclass(slots=True, frozen=True)
class SkillMentionItem:
    name: str
    description: str
    path: str


def search_skill_mentions(
    query: str,
    *,
    root: Path,
    limit: int = 20,
) -> list[SkillMentionItem]:
    """Return installed project skills matching ``query`` for composer completions."""
    normalized_query = query.strip().casefold()
    skills = [
        SkillMentionItem(
            name=skill.name,
            description=skill.description,
            path=_display_path(skill.location, root=root),
        )
        for skill in discover_installed_project_skills(workspace=root)
    ]
    if not normalized_query:
        return sorted(
            skills, key=lambda item: (item.name.casefold(), item.path.casefold())
        )[:limit]

    ranked: list[tuple[int, str, SkillMentionItem]] = []
    for skill in skills:
        name = skill.name.casefold()
        description = skill.description.casefold()
        haystack = f"{name} {description}"
        if normalized_query not in haystack:
            continue
        if name == normalized_query:
            score = 0
        elif name.startswith(normalized_query):
            score = 1
        elif normalized_query in name:
            score = 2
        else:
            score = 3
        ranked.append((score, name, skill))

    ranked.sort(key=lambda item: (item[0], item[1], item[2].path.casefold()))
    return [item for _score, _name, item in ranked[:limit]]


def _display_path(path: Path, *, root: Path) -> str:
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return str(path)


__all__ = ["SkillMentionItem", "search_skill_mentions"]
