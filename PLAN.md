# Plan: Gitignore-aware scan module for @ file suggestions

## Summary
- Harden web composer `@` file suggestions by moving workspace enumeration into a new `src/pbi_agent/web/scan.py` module.
- The scan module must recursively scan all workspace subfolders with no depth-based pruning, while excluding gitignored files and folders. For Git workspaces, use Git’s own ignore view (`git ls-files -co --exclude-standard -z -- .`) so tracked and untracked nonignored files are included and ignored folders are excluded.
- Keep commands on slash completion and do not add skills to `@` in this pass. Codex inspiration to apply: background scanning, stale-result guards, gitignore-aware traversal, and clear loading/empty states; do not port Rust `ignore`/`nucleo` dependencies.

## Checklist
- [X] Add `src/pbi_agent/web/scan.py` with a small public API for `scan_workspace_files(root: Path) -> WorkspaceScanResult`.
  - [X] In Git workspaces, enumerate recursively with `git -C <root> ls-files -co --exclude-standard -z -- .`.
  - [X] Normalize every result to a POSIX path relative to the workspace root, reject absolute/traversal paths, reject directories, and reject symlinks that resolve outside the workspace.
  - [X] If Git is unavailable or the root is not inside a work tree, fall back to a stdlib recursive scan that skips VCS internals but still walks nested subfolders.
- [X] Refactor `WorkspaceFileIndex` in `input_mentions.py` to use the scan module.
  - [X] Replace the current `os.walk` + hardcoded directory skip path with scan results.
  - [X] Make search use a non-blocking snapshot: startup/reload refreshes run in the background, search returns the latest snapshot immediately, and a cold search starts a scan instead of blocking the request.
  - [X] Keep fuzzy ranking and image/file classification behavior; search result limits remain bounded.
- [X] Extend `/api/files/search` to expose scan state along with items.
  - [X] Add response fields: `scan_status: "idle" | "scanning" | "ready" | "failed"`, `is_stale: bool`, `file_count: int`, and `error: str | None`.
  - [X] Update FastAPI schemas/routes, session catalog methods, `webapp/src/api.ts`, `webapp/src/types.ts`, and regenerate `webapp/src/api-types.generated.ts` with `bun run web:api-types`.
- [X] Harden the frontend Composer completion flow.
  - [X] Update `searchFileMentions()` to return the full file-search payload, not just `items`.
  - [X] Show `Indexing files...` for cold scans, `Refreshing file index...` when stale results are displayed during a refresh, and a scan failure message when `scan_status === "failed"`.
  - [X] Preserve stale-response protection by request id/query/mode so older file-search responses cannot replace newer completion state.
  - [X] Replace the `@` parser with a token-under-cursor parser: trigger only at token boundaries, ignore emails/import aliases such as `@/components`, allow cursor movement within the token, and treat later `@` characters inside the same token as part of the query.
- [X] Update focused tests.
  - [X] Add scan-module tests for nested files, ignored files, ignored folders, hidden nonignored files, non-Git fallback, and parent `.gitignore` not suppressing a child Git workspace.
  - [X] Update input-mention tests so gitignored folders are excluded by the scan module and the cache/snapshot behavior is covered without monkeypatching `os.walk`.
  - [X] Update web API tests for the new `/api/files/search` response fields and deterministic warmed-index behavior.
  - [X] Add Composer tests for loading/stale/failed scan states, stale response discard, second-`@` tokens like `@icons/icon@2x.png`, and no popup for email/import-alias text.

## Public API / type changes
- `/api/files/search` response changes from `{ items }` to `{ items, scan_status, is_stale, file_count, error }`.
- `webapp/src/api.ts::searchFileMentions()` should return that full payload; Composer reads `payload.items` and scan state.
- Python scan API is internal to the web backend (`pbi_agent.web.scan`); no CLI command or provider/tool interface changes.

## Validation
- [X] Python focused: `uv run pytest -q --tb=short -x tests/test_scan.py tests/test_input_mentions.py tests/test_web_serve.py::test_file_search_endpoint_returns_workspace_matches tests/test_api_types_codegen.py` passed.
- [X] Frontend focused: `bun run test:web -- webapp/src/components/session/Composer.test.tsx` passed, including review-fix coverage for cold/stale scan polling and Escape dismissal.
- [X] Full frontend: `bun run test:web`, `bun run lint`, `bun run typecheck`, and `bun run web:build` passed.
- [X] Full touched-surface checks: `uv run ruff check .`, `uv run ruff format --check .`, and `uv run basedpyright` passed. Full `uv run pytest -q --tb=short -x` was attempted and stopped at pre-existing/unrelated `tests/cli/test_catalogs.py::DefaultWebCommandTests::test_main_commands_list_lists_project_commands_without_settings` expecting project commands while none were discovered.

## Assumptions / Scope
- Git is the authoritative ignore source when available; the fallback is only for non-Git workspaces and should not try to fully reimplement all Git ignore edge cases.
- The scan module scans file paths only; directory suggestions are out of scope for this pass.
- Skills remain `$`/skill-popup inspired by Codex only conceptually and are not added to pbi-agent `@` suggestions.
- No migrations, compatibility shims, or alternate frontend/backend frameworks are needed.
