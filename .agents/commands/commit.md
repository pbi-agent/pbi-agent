---
name: commit
description: Commit, PR, merge, monitor CI, and update the related issue
---

# Commit Mode

Ship current task-scoped changes end to end: commit, push, create PR, merge, clean branch, monitor CI, update related issue.

Invoking this command authorizes every step below. Do not ask for confirmation between steps. Never force-push, rebase shared history, or stage unrelated files.

## Workflow

1. **Commit**
   - Run `git status --short --branch`, `git fetch origin`, then `git rev-list --oneline origin/master..master`.
   - If local `master` has unpushed commits, follow scope given for them: ship in PR (branch from `master`) or exclude (branch from `origin/master`). No scope given: stop.
   - If on `master`, create branch first (`git switch -c <type>/<short-name>`; append `origin/master` to exclude unpushed commits).
   - Stage task-scoped paths explicitly (`git add <path> ...`). Never `git add .` unless every changed path is task-scoped.
   - Run `git diff --cached --check`, then commit with concise imperative message summarizing staged diff.
   - If issue provided (step 7), reference it in commit and PR body: `Closes #<n>` if change fully resolves it, else `Refs #<n>`.

2. **Push**
   - `git push -u origin HEAD`

3. **Create PR**
   - `gh pr create --base master --fill` (or `--title`/`--body` summarizing change).

4. **Merge**
   - Wait for PR checks first: `gh pr checks <n> --watch --fail-fast`. Use long shell timeout. If it reports no checks yet, wait ~15 s, retry.
   - If any check fails: do not merge. Show failing logs (`gh run view <id> --log-failed`), report, stop.
   - All checks green: `gh pr merge --merge --delete-branch`
   - Get merge commit: `gh pr view <n> --json state,mergeCommit,url`.

5. **Clean branch**
   - `git switch master && git pull --ff-only`. If excluded unpushed commits make pull fail, leave `master` as is, report it, continue.
   - `git branch -d <branch>` if it still exists locally; `git fetch --prune`.

6. **Monitor CI**
   - List runs for merge commit: `gh run list --commit <merge-sha> --json databaseId,status,conclusion,name`. If none listed yet, wait ~15 s, retry.
   - Watch each run: `gh run watch <id> --exit-status`. Use long shell timeout; CI takes minutes.
   - On failure, show failing job logs with `gh run view <id> --log-failed`, report them, stop.

7. **Update issue**
   - Only when user provided issue (number or URL) for this task in conversation. Never guess one from branch names or search for one.
   - After merge, read it: `gh issue view <n> --json state,title,body`.
   - `gh issue edit <n> --title ... --body ...` to match what shipped: original request as quote, then outcome (PR, merge commit), decisions, behavior, follow-ups not built.
   - Do not close issue change only partly resolves; state what remains.

## Stop conditions

Stop and report if: no task-scoped changes, unrelated changes cannot be separated, merge/rebase in progress, local `master` has unpushed commits with no scope given, PR checks fail, diff contains secrets or accidental artifacts, or any command fails (CI included).

## Final response

Report: commit hash and subject, PR URL, merge status and merge commit, final branch state, CI result per run, issue URL with state if updated.
