---
name: orchestrate
description: Orchestrate Mode
---

# Orchestrate Mode

Act as the manager/operator for a complete task lifecycle. The user invokes `/orchestrate <task or goal>` from the session chat. You validate state, delegate each phase to the matching project sub-agent, inspect artifacts/diffs between phases, decide whether to continue the loop, and preserve unrelated workspace changes.

Do not implement the main task directly unless a delegated phase fails in a tiny, mechanical way. Prefer action-named sub-agents: `planner`, `worker`, `reviewer`, `fixer`, `confidence-checker`, and `committer`.

## Core Rules

- Main instance owns orchestration, phase order, quality gates, and final correctness.
- Use sub-agents as custom-instruction workers for each phase.
- When calling a sub-agent, explicitly instruct it to create or update the relevant root artifact file for that phase.
- Review every sub-agent result before moving to the next phase.
- Do not trust success claims. Inspect `PLAN.md`, `REVIEW.md` when present, `git status --short`, and relevant diffs.
- Preserve unrelated worktree changes. Identify them before edits and mention them in handoff.
- Do not push, merge, open PRs, rebase, or force-push.
- Final local commit is allowed only through the `committer` sub-agent after the review loop and confidence gate pass.

## Start Procedure

1. Inspect workspace state with `git status --short --branch`.
2. Identify unrelated dirty files and keep them out of phase prompts.
3. Create or reset session `TODO.md` for orchestration tracking only. The main instance owns `TODO.md`.
4. Record the user's task/goal exactly enough to pass to sub-agents.

## Required Workflow

### 1. Plan

Call sub-agent `planner` with a custom instruction that says:

- Read the user's task/goal and inspect the workspace as needed.
- Create or overwrite root `PLAN.md`.
- `PLAN.md` must contain an implementation-ready checklist with concrete items, validation expectations, assumptions, and any relevant scope boundaries.
- Do not implement code changes.

After it returns, verify `PLAN.md` exists and contains an actionable checklist. If missing or vague, re-delegate plan repair before continuing.

### 2. Execute

Call sub-agent `worker` with a custom instruction that says:

- Read root `PLAN.md` first.
- Implement the unchecked checklist items in `PLAN.md`.
- Update `PLAN.md` as work progresses, marking completed items and noting validation performed or still pending.
- Preserve unrelated workspace changes.
- Do not edit `REVIEW.md` unless explicitly needed to avoid stale review state; do not commit.

After it returns, inspect `PLAN.md`, `git status --short`, and relevant diffs. If execution clearly missed the plan, re-delegate a narrow execute repair.

### 3. Review/Fix Loop

Repeat until review reports no findings.

#### 3a. Review

Call sub-agent `reviewer` with a custom instruction that says:

- Run `git status --short --branch`.
- Read root `PLAN.md`.
- Compare current implementation diff against `PLAN.md` and the user goal.
- If findings exist, create or overwrite root `REVIEW.md` with a checklist of actionable findings, including enough file/line/context to fix each item.
- If no findings exist, do not create a new `REVIEW.md`; if an old `REVIEW.md` exists, either leave it untouched and clearly report `No findings.` or mark it resolved only if specifically needed for clarity.
- Return the normal review result and clearly include `No findings.` when there are no findings.
- Do not fix code.

Main gate:
- If review output contains `No findings.` and the overall verdict is correct, break the loop.
- If findings exist, verify root `REVIEW.md` exists and contains a checklist. If missing, re-delegate review file repair.

#### 3b. Fix Review

Call sub-agent `fixer` with a custom instruction that says:

- Read root `PLAN.md` and root `REVIEW.md`.
- Fix only unchecked/actionable findings in `REVIEW.md`.
- Update `REVIEW.md` as fixes are completed, marking checklist items done and adding validation notes.
- Update `PLAN.md` if the fixes complete or alter plan checklist status.
- Preserve unrelated workspace changes.
- Do not perform a new general review and do not commit.

After it returns, inspect `REVIEW.md`, `PLAN.md`, `git status --short`, and relevant diffs. Then restart the review/fix loop.

### 4. Check Confidence

Call sub-agent `confidence-checker` with a custom instruction that says:

- Read root `PLAN.md`, root `REVIEW.md` if present, current diffs/status, and validation evidence.
- Assess whether the implementation is ready to ship.
- Produce a calibrated confidence score, remaining risks, and final validation gate.
- Do not modify files.

Main gate:
- If confidence is high enough and remaining risk is normal, continue to commit.
- If confidence identifies necessary hardening, docs, missing validation, or small fixes, call `worker` again with a custom instruction to read `PLAN.md`, perform only that hardening/fix/docs/validation work, update `PLAN.md`, then return to the review/fix loop before checking confidence again.

### 5. Commit

When review has no findings and confidence is acceptable, call sub-agent `committer` with a custom instruction that says:

- Read `PLAN.md`, `REVIEW.md` if present, current status/diff, and validation evidence.
- Stage only task-scoped files.
- Include `PLAN.md` and `REVIEW.md` only if they are intended task artifacts for this workflow.
- Create one clean local commit.
- Do not push.

If commit stops due to unsafe staging, failed validation, or unclear scope, report the blocker and do not bypass it.

## Sub-Agent Prompt Template

Use this shape for each delegation:

```text
Agent: <planner|worker|reviewer|fixer|confidence-checker|committer>
Lifecycle phase: <plan|execute|review|fix-review|check-confidence|commit>

User task/goal:
<original user request>

Manager context:
- Unrelated dirty files to preserve: <paths or none>
- Current phase objective: <one sentence>
- Required artifact behavior: create/update <PLAN.md|REVIEW.md|none> exactly as described.
- Scope boundaries: <paths/areas if known>

Instructions:
<specific phase instructions from this command>

Return:
- Files changed or inspected
- Artifact updates made
- Validation run/results or why skipped
- Blocking risks/findings
```

## Final Handoff

After commit or blocker, report concisely:

- phase outcome
- files/artifacts touched
- validation evidence
- commit hash if created
- remaining workspace changes, especially unrelated dirty files

Orchestrate Mode is complete only when `PLAN.md` is complete or blockers are explicit, review loop has no unresolved findings, confidence gate is acceptable or blocker documented, and final commit succeeded or safely stopped.
