# MEMORY.md

Index of durable project memory, preloaded into every main-agent session (first 200 lines / 25 KB only). Keep it short: goal, top rules, open follow-ups, links. Details live in `.agents/memory/*.md`. Conventions already in `AGENTS.md` or config are not repeated here.

Entry shape: rule/fact — why/evidence — `[verified YYYY-MM-DD]` or `[unverified]`. Untagged entries predate this convention (migrated 2026-11-07).

## Current Focus
- Memory redesign (2026-11-07): index + topic pages, capped injection; memory rules and session-DB query guidance live only in `AGENTS.md`, never in the system prompt code (user decision). [verified 2026-11-07]

## Top Rules
- No migrations or backward-compat shims unless asked.
- Report skipped, hung, or broken checks instead of claiming green.
- `web:build` must run `bun --bun vite build`; Node-run Vite changes chunk hashes → CI static-asset drift. See `tooling.md`.
- Never rerun an old-SHA release; PyPI CDN lags, verify instead of republishing. See `tooling.md`.
- ChatGPT/Copilot: never replay `reasoning_text`+`reasoning_opaque` on tool-call messages (422). See `providers.md`.

## Open Follow-Ups
- Follow-ups: post-delivery interrupt removes the accepted live user item; accepted steers should stay. (`web.md`)
- ChatGPT continuation: live-unverified recovered-ID reuse, delayed/encrypted-reasoning recovery, proactive replay. (`providers.md`)
- Packaging: transitive security minima are lock-only, not in published runtime metadata. (`tooling.md`)
- Unverified on real hosts: Windows self-update path; Linux GUI browser launch. (`tooling.md`)

## Topic Pages
- `.agents/memory/tooling.md`: Ruff exceptions, tool pins, test hygiene, releases, upgrade, security.
- `.agents/memory/providers.md`: provider internals, Copilot, xAI, models/pricing, reasoning, OpenAI/ChatGPT, Google.
- `.agents/memory/tools.md`: read_image, shell, background shell, `allowed_tools`, patching, MCP.
- `.agents/memory/runtime.md`: prompt assembly, catalogs, sub-agents, commands, replay, hooks, sandbox/init, branding.
- `.agents/memory/web.md`: API contracts, web sessions, channels, events, timeline, UI quirks, composer, follow-ups.

## Daily Log

### 2026-11-10
- #382: removed `explore_workspace`/`codetool-explore`/`workspace_filters.py`; added `read_image` tool + `read-image` group (aliases `read`/`read_image`); skills load via `shell`; webapp/docs/tests updated. Full ruff/basedpyright/pytest/web lint/typecheck/test/build + docs build green. Uncommitted.
- #382 review fixes: aliases, `.agents` frontmatter → `read-image` (explorer/reviewer + shell), shell read rule always on, skills-need-shell warning, image stat size precheck. No webapp legacy explore rendering (user: no retro-compat). read_image stays unconfined by request.
- #382 live smoke (web :7431, worker profile): legacy `read` profiles load as `read-image`; 13 commands/10 agents discovered; shell read + skill load via shell + read_image (workspace + /usr/share abs path) OK; logs/console clean. Fixed missed profile-card label map (`ModelProfilesSettingsSection.tsx`) + test.
- Merged PR #384 (merge 85ffa831) after CI run 42751808364 green; #382 closed; branch deleted local+remote.
- #383: raw shell output saved to `~/.pbi-agent/shell-output/` on truncation or lossy compression; background raw file only after finish; cleanup in daily startup maintenance. Live web smokes + full checks green. Merged PR #385 (merge dbe89230); CI Tests (PR+master) + Deploy Docs green; #383 closed; branch deleted. Note: master has no required checks, so `gh pr merge --auto` merges immediately. Details: `.agents/memory/tools.md`.
- File-tree polling (PR #386): `SessionPage` polled `/api/files/tree` every 2s even with explorer closed. Now SessionPage is the sole poller via `workspaceFileTreeRefetchInterval(open)` (2s open / 15s closed); panel has no interval; `useLiveSessionEvents` invalidates `workspace-file-tree` once per finished `apply_patch`/`replace_in_file`/`write_file`/`shell` call (dedupe by call_id), so badge + composer index revision stay fresh. Measured: two observers on one key with equal intervals did NOT double requests in React Query. Tests in `SessionPage.test.tsx`, `useLiveSessionEvents.test.tsx`.
