---
name: orchestrate
description: Orchestrate Mode
---

# Orchestrate Mode

Decompose work into fewest accurate sub-agent tasks. Use single sub-agent when work is best as one coherent implementation. Execute in parallel only when tasks fully isolated + dependency-free; otherwise execute sequentially. Main agent owns quality.

## Core Rules

Own task. Sub-agents implement only.

- Own scope, ordering, TODO state, memory, final correctness.
- Default to one implementation sub-agent at a time unless safe parallel batch qualifies below.
- Do not force multiple sub-agent steps when one bounded task clearer or more accurate.
- Run sub-agents in parallel only when scopes completely isolated, touch different code areas, and have no ordering, data, contract, or validation dependency.
- Review every sub-agent result before accept.
- Do not trust sub-agent success claim. Check diff, rerun focused validation.
- If invalid, fix directly or launch repair sub-agent with exact finding.
- Do not move next until current task reviewed + valid.
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

Convert findings to TODOs:
- one reviewable fix per TODO
- use single TODO when task cohesive and splitting would reduce correctness, context, or efficiency
- order by severity, dependency, risk
- keep final TODO for full validation + memory/handoff
- only main agent edits `TODO.md`

## Sequential Execution Loop

For each TODO not part of safe parallel batch. If only one TODO, run this loop once:
1. Mark the TODO `[>]`.
2. Launch one sub-agent with a narrow implementation prompt.
3. Wait for the sub-agent result.
4. Inspect the diff for that task.
5. Run focused validation yourself.
6. Review correctness, integration, contracts, tests, and side effects.
7. If invalid, fix directly or re-delegate a repair prompt.
8. Rerun focused validation.
9. Mark the TODO `[X]` only after acceptance.

Prefer one sub-agent task when requested change is cohesive, has one acceptance boundary, or needs shared context to avoid inconsistent edits. Split into multiple TODOs only when work has independently reviewable fixes, separable risk, or clear ordering dependencies.

## Parallel Execution

Parallel sub-agents allowed only for fully independent TODOs.

Before launching parallel batch, verify every TODO in batch:
- touches different files or clearly separate subsystems
- has no shared symbols, schemas, generated files, routes, persistence, tests, fixtures, or configuration
- has no ordering dependency on another TODO in batch
- can be reviewed and validated independently
- cannot conflict with unrelated dirty worktree changes

For safe parallel batch:
1. Mark each TODO `[>]`.
2. Launch one bounded sub-agent per TODO at the same time.
3. Wait for all sub-agent results.
4. Review each result separately before accepting dependent follow-up work.
5. Inspect combined diff for conflicts, integration issues, accidental overlap.
6. Run focused validation for each TODO plus combined validation needed by touched surfaces.
7. If any TODO fails review, fix directly or launch repair sub-agent for that TODO only.
8. Mark each TODO `[X]` only after own review and validation pass.

If isolation uncertain, do not run in parallel.

## Sub-Agent Prompt Requirements

Every implementation sub-agent prompt concrete + bounded. Use this structure:

```text
Implement TASK <n> only: <task title>.

Goal:
<one sentence describing the required correctness or user-visible outcome>

Context:
- Relevant files/symbols/routes/tests: <specific paths and names>
- Current failure/risk: <exact bug, failing assertion, or scenario>
- Repo conventions to preserve: <validation, contracts, no migrations, style, etc.>

Scope:
- Allowed files/areas: <paths or subsystems>
- Do not implement unrelated TODOs.
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

## Review Gate

After each sub-agent, review before accept.

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
- Apply minimal fix or launch repair sub-agent with exact issue.
- Rerun focused validation + review again.

## Final Validation

Run validation for every touched surface.

Common final checks:
- Python: `uv run ruff check .`, `uv run ruff format --check .`, `uv run basedpyright`, `uv run pytest -q --tb=short -x`
- Frontend: `bun run test:web`, `bun run lint`, `bun run typecheck`, `bun run web:build`
- API/SSE contract changes: run the project codegen command and codegen tests
- Static web assets: verify rebuilt hashed chunks are tracked

If final validation reveals new failure:
- Add or reopen a TODO.
- Isolate the failure.
- Fix before claiming completion.
- Rerun focused validation, then final validation again.

## Handoff

At end, report concise:
- tasks completed
- files or areas touched
- validation commands and results
- remaining workspace changes

Orchestrate Mode complete only when every TODO is `[X]`, `[-]`, or `[!]` with explanation, every sub-agent result reviewed, final validation passed or blockers explicit, and unrelated dirty files preserved.