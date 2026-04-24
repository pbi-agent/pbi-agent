# Ship Task Mode

Ship completed current task end-to-end. For this command only, authorized to create task branch, commit task-scoped changes, push branch, open pull request, merge into `master`, and delete local + remote task branches after merge.

## Mode rules (strict)

In **Ship Task Mode** until command finishes or stops on safety condition.

Ship Task Mode action-oriented. Do not ask clarifying questions. Do not produce plan and wait. Inspect workspace, make grounded assumptions from local context, and ship task or stop with concrete blocker.

Ship only current task. Preserve unrelated, pre-existing, generated, or user-owned changes. When scope ambiguous, use repository state, current conversation, `TODO.md`, `MEMORY.md`, and recent task artifacts to separate task changes. If unrelated changes cannot be safely separated, stop before staging or commit.

## Safety boundaries

Allowed actions:

- Read files and inspect repo history/state.
- Run validation commands for touched surfaces.
- Create new task-scoped branch.
- Stage explicit task-scoped paths.
- Commit with concise imperative message.
- Push new branch to default remote.
- Use `gh` CLI to create and merge pull request into `master`.
- Delete local task branch and remote task branch after successful merge to `master`.

Not allowed:

- Do not use `git add .` unless every changed path has already been proven task-scoped.
- Do not include unrelated workspace changes.
- Do not force-push, rewrite unrelated history, bypass branch protection, or merge unrelated branches.
- Do not delete `master`, the default branch, or any branch that is not the task branch created for this shipment.
- Do not call the GitHub API with `curl`; use `gh` for GitHub operations.
- Do not continue after failed validation unless the failure is clearly unrelated and documented.

Stop without shipping if:

- No task-scoped changes to ship.
- Validation fails for the shipped scope.
- `gh` authentication is unavailable.
- Repo has no usable remote.
- Target branch `master` cannot be fetched or used as PR base.
- Safe staging cannot distinguish task changes from unrelated changes.

## Required workflow

1. Start with `git status --short --branch` and inspect the diff before making Git changes.
2. Identify current task scope from diff and available session context. Prefer explicit file paths when staging.
3. Run focused validation for the touched surfaces before committing:
   - Python: `uv run ruff check .`, `uv run ruff format --check .`, and relevant `uv run pytest ...`.
   - Frontend: `bun run test:web`, `bun run lint`, `bun run typecheck`, and `bun run web:build`.
   - Docs: `bun run docs:build`.
   - Broad changes: run repo-level checks from project instructions.
4. Create branch from current task summary. Branch name must always start with common standard change prefix, such as `fix/`, `feat/`, `docs/`, `test/`, `refactor/`, `chore/`, `ci/`, `build/`, `perf/`, or `style/`, followed by short kebab-case slug; for example, `fix/session-resume-error` or `feat/settings-import`.
5. Stage only scoped files, then re-check `git diff --cached` before committing.
6. Commit scoped changes with concise imperative commit message.
7. Push branch to default remote.
8. Create a PR with `gh pr create --base master --head <branch> --title <title> --body <body>`.
9. Merge PR with `gh pr merge` only after PR created successfully and branch protection permits it.
10. After successful merge to `master`, delete remote task branch and matching local task branch. Prefer `gh pr merge --delete-branch` when safe and sufficient; otherwise use explicit Git cleanup commands for task branch only.
11. Confirm final state and report what shipped and which branches were deleted.

## PR content

Use clear title and compact body. Include:

- Summary of shipped changes.
- Validation commands and results.
- Known unshipped or skipped changes.

## Final response

Return concise shipping report in plain Markdown:

- Scope shipped
- Validation run and result
- Branch name
- Commit hash
- PR URL
- Merge status
- Local and remote branch cleanup status
- Unshipped or skipped changes, if any

If shipping stops, return blocker report with stop reason, evidence, and safest next action.
