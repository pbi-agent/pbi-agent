---
name: factory
description: Run one request, a direct instruction or an issue link, through the factory pipeline from intake to learn, with gates set by an auto-detected work-type profile.
sub_agents: investigator,planner,worker,reviewer,code-quality-reviewer,fixer,operator,retrospector
---

# Factory Mode

Run one request through fixed pipeline `intake → triage → plan → build → review → verify → release → learn`.

Main session = conductor. Owns task folder, profile, gates, routing, TODO, memory, handoff; runs stage sub-agents one at a time. Never implements, fixes, reviews or ships itself.

Invoking `/factory` = explicit authorization for release stage (commit, push, PR, merge, CI watch, as defined by `commit` command) and the brief issue comments under `## Issue updates`, once gates below allow it. Publishing a version is not part of factory; stays with human-run `/release`.

## Input

- `/factory <instruction>` or `/factory <issue URL | #N>`: start task.
- `/factory resume [task-id] [approve | changes: <feedback>]`: continue stored task from recorded stage. Without id, use latest task whose status is not `done`.
- `/factory status`: list task folders with type, stage, status; stop.

## Task folder

Every stage writes output to a Markdown file in `.agents/factory/tasks/<id>/`. Later stages read those files, never session memory. Pass paths to sub-agents, not pasted content.

| File | Written by | Holds |
| --- | --- | --- |
| `task.md` | conductor | Record: frontmatter, goal, acceptance criteria, links, gate log, index of current stage files |
| `triage.md` | `investigator` | Findings, reproduction, unknowns, risk |
| `plan.md` | `planner` | Approach, scope, validation checks |
| `build.md`, `build-<group>.md` | `worker` | Changed files, what changed, check evidence |
| `review-N.md`, `quality-N.md` | `reviewer`, `code-quality-reviewer` | Findings per round |
| `review-human-N.md` | conductor | Human change requests, verbatim |
| `fix-N.md` | `fixer` | Findings fixed, files changed, validation |
| `verify.md` | conductor | Validation, live check, evidence per acceptance criterion |
| `release.md` | `operator` | Commit, PR, merge, CI, issue |
| `learn.md` | `retrospector` | Proposed improvements |

Stage reruns after step back: write new file with suffix (`plan-2.md`), point `task.md` index at it, keep old file. `review-N`, `quality-N` count rounds per reviewer; `fix-N` counts across whole task.

Task folders and `ledger.md` are committed to repo. Release commit carries task folder as written up to release (`task.md`, triage, plan, build, review, quality, fix, verify files). Files written after that commit (`release.md`, `learn.md`, later `task.md` updates, new `ledger.md` rows) stay in working tree; next factory release commit includes them.

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
<!-- decision is one of: auto_pass, skipped, approved_unchanged, approved_with_changes, rejected, blocked -->
## Stage log
| stage | round | result | note |
<!-- reviewer and fixer rounds, validation runs, release outcome -->
```

Gate log `gate` column = effective gate (`auto`, `approve`, `skip`), or `always_run` for stages profiles file lists under `always_run`; those log `auto_pass` when exit check passes.

Update `stage` and `status` in `task.md` before every stage starts and at every stop, so `resume` works from fresh session.

## Profile and gates

At intake, read `.agents/factory/profiles.md`; apply its detection, risk and check rules. Detect profile yourself; do not ask human.

Effective gate per stage = profile gate; when risk is `high`, every `auto` gate becomes `approve` (`skip` stays `skip`). Risk never lowers a gate.

- `skip`: do not run stage; log `skipped`.
- `auto`: continue when stage exit check passes; log `auto_pass`.
- `approve`: summarize stage in max 5 bullets, link stage file, call `ask_user` with one question and suggestions `Approve`, `Request changes`, `Stop the task`. Typed answer = change feedback, except typed `stop` (any case), which = `Stop the task`.
  - Approved, nothing changed: log `approved_unchanged`.
  - Changes requested: write feedback into task folder, rerun stage with it, ask again; log `approved_with_changes` once approved.
  - Stopped: log `rejected`, set status `rejected`, run learn, then hand off.
- Review and release both `approve`: ask once after agent reviewers are clean and verify passes: `Approve and release`, `Approve review, hold release`, `Request changes`. No stop option fits: say in question that typing `stop` stops task. Log both gates. On hold, log only review decision; set status `awaiting_approval` at stage release.
- If `ask_user` unavailable or returns no usable answer: set status `awaiting_approval`, end turn, state exact `/factory resume <id> approve` command.

## Issue updates

Issue-sourced task only. Never post stage files or per-stage progress to the issue. Post at most:

- End, shipped: `operator` posts one brief comment (outcome in one or two sentences, PR link, merge commit, follow-ups not built). It does not edit issue title or body; this overrides `commit` step 7.
- Blocked or rejected: conductor posts one brief comment: what stopped it, what is needed, PR link if one exists. Skip if the last comment already says the same.

## Stages

| Stage | Agent | Reads | Writes | Exit check |
| --- | --- | --- | --- | --- |
| intake | conductor | request or issue | `task.md` | Goal, acceptance criteria, type, risk recorded |
| triage | `investigator` | `task.md` | `triage.md` | `triage: proceed` |
| plan | `planner` | `task.md`, `triage.md` | `plan.md` | Plan covers every acceptance criterion and every profile check |
| build | `worker` | `task.md`, `triage.md`, `plan.md` | `build.md` | Profile checks and surface validation pass when conductor reruns them |
| review | profile `reviewers`, `fixer` on findings | `task.md`, `plan.md`, `build.md`, earlier review and fix files | `review-N.md`, `quality-N.md`, `fix-N.md` | `No findings.` then `No code-quality findings.` after the latest fix |
| verify | conductor | `task.md`, `plan.md`, `build.md`, fix files | `verify.md` | Full validation passes, live check passes, each acceptance criterion confirmed against working tree: `verify: pass` |
| release | `operator` | `task.md`, `build.md`, fix files, `verify.md` | `release.md` | `release: shipped` (PR merged, PR checks and CI on merge commit green, issue state correct) |
| learn | `retrospector` | whole task folder | `learn.md` | Ledger rows appended, memory updated |

Stage notes:

- **Intake.** Issue: `gh issue view <n> --json number,title,body,labels,comments,state,url`. If folder for id exists and is not `done`, treat call as `resume`. Run `git status --short --branch`. Record unrelated dirty files in `task.md`. Stop if merge or rebase in progress. Ask one `ask_user` batch only when goal or acceptance criteria cannot be inferred. Run `git rev-list --oneline origin/<base>..<base>`; base is `master`. Unpushed commits on base: list under `## Environment notes` in `task.md`. Out of scope unless human includes them: release-gate `ask_user` call then adds second question (each question takes exactly three suggestions) with options `Ship them as separate commits in this PR`, `Exclude them (release from origin/<base>)`, `Stop`. When release is `auto`, ask that question alone before release. Pass chosen scope to `operator` verbatim. Without that decision, release must not start from base ahead of its upstream.
- **Triage.** `triage: needs-human` forces `approve` gate. `triage: reject` (duplicate, already fixed, not worth doing) goes to human with reason through `approve` gate.
- **Build.** Never trust success claim: inspect diff, rerun checks yourself. Reassess type and risk against real diff. Stage agents do not spawn sub-agents (pbi-agent runtime rejects nested runs for agents without scoped `sub_agents` list; nested time counts against parent's cap). `plan.md` splits work into groups: run `worker` once per group in plan order, each writing `build-<group>.md` and running that group's checks. Then one final `worker` pass integrates, runs full checks, writes `build.md`.
- **UI and CLI evidence.** Triage reproduces on base and build verifies the change, both with the `verify` skill (scratch-server recipe for web). Reviewers reuse `build.md` measurements and run only targeted checks for claims they doubt.
- **Review.** Run profile's reviewers in order, each as own loop: reviewer → `fixer` with exact findings file → conductor reruns validation → same reviewer again, until no findings. Later reviewer's fixes do not reopen earlier reviewer's clean loop. Human change requests go to `review-human-N.md`, then through `fixer`, agent reviewers and verify again.
- **Verify.** Runs after agent reviewers are clean, before the release gate question; it is the pre-commit check. Run full validation for touched surfaces (full `uv run pytest`, full `bun run test:web`, plus lint, type, build checks; `bun run docs:build` for docs). For web or CLI behavior, run the `verify` skill live: if no `fix-N` changed source since the live check in `build.md`, a smoke check of the primary acceptance criterion with the build fixtures; otherwise the full check. Confirm each acceptance criterion against the working tree; record evidence per criterion and the verdict line in `verify.md`. Any source change after verify (human change requests) reruns verify.
- **Release.** Delegate to `operator` with: issue number when there is one, task-scoped paths from `build.md` and fix files, task folder `.agents/factory/tasks/<id>/`, and the human's decision on unpushed base commits (ship or exclude) when intake found any. Afterwards read `release.md` and confirm with `gh` that the PR is merged, CI on the merge commit is green and the issue state is correct.
- **Learn.** Always runs, also for blocked and rejected tasks. Afterwards append one row per gate decision to `.agents/factory/tasks/ledger.md` (`date | task | profile | stage | gate | decision`). Ledger rows come only from `## Gate log`; one row per gated stage; combined review+release question logs two rows. Apply promotion rule from profiles file. Append `MEMORY.md` daily-log entry. Leave post-release task files and ledger rows uncommitted for next factory release. Do not apply proposals in `learn.md`; report them.

## Routing on failure

Failed exit check sends task back one stage, with failing evidence file as extra input.

- build fails: rerun `worker` once with exact failing output; still failing, back to plan.
- plan cannot cover criteria: back to triage.
- review findings: `fixer`, then same reviewer again.
- verify fails: back to build with `verify.md` as failing evidence (`worker` rerun), then review and verify again; criterion the plan cannot meet: back to plan.
- release stopped: back to review. Environmental cause (`gh` auth, remote, branch protection): set `blocked`. CI on `master` red after merge: set `blocked`, report failing run.

Limits: 3 rounds per reviewer loop, 2 reruns of any other stage, 2 full passes after verify failure. Past a limit: set status `blocked`, log why, run learn, hand off.

## Sub-agent calls

One sub-agent at a time. Never pass `include_context: true`: each stage agent starts clean, knows only files given; keeps reviewer independent of builder.

```text
Factory task <id>, stage <stage>. Profile: <type>. Risk: <risk>.

Read first:
- .agents/factory/tasks/<id>/task.md
- <the other input files for this stage>

Do: <one or two sentences, including the profile checks this stage must satisfy
and, for planner, worker and fixer, the verdict line the file must contain>

Write your full output to: .agents/factory/tasks/<id>/<file>.md
Use a file-write tool when you have one, otherwise a shell heredoc. This file is
your output channel: writing it is required, also in read-only or plan-only modes.
Do not edit task.md, TODO.md, MEMORY.md or other stage files.

Return only: the output path, the verdict line, and at most 5 bullets.
```

Verdict lines: `triage: proceed | needs-human | reject`; `plan: ready | blocked`; `build: checks-pass | checks-fail`; `No findings.` or `findings: N`; `No code-quality findings.` or `findings: N`; `fix: done | partial`; `release: shipped | stopped`; `verify: pass | fail`; `learn: N proposals`.

Output file missing after call: write returned text to it yourself. Read stage file only when exit check or gate summary needs it.

## TODO

Follow `AGENTS.md` TODO rule. Add one `TODO.md` entry per stage with its effective gate, e.g. `- [ ] Plan (approve)`. Keep exactly one entry `[>]`. Add entry per extra round. `task.md` stays durable record.

## Handoff

Report concisely: task id and folder; profile and risk with reasons; each stage with gate decision; files touched; validation run and result; PR URL and CI result; proposals from `learn.md`; any gate now eligible for promotion; pending task files to commit (post-release files, ledger rows); what is blocked or waiting, with exact resume command.
