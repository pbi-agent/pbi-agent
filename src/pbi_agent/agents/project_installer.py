from __future__ import annotations

import shutil

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
)

DEFAULT_AGENTS_SOURCE = "pbi-agent/agents"
_INSTALL_ROOT = Path(".agents/agents")

GitHubAgentSource = GitHubProjectSource
LocalAgentSource = LocalProjectSource


class ProjectAgentInstallError(ValueError):
    """Raised when project agent installation fails."""


@dataclass(slots=True, frozen=True)
class RemoteAgentCandidateSummary:
    agent_name: str
    description: str
    subpath: str | None


@dataclass(slots=True, frozen=True)
class RemoteAgentListing:
    source: str
    ref: str | None
    candidates: list[RemoteAgentCandidateSummary]


@dataclass(slots=True, frozen=True)
class ProjectAgentInstallResult:
    agent_name: str
    install_path: Path
    source: str
    ref: str | None
    subpath: str | None


@dataclass(slots=True, frozen=True)
class _RemoteAgentCandidate:
    agent_name: str
    description: str
    system_prompt: str
    source_text: str
    source_path: Path
    repo_subpath: str | None


def resolve_default_agents_source() -> str:
    return DEFAULT_AGENTS_SOURCE


def render_remote_agent_listing(
    listing: RemoteAgentListing,
    *,
    console: Console | None = None,
) -> int:
    active_console = console or Console()
    table = Table(title="Available Agents", title_style="bold cyan")
    table.add_column("Name", style="green")
    table.add_column("Description")
    table.add_column("Source Path", style="dim")
    for candidate in listing.candidates:
        table.add_row(
            candidate.agent_name,
            candidate.description,
            candidate.subpath or ".",
        )
    active_console.print(table)
    return 0


def list_remote_project_agents(source: str) -> RemoteAgentListing:
    parsed_source = parse_project_agent_source(source)
    with TemporaryDirectory(prefix="pbi-agent-agent-") as temp_dir:
        materialized = materialize_project_source(
            parsed_source,
            temp_root=Path(temp_dir),
            source_label="agent",
            user_agent="pbi-agent-agents",
            allow_local_file=True,
        )
        candidates = _discover_remote_agent_candidates(
            repo_root=materialized.repo_root,
            resolved_root=materialized.resolved_root,
            include_root_markdown=_should_include_root_markdown(
                parsed_source=parsed_source,
                repo_root=materialized.repo_root,
                resolved_root=materialized.resolved_root,
            ),
        )

    if not candidates:
        raise ProjectAgentInstallError(
            "No valid agents found. Agents require Markdown files with supported frontmatter."
        )

    return RemoteAgentListing(
        source=source,
        ref=materialized.ref,
        candidates=[
            RemoteAgentCandidateSummary(
                agent_name=candidate.agent_name,
                description=candidate.description,
                subpath=candidate.repo_subpath,
            )
            for candidate in candidates
        ],
    )


def install_project_agent(
    source: str,
    *,
    agent_name: str | None = None,
    force: bool = False,
    workspace: Path | None = None,
) -> ProjectAgentInstallResult:
    parsed_source = parse_project_agent_source(source)
    install_workspace = (workspace or Path.cwd()).resolve()
    install_root = (install_workspace / _INSTALL_ROOT).resolve()

    with TemporaryDirectory(prefix="pbi-agent-agent-") as temp_dir:
        materialized = materialize_project_source(
            parsed_source,
            temp_root=Path(temp_dir),
            source_label="agent",
            user_agent="pbi-agent-agents",
            allow_local_file=True,
        )
        candidates = _discover_remote_agent_candidates(
            repo_root=materialized.repo_root,
            resolved_root=materialized.resolved_root,
            include_root_markdown=_should_include_root_markdown(
                parsed_source=parsed_source,
                repo_root=materialized.repo_root,
                resolved_root=materialized.resolved_root,
            ),
        )
        selected = _select_remote_agent_candidate(
            candidates,
            agent_name=agent_name,
        )
        target_path = _resolve_install_target(
            install_root=install_root,
            agent_name=selected.agent_name,
        )
        _prepare_install_target(target_path, force=force)
        target_path.write_text(selected.source_text, encoding="utf-8")

    return ProjectAgentInstallResult(
        agent_name=selected.agent_name,
        install_path=target_path,
        source=source,
        ref=materialized.ref,
        subpath=selected.repo_subpath,
    )


def parse_project_agent_source(
    source: str,
) -> GitHubAgentSource | LocalAgentSource:
    try:
        return parse_project_source(source, source_label="agent")
    except ProjectSourceError as exc:
        raise ProjectAgentInstallError(str(exc)) from exc


def parse_github_agent_source(source: str) -> GitHubAgentSource:
    try:
        return parse_github_project_source(source, source_label="agent")
    except ProjectSourceError as exc:
        raise ProjectAgentInstallError(str(exc)) from exc


def _discover_remote_agent_candidates(
    *,
    repo_root: Path,
    resolved_root: Path,
    include_root_markdown: bool,
) -> list[_RemoteAgentCandidate]:
    from pbi_agent.agent.sub_agent_discovery import _load_project_sub_agent

    candidate_paths: list[Path] = []
    seen_paths: set[Path] = set()

    def enqueue(agent_path: Path) -> None:
        resolved_path = agent_path.resolve()
        if resolved_path in seen_paths:
            return
        seen_paths.add(resolved_path)
        candidate_paths.append(resolved_path)

    if resolved_root.is_file():
        if resolved_root.suffix == ".md":
            enqueue(resolved_root)
    else:
        if include_root_markdown:
            for child in sorted(
                resolved_root.iterdir(), key=lambda item: item.name.casefold()
            ):
                if child.is_file() and child.suffix == ".md":
                    enqueue(child)

        container = resolved_root / "agents"
        if container.is_dir():
            for child in sorted(
                container.iterdir(), key=lambda item: item.name.casefold()
            ):
                if child.is_file() and child.suffix == ".md":
                    enqueue(child)

    candidates: list[_RemoteAgentCandidate] = []
    seen_names: set[str] = set()
    for agent_path in candidate_paths:
        loaded = _load_project_sub_agent(agent_path)
        if loaded is None or loaded.name in seen_names:
            continue
        seen_names.add(loaded.name)
        repo_subpath = agent_path.relative_to(repo_root).as_posix()
        candidates.append(
            _RemoteAgentCandidate(
                agent_name=loaded.name,
                description=loaded.description,
                system_prompt=loaded.system_prompt,
                source_text=agent_path.read_text(encoding="utf-8"),
                source_path=agent_path,
                repo_subpath=None if repo_subpath == "." else repo_subpath,
            )
        )

    return candidates


def _should_include_root_markdown(
    *,
    parsed_source: GitHubAgentSource | LocalAgentSource,
    repo_root: Path,
    resolved_root: Path,
) -> bool:
    if resolved_root.is_file():
        return True
    if resolved_root != repo_root:
        return True
    return (
        isinstance(parsed_source, LocalAgentSource) and resolved_root.name == "agents"
    )


def _select_remote_agent_candidate(
    candidates: list[_RemoteAgentCandidate],
    *,
    agent_name: str | None,
) -> _RemoteAgentCandidate:
    if not candidates:
        raise ProjectAgentInstallError(
            "No valid agents found. Agents require Markdown files with supported frontmatter."
        )

    if agent_name is not None:
        normalized_name = agent_name.strip()
        for candidate in candidates:
            if candidate.agent_name == normalized_name:
                return candidate
        available = ", ".join(candidate.agent_name for candidate in candidates)
        raise ProjectAgentInstallError(
            f"Agent {agent_name!r} was not found in this source. Available agents: {available}."
        )

    if len(candidates) == 1:
        return candidates[0]

    available = ", ".join(candidate.agent_name for candidate in candidates)
    raise ProjectAgentInstallError(
        "Source contains multiple agents. Re-run with --list or --agent <name>. "
        f"Available agents: {available}."
    )


def _resolve_install_target(*, install_root: Path, agent_name: str) -> Path:
    normalized_name = agent_name.strip()
    if not normalized_name:
        raise ProjectAgentInstallError("Agent name must not be empty.")
    if (
        "/" in normalized_name
        or "\\" in normalized_name
        or normalized_name in {".", ".."}
    ):
        raise ProjectAgentInstallError(
            "Unsupported agent name "
            f"{agent_name!r}. Agent install names must be a single path segment."
        )

    install_root.mkdir(parents=True, exist_ok=True)
    target_path = (install_root / f"{normalized_name}.md").resolve()
    if target_path.parent != install_root.resolve():
        raise ProjectAgentInstallError(
            f"Path {target_path} escapes the allowed root {install_root.resolve()}."
        )
    return target_path


def _prepare_install_target(target_path: Path, *, force: bool) -> None:
    target_path.parent.mkdir(parents=True, exist_ok=True)
    if target_path.exists():
        if not force:
            raise ProjectAgentInstallError(
                f"Agent '{target_path.stem}' is already installed at {target_path}. "
                "Use --force to replace it."
            )
        if target_path.is_dir():
            shutil.rmtree(target_path)
        else:
            target_path.unlink()


__all__ = [
    "DEFAULT_AGENTS_SOURCE",
    "GitHubAgentSource",
    "LocalAgentSource",
    "ProjectAgentInstallError",
    "ProjectAgentInstallResult",
    "RemoteAgentCandidateSummary",
    "RemoteAgentListing",
    "install_project_agent",
    "list_remote_project_agents",
    "parse_github_agent_source",
    "parse_project_agent_source",
    "render_remote_agent_listing",
    "resolve_default_agents_source",
]
