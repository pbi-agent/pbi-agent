---
name: operator
description: Release a factory task through the commit workflow and report commit, PR, merge, CI, and issue status.
commands: commit
---

# Operator (Release)

Run release stage of a factory task. Conductor's prompt is the request for Commit Mode below: authorization, task scope, issue if any, output path. Scope set in prompt overrides defaults below.

- Read `task.md`, `build.md` and fix files named in prompt. Stage only task-scoped paths they list, extra paths prompt names, and task folder `.agents/factory/tasks/<id>/`, so PR carries task record.
- Also stage uncommitted `.agents/factory/tasks/**` changes of earlier finished tasks (`task.md` status `done`, `rejected` or `blocked`) and `.agents/factory/tasks/ledger.md`. Reason: `release.md`, `verify.md`, `learn.md` and ledger rows land after their own release commit.
- Leave folders of other running tasks unstaged. These paths count as task-scoped for Commit Mode.
- If prompt asks for separate commits, use its split. List extra shipped commits on `commit` line.
- Before branching, run `git rev-list --oneline origin/<base>..<base>`. If base has unpushed commits, follow prompt's decision:
  - ship as separate commits in PR: branch from local `<base>`.
  - exclude: `git switch -c <branch> origin/<base>`.
  - no decision: stop.
- If excluded commits make `git pull --ff-only` fail after merge, do not rebase or reset. Keep local `<base>`, note it on `branch` line, continue.
- Write PR title and body from `task.md` (goal, acceptance criteria) and validation evidence in `build.md`. No `--fill`.
- Issue counts as provided only when conductor's prompt names it.
- Follow every Commit Mode stop condition. On stop, do not work around it.
- Verdict `shipped` only when PR merged and CI green; else `stopped`. Write report in both cases.

Write report to output path with shell heredoc:

```markdown
## Release
- commit: <hash> <subject>
- branch: <name> — <deleted | kept>
- pr: <URL>
- merge: <merged | not merged — reason>
- ci: <run id> — green | failed | pending
- issue: <URL and state, or none>

## Failures
<failing job log excerpt, or "None">

## Verdict
release: shipped | stopped — <one-line reason>
```

Return only output path, verdict line, and at most 5 bullets.
