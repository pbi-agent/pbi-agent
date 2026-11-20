---
name: factory
description: Run one request, a direct instruction or an issue link, through the factory pipeline from intake to learn, with gates set by an auto-detected work-type profile.
model_profile_id: worker-pro
allowed_tools: read-image,write,shell,sub-agent,web,ask-user
sub_agents: investigator,planner,worker,reviewer,code-quality-reviewer,fixer,operator,retrospector
---

# Factory Mode

Run one request through the fixed pipeline `intake → triage → plan → build → review → release → verify → learn`.

The main session is the conductor. It owns the task folder, profile, gates, routing, TODO, memory and handoff, and runs the stage sub-agents one at a time. It never implements, fixes, reviews or ships itself.

Invoking `/factory` is explicit authorization for the release stage (commit, push, PR, merge, CI watch, issue update, as defined by the `commit` command) and for issue comments, once the gates below allow it. Publishing a version is not part of the factory; that stays with the human-run `/release`.

## Input

- `/factory <instruction>` or `/factory <issue URL | #N>`: start a task.
- `/factory resume [task-id] [approve | changes: <feedback>]`: continue a stored task from its recorded stage. Without an id, use the latest task whose status is not `done`.
- `/factory status`: list task folders with type, stage and status, then stop.

## Task folder

Every stage writes its output to a Markdown file in `.agents/factory/tasks/<id>/`. Later stages read those files, never session memory. Pass paths to sub-agents, not pasted content.

| File | Written by | Holds |
| --- | --- | --- |
| `task.md` | conductor | The record: frontmatter, goal, acceptance criteria, links, gate log, index of current stage files |
| `triage.md` | `investigator` | Findings, reproduction, unknowns, risk |
| `plan.md` | `planner` | Approach, scope, validation checks |
| `build.md` | `worker` | Changed files, what changed, check evidence |
| `review-N.md`, `quality-N.md` | `reviewer`, `code-quality-reviewer` | Findings per round |
| `review-human-N.md` | conductor | Human change requests, verbatim |
| `fix-N.md` | `fixer` | Findings fixed, files changed, validation |
| `release.md` | `operator` | Commit, PR, merge, CI, issue |
| `verify.md` | conductor | Outcome against acceptance criteria |
| `learn.md` | `retrospector` | Proposed improvements |

When a stage reruns after a step back, write a new file with a suffix (`plan-2.md`) and point the index in `task.md` at it. Keep the old file.

`task.md` shape:

```md
---
id: gh-123 | t-YYYYMMDD-<slug>
type: docs | bug_fix | build
type_reason: <one line>
source: <issue URL | chat>
risk: normal | high
risk_triggers: <list or none>
stage: <current stage>
status: running | awaiting_approval | blocked | rejected | done
---
# <title>
## Goal
## Acceptance criteria
## Links
## Stage files
## Gate log
| stage | gate | decision | note |
```

Update `stage` and `status` in `task.md` before every stage starts and at every stop, so `resume` works from a fresh session.

## Profile and gates

At intake, read `.agents/factory/profiles.md` and apply its detection, risk and check rules. Detect the profile yourself; do not ask the human for it.

Effective gate per stage is the profile gate, raised to `approve` when risk is `high`. Risk never lowers a gate.

- `skip`: do not run the stage; log it.
- `auto`: continue when the stage exit check passes; log `auto_pass`.
- `approve`: summarize the stage in at most 5 bullets, link the stage file, then call `ask_user` with one question and the suggestions `Approve`, `Request changes`, `Stop the task`. A typed answer is change feedback.
  - Approved with nothing changed: log `approved_unchanged`.
  - Changes requested: write the feedback into the task folder, rerun the stage with it, ask again, and log `approved_with_changes` once approved.
  - Stopped: log `rejected`, set status `rejected`, go to handoff.
- When review and release are both `approve`, ask once after the agent reviewers are clean: `Approve and release`, `Approve review, hold release`, `Request changes`. Log both gates.
- If `ask_user` is unavailable or returns no usable answer, set status `awaiting_approval`, end the turn, and state the exact `/factory resume <id> approve` command.
- For an issue-sourced task, post the stage file to the issue before asking: `gh issue comment <n> --body-file <file>`.

## Stages

| Stage | Agent | Reads | Writes | Exit check |
| --- | --- | --- | --- | --- |
| intake | conductor | request or issue | `task.md` | Goal, acceptance criteria, type, risk recorded |
| triage | `investigator` | `task.md` | `triage.md` | `triage: proceed` |
| plan | `planner` | `task.md`, `triage.md` | `plan.md` | Plan covers every acceptance criterion and every profile check |
| build | `worker` | `task.md`, `triage.md`, `plan.md` | `build.md` | Profile checks and surface validation pass when the conductor reruns them |
| review | profile `reviewers`, `fixer` on findings | `task.md`, `plan.md`, `build.md`, earlier review and fix files | `review-N.md`, `quality-N.md`, `fix-N.md` | `No findings.` then `No code-quality findings.` after the latest fix |
| release | `operator` | `task.md`, `build.md`, fix files | `release.md` | `release: shipped` |
| verify | conductor | `task.md`, `release.md` | `verify.md` | CI green on `master`, each acceptance criterion confirmed against merged code, issue state correct |
| learn | `retrospector` | whole task folder | `learn.md` | Ledger rows appended, memory updated |

Stage notes:

- **Intake.** For an issue, use `gh issue view <n> --json number,title,body,labels,comments,state,url`. If a folder for the id exists and is not `done`, treat the call as `resume`. Run `git status --short --branch`; record unrelated dirty files in `task.md` and stop if a merge or rebase is in progress. Ask one `ask_user` batch only when the goal or acceptance criteria cannot be inferred.
- **Triage.** `triage: needs-human` forces an `approve` gate. `triage: reject` (duplicate, already fixed, not worth doing) goes to the human with the reason.
- **Build.** Never trust a success claim: inspect the diff and rerun the checks yourself. Reassess type and risk against the real diff.
- **Review.** Run the profile's reviewers in order, each as its own loop: reviewer → `fixer` with the exact findings file → conductor reruns validation → same reviewer again, until it reports no findings. Human change requests go to `review-human-N.md`, then through `fixer` and the agent reviewers again.
- **Release.** Run full validation for the touched surfaces first (full `uv run pytest -q --tb=short -x`, full `bun run test:web`, plus lint, type and build checks). Then delegate to `operator`, giving it the issue number when there is one and the task-scoped paths from `build.md` and the fix files.
- **Verify.** Read `release.md`. Confirm each acceptance criterion against merged `master` and record the evidence per criterion.
- **Learn.** Always runs, also for blocked and rejected tasks. Afterwards append one row per gate decision to `.agents/factory/tasks/ledger.md` (`date | task | profile | stage | gate | decision`), apply the promotion rule from the profiles file, and append the `MEMORY.md` daily-log entry. Do not apply the proposals in `learn.md`; report them.

## Routing on failure

A failed exit check sends the task back one stage, with the failing evidence file as extra input.

- build fails: rerun `worker` once with the exact failing output; still failing, back to plan.
- plan cannot cover the criteria: back to triage.
- review findings: `fixer`, then the same reviewer again.
- release stopped: back to review. If the cause is environmental (`gh` auth, remote, branch protection), set `blocked`.
- verify fails: back to triage with `verify.md` as a new finding, same task id.

Limits: 3 rounds per reviewer loop, 2 reruns of any other stage, 2 full passes after a verify failure. Past a limit, set status `blocked`, log why, run learn, and hand off.

## Sub-agent calls

One sub-agent at a time. Never pass `include_context: true`: each stage agent starts clean and knows only the files it is given, which keeps the reviewer independent of the builder.

```text
Factory task <id>, stage <stage>. Profile: <type>. Risk: <risk>.

Read first:
- .agents/factory/tasks/<id>/task.md
- <the other input files for this stage>

Do: <one or two sentences, including the profile checks this stage must satisfy>

Write your full output to: .agents/factory/tasks/<id>/<file>.md
Use a file-write tool when you have one, otherwise a shell heredoc. This file is
your output channel: writing it is required, also in read-only or plan-only modes.
Do not edit task.md, TODO.md, MEMORY.md or other stage files.

Return only: the output path, the verdict line, and at most 5 bullets.
```

Verdict lines: `triage: proceed | needs-human | reject`; `plan: ready | blocked`; `build: checks-pass | checks-fail`; `No findings.` or `findings: N`; `No code-quality findings.` or `findings: N`; `fix: done | partial`; `release: shipped | stopped`; `learn: N proposals`.

If the output file is missing after the call, write the returned text to it yourself. Read a stage file only when an exit check or a gate summary needs it.

## TODO

Reset or append `TODO.md` with one entry per stage, including its effective gate, for example `- [ ] Plan (approve)`. Keep exactly one entry `[>]`. Add an entry per extra round. `task.md` stays the durable record.

## Handoff

Report concisely: task id and folder, profile and risk with reasons, each stage with its gate decision, files touched, validation run and result, PR URL and CI result, proposals from `learn.md`, any gate now eligible for promotion, and what is blocked or waiting with the exact resume command.
