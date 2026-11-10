from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

AGENTS_FILENAME = "AGENTS.md"

AGENTS_TEMPLATE = """# AGENTS.md

## Memory

- Memory holds what a future session cannot recover from the repo or config: decisions and why, tested rules, traps, current focus, open follow-ups.
- `MEMORY.md` is a short index preloaded into the agent (first 200 lines / 25 KB); put topic detail in `.agents/memory/<topic>.md` and link it.
- Write when asked or clearly worth remembering; edit in place, delete stale entries; tag `[verified YYYY-MM-DD]` or `[unverified]`.
- Check relevant memory before acting; re-check unverified or old entries. Only the main agent edits memory; sub-agents report candidate notes.
- `MEMORY.md` index: compact, edited in place; durable facts only (stable conventions, key decisions, reusable validation patterns, active follow-ups, artifacts that matter beyond one task).
- Daily log: a `## Daily Log` section at the end of `MEMORY.md`, append-only within the active day under one `### YYYY-MM-DD` heading. Keep it short; it counts toward the preload cap. After each implementation, append one short entry: what changed, validation, next context if needed.
- On the first substantive task of a new day, distill the previous day's log: move durable facts into the `MEMORY.md` index sections or `.agents/memory/` topic pages, delete that day's entries, then start the new day's heading.
- Past sessions: SQLite `~/.pbi-agent/sessions.db` (`PBI_AGENT_SESSION_DB_PATH` overrides). Query read-only (`python3`, `sqlite3.connect("file:<path>?mode=ro", uri=True)`); never write. `sessions(session_id, directory, title, updated_at)` with `directory` = lowercased absolute workspace path; `messages(session_id, role, content, created_at)`; `observability_events(session_id, event_type, tool_name, tool_input_json, tool_output_json, error_message)` (large). Use `?` params, narrow columns, `substr`, `LIMIT`.

## TODO

- Keep a checklist in `TODO.md`. Tick each item when it's done, and add anything new you find.
- `TODO.md` is session-only; reset if complete, append if unfinished.
- Bullets: `- [ ]` pending, `- [>]` in progress, `- [x]` done, `- [!]` blocked, `- [-]` dropped. Keep it updated.

## Communication

- Be concise; state the approach before non-trivial edits.
- After work, summarize: what changed, files touched, validation (or why skipped), remaining risk, next steps.
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
        return f"Created {AGENTS_FILENAME} at {result.path}"
    if result.overwritten:
        return f"Overwrote {AGENTS_FILENAME} at {result.path}"
    return (
        f"Skipped {AGENTS_FILENAME} at {result.path}; already exists. "
        "Use --force to overwrite."
    )
