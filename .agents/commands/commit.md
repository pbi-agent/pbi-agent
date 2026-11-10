---
name: commit
description: Commit, PR, merge, and monitor CI
model_profile_id: worker-mini
allowed_tools: read-image,shell
---

# Commit Mode

Ship the current task-scoped changes end to end: commit, create PR, push, merge, clean branch, monitor CI.

Invoking this command is explicit authorization for every step below. Do not ask for confirmation between steps. Never force-push, rebase shared history, or stage unrelated files.

## Workflow

1. **Commit**
   - `git status --short --branch`; if on `master`, create a branch first (`git switch -c <type>/<short-name>`).
   - Stage task-scoped paths explicitly (`git add <path> ...`); never `git add .` unless every changed path is task-scoped.
   - Run `git diff --check`, then commit with a concise imperative message summarizing the staged diff.

2. **Push**
   - `git push -u origin HEAD`

3. **Create PR**
   - `gh pr create --base master --fill` (or `--title`/`--body` summarizing the change).

4. **Merge**
   - `gh pr merge --merge --delete-branch`

5. **Clean branch**
   - `git switch master && git pull --ff-only`
   - `git branch -d <branch>` if it still exists locally; `git fetch --prune`.

6. **Monitor CI**
   - Find the run for the merge commit: `gh run list --branch master --limit 5 --json databaseId,headSha,status,conclusion,name`
   - `gh run watch <id> --exit-status`
   - On failure, show the failing job logs with `gh run view <id> --log-failed` and report them.

## Stop conditions

Stop and report if: there are no task-scoped changes, unrelated changes cannot be separated, a merge/rebase is in progress, the diff contains secrets or accidental artifacts, or any command fails.

## Final response

Report: commit hash and subject, PR URL, merge status, final branch state, and CI result.
