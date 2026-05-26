from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


AGENTS_FILENAME = "AGENTS.md"

AGENTS_TEMPLATE = """# AGENTS.md

This file gives coding agents project-specific context and instructions.
Treat it like a README for agents: keep it concise, accurate, and updated
when project workflows change.

## Task Memory Protocol

- Use a single `MEMORY.md` file for both durable memory and recent task history.
- Keep `MEMORY.md` in three sections only: `Metadata`, `Long-Term Memory`, and `Detailed Task Events`.
- At the start of substantive work, read `Metadata`, `Long-Term Memory`, and any current-day detailed entries relevant to the task.
- Keep `Long-Term Memory` compact and edited in place. Store only durable facts: stable repo conventions, important decisions, reusable validation patterns, active follow-ups, and artifacts that matter beyond one task.
- Keep `Detailed Task Events` append-only within the active day. Group entries under one `## YYYY-MM-DD` heading per day.
- After each implementation, append one short task entry to the current day with only: what changed, validation, and next context if needed.
- On the first substantive task of a new day, compact the previous day's detailed entries before appending new ones.
- During compaction, first review every prior-day detailed entry and explicitly write a compact resume of its durable outcome into `Long-Term Memory` before deleting the dated section. Do not delete a prior-day section unless its durable facts, decisions, validation patterns, and unresolved follow-ups have been promoted or consciously deemed non-durable.
- Carry unresolved items into an active/open follow-up bullet if still relevant, then remove prior-day detail that is no longer needed.
- Avoid duplicating long-term bullets. Merge with existing bullets when the fact already exists.
- Keep the file token-efficient: prefer short bullets, avoid command noise, and do not preserve obsolete troubleshooting detail once compacted.

## Session TODO Protocol

- Use `TODO.md` for the current task session only.
- Create or reset `TODO.md` before starting substantive work.
- Use GitHub task-list bullets for every TODO entry: `- [ ]` pending, `- [>]` in progress, `- [x]` done, `- [!]` blocked, `- [-]` dropped.
- Update `TODO.md` as you work. Mark steps complete when they finish, and revise the list when scope changes.
- If TODO.md contains a completed task list, reset it before adding new changes. If it contains an unfinished list, append new `- [ ] ...` tasks instead of writing plain paragraphs.

## Command Output

Protect context usage. **Any command with unknown or potentially large output must be byte-capped.**

## Communication

Before editing, state the approach only for non-trivial tasks.

During complex work, keep updates very short:

- what was found
- what changed
- what risk remains

After work, summarize:

- what changed
- files touched
- validation run, or why skipped
- remaining risk
- next logic steps

Keep summaries short. Do not explain obvious edits.

Oververbosity:low
"""


@dataclass(frozen=True, slots=True)
class InitAgentsResult:
    path: Path
    created: bool
    overwritten: bool


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


def format_init_agents_result(result: InitAgentsResult) -> str:
    if result.created:
        return f"Created {result.path}"
    if result.overwritten:
        return f"Overwrote {result.path}"
    return f"Skipped {result.path}; AGENTS.md already exists. Use --force to overwrite."
