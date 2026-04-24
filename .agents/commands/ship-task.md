# Ship Task Mode

Ship the completed current task end-to-end. You are explicitly authorized, for this command only, to create a task branch, commit task-scoped changes, push the branch, open a pull request, and merge it into `master`.

## Mode rules (strict)

You are in **Ship Task Mode** until this command finishes or stops on a safety condition.

Ship Task Mode is action-oriented. Do not ask clarifying questions. Do not produce a plan and wait. Inspect the workspace, make grounded assumptions from local context, and either ship the task or stop with a concrete blocker.

Ship only the current task. Preserve unrelated, pre-existing, generated, or user-owned changes. When scope is ambiguous, use repository state, the current conversation, `TODO.md`, `MEMORY.md`, and recent task artifacts to separate task changes. If unrelated changes cannot be safely separated, stop before staging or committing.

## Safety boundaries

Allowed actions:

- Read files and inspect repository history/state.
- Run validation commands appropriate to the touched surfaces.
- Create a new task-scoped branch.
- Stage explicit task-scoped paths.
- Commit with a concise imperative message.
- Push the new branch to the default remote.
- Use `gh` CLI to create and merge a pull request into `master`.

Not allowed:

- Do not use `git add .` unless every changed path has already been proven task-scoped.
- Do not include unrelated workspace changes.
- Do not force-push, rewrite unrelated history, bypass branch protection, or merge unrelated branches.
- Do not call the GitHub API with `curl`; use `gh` for GitHub operations.
- Do not continue after failed validation unless the failure is clearly unrelated and documented.

Stop without shipping if:

- There are no task-scoped changes to ship.
- Validation fails for the shipped scope.
- `gh` authentication is unavailable.
- The repository has no usable remote.
- The target branch `master` cannot be fetched or used as PR base.
- Safe staging cannot distinguish task changes from unrelated changes.

## Required workflow

1. Start with `git status --short --branch` and inspect the diff before making Git changes.
2. Identify the current task scope from the diff and available session context. Prefer explicit file paths when staging.
3. Run focused validation for the touched surfaces before committing:
   - Python: `uv run ruff check .`, `uv run ruff format --check .`, and relevant `uv run pytest ...`.
   - Frontend: `bun run test:web`, `bun run lint`, `bun run typecheck`, and `bun run web:build`.
   - Docs: `bun run docs:build`.
   - Broad changes: run the repo-level checks from project instructions.
4. Create a branch from the current task summary, usually `ship/<short-slug>` or `task/<short-slug>`.
5. Stage only scoped files, then re-check `git diff --cached` before committing.
6. Commit the scoped changes with a concise imperative commit message.
7. Push the branch to the default remote.
8. Create a PR with `gh pr create --base master --head <branch> --title <title> --body <body>`.
9. Merge the PR with `gh pr merge` only after the PR is created successfully and branch protection permits it.
10. Confirm the final state and report what shipped.

## PR content

Use a clear title and a compact body. Include:

- Summary of shipped changes.
- Validation commands and results.
- Any known unshipped or skipped changes.

## Final response

Return a concise shipping report in plain Markdown:

- Scope shipped
- Validation run and result
- Branch name
- Commit hash
- PR URL
- Merge status
- Unshipped or skipped changes, if any

If shipping stops, return a blocker report instead with the stop reason, evidence, and the safest next action.