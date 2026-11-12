"""One-shot installer for kits.

A kit is a directory (local or in a GitHub repository) that packages a
specialized workspace setup: skills, commands, sub-agents, MCP servers, and
instructions. Installing a kit copies those parts into the workspace once;
nothing tracks the kit afterwards.
"""

from __future__ import annotations

import json
import shutil
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any, Literal

from rich.console import Console
from rich.table import Table

from pbi_agent.agents.project_installer import _discover_remote_agent_candidates
from pbi_agent.commands.project_installer import _discover_remote_command_candidates
from pbi_agent.config import ConfigError, slugify
from pbi_agent.project_sources import (
    GitHubProjectSource,
    ProjectSourceError,
    materialize_project_source,
    parse_project_source,
)
from pbi_agent.skills.project_installer import _discover_remote_skill_candidates

_AGENTS_DIR = Path(".agents")
_INSTRUCTIONS_FILENAME = "AGENTS.md"
_MCP_FILENAME = "mcp.json"
_MANIFEST_FILENAME = "kit.json"
_CATALOG_DIR = "kits"

DEFAULT_KITS_SOURCE = "pbi-agent/kits"

KitItemKind = Literal["skill", "command", "agent", "mcp", "instructions"]
KitItemAction = Literal["install", "replace", "skip"]


class KitInstallError(ValueError):
    """Raised when kit installation fails."""


@dataclass(slots=True, frozen=True)
class KitItem:
    kind: KitItemKind
    name: str
    action: KitItemAction
    path: Path


@dataclass(slots=True, frozen=True)
class KitInstallResult:
    name: str
    source: str
    ref: str | None
    items: list[KitItem]
    applied: bool


@dataclass(slots=True, frozen=True)
class KitSummary:
    name: str
    description: str
    subpath: str


@dataclass(slots=True, frozen=True)
class KitListing:
    source: str
    ref: str | None
    kits: list[KitSummary]


class KitSelectionRequiredError(KitInstallError):
    """Raised when a catalog holds several kits and none was selected."""

    def __init__(self, listing: KitListing) -> None:
        super().__init__(
            "Source is a catalog with several kits. Re-run with --kit <name>. "
            f"Available kits: {', '.join(kit.name for kit in listing.kits)}."
        )
        self.listing = listing


@dataclass(slots=True)
class _Plan:
    items: list[KitItem]
    steps: list[Callable[[], None]]


def install_kit(
    source: str = DEFAULT_KITS_SOURCE,
    *,
    kit_name: str | None = None,
    force: bool = False,
    dry_run: bool = False,
    workspace: Path | None = None,
) -> KitInstallResult:
    """Copy the kit at *source* into *workspace*.

    *source* is either a kit or a catalog holding kits under ``kits/<name>/``;
    *kit_name* selects one kit from a catalog. Existing skills, commands,
    agents, MCP servers, and a previously added instructions block are left
    untouched unless *force* is set. With *dry_run*, the plan is returned
    without writing anything.
    """

    try:
        parsed_source = parse_project_source(source, source_label="kit")
    except ProjectSourceError as exc:
        raise KitInstallError(str(exc)) from exc
    install_workspace = (workspace or Path.cwd()).resolve()

    with TemporaryDirectory(prefix="pbi-agent-kit-") as temp_dir:
        try:
            materialized = materialize_project_source(
                parsed_source,
                temp_root=Path(temp_dir),
                source_label="kit",
                user_agent="pbi-agent-kits",
            )
        except ProjectSourceError as exc:
            raise KitInstallError(str(exc)) from exc

        source_root = materialized.resolved_root
        catalog = _discover_catalog_kits(source_root)
        if catalog:
            kit_root = _select_catalog_kit(
                catalog,
                kit_name=kit_name,
                listing=KitListing(
                    source=source,
                    ref=materialized.ref,
                    kits=[
                        KitSummary(
                            name=path.name,
                            description=_kit_description(path),
                            subpath=path.relative_to(source_root).as_posix(),
                        )
                        for path in catalog
                    ],
                ),
            )
            raw_name = kit_root.name
        elif kit_name is not None:
            raise KitInstallError(
                "Source is a single kit, not a catalog. Re-run without --kit."
            )
        else:
            kit_root = source_root
            at_repo_root = kit_root == materialized.repo_root
            raw_name = (
                parsed_source.repo
                if isinstance(parsed_source, GitHubProjectSource) and at_repo_root
                else kit_root.name
            )
        try:
            resolved_name = slugify(raw_name)
        except ConfigError:
            resolved_name = "kit"

        plan = _Plan(items=[], steps=[])
        _plan_skills(plan, kit_root, install_workspace, force=force)
        _plan_commands(plan, kit_root, install_workspace, force=force)
        _plan_agents(plan, kit_root, install_workspace, force=force)
        _plan_mcp(plan, kit_root, install_workspace, force=force)
        _plan_instructions(
            plan, kit_root, install_workspace, resolved_name, force=force
        )

        if not plan.items:
            raise KitInstallError(
                "No kit content found. A kit provides skills/, commands/, agents/, "
                "mcp.json (at its root or under .agents/), or an AGENTS.md. A "
                "catalog holds kits under kits/<name>/."
            )

        if not dry_run:
            for step in plan.steps:
                step()

    return KitInstallResult(
        name=resolved_name,
        source=source,
        ref=materialized.ref,
        items=plan.items,
        applied=not dry_run,
    )


def render_kit_listing(
    listing: KitListing,
    *,
    console: Console | None = None,
) -> int:
    active_console = console or Console()
    table = Table(title="Available Kits", title_style="bold cyan")
    table.add_column("Name", style="green")
    table.add_column("Description")
    table.add_column("Source Path", style="dim")
    for kit in listing.kits:
        table.add_row(kit.name, kit.description, kit.subpath)
    active_console.print(table)
    return 0


def _display_path(path: Path) -> str:
    try:
        return path.relative_to(Path.cwd().resolve()).as_posix()
    except ValueError:
        return str(path)


def _has_kit_content(root: Path) -> bool:
    if (root / _INSTRUCTIONS_FILENAME).is_file():
        return True
    return any(
        (base / entry).exists()
        for base in (root, root / _AGENTS_DIR)
        for entry in ("skills", "commands", "agents", _MCP_FILENAME)
    )


def _discover_catalog_kits(source_root: Path) -> list[Path]:
    container = source_root / _CATALOG_DIR
    if not container.is_dir():
        return []
    return [
        child
        for child in sorted(container.iterdir(), key=lambda item: item.name.casefold())
        if child.is_dir() and _has_kit_content(child)
    ]


def _select_catalog_kit(
    catalog: list[Path],
    *,
    kit_name: str | None,
    listing: KitListing,
) -> Path:
    if kit_name is None:
        if len(catalog) == 1:
            return catalog[0]
        raise KitSelectionRequiredError(listing)
    for path in catalog:
        if path.name.casefold() == kit_name.strip().casefold():
            return path
    raise KitInstallError(
        f"Unknown kit {kit_name!r}. Available kits: "
        f"{', '.join(path.name for path in catalog)}."
    )


def _kit_description(kit_root: Path) -> str:
    """Read the optional ``description`` from the kit's ``kit.json``."""

    try:
        manifest = json.loads((kit_root / _MANIFEST_FILENAME).read_text("utf-8"))
    except (OSError, ValueError):
        return ""
    description = manifest.get("description") if isinstance(manifest, dict) else None
    return description.strip() if isinstance(description, str) else ""


def render_kit_result(
    result: KitInstallResult,
    *,
    console: Console | None = None,
) -> int:
    active_console = console or Console()
    title = f"Kit '{result.name}'" + ("" if result.applied else " (preview)")
    labels: dict[KitItemAction, str] = (
        {"install": "installed", "replace": "replaced", "skip": "skipped (exists)"}
        if result.applied
        else {"install": "new", "replace": "will replace", "skip": "exists"}
    )
    table = Table(title=title, title_style="bold cyan")
    table.add_column("Type", style="yellow")
    table.add_column("Name", style="green")
    table.add_column("Status")
    table.add_column("Path", style="dim")
    for item in result.items:
        table.add_row(
            item.kind, item.name, labels[item.action], _display_path(item.path)
        )
    active_console.print(table)

    if any(item.action == "skip" for item in result.items):
        active_console.print(
            "[dim]Existing items were kept. Re-run with --force to replace them.[/dim]"
        )
    changed = [item for item in result.items if item.action != "skip"]
    if result.applied and changed:
        hint = "Run /reload in open sessions"
        if any(item.kind == "mcp" for item in changed):
            hint += "; restart them to load the new MCP servers"
        active_console.print(f"[dim]{hint}.[/dim]")
    return 0


def _component_root(kit_root: Path, entry: str) -> Path:
    """Return the directory holding *entry*: the kit root, else its ``.agents``."""

    if (kit_root / entry).exists():
        return kit_root
    return kit_root / _AGENTS_DIR


def _action(target: Path, *, force: bool) -> KitItemAction:
    if not (target.exists() or target.is_symlink()):
        return "install"
    return "replace" if force else "skip"


def _install_target(install_root: Path, filename: str, *, kind: str) -> Path:
    if (
        not filename.strip()
        or "/" in filename
        or "\\" in filename
        or filename in {".", ".."}
    ):
        raise KitInstallError(
            f"Unsupported {kind} name {filename!r}. Install names must be a single "
            "path segment."
        )
    return install_root / filename


def _remove(path: Path) -> None:
    if path.is_symlink() or path.is_file():
        path.unlink()
    elif path.is_dir():
        shutil.rmtree(path)


def _plan_skills(plan: _Plan, kit_root: Path, workspace: Path, *, force: bool) -> None:
    base = _component_root(kit_root, "skills")
    if not (base / "skills").is_dir():
        return
    install_root = workspace / _AGENTS_DIR / "skills"
    for candidate in _discover_remote_skill_candidates(
        repo_root=kit_root, resolved_root=base
    ):
        target = _install_target(install_root, candidate.name.strip(), kind="skill")
        action = _action(target, force=force)
        plan.items.append(KitItem("skill", candidate.name, action, target))
        if action == "skip":
            continue

        def copy_skill(source_dir: Path = candidate.skill_dir, target: Path = target):
            _remove(target)
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copytree(source_dir, target)

        plan.steps.append(copy_skill)


def _plan_text_file(
    plan: _Plan,
    *,
    kind: KitItemKind,
    name: str,
    target: Path,
    contents: str,
    force: bool,
) -> None:
    action = _action(target, force=force)
    plan.items.append(KitItem(kind, name, action, target))
    if action == "skip":
        return

    def write_file() -> None:
        _remove(target)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(contents, encoding="utf-8")

    plan.steps.append(write_file)


def _plan_commands(
    plan: _Plan, kit_root: Path, workspace: Path, *, force: bool
) -> None:
    base = _component_root(kit_root, "commands")
    if not (base / "commands").is_dir():
        return
    install_root = workspace / _AGENTS_DIR / "commands"
    for candidate in _discover_remote_command_candidates(
        repo_root=kit_root, resolved_root=base, include_root_markdown=False
    ):
        _plan_text_file(
            plan,
            kind="command",
            name=candidate.slash_alias,
            target=_install_target(
                install_root, f"{candidate.command_id}.md", kind="command"
            ),
            contents=candidate.install_contents,
            force=force,
        )


def _plan_agents(plan: _Plan, kit_root: Path, workspace: Path, *, force: bool) -> None:
    base = _component_root(kit_root, "agents")
    if not (base / "agents").is_dir():
        return
    install_root = workspace / _AGENTS_DIR / "agents"
    for candidate in _discover_remote_agent_candidates(
        repo_root=kit_root, resolved_root=base, include_root_markdown=False
    ):
        _plan_text_file(
            plan,
            kind="agent",
            name=candidate.agent_name,
            target=_install_target(
                install_root, f"{candidate.agent_name.strip()}.md", kind="agent"
            ),
            contents=candidate.source_text,
            force=force,
        )


def _read_mcp_payload(path: Path, *, owner: str) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise KitInstallError(f"Could not read {owner} MCP config at {path}.") from exc
    except json.JSONDecodeError as exc:
        raise KitInstallError(
            f"Invalid JSON in {owner} MCP config at {path}: {exc.msg}."
        ) from exc
    if not isinstance(payload, dict):
        raise KitInstallError(
            f"{owner.capitalize()} MCP config at {path} must be a JSON object."
        )
    servers = payload.setdefault("servers", {})
    if not isinstance(servers, dict) or not all(
        isinstance(name, str) and name.strip() and isinstance(config, dict)
        for name, config in servers.items()
    ):
        raise KitInstallError(
            f"{owner.capitalize()} MCP config at {path} needs a 'servers' object "
            "mapping server names to objects."
        )
    return payload


def _plan_mcp(plan: _Plan, kit_root: Path, workspace: Path, *, force: bool) -> None:
    kit_config = _component_root(kit_root, _MCP_FILENAME) / _MCP_FILENAME
    if not kit_config.is_file():
        return
    kit_servers: dict[str, Any] = _read_mcp_payload(kit_config, owner="kit")["servers"]
    if not kit_servers:
        return

    target = workspace / _AGENTS_DIR / _MCP_FILENAME
    payload: dict[str, Any] = (
        _read_mcp_payload(target, owner="workspace")
        if target.is_file()
        else {"servers": {}}
    )
    servers: dict[str, Any] = payload["servers"]

    changed = False
    for name in sorted(kit_servers):
        action: KitItemAction = (
            "install" if name not in servers else "replace" if force else "skip"
        )
        plan.items.append(KitItem("mcp", name, action, target))
        if action != "skip":
            servers[name] = kit_servers[name]
            changed = True
    if not changed:
        return

    def write_config() -> None:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")

    plan.steps.append(write_config)


def _plan_instructions(
    plan: _Plan,
    kit_root: Path,
    workspace: Path,
    kit_name: str,
    *,
    force: bool,
) -> None:
    kit_file = kit_root / _INSTRUCTIONS_FILENAME
    if not kit_file.is_file():
        return
    try:
        instructions = kit_file.read_text(encoding="utf-8").strip()
    except (OSError, UnicodeDecodeError) as exc:
        raise KitInstallError(
            f"Could not read kit instructions at {kit_file}."
        ) from exc
    if not instructions:
        return

    start = f"<!-- kit:{kit_name}:start -->"
    end = f"<!-- kit:{kit_name}:end -->"
    block = f"{start}\n{instructions}\n{end}"

    target = workspace / _INSTRUCTIONS_FILENAME
    try:
        existing = target.read_text(encoding="utf-8") if target.is_file() else ""
    except (OSError, UnicodeDecodeError) as exc:
        raise KitInstallError(f"Could not read {target}.") from exc

    action: KitItemAction
    if start not in existing:
        action = "install"
        updated = (
            f"{existing.rstrip()}\n\n{block}\n" if existing.strip() else f"{block}\n"
        )
    elif not force:
        action = "skip"
        updated = existing
    else:
        action = "replace"
        start_index = existing.index(start)
        end_index = existing.find(end, start_index)
        if end_index == -1:
            raise KitInstallError(
                f"{target} has '{start}' without a matching '{end}'. Fix the file "
                "and re-run."
            )
        updated = existing[:start_index] + block + existing[end_index + len(end) :]

    plan.items.append(KitItem("instructions", _INSTRUCTIONS_FILENAME, action, target))
    if action == "skip":
        return

    def write_instructions() -> None:
        target.write_text(updated, encoding="utf-8")

    plan.steps.append(write_instructions)


__all__ = [
    "DEFAULT_KITS_SOURCE",
    "KitInstallError",
    "KitInstallResult",
    "KitItem",
    "KitListing",
    "KitSelectionRequiredError",
    "KitSummary",
    "install_kit",
    "render_kit_listing",
    "render_kit_result",
]
