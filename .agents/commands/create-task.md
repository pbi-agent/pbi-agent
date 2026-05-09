# Create Kanban Task

Create a Kanban task from the user's request by invoking the existing CLI. Do not implement or start the task.

## Workflow

1. Derive a concise task title from the user text and available conversation context.
2. Use the full user request/context as the task description, preserving important details, constraints, and acceptance criteria.
3. Default to the board's first lane by omitting `--lane` unless the user explicitly names a lane, stage, or state; when specified, pass it with `--lane`.
4. Run the CLI with the shell tool:

   ```bash
   pbi-agent kanban create --title "TITLE" --desc "DESCRIPTION" --json
   ```

   Add `--lane "LANE"`, `--project-dir "DIR"`, or `--session-id "ID"` only when the user provided them. Quote every dynamic argument safely for the shell; do not interpolate raw user text unescaped.

## Final Report

Report the created task ID, title, and lane from the CLI output. If creation fails, report the CLI error and do not claim a task was created.
