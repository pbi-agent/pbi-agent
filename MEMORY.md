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

- Prior implementation/validation notes: `.agents/memory/2026-11-12.md` (web terminal/ConPTY, local session titles, badge centering, session-title UI, #169 kits, releases v0.53–v0.56), `.agents/memory/2026-11-10.md` (includes #292 interrupt cleanup, #199 status dashboard, #344 questionnaire). [verified 2026-11-12]

## Daily Log

### 2026-11-13
- #149 trace timeline: Run Detail modal's flat event list replaced by a span tree (`webapp/src/components/session/runTrace.ts::buildRunTrace` + `TraceRow` in `RunDetailModal.tsx`): run (AGENT) > `model_call` (CHAT) / `tool_call` (TOOL) / `error`+`model_call_retry` (ERROR), marker events hidden, waterfall bar = offset+share of root duration (event timestamp is the span END; start = timestamp − duration). `GET /api/runs/{id}` now returns `child_runs[{run, events, parent_tool_call_id}]` (all descendants); sub-agent runs store `parent_tool_call_id` in run metadata, older runs nest by time-window fallback. Lint (`shadcn/no-restyle`, `no-inline-styles`) forced: Badge `trace-*` variants, `CollapsibleContent animated` prop, bar geometry via `--trace-bar-offset/width` CSS vars; colours are `--trace-*` tokens in `tokens.css` (three theme blocks). Headless check: dashboard rows are `tr[data-run-id]` (first `tbody tr` is the breakdown table); `page.route` can redirect `/api/runs/<id>` to a run with sub-agents. 781 web tests, full pytest, Ruff/format/basedpyright, lint/typecheck/build, headless Chromium dark/light/620px green.
- #149 trace timeline [verified 2026-11-13]: Run Detail modal's flat event list is now a span tree (`webapp/src/components/session/runTrace.ts::buildRunTrace`, `TraceRow` in `RunDetailModal.tsx`). `GET /api/runs/{id}` returns payload-free event summaries (`has_payload`) for the run plus all descendants in `child_runs` (recursive CTE + one events query); payloads load per event from `GET /api/runs/{id}/events/{step_index}`. Sub-agent runs store `parent_tool_call_id` in run metadata and nest under that tool call; runs without it sit under their parent run (no time-based guessing, user decision: no retro-compat). Event timestamp = span END; run start = its `run_start` event; time scale extends to the last descendant end. In-flight: trailing `model_call_start` and a running sub-agent's unrecorded tool call render as running spans (tool span id = `<run>:call:<tool_call_id>` so the row survives completion). Row expand/details state is lifted to `TraceTimeline` (Radix Collapsible unmounts closed content). Lint (`shadcn/no-restyle`, `no-inline-styles`) forced Badge `trace-*` variants, `CollapsibleContent animated`, bar geometry via CSS vars; colours = `--trace-*` in `tokens.css` (three theme blocks).
- Headless UI check while the user's own server holds the workspace: run a second instance from a scratch cwd with `PBI_AGENT_SESSION_DB_PATH` = a `sqlite3 .backup` copy and use dashboard scope Global; rows are `tr[data-run-id]`. Never `pkill -f` a pattern that also matches the running shell command (kills the tool shell); kill by listening pid. [verified 2026-11-13]
- Released v0.57.0 (#419; PRs #414–#418: kits, run trace timeline, session-title topbar, badge centering, Windows terminal CI); validation green, Release run published PyPI + GitHub Release. `scripts/dead_code.py` is report-only (exit 0) and lists 5 unused `ready_assets` variables in `tests/test_session_titles.py`. [verified 2026-11-13]
