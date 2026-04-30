---
name: release-writing
description: >
  Write pbi-agent release notes, changelog entries, and release PRs from merged
  feature/fix PRs. Use when preparing a version bump, GitHub Release, changelog,
  or PR release summary for the pbi-agent master-based release workflow.
---

# Release Writing

## Purpose

Prepare pbi-agent release notes + release PRs from branch/PR story. Keep per-release changelog pages, `pyproject.toml`, and GitHub Releases aligned.

## Activation Modes

- **PR note mode**: user asks for release notes for one branch or PR.
- **Release PR mode**: user asks to prepare version bump/release PR from accumulated merged PRs.
- **Publish mode**: user explicitly asks to merge/publish release after review.

Do not commit, push, open PRs, merge, tag, or edit GitHub Releases unless user explicitly asks for that mode.

## pbi-agent Release Model

- Default branch: `master`.
- Normal work lands through dedicated `feat/*`, `fix/*`, etc. PRs into `master`.
- Release uses dedicated `chore/release-v<version>` branch and PR.
- Release PR bumps `[project].version` in `pyproject.toml`, creates release changelog file, updates changelog index.
- `.github/workflows/release.yml` creates GitHub Release when version bump reaches `master`.
- `.github/workflows/publish.yml` publishes only when matching `v<version>` release/tag exists.

## Preflight

1. Read `MEMORY.md`, current-day entries, reset/update `TODO.md`.
2. Run `git status --short --branch`; inspect relevant diffs. Preserve unrelated changes.
3. Fetch release context: `git fetch --tags origin master`.
4. Find current version from `pyproject.toml`; find previous tag with `git describe --tags --abbrev=0 master` when available.
5. Use `gh` for GitHub data. Prefer `gh pr view <n> --json number,title,body,labels,url,mergedAt,author`.

## PR Note Mode

Create concise notes for one branch/PR from title/body, commits, labels, diff. Include PR URL when known.

Write optional draft notes to `.release-notes/<branch-or-pr>.md` when requested. Keep under 200 words:

```md
# <Impact Title>

## Summary
<2-3 sentences, under 50 words>

## Key Changes
- <user-facing highlight>
- <user-facing highlight>
- <user-facing highlight>

## Changes
### Added
- <one-line change>
### Changed
- <one-line change>
### Removed
- <one-line change>
### Fixed
- <one-line change>

## Links
- [Pull Request](<PR-URL>)
```

Omit empty categories. Use active voice, user-facing impact, minimal jargon.

## Release PR Mode

1. Identify merged PRs since previous release:
   - Prefer first-parent merge log: `git log --first-parent --merges --oneline <last-tag>..origin/master`.
   - Parse PR numbers from merge commits, then enrich with `gh pr view` JSON.
   - If no tag exists, use all relevant merged PRs or ask cutoff only if release set unsafe.
2. Choose next version:
   - Use user-provided version when given.
   - Otherwise infer SemVer conservatively: breaking/API-removal = major; `feat` = minor; fixes/docs/chore = patch. Do not infer major without explicit evidence.
3. Create `chore/release-v<version>` from `origin/master` only when authorized.
4. Update `pyproject.toml` version.
5. Create `docs/changelog/v<version>.md` and update `docs/changelog/index.md`:
   - File frontmatter title: `v<version>`.
   - File frontmatter description: `Changelog for pbi-agent v<version>, released on YYYY-MM-DD.`
   - H1: `# v<version>`.
   - Release date line: `**Release date:** YYYY-MM-DD`.
   - Categories in this order: `Added`, `Changed`, `Fixed`, `Removed`, `Documentation`, `Internal`.
   - One bullet per notable PR, with PR link: `- User-facing summary ([#123](https://...))`.
   - Keep bullets concise, active voice, impact-focused.
   - Add new release atop index `## Releases` list: `- [v<version> - YYYY-MM-DD](./v<version>.md)`.
   - Add release page to VitePress release notes sidebar.
6. Create GitHub Release body draft from same per-release changelog file; include `Full changelog: docs/changelog/v<version>.md`.
7. Validate touched surfaces:
   - `uv run ruff check .`
   - `uv run ruff format --check .`
   - `uv run pytest`
   - `bun run docs:build`
8. Stage only release-scoped paths. Re-check `git diff --cached`.
9. Commit: `chore: release v<version>`.
10. Push branch and open PR with `gh pr create --base master --head chore/release-v<version>`.

## Publish Mode

Only after explicit user approval and clean checks:

1. Confirm release PR status with `gh pr view <pr> --json mergeStateStatus,statusCheckRollup,url`.
2. Merge release PR into `master` using `gh pr merge` when branch protection permits.
3. Wait for `.github/workflows/release.yml` or inspect with `gh run list --workflow Release`.
4. Confirm `gh release view v<version>` exists.
5. If auto-created GitHub Release body is generic, update from changelog draft with `gh release edit v<version> --notes-file <file>`.
6. Inspect `.github/workflows/publish.yml` or known workflow triggers, then wait for matching Publish workflow run triggered by Release workflow.
7. Confirm publish job succeeded, including package upload step when visible in logs/status.
8. Report separate states:
   - PR merged to `master`.
   - GitHub Release/tag created.
   - package publish workflow completed.
9. Report version, PR URL, release URL, validation, publish status.

## Writing Rules

- Keep summaries under 50 words and release bodies concise.
- Prefer user-facing outcomes over implementation details.
- No emojis.
- No unexplained jargon.
- Mention validation and known skipped/unreleased changes.
- Never include unrelated PRs or workspace changes.
