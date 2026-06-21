---
name: release
description: Release Workflow Mode
model_profile_id: worker-pro
allowed_tools: read,write,shell
skills: browser-use,release-writing
---

# Release Workflow Mode

Use `release-writing` skill for complete pbi-agent release workflow before acting; follow it for mechanics, but these command instructions are the source of truth for default versioning scope and publish authorization.

## Mode rules

Operate in Release Workflow Mode until release task finishes or stops on safety condition.

Default goal for plain `/release`: complete a full minor release by creating a new release branch, bumping the MINOR version (unless otherwise specified), including all local and remote commits since the last release, validating, committing, pushing, opening/merging the release PR, and publishing/verifying the release.

The `/release` command itself is explicit authorization to push, merge, and publish the release. Additional wording such as `publish`, `merge`, or `push` is not required. If the user asks for a draft, PR-only, notes-only, dry run, or no-publish release, obey that narrower scope instead.

Do not ask clarifying questions unless release set unsafe to infer. Use Git history, GitHub PR data, repo files, and release-writing skill.

## Safety boundaries

Allowed in default Release Workflow Mode:

- Inspect workspace, Git history, tags, GitHub PR metadata.
- Fetch `origin master` and tags.
- Create `chore/release-v<version>` from the safe release base containing the intended unreleased local and remote commits.
- Edit only release-scoped files, typically `pyproject.toml`, `docs/changelog/v<version>.md`, `docs/changelog/index.md`, and VitePress changelog sidebar config.
- Run required validation.
- Stage explicit release-scoped paths, commit, push release branch, open PR to `master` with `gh pr create`.
- Merge release PR into `master` with `gh pr merge` when checks and branch protection permit.
- Confirm release workflow completion, release tag, and GitHub Release existence.
- Update GitHub Release notes from per-release changelog file when needed.

Never:

- Include unrelated workspace changes.
- Use `git add .` unless every changed path already proven release-scoped.
- Force-push, amend pushed release commits, reset remote branch, rebase remote branch, bypass branch protection, rewrite unrelated history, or merge non-release PRs unless user explicitly asks for that exact history rewrite.
- Call GitHub API with `curl`; use `gh`.
- Continue after failed validation unless clearly unrelated and documented.

Stop if:

- `gh` authentication unavailable.
- `origin/master` or release tags cannot be fetched.
- Current workspace changes cannot be safely separated from release edits.
- Previous release boundary or next version cannot be inferred safely.
- Validation fails for release-scoped changes.
- Local or remote commits since the last release cannot be reconciled safely into the release branch without risking unrelated workspace changes.

## Continuation / Publish Resume Gate

When user asks to continue, merge, or publish existing release workflow:

1. Identify active release PR from current branch, latest release branch, or user-provided PR number.
2. Run `git status --short --branch` and preserve unrelated local changes.
3. Inspect PR branch commits and checks:
   - `gh pr view <pr> --json number,url,headRefName,baseRefName,mergeStateStatus,statusCheckRollup,commits`
   - if checks failed, inspect failed logs before changes.
4. Compare local/branch diff against `origin/master`; classify each changed path as release-scoped, required repair, bookkeeping, or unrelated.
5. Batch required repair edits before pushing when possible.
6. Once release branch pushed or PR exists, do not amend, reset, rebase, or force-push. Use normal follow-up commits for fixes.
7. Stop before history rewrite unless user explicitly authorizes it.
8. Do not merge/publish until local release validation and PR checks clean, except when documenting blocker and stopping.

## Required workflow

1. Load the `release-writing` skill.
2. Read `MEMORY.md`, reset/update `TODO.md`, then run `git status --short --branch`.
3. Inspect existing release/changelog structure and preserve unrelated changes.
4. Run `git fetch --tags origin master`.
5. Determine current version from `pyproject.toml`, previous tag from Git, and all local plus remote commits since previous release:
   - Include commits reachable from local `master` and `origin/master` since the previous release tag.
   - Include any current branch commits only when they are intended release content and can be safely separated from unrelated workspace changes.
   - Prefer PR metadata for merged PRs when available, but do not omit local unreleased commits just because they are not on `origin/master` yet.
6. Enrich PRs with `gh pr view <number> --json number,title,body,labels,url,mergedAt,author`.
7. Choose next SemVer version:
   - Use user-provided version if present.
   - Otherwise bump the MINOR version by default, preserving MAJOR and resetting PATCH to 0.
8. Create/switch to `chore/release-v<version>` from the release base that contains the intended local and remote unreleased commits. Prefer `origin/master` when it already contains all release commits; otherwise first reconcile local `master` and `origin/master` safely without including unrelated workspace changes.
9. Apply release edits:
   - Bump `[project].version` in `pyproject.toml`.
   - Create `docs/changelog/v<version>.md` with version and release date.
   - Add new release at top of `docs/changelog/index.md`.
   - Add release page to VitePress changelog sidebar.
10. Draft PR body from same release summary and include validation checklist.
11. Validate:
   - `uv run ruff check .`
   - `uv run ruff format --check .`
   - `uv run basedpyright`
   - `uv run python scripts/dead_code.py`
   - `uv run pytest -q --tb=short -x`
   - `bun run docs:build`
12. Stage only release-scoped paths and inspect `git diff --cached`.
13. Commit `chore: release v<version>`.
14. Push branch and open release PR against `master`.
15. Verify PR checks/status, merge, confirm release/tag, update release notes if needed, and report publish status.

## PR content

Title: `chore: release v<version>`

Body must include:

- Summary of release.
- Categorized highlights from per-release changelog.
- Changelog link: `docs/changelog/v<version>.md`.
- Validation commands and results.
- Any skipped, excluded, or unrelated changes.

## Final response

Return compact Markdown report:

- Version
- Release date
- Branch
- Commit hash
- PR URL
- Changelog file
- Validation run and result
- Publish/merge status
- Unrelated or skipped changes, if any

If stopped, return blocker, evidence, safest next action.
