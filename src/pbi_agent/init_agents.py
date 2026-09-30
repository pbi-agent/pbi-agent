from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from pbi_agent.agents.state import set_agent_enabled
from pbi_agent.agents.project_installer import (
    DEFAULT_AGENTS_SOURCE,
    ProjectAgentInstallError,
    install_project_agent,
)
from pbi_agent.commands.project_installer import (
    DEFAULT_COMMANDS_SOURCE,
    ProjectCommandInstallError,
    install_project_command,
)

AGENTS_FILENAME = "AGENTS.md"
DEFAULT_INIT_COMMANDS: tuple[str, ...] = (
    "execute",
    "fix-review",
    "orchestrate",
    "plan-interactive",
    "plan",
    "refine-task",
    "retrospective",
    "review",
    "code-quality-review",
)
DEFAULT_INIT_AGENTS: tuple[str, ...] = (
    "code-reviewer",
    "explorer",
    "planner",
    "worker",
)
COMMAND_INSTALL_ROOT = Path(".agents/commands")
AGENT_INSTALL_ROOT = Path(".agents/agents")

AGENTS_TEMPLATE = """# AGENTS.md

Project context and instructions for coding agents. Keep it concise, accurate,
and updated when workflows change.

## Task Memory

- `MEMORY.md` holds durable memory and recent task history in exactly three sections: `Metadata`, `Long-Term Memory`, `Detailed Task Events`.
- Start substantive work from the preloaded `<workspace_memory>` section. Read `MEMORY.md` with tools only if that section is absent, before editing/compacting it, or when asked.
- `Long-Term Memory`: compact bullets edited in place; only durable facts (conventions, decisions, validation patterns, open follow-ups, lasting artifacts). Merge instead of duplicating.
- `Detailed Task Events`: append-only per day under one `## YYYY-MM-DD` heading. After each implementation, add one short entry: what changed, validation, next context if needed.
- On the first substantive task of a new day, compact prior days: promote every durable outcome and unresolved follow-up to `Long-Term Memory`, then delete the dated sections.
- Stay token-efficient: short bullets, no command noise, no obsolete troubleshooting.

## Session TODO

- `TODO.md` tracks the current session only; create or reset it before substantive work.
- Use task-list bullets only: `- [ ]` pending, `- [>]` in progress, `- [x]` done, `- [!]` blocked, `- [-]` dropped.
- Update `TODO.md` as work progresses and when scope changes.
- If the existing list is complete, reset it; if unfinished, append new `- [ ]` tasks.

## Command Output

- Protect context: byte-cap any command with unknown or potentially large output.

## Communication

- Before editing, state the approach only for non-trivial tasks.
- During complex work, keep updates very short: findings, changes, remaining risk.
- After work, summarize briefly: what changed, files touched, validation run (or why skipped), remaining risk, next steps.
- Keep output low-verbosity; do not explain obvious edits.
"""


@dataclass(frozen=True, slots=True)
class InitAgentsResult:
    path: Path
    created: bool
    overwritten: bool


@dataclass(frozen=True, slots=True)
class InitBootstrapItemResult:
    kind: str
    name: str
    status: str
    path: Path | None = None
    message: str | None = None


@dataclass(frozen=True, slots=True)
class InitBootstrapResult:
    agents_file: InitAgentsResult
    commands: tuple[InitBootstrapItemResult, ...]
    agents: tuple[InitBootstrapItemResult, ...]

    @property
    def items(self) -> tuple[InitBootstrapItemResult, ...]:
        return (
            _agents_file_item(self.agents_file),
            *self.commands,
            *self.agents,
        )


def init_agents_file(
    *,
    workspace: Path | str = Path("."),
    force: bool = False,
) -> InitAgentsResult:
    """Create the starter AGENTS.md file for *workspace*."""

    root = Path(workspace)
    path = root / AGENTS_FILENAME
    exists = path.exists()
    if exists and not force:
        return InitAgentsResult(path=path.resolve(), created=False, overwritten=False)

    path.write_text(AGENTS_TEMPLATE, encoding="utf-8")
    return InitAgentsResult(path=path.resolve(), created=not exists, overwritten=exists)


def init_workspace_bootstrap(
    *,
    workspace: Path | str = Path("."),
    force: bool = False,
    directory_key: str | None = None,
) -> InitBootstrapResult:
    """Create starter workspace files and install default official catalogs."""

    root = Path(workspace).resolve()
    agents_file = init_agents_file(workspace=root, force=force)
    commands = tuple(
        _install_default_command(command_name, workspace=root, force=force)
        for command_name in DEFAULT_INIT_COMMANDS
    )
    agents = tuple(
        _install_default_agent(
            agent_name,
            workspace=root,
            force=force,
            directory_key=directory_key,
        )
        for agent_name in DEFAULT_INIT_AGENTS
    )
    return InitBootstrapResult(
        agents_file=agents_file,
        commands=commands,
        agents=agents,
    )


def format_init_agents_result(result: InitAgentsResult) -> str:
    if result.created:
        return f"Created {result.path}"
    if result.overwritten:
        return f"Overwrote {result.path}"
    return f"Skipped {result.path}; AGENTS.md already exists. Use --force to overwrite."


def format_init_bootstrap_result(result: InitBootstrapResult) -> str:
    counts = _count_statuses(result.items)
    lines = [
        "# Workspace Init",
        "",
        (
            "Summary: "
            f"{counts['created']} created, "
            f"{counts['installed']} installed, "
            f"{counts['overwritten']} overwritten, "
            f"{counts['skipped']} skipped, "
            f"{counts['failed']} failed."
        ),
        "",
        "## AGENTS.md",
        f"- {_format_bootstrap_item(_agents_file_item(result.agents_file))}",
        "",
        "## Commands",
    ]
    lines.extend(f"- {_format_bootstrap_item(item)}" for item in result.commands)
    lines.extend(["", "## Sub-agents"])
    lines.extend(f"- {_format_bootstrap_item(item)}" for item in result.agents)
    return "\n".join(lines)


def _install_default_command(
    command_name: str,
    *,
    workspace: Path,
    force: bool,
) -> InitBootstrapItemResult:
    target_path = (workspace / COMMAND_INSTALL_ROOT / f"{command_name}.md").resolve()
    pre_existing = target_path.exists()
    if pre_existing and not force:
        return InitBootstrapItemResult(
            kind="command",
            name=command_name,
            status="skipped",
            path=target_path,
            message="already installed. Use --force to overwrite.",
        )

    try:
        result = install_project_command(
            DEFAULT_COMMANDS_SOURCE,
            command_name=command_name,
            force=force,
            workspace=workspace,
        )
    except (ProjectCommandInstallError, OSError) as exc:
        if not force and _is_already_installed_error(exc):
            return InitBootstrapItemResult(
                kind="command",
                name=command_name,
                status="skipped",
                path=target_path,
                message="already installed. Use --force to overwrite.",
            )
        return InitBootstrapItemResult(
            kind="command",
            name=command_name,
            status="failed",
            message=str(exc),
        )

    return InitBootstrapItemResult(
        kind="command",
        name=result.command_id,
        status="overwritten" if pre_existing else "installed",
        path=result.install_path,
    )


def _install_default_agent(
    agent_name: str,
    *,
    workspace: Path,
    force: bool,
    directory_key: str | None,
) -> InitBootstrapItemResult:
    target_path = (workspace / AGENT_INSTALL_ROOT / f"{agent_name}.md").resolve()
    pre_existing = target_path.exists()
    if pre_existing and not force:
        return InitBootstrapItemResult(
            kind="agent",
            name=agent_name,
            status="skipped",
            path=target_path,
            message="already installed. Use --force to overwrite.",
        )

    try:
        result = install_project_agent(
            DEFAULT_AGENTS_SOURCE,
            agent_name=agent_name,
            force=force,
            workspace=workspace,
        )
    except (ProjectAgentInstallError, OSError) as exc:
        if not force and _is_already_installed_error(exc):
            return InitBootstrapItemResult(
                kind="agent",
                name=agent_name,
                status="skipped",
                path=target_path,
                message="already installed. Use --force to overwrite.",
            )
        return InitBootstrapItemResult(
            kind="agent",
            name=agent_name,
            status="failed",
            message=str(exc),
        )

    try:
        set_agent_enabled(
            result.agent_name,
            False,
            workspace=workspace,
            directory_key=directory_key,
        )
    except Exception as exc:  # noqa: BLE001 - report per-item init failures
        if not pre_existing:
            result.install_path.unlink(missing_ok=True)
        return InitBootstrapItemResult(
            kind="agent",
            name=result.agent_name,
            status="failed",
            path=result.install_path,
            message=str(exc),
        )
    return InitBootstrapItemResult(
        kind="agent",
        name=result.agent_name,
        status="overwritten" if pre_existing else "installed",
        path=result.install_path,
    )


def _agents_file_item(result: InitAgentsResult) -> InitBootstrapItemResult:
    if result.created:
        status = "created"
        message = None
    elif result.overwritten:
        status = "overwritten"
        message = None
    else:
        status = "skipped"
        message = "already exists. Use --force to overwrite."
    return InitBootstrapItemResult(
        kind="agents_file",
        name=AGENTS_FILENAME,
        status=status,
        path=result.path,
        message=message,
    )


def _is_already_installed_error(exc: Exception) -> bool:
    return "already installed" in str(exc).casefold()


def _count_statuses(items: tuple[InitBootstrapItemResult, ...]) -> dict[str, int]:
    counts = {
        "created": 0,
        "installed": 0,
        "overwritten": 0,
        "skipped": 0,
        "failed": 0,
    }
    for item in items:
        if item.status in counts:
            counts[item.status] += 1
    return counts


def _format_bootstrap_item(item: InitBootstrapItemResult) -> str:
    subject = _format_item_subject(item)
    if item.status == "created":
        return f"Created {subject} at {item.path}"
    if item.status == "installed":
        return f"Installed {subject} to {item.path}"
    if item.status == "overwritten":
        return f"Overwrote {subject} at {item.path}"
    if item.status == "skipped":
        suffix = f"; {item.message}" if item.message else ""
        return f"Skipped {subject} at {item.path}{suffix}"
    if item.status == "failed":
        return f"Failed {subject}: {item.message or 'unknown error'}"
    return f"{item.status.title()} {subject}"


def _format_item_subject(item: InitBootstrapItemResult) -> str:
    if item.kind == "command":
        return f"command `/{item.name}`"
    if item.kind == "agent":
        return f"sub-agent `{item.name}`"
    return AGENTS_FILENAME
