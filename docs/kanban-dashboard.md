---
title: 'Kanban Dashboard'
description: 'Kanban task automation and observability dashboard workflows in the pbi-agent web UI.'
---

# Kanban Dashboard

The web UI includes two workflow-oriented areas:

- **Kanban** for managing queued agent tasks across stages.
- **Dashboard** for observing completed and running agent runs across sessions and tasks.

## Kanban overview

Open **Kanban** from the web UI header. The board stores task cards for the current workspace and displays them by stage.

Each task contains:

| Field | Purpose |
| --- | --- |
| Title | Short task label shown on the card. |
| Prompt | The user prompt sent when the task runs. |
| Image attachments | Optional PNG, JPEG, or WEBP images sent with the initial task prompt. |
| Stage | Current board stage. |
| Profile override | Optional model profile for this task. If empty, the stage/default runtime is used. |

You can add, edit, delete, drag, and run tasks from the board.

## Creating tasks from the CLI

Use `pbi-agent kanban create` when you want to add a task from automation, scripts, or a terminal workflow:

```bash
pbi-agent kanban create \
  --title "Refactor API endpoint" \
  --desc "Improve and optimize the main API endpoint for faster response time." \
  --lane "In Progress"
```

The command creates a card on the current workspace board and exits without starting an agent run. Omit `--lane` to use the first board stage, normally Backlog. When provided, `--lane` (also available as `--stage` or `--state`) must match an existing stage ID, stage name, or slugified stage name. Configure custom stages in the web UI before targeting them from scripts.

For automation, add `--json` to print the created task ID, stage, timestamps, and related fields as JSON.

Use `pbi-agent kanban list` to inspect board tasks without opening the web UI:

```bash
pbi-agent kanban list
pbi-agent kanban list --stage "In Progress"
pbi-agent kanban list --json
```

The list command defaults to all stages. Its `--stage` filter (also available as `--lane` or `--state`) must match an existing stage ID, stage name, or slugified stage name. Human output includes each task's ID, title, full prompt, stage, position, project directory, associated session/profile IDs, run status, timestamps, last result summary, and image attachment count. JSON output returns an array with the same task fields and image attachment metadata.

## Board stages

Use **Edit Stages** to configure the workflow. The board always has two fixed stages:

| Stage | Behavior |
| --- | --- |
| Backlog | Stays first and never runs directly unless there is a runnable stage to move into. |
| Done | Stays last and is archive-only. |

Custom stages can be placed between Backlog and Done. Each custom stage can define:

| Stage option | Purpose |
| --- | --- |
| Name | Label shown as the column title. |
| Profile | Default model profile for tasks in that stage. |
| Command | Default project command to apply when tasks enter or run in that stage. |
| Auto-start | Automatically starts a task when it moves into the stage. |

Stage profile and command references are validated against the current saved model profiles and project commands.

## Running tasks

Click **Run** on a task card to start an agent run for that task.

Profile selection follows this order:

1. Task profile override.
2. Stage profile.
3. Active default model profile.
4. CLI/env/provider defaults if no saved profile applies.

Command selection follows the stage configuration. The first runnable stage sends the slash command plus task details; later stages can run command-only handoffs when configured. Project commands come from `.agents/commands/*.md` and are documented in [Session Commands](/session-commands#project-slash-commands).

Task image attachments are included only with the initial full task prompt. Later continuation or command-only stage handoffs do not resend the original images. The selected task/stage/default runtime must support image inputs for attached-image tasks to run.

If the board only has Backlog and Done, pbi-agent prompts you to create a runnable stage before starting backlog tasks.

## Moving tasks

Drag tasks between stages to update their status. If a destination stage has **Auto-start** enabled, pbi-agent starts the task automatically after it enters that stage.

The Done column sorts newest-first so recently completed tasks stay visible near the top.

## Dashboard overview

Open **Dashboard** from the web UI header to inspect observability data. The dashboard includes:

- Date-range filters.
- Workspace/global scope toggle.
- KPI cards for run totals, token usage, cost, duration, and errors.
- Provider/model breakdown table.
- All Runs table with status, provider, model, duration, cost, token counts, and errors.
- Run detail modal with recorded request/tool events.

## Workspace vs global scope

| Scope | Meaning |
| --- | --- |
| Workspace | Shows runs associated with the current workspace. |
| Global | Shows runs across all stored pbi-agent workspaces. |

Use global scope when comparing cost or reliability across projects. Use workspace scope when debugging the current repository.

## Run details

The All Runs table opens a detail modal for a selected run. Use it to inspect:

- Run status and duration.
- Provider, model, profile, and session metadata.
- Request/response observability events.
- Tool calls, inputs, outputs, and failures.
- Token and estimated cost accounting.

Session pages also show a per-session run history, which is useful when you want the run list next to the conversation that produced it.

## Recommended setup

1. Create at least one [model profile](/model-profiles).
2. Add project commands under `.agents/commands/`, such as `/plan`, `/execute`, or `/review`.
3. Open Kanban and create custom stages like `Ready`, `Implement`, and `Review`.
4. Assign a profile and command to each runnable stage.
5. Enable Auto-start only for stages where automatic handoff is safe.
6. Use Dashboard to review cost, failures, and tool behavior after runs complete.

## Related pages

- [Web UI](/web-ui)
- [Model Profiles](/model-profiles)
- [Session Commands](/session-commands)
- [Customization](/customization#project-command-files)
