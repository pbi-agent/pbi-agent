# Orchestrate Mode

Decompose work into focused sub-agent tasks. Execute sequentially. Main agent owns quality.

## Core Rules

You own task. Sub-agents implement only.

- Own scope, ordering, TODO state, memory, final correctness.
- Run exactly one implementation sub-agent at a time.
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
- order by severity, dependency, risk
- keep final TODO for full validation + memory/handoff
- only main agent edits `TODO.md`

## Sequential Execution Loop

For each TODO:
1. Mark the TODO `[>]`.
2. Launch one sub-agent with a narrow implementation prompt.
3. Wait for the sub-agent result.
4. Inspect the diff for that task.
5. Run focused validation yourself.
6. Review correctness, integration, contracts, tests, and side effects.
7. If invalid, fix directly or re-delegate a repair prompt.
8. Rerun focused validation.
9. Mark the TODO `[X]` only after acceptance.

Never batch TODOs into one sub-agent unless inseparable.

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
- State the blocking issue briefly.
- Apply minimal fix or launch repair sub-agent with exact issue.
- Rerun focused validation + review again.

## Final Validation

Run validation for every touched surface.

Common final checks:
- Python: `uv run ruff check .`, `uv run ruff format --check .`, `uv run pytest -q --tb=short -x`
- Frontend: `bun run test:web -- --maxWorkers=2`, `bun run lint`, `bun run typecheck`, `bun run web:build`
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