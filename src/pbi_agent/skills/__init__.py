"""Dynamic skill definition loader.

Scans this directory for *.md files and provides:
- list_available_skills() -> [(name, brief_description), ...]
- load_skill(name)        -> full markdown content or None
"""

from __future__ import annotations

from pathlib import Path

_SKILLS_DIR = Path(__file__).parent


def list_available_skills() -> list[tuple[str, str]]:
    """Return (name, brief_description) for every .md file in the skills dir."""
    skills: list[tuple[str, str]] = []
    for md_file in sorted(_SKILLS_DIR.glob("*.md")):
        name = md_file.stem
        brief = _extract_brief(md_file)
        skills.append((name, brief))
    return skills


def load_skill(name: str) -> str | None:
    """Return full markdown content for the named skill, or None if not found."""
    path = _SKILLS_DIR / f"{name}.md"
    if not path.is_file():
        return None
    return path.read_text(encoding="utf-8")


def _extract_brief(path: Path) -> str:
    """Extract the first non-heading, non-empty line as the brief description."""
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        return stripped
    return "No description available."
