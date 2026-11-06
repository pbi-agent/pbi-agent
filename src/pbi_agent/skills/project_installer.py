from __future__ import annotations

import shutil
import sys
from dataclasses import dataclass
from pathlib import Path
from tempfile import TemporaryDirectory

from rich.console import Console
from rich.table import Table

from pbi_agent.project_sources import (
    GitHubProjectSource,
    LocalProjectSource,
    ProjectSourceError,
    materialize_project_source,
    parse_github_project_source,
    parse_project_source,
    resolve_github_source_ref,
    sanitize_project_subpath,
)
from pbi_agent.skills.project_catalog import (
    SkillManifestError,
    load_project_skill_manifest,
)

DEFAULT_SKILLS_SOURCE = "pbi-agent/skills"
_INSTALL_ROOT = Path(".agents/skills")

GitHubSkillSource = GitHubProjectSource
LocalSkillSource = LocalProjectSource


class ProjectSkillInstallError(ValueError):
    """Raised when project skill installation fails."""


@dataclass(slots=True, frozen=True)
class RemoteSkillCandidateSummary:
    name: str
    description: str
    subpath: str | None


@dataclass(slots=True, frozen=True)
class RemoteSkillListing:
    source: str
    ref: str | None
    candidates: list[RemoteSkillCandidateSummary]


@dataclass(slots=True, frozen=True)
class ProjectSkillInstallResult:
    name: str
    install_path: Path
    source: str
    ref: str | None
    subpath: str | None


@dataclass(slots=True, frozen=True)
class _RemoteSkillCandidate:
    name: str
    description: str
    skill_dir: Path
    repo_subpath: str | None


def resolve_default_skills_source() -> str:
    return DEFAULT_SKILLS_SOURCE


def render_remote_skill_listing(
    listing: RemoteSkillListing,
    *,
    console: Console | None = None,
) -> int:
    active_console = console or Console()
    table = Table(title="Available Skills", title_style="bold cyan")
    table.add_column("Name", style="green")
    table.add_column("Description")
    table.add_column("Source Path", style="dim")
    for candidate in listing.candidates:
        table.add_row(candidate.name, candidate.description, candidate.subpath or ".")
    active_console.print(table)
    return 0


def list_remote_project_skills(source: str) -> RemoteSkillListing:
    parsed_source = parse_project_skill_source(source)
    with TemporaryDirectory(prefix="pbi-agent-skill-") as temp_dir:
        materialized = _materialize_skill_source(
            parsed_source,
            temp_root=Path(temp_dir),
        )
        candidates = _discover_remote_skill_candidates(
            repo_root=materialized.repo_root,
            resolved_root=materialized.resolved_root,
        )

    if not candidates:
        raise ProjectSkillInstallError(
            "No valid skills found. Skills require a SKILL.md with name and description."
        )

    return RemoteSkillListing(
        source=source,
        ref=materialized.ref,
        candidates=[
            RemoteSkillCandidateSummary(
                name=candidate.name,
                description=candidate.description,
                subpath=candidate.repo_subpath,
            )
            for candidate in candidates
        ],
    )


def install_project_skill(
    source: str,
    *,
    skill_name: str | None = None,
    force: bool = False,
    workspace: Path | None = None,
) -> ProjectSkillInstallResult:
    parsed_source = parse_project_skill_source(source)
    install_workspace = (workspace or Path.cwd()).resolve()
    install_root = (install_workspace / _INSTALL_ROOT).resolve()

    with TemporaryDirectory(prefix="pbi-agent-skill-") as temp_dir:
        materialized = _materialize_skill_source(
            parsed_source,
            temp_root=Path(temp_dir),
        )
        candidates = _discover_remote_skill_candidates(
            repo_root=materialized.repo_root,
            resolved_root=materialized.resolved_root,
        )
        selected = _select_remote_skill_candidate(candidates, skill_name=skill_name)
        target_dir = _resolve_install_target(
            install_root=install_root,
            skill_name=selected.name,
        )
        _prepare_install_target(target_dir, force=force)
        shutil.copytree(selected.skill_dir, target_dir)

    return ProjectSkillInstallResult(
        name=selected.name,
        install_path=target_dir,
        source=source,
        ref=materialized.ref,
        subpath=selected.repo_subpath,
    )


def parse_project_skill_source(source: str) -> GitHubSkillSource | LocalSkillSource:
    try:
        return parse_project_source(source, source_label="skill")
    except ProjectSourceError as exc:
        raise ProjectSkillInstallError(str(exc)) from exc


def parse_github_skill_source(source: str) -> GitHubSkillSource:
    try:
        return parse_github_project_source(source, source_label="skill")
    except ProjectSourceError as exc:
        raise ProjectSkillInstallError(str(exc)) from exc


def sanitize_skill_subpath(subpath: str) -> str:
    try:
        return sanitize_project_subpath(subpath, source_label="skill")
    except ProjectSourceError as exc:
        raise ProjectSkillInstallError(str(exc)) from exc


def resolve_github_skill_source_ref(source: GitHubSkillSource) -> str:
    try:
        return resolve_github_source_ref(source, source_label="skill")
    except ProjectSourceError as exc:
        raise ProjectSkillInstallError(str(exc)) from exc


def _materialize_skill_source(
    source: GitHubSkillSource | LocalSkillSource,
    *,
    temp_root: Path,
):
    try:
        return materialize_project_source(
            source,
            temp_root=temp_root,
            source_label="skill",
            user_agent="pbi-agent-skills",
        )
    except ProjectSourceError as exc:
        raise ProjectSkillInstallError(str(exc)) from exc


def _discover_remote_skill_candidates(
    *,
    repo_root: Path,
    resolved_root: Path,
) -> list[_RemoteSkillCandidate]:
    candidate_dirs: list[Path] = []
    seen_dirs: set[Path] = set()

    def enqueue(skill_dir: Path) -> None:
        resolved_dir = skill_dir.resolve()
        if resolved_dir in seen_dirs:
            return
        seen_dirs.add(resolved_dir)
        candidate_dirs.append(resolved_dir)

    if (resolved_root / "SKILL.md").is_file():
        enqueue(resolved_root)

    for container in (resolved_root / "skills",):
        if not container.is_dir():
            continue
        for child in sorted(container.iterdir(), key=lambda item: item.name.casefold()):
            if child.is_dir() and (child / "SKILL.md").is_file():
                enqueue(child)

    candidates: list[_RemoteSkillCandidate] = []
    for skill_dir in candidate_dirs:
        try:
            manifest = load_project_skill_manifest(skill_dir / "SKILL.md")
        except SkillManifestError as exc:
            _warn(
                f"Skipping skill at {skill_dir / 'SKILL.md'}: unsupported manifest: {exc}"
            )
            continue

        repo_subpath = skill_dir.relative_to(repo_root).as_posix()
        candidates.append(
            _RemoteSkillCandidate(
                name=manifest.name,
                description=manifest.description,
                skill_dir=skill_dir,
                repo_subpath=None if repo_subpath == "." else repo_subpath,
            )
        )

    return candidates


def _warn(message: str) -> None:
    print(message, file=sys.stderr)


def _select_remote_skill_candidate(
    candidates: list[_RemoteSkillCandidate],
    *,
    skill_name: str | None,
) -> _RemoteSkillCandidate:
    if not candidates:
        raise ProjectSkillInstallError(
            "No valid skills found. Skills require a SKILL.md with name and description."
        )

    if skill_name is None:
        if len(candidates) != 1:
            raise ProjectSkillInstallError(
                "Multiple skills were found in the source. Re-run with --list or "
                "--skill <name>."
            )
        return candidates[0]

    matched = [
        candidate
        for candidate in candidates
        if candidate.name.casefold() == skill_name.casefold()
    ]
    if not matched:
        available = ", ".join(candidate.name for candidate in candidates)
        raise ProjectSkillInstallError(
            f"Unknown skill {skill_name!r}. Available skills: {available}."
        )
    if len(matched) > 1:
        raise ProjectSkillInstallError(
            f"Skill name {skill_name!r} matched multiple remote skill bundles."
        )
    return matched[0]


def _resolve_install_target(*, install_root: Path, skill_name: str) -> Path:
    normalized_name = skill_name.strip()
    if not normalized_name:
        raise ProjectSkillInstallError("Skill manifest name must not be empty.")
    if (
        "/" in normalized_name
        or "\\" in normalized_name
        or normalized_name in {".", ".."}
    ):
        raise ProjectSkillInstallError(
            "Unsupported skill name "
            f"{skill_name!r}. Skill install names must be a single path segment."
        )

    install_root.mkdir(parents=True, exist_ok=True)
    target_dir = (install_root / normalized_name).resolve()
    if target_dir.parent != install_root.resolve():
        raise ProjectSkillInstallError(
            f"Path {target_dir} escapes the allowed root {install_root.resolve()}."
        )
    return target_dir


def _prepare_install_target(target_dir: Path, *, force: bool) -> None:
    if not target_dir.exists():
        return

    if not force:
        raise ProjectSkillInstallError(
            f"Skill already installed at {target_dir}. Re-run with --force to replace it."
        )

    if target_dir.is_symlink() or target_dir.is_file():
        target_dir.unlink()
        return
    shutil.rmtree(target_dir)
