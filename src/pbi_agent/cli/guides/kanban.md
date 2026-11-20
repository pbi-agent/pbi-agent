# pbi-agent kanban

Create and list Kanban board task cards for the current workspace from the terminal, using the same board the web UI shows.

## Purpose
Use `pbi-agent kanban` to add tasks to the workspace board or inspect them from scripts and agents without opening the web UI. The board is keyed by the current working directory (the workspace) and stored in the local session database (`~/.pbi-agent/sessions.db`, or the path in `PBI_AGENT_SESSION_DB_PATH`). These commands only create and read cards: they never start, move, edit, or delete tasks. Running and moving tasks, and editing stages, happen in the web UI (`pbi-agent web`, then open **Kanban**).

## Usage
```text
pbi-agent kanban <action> ...
```

## Subcommands
- `pbi-agent kanban create`: create a task card in an existing board stage (default: the first stage). Guide: `pbi-agent kanban create --doc`.
- `pbi-agent kanban list`: list task cards, optionally filtered to one stage, as text blocks or JSON. Guide: `pbi-agent kanban list --doc`.

An action is required: `pbi-agent kanban` with no subcommand prints an argparse usage error and exits 2.

## Options and arguments
No options besides `-h/--help` and `--doc`.

**Stage matching (both subcommands).** A stage value is matched against each stage's ID and name, and the slugified form of both (lowercase, runs of non-alphanumerics turned into `-`), case-insensitively. So `"In Progress"`, `in-progress`, and `IN_PROGRESS` all match a stage named `In Progress`. Every board always has the fixed stages `Backlog` (ID `backlog`, first) and `Done` (ID `done`, last); custom stages live between them and are created in the web UI.

## Examples
```bash
# Add a card to the first stage (normally Backlog)
pbi-agent kanban create --title "Fix login bug" --desc "Users get a 500 when the password has a quote."

# Show every card on the board as JSON
pbi-agent kanban list --json

# Show only the Backlog column
pbi-agent kanban list --stage backlog
```

## Workflows
1. Queue work from a script: `pbi-agent kanban create --title ... --desc ... --json`, read `task_id` from the output, then run the task from the web UI board.
2. Check board state: `pbi-agent kanban list --json` and filter on `stage`, `run_status`, or `last_result_summary`.
3. Target a custom stage: create it with **Edit Stages** in the web UI, confirm its name with `pbi-agent kanban list`, then `pbi-agent kanban create --lane "Review" ...`.

## Related commands
- `pbi-agent web`: the board UI where tasks are run, moved, edited, and stages configured.
- `pbi-agent sessions`: inspect sessions that a task may be associated with via `--session-id`.

## Pitfalls
- Both commands act on the workspace of the current working directory; run them from the repository root to hit the right board.
- An unknown stage exits 2 and the error lists the available stages as `Name (id)`.
- Creating a card does not start it, even if the target stage has Auto-start enabled; the CLI writes straight to the database, and Auto-start is only triggered by the web UI when a task is created or moved there.
