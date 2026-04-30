# Release Workflow Mode

Use the `release-writing` skill for the complete pbi-agent release workflow. Load `.agents/skills/release-writing/SKILL.md` before acting and follow it as the source of truth.

## Mode rules

Operate in Release Workflow Mode until the release task finishes or stops on a safety condition.

Default goal: prepare a release branch and PR from accumulated merged feature/fix PRs on `master`, including version bump, per-release changelog file, changelog index/sidebar updates, validation, commit, push, and PR creation.

Publish goal: merge/publish only when the user explicitly includes `publish`, `merge`, or equivalent approval in the command request.

Do not ask clarifying questions unless the release set is unsafe to infer. Make grounded assumptions from Git history, GitHub PR data, repository files, and the release-writing skill.

## Safety boundaries

Allowed in default Release Workflow Mode:

- Inspect workspace, Git history, tags, and GitHub PR metadata.
- Fetch `origin master` and tags.
- Create `chore/release-v<version>` from `origin/master`.
- Edit only release-scoped files, typically `pyproject.toml`, `docs/changelog/v<version>.md`, `docs/changelog/index.md`, and VitePress changelog sidebar config.
- Run required validation.
- Stage explicit release-scoped paths, commit, push the release branch, and open a PR to `master` with `gh pr create`.

Allowed only in Publish goal:

- Merge the release PR into `master` with `gh pr merge` when checks and branch protection permit it.
- Confirm release workflow completion, release tag, and GitHub Release existence.
- Update GitHub Release notes from the per-release changelog file when needed.

Never:

- Include unrelated workspace changes.
- Use `git add .` unless every changed path has already been proven release-scoped.
- Force-push, bypass branch protection, rewrite unrelated history, or merge non-release PRs.
- Call the GitHub API with `curl`; use `gh`.
- Continue after failed validation unless clearly unrelated and documented.

Stop if:

- `gh` authentication is unavailable.
- `origin/master` or release tags cannot be fetched.
- Current workspace changes cannot be safely separated from release edits.
- The previous release boundary or next version cannot be inferred safely.
- Validation fails for release-scoped changes.

## Required workflow

1. Load the `release-writing` skill.
2. Read `MEMORY.md`, reset/update `TODO.md`, then run `git status --short --branch`.
3. Inspect existing release/changelog structure and preserve unrelated changes.
4. Run `git fetch --tags origin master`.
5. Determine current version from `pyproject.toml`, previous tag from Git, and merged PRs since previous release.
6. Enrich PRs with `gh pr view <number> --json number,title,body,labels,url,mergedAt,author`.
7. Choose next SemVer version:
   - Use a user-provided version if present.
   - Otherwise infer conservatively from merged PRs.
8. Create/switch to `chore/release-v<version>` from `origin/master`.
9. Apply release edits:
   - Bump `[project].version` in `pyproject.toml`.
   - Create `docs/changelog/v<version>.md` with version and release date.
   - Add the new release at the top of `docs/changelog/index.md`.
   - Add the release page to the VitePress changelog sidebar.
10. Draft PR body from the same release summary and include validation checklist.
11. Validate:
   - `uv run ruff check .`
   - `uv run ruff format --check .`
   - `uv run pytest`
   - `bun run docs:build`
12. Stage only release-scoped paths and inspect `git diff --cached`.
13. Commit `chore: release v<version>`.
14. Push the branch and open the release PR against `master`.
15. If Publish goal is active, verify PR checks/status, merge, confirm release/tag, update release notes if needed, and report publish status.

## PR content

Title: `chore: release v<version>`

Body must include:

- Summary of the release.
- Categorized highlights from the per-release changelog.
- Changelog link: `docs/changelog/v<version>.md`.
- Validation commands and results.
- Any skipped, excluded, or unrelated changes.

## Final response

Return a compact Markdown report:

- Version
- Release date
- Branch
- Commit hash
- PR URL
- Changelog file
- Validation run and result
- Publish/merge status
- Unrelated or skipped changes, if any

If stopped, return blocker, evidence, and safest next action.
