# pbi-agent kanban create

Create a task card on the current workspace's Kanban board without starting it.

## Purpose
Adds a card (title plus prompt) to an existing board stage so it can later be run from the web UI. Use it from automation or another agent to queue work. The card gets run status `idle`, no model profile override, no image attachments, and is appended at the end of its stage. It does not run, move, or auto-start the task.

## Usage
```text
pbi-agent kanban create --title TITLE --desc DESC [--lane LANE] [--project-dir PROJECT_DIR] [--session-id SESSION_ID] [--json]
```

## Options and arguments
- `--title TITLE` (required): title shown on the card. Leading/trailing whitespace is stripped; an empty result exits 2.
- `--desc, --description, --prompt DESC` (required): the prompt stored on the card and sent when the task runs. Stripped; an empty result exits 2.
- `--lane, --stage, --state LANE`: existing stage, matched by ID, name, or slugified name, case-insensitively. Default (or empty value): the first stage, normally `Backlog`. Unknown values exit 2 and list the available stages.
- `--project-dir PROJECT_DIR`: workspace-relative directory used for future runs of this task. Default `.`. It must exist, be a directory, and resolve inside the workspace, otherwise exit 2.
- `--session-id SESSION_ID`: optional session ID to associate with the task. Stored as given; it is not validated.
- `--json`: print the created task as one line of JSON (sorted keys: `task_id`, `directory`, `title`, `prompt`, `stage`, `stage_name`, `position`, `project_dir`, `session_id`, `model_profile_id`, `run_status`, `last_result_summary`, `created_at`, `updated_at`, `last_run_started_at`, `last_run_finished_at`, `image_attachments`).

Without `--json` it prints `Created Kanban task <task_id> in <stage name>: <title>`.

## Examples
```bash
# Queue a task in the first stage
pbi-agent kanban create --title "Refactor API endpoint" --desc "Improve the main API endpoint response time."

# Put it in a custom stage by display name and capture the ID
pbi-agent kanban create --title "Review docs" --prompt "Check docs/cli.md against the parser." --lane "In Progress" --json

# Scope future runs to a subdirectory of the workspace
pbi-agent kanban create --title "Frontend lint" --desc "Fix all lint warnings." --project-dir webapp
```

## Workflows
1. Script a task: `pbi-agent kanban create ... --json`, parse `task_id`, then run it from the board in `pbi-agent web`.
2. Pick a valid stage first: `pbi-agent kanban list` (or trigger the unknown-stage error) to see stage names, then pass one to `--lane`.

## Related commands
- `pbi-agent kanban list`: verify the card was created and see its stage and position.
- `pbi-agent web`: run, move, or edit the task; configure stages.

## Pitfalls
- Runs against the workspace of the current working directory; `--project-dir` is resolved relative to that directory.
- `--lane` cannot create stages. Only `Backlog` and `Done` exist until custom stages are added in the web UI.
- Placing a card directly in a stage with Auto-start does not start it; only the web UI triggers Auto-start (on create or move there).
- Error exits (code 2): empty `--title` or `--desc`, bad `--project-dir`, unknown stage. Missing `--title` or `--desc` is an argparse usage error (also exit 2).
