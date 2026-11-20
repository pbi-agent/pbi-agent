---
id: gh-449
type: build
type_reason: Labels enhancement+documentation+cli; adds a new CLI flag (behavior change), not confined to docs/**, so build (stricter) wins.
source: https://github.com/pbi-agent/pbi-agent/issues/449
risk: high
risk_triggers: diff estimate >500 lines and >15 files (~56 guides); unknown on import-time sessions.db creation vs AC3 (triage)
stage: release
status: running
---
# Add integrated --doc documentation to every pbi-agent CLI command

## Goal
Add a `--doc` flag at the root, on every top-level command, and on every subcommand at any depth of the argparse-based `pbi-agent` CLI. It prints a long-form Markdown usage guide to stdout (no colors, no pager, exit 0), so an agent can learn any part of the CLI from the terminal. Full requirements and scope: issue #449 (`gh issue view 449 --json body`).

## Acceptance criteria
1. `pbi-agent --doc` and `pbi-agent <path> --doc` print a non-empty Markdown guide and exit 0, for every command and subcommand path the CLI exposes.
2. The CLI cannot have a command or subcommand without a `--doc` guide: adding one without a guide is caught by the tests.
3. `pbi-agent run --doc`, `pbi-agent web --doc` and `pbi-agent config providers create --doc` succeed with no required arguments and no configuration, and have no side effects (no server start, provider calls, config writes, network).
4. Each command guide covers purpose, options, examples, workflows, related commands and pitfalls. Each parent command's guide lists its subcommands and how to reach their `--doc`. The root guide covers what pbi-agent is, global options and runtime-settings resolution, an index of all commands, and how to drill down with `--doc`.
5. The root and command `--help` output mentions `--doc`.
6. The docs site CLI reference (`docs/cli.md`) documents the `--doc` flag, and `bun run docs:build` passes.
7. The existing behavior and `--help` output of every command are unchanged apart from the `--doc` mention, and the existing CLI tests pass.

Out of scope: changing existing command behavior/args/help (beyond the `--doc` mention), JSON output, colored output or pagers, runtime system prompt changes, single-sourcing with the docs site.
Open assumptions (from issue): hidden/suppressed aliases need no own `--doc` entry; command aliases show the guide of their target.

## Links
- Issue: https://github.com/pbi-agent/pbi-agent/issues/449
- CLI: `src/pbi_agent/cli/` (parser.py, entrypoint.py, per-command modules); tests in `tests/cli/`
- Docs: `docs/cli.md`

## Environment notes (intake)
- Branch `master`, clean tree, ahead of origin/master by 1 unpushed commit `a9616814 add factory` (`.agents/**`, MEMORY.md, TODO.md). Release must not silently ship it inside this PR; decide at the release gate.
- `.agents/factory/tasks/` is committed to the repo on purpose (user decision 2026-11-20). The release ships this task folder with the PR; files written after the commit (release/verify/learn, ledger rows) wait for the next factory release.
- Uncommitted files outside this task: the factory instruction updates (`.agents/**`) for the task-folder decision, plus MEMORY.md/TODO.md. Decide at the release gate whether they ship with this PR.
- Conductor runs in Claude Code: stage agents are Agent-tool sub-agents told to follow `.agents/agents/<name>.md` and its referenced `.agents/commands/<cmd>.md`.

## Stage files
- task: task.md
- triage: triage.md
- plan: plan.md
- build: build.md
- review: review-1.md
- fix: fix-1.md
- review (latest): review-2.md
- quality (latest): quality-2.md
- fix (latest): fix-2.md
- release: release.md

## Gate log
| stage | gate | decision | note |
| --- | --- | --- | --- |
| intake | always_run | auto_pass | type build, risk normal |
| triage | approve | approved_unchanged | triage: proceed; risk raised to high; sessions.db import-time creation accepted as --help parity |
| plan | approve | approved_unchanged | plan: ready; all 7 AC + acceptance_tests/docs mapped |
| build | always_run | auto_pass | conductor reran ruff/format/basedpyright/full pytest/docs:build + fresh-HOME smoke: green; risk stays high (~60 files, ~3.9k lines) |
| review | reviewer r1 | findings: 1 | P3 guide wording (config writers); conductor added docs/environment.md reasoning-effort alignment to fix-1 |
| review | reviewer r2 | No findings. | fix-1 verified |
| review | code-quality r1 | findings: 1 | major: guide/parser sync check is one-directional (stale flags undetected) |
| review | fixer (quality r1) | fix: done | reverse flag + usage checks; channels telegram guide corrected; conductor reran tests/cli, ruff, format, basedpyright: green |
| review | code-quality r2 | No code-quality findings. | agent reviewers clean; awaiting human review+release gate |
| review | approve | approved_unchanged | human: Approve and release |
| release | approve | approved_unchanged | human: Approve and release; PR scope = 'add factory' + separate commit for task-folder instruction edits (operator.md, factory.md, MEMORY.md, TODO.md) + #449 commit |
| release | validation | pass | ruff/format/basedpyright clean; full pytest 2526 passed in 3/4 runs, 1 run hit pre-existing flake tests/test_web_serve.py::test_lost_manager_lease_rejects_new_live_sessions (2/15 fails on clean HEAD, 3/15 with change; unrelated); test:web 890 passed; docs:build ok; uv build: 56 guides in wheel+sdist |
| release | pre-commit /verify | pass | scratch workspace: bare `pbi-agent` and `pbi-agent --verbose` launch web (index 200, POST /api/sessions ok); `--doc`, `--verbose --doc`, `web --doc` print guides, rc 0, no server; user's 7424 server untouched |
