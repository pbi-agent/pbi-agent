from __future__ import annotations

import shutil

from dataclasses import dataclass
from pathlib import Path
from tempfile import TemporaryDirectory

from rich.console import Console
from rich.table import Table

from pbi_agent.config import (
    CommandConfig,
    ConfigError,
    RESERVED_COMMAND_ALIASES,
    slugify,
)
from pbi_agent.project_sources import (
    GitHubProjectSource,
    LocalProjectSource,
    ProjectSourceError,
    materialize_project_source,
    parse_github_project_source,
    parse_project_source,
)

DEFAULT_COMMANDS_SOURCE = "pbi-agent/commands"
_INSTALL_ROOT = Path(".agents/commands")

GitHubCommandSource = GitHubProjectSource
LocalCommandSource = LocalProjectSource


class ProjectCommandInstallError(ValueError):
    """Raised when project command installation fails."""


@dataclass(slots=True, frozen=True)
class RemoteCommandCandidateSummary:
    command_id: str
    slash_alias: str
    description: str
    subpath: str | None


@dataclass(slots=True, frozen=True)
class RemoteCommandListing:
    source: str
    ref: str | None
    candidates: list[RemoteCommandCandidateSummary]


@dataclass(slots=True, frozen=True)
class ProjectCommandInstallResult:
    command_id: str
    slash_alias: str
    install_path: Path
    source: str
    ref: str | None
    subpath: str | None


@dataclass(slots=True, frozen=True)
class _RemoteCommandCandidate:
    command_id: str
    slash_alias: str
    description: str
    instructions: str
    source_path: Path
    repo_subpath: str | None


def resolve_default_commands_source() -> str:
    return DEFAULT_COMMANDS_SOURCE


def render_remote_command_listing(
    listing: RemoteCommandListing,
    *,
    console: Console | None = None,
) -> int:
    active_console = console or Console()
    table = Table(title="Available Commands", title_style="bold cyan")
    table.add_column("Alias", style="green")
    table.add_column("Description")
    table.add_column("Source Path", style="dim")
    for candidate in listing.candidates:
        table.add_row(
            candidate.slash_alias,
            candidate.description,
            candidate.subpath or ".",
        )
    active_console.print(table)
    return 0


def list_remote_project_commands(source: str) -> RemoteCommandListing:
    parsed_source = parse_project_command_source(source)
    with TemporaryDirectory(prefix="pbi-agent-command-") as temp_dir:
        materialized = _materialize_command_source(
            parsed_source,
            temp_root=Path(temp_dir),
        )
        candidates = _discover_remote_command_candidates(
            repo_root=materialized.repo_root,
            resolved_root=materialized.resolved_root,
            include_root_markdown=_should_include_root_markdown(
                parsed_source=parsed_source,
                repo_root=materialized.repo_root,
                resolved_root=materialized.resolved_root,
            ),
        )

    if not candidates:
        raise ProjectCommandInstallError(
            "No valid commands found. Commands require non-empty Markdown files."
        )

    return RemoteCommandListing(
        source=source,
        ref=materialized.ref,
        candidates=[
            RemoteCommandCandidateSummary(
                command_id=candidate.command_id,
                slash_alias=candidate.slash_alias,
                description=candidate.description,
                subpath=candidate.repo_subpath,
            )
            for candidate in candidates
        ],
    )


def install_project_command(
    source: str,
    *,
    command_name: str | None = None,
    force: bool = False,
    workspace: Path | None = None,
) -> ProjectCommandInstallResult:
    parsed_source = parse_project_command_source(source)
    install_workspace = (workspace or Path.cwd()).resolve()
    install_root = (install_workspace / _INSTALL_ROOT).resolve()

    with TemporaryDirectory(prefix="pbi-agent-command-") as temp_dir:
        materialized = _materialize_command_source(
            parsed_source,
            temp_root=Path(temp_dir),
        )
        candidates = _discover_remote_command_candidates(
            repo_root=materialized.repo_root,
            resolved_root=materialized.resolved_root,
            include_root_markdown=_should_include_root_markdown(
                parsed_source=parsed_source,
                repo_root=materialized.repo_root,
                resolved_root=materialized.resolved_root,
            ),
        )
        selected = _select_remote_command_candidate(
            candidates,
            command_name=command_name,
        )
        target_path = _resolve_install_target(
            install_root=install_root,
            command_id=selected.command_id,
        )
        _prepare_install_target(target_path, force=force)
        target_path.write_text(selected.instructions, encoding="utf-8")

    return ProjectCommandInstallResult(
        command_id=selected.command_id,
        slash_alias=selected.slash_alias,
        install_path=target_path,
        source=source,
        ref=materialized.ref,
        subpath=selected.repo_subpath,
    )


def parse_project_command_source(
    source: str,
) -> GitHubCommandSource | LocalCommandSource:
    try:
        return parse_project_source(source, source_label="command")
    except ProjectSourceError as exc:
        raise ProjectCommandInstallError(str(exc)) from exc


def parse_github_command_source(source: str) -> GitHubCommandSource:
    try:
        return parse_github_project_source(source, source_label="command")
    except ProjectSourceError as exc:
        raise ProjectCommandInstallError(str(exc)) from exc


def _materialize_command_source(
    source: GitHubCommandSource | LocalCommandSource,
    *,
    temp_root: Path,
):
    try:
        return materialize_project_source(
            source,
            temp_root=temp_root,
            source_label="command",
            user_agent="pbi-agent-commands",
            allow_local_file=True,
        )
    except ProjectSourceError as exc:
        raise ProjectCommandInstallError(str(exc)) from exc


def _discover_remote_command_candidates(
    *,
    repo_root: Path,
    resolved_root: Path,
    include_root_markdown: bool,
) -> list[_RemoteCommandCandidate]:
    candidate_paths: list[Path] = []
    seen_paths: set[Path] = set()

    def enqueue(command_path: Path) -> None:
        resolved_path = command_path.resolve()
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

        container = resolved_root / "commands"
        if container.is_dir():
            for child in sorted(
                container.iterdir(), key=lambda item: item.name.casefold()
            ):
                if child.is_file() and child.suffix == ".md":
                    enqueue(child)

    candidates: list[_RemoteCommandCandidate] = []
    seen_ids: set[str] = set()
    for command_path in candidate_paths:
        candidate = _load_remote_command_candidate(
            command_path=command_path,
            repo_root=repo_root,
        )
        if candidate is None or candidate.command_id in seen_ids:
            continue
        seen_ids.add(candidate.command_id)
        candidates.append(candidate)

    return candidates


def _should_include_root_markdown(
    *,
    parsed_source: GitHubCommandSource | LocalCommandSource,
    repo_root: Path,
    resolved_root: Path,
) -> bool:
    if resolved_root.is_file():
        return True
    if resolved_root != repo_root:
        return True
    return (
        isinstance(parsed_source, LocalCommandSource)
        and resolved_root.name == "commands"
    )


def _load_remote_command_candidate(
    *,
    command_path: Path,
    repo_root: Path,
) -> _RemoteCommandCandidate | None:
    try:
        instructions = command_path.read_text(encoding="utf-8").strip()
    except OSError:
        return None
    if not instructions:
        return None

    try:
        command_id = slugify(command_path.stem)
    except ConfigError:
        return None

    slash_alias = f"/{command_id}"
    if slash_alias in RESERVED_COMMAND_ALIASES:
        return None

    description = _command_description_from_markdown(instructions, command_id)
    command = CommandConfig(
        id=command_id,
        name=_command_name_from_id(command_id),
        slash_alias=slash_alias,
        description=description,
        instructions=instructions,
        path=command_path.name,
    )
    try:
        command.validate()
    except ConfigError:
        return None

    repo_subpath = command_path.relative_to(repo_root).as_posix()
    return _RemoteCommandCandidate(
        command_id=command.id,
        slash_alias=command.slash_alias,
        description=command.description,
        instructions=command.instructions,
        source_path=command_path,
        repo_subpath=None if repo_subpath == "." else repo_subpath,
    )


def _select_remote_command_candidate(
    candidates: list[_RemoteCommandCandidate],
    *,
    command_name: str | None,
) -> _RemoteCommandCandidate:
    if not candidates:
        raise ProjectCommandInstallError(
            "No valid commands found. Commands require non-empty Markdown files."
        )

    if command_name is None:
        if len(candidates) != 1:
            raise ProjectCommandInstallError(
                "Multiple commands were found in the source. Re-run with --list or "
                "--command <name>."
            )
        return candidates[0]

    normalized_name = command_name.casefold().lstrip("/")
    matched = [
        candidate
        for candidate in candidates
        if candidate.command_id.casefold() == normalized_name
    ]
    if not matched:
        available = ", ".join(candidate.command_id for candidate in candidates)
        raise ProjectCommandInstallError(
            f"Unknown command {command_name!r}. Available commands: {available}."
        )
    if len(matched) > 1:
        raise ProjectCommandInstallError(
            f"Command name {command_name!r} matched multiple remote command files."
        )
    return matched[0]


def _resolve_install_target(*, install_root: Path, command_id: str) -> Path:
    install_root.mkdir(parents=True, exist_ok=True)
    target_path = (install_root / f"{command_id}.md").resolve()
    if target_path.parent != install_root.resolve():
        raise ProjectCommandInstallError(
            f"Unsupported command ID {command_id!r}. Command install names must be a single path segment."
        )
    return target_path


def _prepare_install_target(target_path: Path, *, force: bool) -> None:
    if not target_path.exists():
        return

    if not force:
        raise ProjectCommandInstallError(
            f"Command already installed at {target_path}. Re-run with --force to replace it."
        )

    if target_path.is_dir():
        shutil.rmtree(target_path)
        return
    target_path.unlink()


def _command_name_from_id(command_id: str) -> str:
    return " ".join(part.capitalize() for part in command_id.split("-") if part)


def _command_description_from_markdown(instructions: str, command_id: str) -> str:
    for line in instructions.splitlines():
        stripped = line.strip()
        if not stripped.startswith("#"):
            continue
        heading = stripped.lstrip("#").strip()
        if heading:
            return heading
    return f"Activate {_command_name_from_id(command_id)}"
