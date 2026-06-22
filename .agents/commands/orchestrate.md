---
name: orchestrate
description: Run one implementation task through an optional initial planning step, then mandatory sequential worker, reviewer/fixer, and code-quality/fixer loops.
model_profile_id: worker-pro
allowed_tools: read,write,shell,sub-agent,web
sub_agents: planner,worker,reviewer,code-quality-reviewer,fixer
---

# Orchestrate Mode

Run one cohesive implementation task through a single sequential workflow. The main agent orchestrates only: it owns scope, ordering, validation, TODO/memory/handoff, and quality gates. It never implements or fixes directly.

## Core Rules

- Treat the request as one task. No parallel work, parallel sub-agents, or batched independent TODOs. Run exactly one sub-agent at a time and wait for each result before the next step.
- Decide before implementation whether the user already provided a plan. If a user plan exists, skip `planner` and start with `worker` using that plan. If no user plan exists, run `planner` as the first step only, review its plan, then continue with `worker`.
- Delegate implementation to `worker` and fixes to `fixer`; the main agent never writes task changes itself.
- Required gate order per task: optional `planner` only when the user did not provide a plan → `worker` → main diff/validation → `reviewer` loop (`reviewer` → `fixer` on review findings → rerun `reviewer` until no findings) → `code-quality-reviewer` loop (`code-quality-reviewer` → `fixer` on code-quality findings → rerun `code-quality-reviewer` until no findings) → final validation/handoff.
- Review every sub-agent result before accepting. Never trust a success claim: inspect the diff and rerun focused validation.
- Task is accepted only after the review loop reports no findings, then the code-quality loop reports no findings after its latest fixes.
- Preserve unrelated worktree changes.

## Start Procedure

- Inspect current workspace changes.
- Identify unrelated dirty files; do not touch them.
- Determine whether the user provided an implementation plan. When the user provided a plan, do not run `planner` or ask for another plan; start the workflow at `worker`. When no plan was provided, run `planner` first and do not run it again later.

## TODO Setup

Create or reset `TODO.md`. Only the main agent edits it.

Markers (GitHub task-list bullets): `- [ ]` pending, `- [>]` in progress, `- [x]` accepted, `- [!]` blocked, `- [-]` dropped.

Rules:
- One TODO entry per workflow step—do not collapse the workflow into a single implementation TODO.
- Keep exactly one entry `[>]` at a time.
- Mark a step `[x]` only after the main agent reviews its result.
- Add repeat-cycle entries as needed (e.g. `Fixer round 2`, `Reviewer round 3`, `Code-quality-reviewer round 2`). Feed exact findings back into the active loop; never convert findings into broad new tasks.

Good shape:

```md
- [>] Planner: create plan for <task> (only when no user plan was provided)
- [ ] Main: review planner plan
- [ ] Worker: implement <task>
- [ ] Main: inspect worker diff and run focused validation
- [ ] Reviewer round 1: review implementation
- [ ] Fixer round 1: resolve reviewer findings when needed
- [ ] Reviewer round 2: verify fixer changes when needed
- [ ] Code-quality-reviewer round 1: review maintainability
- [ ] Fixer round 2: resolve code-quality findings when needed
- [ ] Code-quality-reviewer round 2: verify code-quality fixes when needed
- [ ] Final validation
- [ ] Update memory
- [ ] Handoff
```

If the user provided a plan, omit the planner TODO entries and make `Worker: implement <task>` the first active step.

Bad shape (workflow collapsed):

```md
- [>] Implement <task>
- [ ] Final validation
- [ ] Update memory and handoff
```

## Sequential Execution Loop

1. If the user did not provide a plan: mark `Planner: create plan for <task>` `[>]`; delegate to `planner` for planning only; mark planner `[x]`, then mark `Main: review planner plan` `[>]`, review the returned plan, and mark it `[x]`. Never run `planner` after this first step. If the user provided a plan, skip this step entirely.
2. Mark `Worker: implement <task>` `[>]`; delegate to `worker` with a narrow prompt that includes the user-provided plan or the reviewed planner plan.
3. Review the `worker` result; mark its TODO `[x]`.
4. Mark main diff/validation `[>]`; inspect the diff, run focused validation, mark `[x]` or `[!]`.
5. Mark `Reviewer round 1` `[>]`; run `reviewer`; mark `[x]` after reading the result.
6. If `reviewer` reports findings: add/mark `Fixer round N` `[>]`, delegate the exact findings to `fixer`.
7. After each `fixer` result: mark its TODO `[x]`, add/mark a main diff/validation rerun `[>]`, inspect diff, rerun validation, mark `[x]` or `[!]`.
8. Add/mark `Reviewer round N+1` `[>]` and rerun; repeat 6–8 until `reviewer` reports no findings.
9. Mark `Code-quality-reviewer round 1` `[>]`; run it on the task, final diff, reviewer outcome, and validation; mark `[x]` after reading.
10. If `code-quality-reviewer` reports findings: add/mark `Fixer round N` `[>]`, delegate the exact code-quality findings to `fixer`, and mark `[x]` after reading the fixer result.
11. After each code-quality fixer result: add/mark a main diff/validation rerun `[>]`, inspect diff, rerun validation, mark `[x]` or `[!]`, then add/mark `Code-quality-reviewer round N+1` `[>]` and rerun. Repeat 10–11 until `code-quality-reviewer` reports no findings.
12. Complete final validation, memory, and handoff as separate TODOs. Done only when the reviewer loop and code-quality loop have both ended with no findings and every TODO is `[x]`, `[-]`, or `[!]` with explanation.

Never use parallel execution.

## Sub-Agent Prompts

When `planner` is needed, prompt it for planning only:

```text
Create an implementation plan only for this task: <task title>.

Goal:
<one sentence: required correctness or user-visible outcome>

Context:
- User did not provide an implementation plan, so this is the only planning step.
- Relevant files/symbols/routes/tests if known: <specific paths and names, or unknown>
- Repo conventions to preserve: <validation, contracts, no migrations, style>

Scope:
- Do not edit files.
- Do not run implementation.
- Do not edit TODO.md or MEMORY.md.
- Keep the plan focused on the requested task only.

Return exactly:
- Brief plan steps
- Files/areas likely involved
- Focused validation to run
- Risks or assumptions
```

Make every `worker`/`fixer` prompt concrete and bounded:

```text
Implement the single assigned task only: <task title>.

Goal:
<one sentence: required correctness or user-visible outcome>

Context:
- Relevant files/symbols/routes/tests: <specific paths and names>
- Current failure/risk: <exact bug, failing assertion, or scenario>
- Repo conventions to preserve: <validation, contracts, no migrations, style>

Scope:
- Allowed files/areas: <paths or subsystems>
- Do not implement unrelated work.
- Do not edit TODO.md or MEMORY.md.
- Do not change generated/static assets unless this task requires it.
- Preserve unrelated worktree changes.

Implementation expectations:
- Make the smallest correct change.
- Add/update focused tests proving this specific fix.
- Keep backend/frontend/API/generated contracts aligned when touched.
- Prefer behavior-level fixes over broad rewrites.

Validation to run if feasible:
- <focused test command(s)>
- <lint/typecheck/codegen command(s) for the touched surface>

Return exactly:
- Changed files
- What changed
- Validation commands and results
- Residual risks or follow-up intentionally not handled
```

For `fixer`, replace Goal/Context with the exact current-loop findings to resolve: `reviewer` findings during the review loop, or `code-quality-reviewer` findings during the code-quality loop.

`reviewer` prompt must include: task scope and acceptance criteria; changed files/diff summary; validation run by main agent and sub-agents; prior `reviewer` findings when rerunning after fixes; any exact issue from main-agent review.

`code-quality-reviewer` prompt must include: task scope and acceptance criteria; final reviewer outcome showing no findings; changed files/diff summary; validation run after the latest fixes.

## Review Gate

Main-agent review supplements—never replaces—the sub-agent gates. Check:
- Diff matches the assigned task only; no unrelated TODOs, broad cleanup, or memory edits.
- API schemas, generated types, event parsers, persistence, and frontend boundaries stay aligned.
- Concurrency/lifecycle code adds no races, stale state, missed cleanup, or silent failure.
- Terminal states and snapshots persist before visible lifecycle events when relevant.
- Tests cover the old failure and the new expected behavior directly.
- Focused validation passes when the main agent runs it.
- Generated/static files tracked when changed.

If review fails: do not proceed; state the blocking issue briefly; rerun `reviewer` with the exact issue; launch `fixer` only for reviewer-reported findings; rerun validation + `reviewer`.

## Final Validation

Run validation for every touched surface:
- Python: `uv run ruff check .`, `uv run ruff format --check .`, `uv run pytest -q --tb=short -x`
- Frontend: `bun run test:web`, `bun run lint`, `bun run typecheck`, `bun run web:build`
- API/SSE contract changes: run project codegen command and codegen tests
- Static web assets: verify rebuilt hashed chunks are tracked

If new failures appear: reopen the implementation TODO, isolate the failure, rerun the affected loop in order (`reviewer`/`fixer` until review has no findings, then `code-quality-reviewer`/`fixer` until code quality has no findings), rerun focused validation, then run final validation again.

## Handoff

Report concisely: tasks completed; files/areas touched; validation commands and results; remaining workspace changes.

Complete only when every TODO is `[x]`, `[-]`, or `[!]` with explanation, every sub-agent result reviewed, final validation passed or blockers explicit, and unrelated dirty files preserved.
