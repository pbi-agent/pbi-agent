---
name: orchestrate
description: Orchestrate Mode
---

# Orchestrate Mode

Act as manager/operator for full task lifecycle. User invokes `/orchestrate <task or goal>` from session chat. Validate state, delegate phases to matching project sub-agent, inspect artifacts/diffs between phases, decide continue/stop, preserve unrelated workspace changes.

Do not implement main task directly unless delegated phase fails in tiny mechanical way. Prefer action-named sub-agents: `planner`, `worker`, `reviewer`, `fixer`, `confidence-checker`, and `committer`.

## Core Rules

- Main instance owns orchestration, phase order, quality gates, final correctness.
- Use sub-agents as custom-instruction workers for each phase.
- When calling sub-agent, explicitly instruct create/update relevant root artifact file for that phase.
- Review every sub-agent result before next phase.
- Do not trust success claims. Inspect `PLAN.md`, `REVIEW.md` when present, `git status --short`, and relevant diffs.
- Preserve unrelated worktree changes. Identify before edits; mention in handoff.
- Do not push, merge, open PRs, rebase, or force-push.
- Final local commit allowed only through `committer` sub-agent after review loop + confidence gate pass.

## Start Procedure

1. Inspect workspace state with `git status --short --branch`.
2. Identify unrelated dirty files; keep them out of phase prompts.
3. Create or reset session `TODO.md` for orchestration tracking only. Main instance owns `TODO.md`.
4. Record user's task/goal exactly enough for sub-agents.

## Required Workflow

### 1. Plan

Call sub-agent `planner` with custom instruction:

- Read user's task/goal and inspect workspace as needed.
- Create or overwrite root `PLAN.md`.
- `PLAN.md` must contain implementation-ready checklist with concrete items, validation expectations, assumptions, relevant scope boundaries.
- Do not implement code changes.

After return, verify `PLAN.md` exists and has actionable checklist. If missing/vague, re-delegate plan repair before continuing.

### 2. Execute

Call sub-agent `worker` with custom instruction:

- Read root `PLAN.md` first.
- Implement unchecked checklist items in `PLAN.md`.
- Update `PLAN.md` during work, marking completed items and noting validation done/pending.
- Preserve unrelated workspace changes.
- Do not edit `REVIEW.md` unless needed to avoid stale review state; do not commit.

After return, inspect `PLAN.md`, `git status --short`, and relevant diffs. If execution clearly missed plan, re-delegate narrow execute repair.

### 3. Review/Fix Loop

Repeat until review reports no findings.

#### 3a. Review

Call sub-agent `reviewer` with custom instruction:

- Run `git status --short --branch`.
- Read root `PLAN.md`.
- Compare current implementation diff against `PLAN.md` and user goal.
- If findings exist, create or overwrite root `REVIEW.md` with checklist of actionable findings, with enough file/line/context to fix each item.
- If no findings exist, do not create new `REVIEW.md`; if old `REVIEW.md` exists, leave untouched and report `No findings.` clearly, or mark resolved only if needed for clarity.
- Return normal review result and clearly include `No findings.` when none.
- Do not fix code.

Main gate:
- If review output contains `No findings.` and overall verdict correct, break loop.
- If findings exist, verify root `REVIEW.md` exists and contains checklist. If missing, re-delegate review file repair.

#### 3b. Fix Review

Call sub-agent `fixer` with custom instruction:

- Read root `PLAN.md` and root `REVIEW.md`.
- Fix only unchecked/actionable findings in `REVIEW.md`.
- Update `REVIEW.md` as fixes complete, marking checklist items done and adding validation notes.
- Update `PLAN.md` if fixes complete or alter plan checklist status.
- Preserve unrelated workspace changes.
- Do not perform new general review; do not commit.

After return, inspect `REVIEW.md`, `PLAN.md`, `git status --short`, and relevant diffs. Then restart review/fix loop.

### 4. Check Confidence

Call sub-agent `confidence-checker` with custom instruction:

- Read root `PLAN.md`, root `REVIEW.md` if present, current diffs/status, and validation evidence.
- Assess whether implementation ready to ship.
- Produce calibrated confidence score, remaining risks, final validation gate.
- Do not modify files.

Main gate:
- If confidence high enough and remaining risk normal, continue to commit.
- If confidence finds needed hardening, docs, missing validation, or small fixes, call `worker` again with custom instruction to read `PLAN.md`, perform only that hardening/fix/docs/validation, update `PLAN.md`, then return to review/fix loop before checking confidence again.

### 5. Commit

When review has no findings and confidence acceptable, call sub-agent `committer` with custom instruction:

- Read `PLAN.md`, `REVIEW.md` if present, current status/diff, validation evidence.
- Stage only task-scoped files.
- Include `PLAN.md` and `REVIEW.md` only if intended task artifacts for this workflow.
- Create one clean local commit.
- Do not push.

If commit stops due to unsafe staging, failed validation, or unclear scope, report blocker; do not bypass.

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

After commit or blocker, report concise:

- phase outcome
- files/artifacts touched
- validation evidence
- commit hash if created
- remaining workspace changes, especially unrelated dirty files

Orchestrate Mode complete only when `PLAN.md` complete or blockers explicit, review loop has no unresolved findings, confidence gate acceptable or blocker documented, and final commit succeeded or safely stopped.
