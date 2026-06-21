---
name: orchestrate
description: Run one implementation task through mandatory sequential worker, reviewer, code-quality-reviewer, and fixer sub-agent gates.
model_profile_id: worker-pro
allowed_tools: read,write,shell,sub-agent,web
sub-agent: reviewer,code-quality-reviewer,fixer,worker
---

# Orchestrate Mode

Run a single workflow for the user's implementation task. Do not decompose into parallel batches or independently executed implementation tasks. The main agent is the orchestrator for sub-agents: it owns scope, ordering, validation, TODO/memory/handoff, and quality gates, but it does not implement or fix the task directly.

## Core Rules

Orchestrate one task. Required sub-agents implement, review, and fix.

- Treat the user request as one cohesive implementation task with one sequential workflow.
- Do not split into parallel work, launch parallel sub-agents, or batch independent TODOs.
- Main agent role: orchestrate sub-agents, inspect diffs, run validation, manage TODO/memory, and report results.
- Main agent must not implement assigned task changes or fix findings directly; delegate implementation to `worker` and fixes to `fixer`.
- Use all required roles for every implementation task: `worker`, `reviewer`, `code-quality-reviewer`, and `fixer`.
- Always start implementation by delegating the task to `worker`; never implement an assigned task directly in the main agent.
- Always run `reviewer` after `worker`.
- Resolve every `reviewer` finding with `fixer`, then rerun `reviewer` until `reviewer` reports no findings.
- Only after `reviewer` reports no findings, run `code-quality-reviewer`.
- If `code-quality-reviewer` reports findings, run `reviewer`, resolve any reviewer findings with `fixer`, then rerun `code-quality-reviewer`; repeat until both reviewers report no findings.
- Do not mark a task accepted until `reviewer` and `code-quality-reviewer` both report no findings after the latest fixes.
- Run exactly one sub-agent at a time. Wait for each result before deciding the next sequential step.
- Review every sub-agent result before accept.
- Do not trust sub-agent success claim. Check diff, rerun focused validation.
- If invalid, rerun `reviewer` with the exact issue, then use the mandatory `fixer` + `reviewer` loop; do not bypass it with direct main-agent implementation.
- Preserve unrelated worktree changes.

## Start Procedure

First inspect workspace state:
- Inspect current workspace changes with available tools.
- Identify unrelated dirty files. Do not touch.

## TODO Setup

Create or reset `TODO.md` for Orchestrate session.

Use compact markers:
- `[ ]` pending
- `[>]` in progress
- `[X]` accepted
- `[!]` blocked
- `[-]` dropped

Use one detailed task list TODO for the user's task plus final validation/memory/handoff TODOs. Do not convert reviewer findings into independent implementation TODOs; feed findings back into the sequential `reviewer`/`fixer` loop. Only main agent edits `TODO.md`.

## Single Sequential Execution Loop

Run this loop once for the single implementation task:
1. Mark the TODO `[>]`.
2. Delegate the implementation task to `worker` with a narrow prompt.
3. Wait for the `worker` result.
4. Inspect the diff for that task and run focused validation yourself.
5. Run `reviewer` on the task, diff, and validation results.
6. If `reviewer` reports findings, delegate those exact findings to `fixer`.
7. After every `fixer` result, inspect the diff, rerun focused validation, then rerun `reviewer`.
8. Repeat steps 6-7 until `reviewer` reports no findings.
9. Run `code-quality-reviewer` on the task, final diff, reviewer outcome, and validation results.
10. If `code-quality-reviewer` reports findings, rerun `reviewer` with those findings and the current diff.
11. Resolve any `reviewer` findings with `fixer`, then rerun `reviewer` until it reports no findings.
12. Rerun `code-quality-reviewer`; repeat steps 10-12 until `code-quality-reviewer` reports no findings.
13. Mark the TODO `[X]` only after both `reviewer` and `code-quality-reviewer` report no findings after the latest changes.

Never use parallel execution in Orchestrate Mode.

## Sub-Agent Prompt Requirements

Every `worker` and `fixer` prompt concrete + bounded. Use this structure:

```text
Implement the single assigned task only: <task title>.

Goal:
<one sentence describing the required correctness or user-visible outcome>

Context:
- Relevant files/symbols/routes/tests: <specific paths and names>
- Current failure/risk: <exact bug, failing assertion, or scenario>
- Repo conventions to preserve: <validation, contracts, no migrations, style, etc.>

Scope:
- Allowed files/areas: <paths or subsystems>
- Do not implement unrelated work.
- Do not edit TODO.md or MEMORY.md.
- Do not change generated/static assets unless this task explicitly requires it.
- Preserve unrelated worktree changes.

Implementation expectations:
- Make the smallest correct change.
- Add or update focused tests that prove this specific bug is fixed.
- Keep backend/frontend/API/generated contracts aligned when touched.
- Prefer behavior-level fixes over broad rewrites.

Validation to run if feasible:
- <focused test command(s)>
- <lint/typecheck/codegen command(s) relevant to touched surface>

Return exactly:
- Changed files
- What changed
- Validation commands and results
- Residual risks or follow-up intentionally not handled
```

For `fixer`, replace the Goal/Context with the exact `reviewer` findings to resolve. Do not ask `fixer` to address unreviewed code-quality findings directly; first rerun `reviewer` with those findings, then fix the resulting reviewer findings.

Every `reviewer` prompt must include:
- task scope and acceptance criteria
- changed files/diff summary
- validation run by main agent and sub-agents
- prior `code-quality-reviewer` findings when rerunning after code-quality review
- any exact issue found by main-agent review so the reviewer can confirm or refine actionable findings

Every `code-quality-reviewer` prompt must include:
- task scope and acceptance criteria
- final reviewer outcome showing no findings
- changed files/diff summary
- validation run after the latest fixes

## Review Gate

After each required sub-agent step, review before accept. Main-agent review supplements the sub-agent gates but never replaces them.

Check:
- Diff matches assigned task only.
- No unrelated TODOs, broad cleanup, or memory edits.
- API schemas, generated types, event parsers, persistence, frontend boundaries stay aligned.
- Concurrency/lifecycle code adds no races, stale state, missed cleanup, or silent failure.
- Terminal states and snapshots persist before visible lifecycle events when relevant.
- Tests cover old failure and new expected behavior directly.
- Focused validation passes when main agent runs it.
- Generated/static files tracked when changed.

If review fails:
- Do not proceed.
- State blocking issue briefly.
- Rerun `reviewer` with the exact issue.
- Launch `fixer` only for findings reported by `reviewer`.
- Rerun focused validation + `reviewer` again.

## Final Validation

Run validation for every touched surface.

Common final checks:
- Python: `uv run ruff check .`, `uv run ruff format --check .`, `uv run pytest -q --tb=short -x`
- Frontend: `bun run test:web -- --maxWorkers=2`, `bun run lint`, `bun run typecheck`, `bun run web:build`
- API/SSE contract changes: run the project codegen command and codegen tests
- Static web assets: verify rebuilt hashed chunks are tracked

If final validation reveals new failure:
- Reopen the single implementation TODO.
- Isolate the failure.
- Rerun `reviewer` with the exact failure.
- Resolve resulting reviewer findings with `fixer`; do not fix directly in the main agent.
- Rerun focused validation, then the required `reviewer` and `code-quality-reviewer` gates again before final validation.

## Handoff

At end, report concise:
- tasks completed
- files or areas touched
- validation commands and results
- remaining workspace changes

Orchestrate Mode complete only when every TODO is `[X]`, `[-]`, or `[!]` with explanation, every sub-agent result reviewed, final validation passed or blockers explicit, and unrelated dirty files preserved.