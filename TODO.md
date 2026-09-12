- [x] Identify the actual local sessions database and check active database users.
- [!] Run the authorized migration with backup, then verify schema and integrity: blocked until active pbi-agent database users stop.
- [x] Record the migration outcome.

- [x] Inspect and select local-shell provenance task changes; exclude the broader AGENTS.md policy edit.
- [x] Validate commit scope: 449 focused tests, Ruff lint/format, repo and migration-script basedpyright, and diff checks passed.
- [x] Prepare one local commit; leave AGENTS.md policy edit out and actual database migration blocked.

- [x] Trace failed-turn follow-up replay and inspect the reported session read-only.
- [x] Fix confirmed history gaps and add HTTP 400, unfinished-tool, and cross-provider regression coverage.
- [x] Run relevant validation and record findings in memory: 1,619 Python tests, Ruff lint/format, basedpyright, and diff checks passed.

- [x] Review the failed-turn HTTP 400 replay diff and trace affected follow-up paths.
- [x] Validate review findings without changing implementation: 376 session/provider tests and diff checks passed; temporary-database reproductions confirmed compaction replays full raw tools and completed checkpoint turns can attach prior-run tools to the wrong prompt.

- [x] Fix review finding 1: keep automatic unfinished-tool recovery behind the compaction boundary and add regression coverage.
- [x] Fix review finding 2: associate checkpoint inputs with their run and use run completion for unfinished-history recovery.
- [x] Run focused regressions and Python checks; record the fix outcomes. 329 focused and 1,649 full-suite tests passed, along with Ruff lint/format, basedpyright, and diff checks.

- [x] Review the updated failed-turn replay patch and both review fixes without changing implementation.
- [x] Validate edge cases and report actionable regressions: 329 focused tests, Ruff lint/format, basedpyright, and diff checks passed; temporary-database reproductions confirmed lost tool replay for image turns, Google step-input requests, and compacted checkpoint runs. No implementation or user database changes.

- [x] Fix review finding 1: extract traced user prompts from Google step inputs and add replay regressions.
- [x] Fix review finding 2: associate image turns using undecorated prompt text and cover both replay paths, including image-only input.
- [x] Fix review finding 3: associate compacted runs through surviving checkpoints without restoring summarized tools.
- [x] Validate replay boundaries and run focused replay/provider tests and Python checks; record results in memory. All 73 history regressions and 1,692 full-suite tests passed, plus Ruff lint/format, basedpyright, and diff checks.

- [x] Review the current failed-turn replay diff and trace in-scope recovery paths without changing implementation.
- [x] Validate uncovered edge cases and report actionable findings: 321 focused tests, Ruff lint/format, basedpyright, and diff checks passed. Temporary-database/mock-provider reproductions confirmed duplicate retry outputs, repeated-prompt fork misassociation, and dropped unsummarized tools for compaction-wrapped checkpoints. No implementation or user database changes.

- [x] Fix review finding 1: deduplicate failed/retried input deltas per logical request and add recovery regressions. All 16 HTTP retry cases pass.
- [x] Fix review finding 2: use run/message chronology to match repeated prompts, including forked histories. All 223 history/session tests pass, including 16 fork cases.
- [x] Fix review finding 3: recognize compaction-wrapped checkpoints while retaining the replay cutoff. All 121 history regressions pass, including 16 runtime compaction cases.
- [x] Run focused replay validation and Python checks; record results in memory. All 424 focused and 1,740 full-suite tests passed, plus Ruff lint/format, basedpyright, and diff checks.

- [x] Review the current failed-turn replay patch and latest regression fixes without changing implementation.
- [x] Validate uncovered edge cases and report actionable findings: 446 focused tests, Ruff lint/format, basedpyright, and diff checks passed. A temporary-database/mock-Copilot reproduction against HEAD confirms duplicate prompts/tool-call IDs when recovering a failed stateless Responses request. No implementation or user database changes.

- [x] Fix the listed Responses replay finding: normalize failed-request delta comparisons and add stateless follow-up regressions. The regression failed before the fix; all 24 Copilot/ChatGPT recovery cases now pass.
- [x] Run focused replay/provider tests and Python checks; record results in memory. All 436 focused tests (including 32 new regressions), Ruff lint/format, basedpyright, and diff checks passed.

- [x] Review the failed-turn replay patch and latest Responses normalization fix without changing implementation.
- [x] Validate replay recovery and report findings: no actionable regressions found; all 1,772 Python tests, Ruff lint/format, basedpyright, and diff checks passed. No implementation or user database changes.
