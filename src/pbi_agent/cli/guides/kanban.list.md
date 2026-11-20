# pbi-agent kanban list

List the task cards on the current workspace's Kanban board, optionally limited to one stage.

## Purpose
Read board state from the terminal or a script: IDs, titles, full prompts, stage, run status, and timestamps. Use it to find a task ID, check whether runs completed, or confirm a `pbi-agent kanban create` worked. It is read-only.

## Usage
```text
pbi-agent kanban list [--stage STAGE] [--json]
```

## Options and arguments
- `--stage, --lane, --state STAGE`: only show tasks in this existing stage, matched by ID, name, or slugified name, case-insensitively. Default (or empty value): all stages. An unknown stage exits 2 and lists the available stages as `Name (id)`.
- `--json`: print a one-line JSON array of task objects (sorted keys: `task_id`, `directory`, `title`, `prompt`, `stage`, `stage_name`, `position`, `project_dir`, `session_id`, `model_profile_id`, `run_status`, `last_result_summary`, `created_at`, `updated_at`, `last_run_started_at`, `last_run_finished_at`, `image_attachments`). Each attachment has `upload_id`, `name`, `mime_type`, `byte_count`, `preview_url`. An empty board prints `[]`.

**Text output.** One block per task, separated by a blank line, with `Task ID`, `Title`, `Prompt` (not truncated), `Stage: <name> (<id>)`, `Position`, `Project dir`, `Session ID`, `Model profile ID`, `Run status`, `Last result summary`, timestamps, and `Image attachments: <count>`. Missing values print `-`. With no tasks it prints `No Kanban tasks found.` (or `No Kanban tasks found in <name> (<id>).` when filtered).

**Order.** Tasks follow board stage order. Within `Done`, newest first; in other stages, by board position.

## Examples
```bash
# Everything on the board
pbi-agent kanban list

# Only one column, by display name
pbi-agent kanban list --stage "In Progress"

# Machine-readable, then filter with jq
pbi-agent kanban list --json | jq '.[] | select(.run_status == "failed") | .task_id'
```

## Workflows
1. Check outcomes: `pbi-agent kanban list --stage done --json` and read `run_status` (`idle`, `running`, `completed`, `failed`) and `last_result_summary`.
2. After `pbi-agent kanban create`, run `pbi-agent kanban list --stage backlog` to confirm the new card and its position.

## Related commands
- `pbi-agent kanban create`: add cards.
- `pbi-agent web`: run, move, and edit tasks; configure stages.

## Pitfalls
- Shows only the board of the current working directory's workspace.
- `run_status` is stored state; it reflects what the web UI last recorded, not a live process check.
- The stage filter must name an existing stage; it is not a substring search.
