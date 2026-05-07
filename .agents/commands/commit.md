# Commit Mode

Create one clean local Git commit for the current task-scoped workspace changes.

This command is local-only. It is authorized to inspect diffs, run needed validation, stage task-scoped files, and create a local commit. It is not authorized to push, open a PR, merge, rebase, force-push, or delete branches unless the user explicitly asks separately.

## Mode rules

Commit Mode is action-oriented. Do not ask clarifying questions unless safe staging or commit intent cannot be determined from the transcript, `TODO.md`, `MEMORY.md`, and current diff.

Prefer a single focused commit. If the diff clearly contains unrelated changes, stage only the task-scoped files. If unrelated changes cannot be separated safely, stop before staging.

Do not use `git add .` unless every changed path has already been proven task-scoped.

Do not commit failing or unvalidated changes. Validation must be current enough for the touched surface and must have happened after the latest code/docs/build edits. If validation evidence is stale or missing, run the smallest relevant validation set before committing.

## Required workflow

1. Inspect state:
   - `git status --short --branch`
   - relevant `git diff -- <paths>` or `git diff --stat`
   - recent transcript context, `TODO.md`, and `MEMORY.md` when needed.

2. Identify task scope:
   - Include source, tests, docs, generated static assets, `TODO.md`, and `MEMORY.md` only when they are part of the current task.
   - Exclude unrelated user files, snapshots, temporary downloads, logs, and accidental artifacts.

3. Check validation freshness:
   - If relevant validation already passed after the latest edits, reuse that evidence.
   - Always run `git diff --check` before commit.
   - If validation is missing or stale, run focused commands for the touched surface:
     - Python: relevant pytest plus `uv run ruff check ...` and `uv run ruff format --check ...`
     - Frontend: relevant `bun run test:web -- ...`, plus `bun run lint`, `bun run typecheck`, and `bun run web:build` when frontend build/static assets are touched
     - Docs: `bun run docs:build` when docs are touched
   - Stop if validation fails unless failure is clearly unrelated and documented.

4. Stage explicit paths only:
   - Use `git add <path> ...`
   - Re-check staged content with:
     - `git diff --cached --stat`
     - targeted `git diff --cached -- <paths>` when needed

5. Commit:
   - Use a concise imperative message.
   - Message should summarize the actual staged diff, not the user’s wording.
   - Prefer conventional style only when obvious, but do not force it.
   - Examples:
     - `Refine working timeline grouping`
     - `Fix sub-agent child processing`
     - `Update commit command`

6. Verify final state:
   - Run `git status --short --branch`
   - Confirm whether the working tree is clean or list any remaining untracked/uncommitted files.
   - Do not push.

## Stop conditions

Stop without committing if:

- There are no task-scoped changes.
- Safe staging cannot distinguish task changes from unrelated changes.
- Validation fails or is missing and cannot be run.
- The staged diff contains accidental artifacts.
- The commit would include secrets, local snapshots, build caches, or unrelated generated files.
- The repo is in the middle of an unresolved merge/rebase/cherry-pick.

## Final response

Return a concise local commit report:

- Commit hash and subject
- Files committed, summarized by area
- Validation used
- Final working tree status
- Any uncommitted/untracked files intentionally left out
