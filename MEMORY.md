# MEMORY.md

## Metadata
- Last compacted: 2026-05-07
- Scope: durable repo memory + active-day task events.
- Format: only `Metadata`, `Long-Term Memory`, and `Detailed Task Events`.

## Long-Term Memory
- Memory: token-efficient; keep durable decisions/follow-ups only, not logs.
- Workflow: no commit/push/merge/PR unless asked. Use session-only `TODO.md`; markers `[ ]`, `[>]`, `[X]`, `[!]`, `[-]`. Shell from workspace root; use `python3` for direct Python shell commands.
- Validate touched surface: Python Ruff+pytest; frontend Bun tests/lint/typecheck/build; docs build. Note skipped/hung checks.
- Architecture: CLI `src/pbi_agent/__main__.py` -> `src/pbi_agent/cli.py`; default command `web`; backend FastAPI `src/pbi_agent/web/`; frontend Vite React `webapp/`.
- API changes: align routes/schemas/session manager with `webapp/src/api.ts` + `webapp/src/types.ts`.
- Web API contract: `bun run web:api-types` runs `scripts/generate_api_types.py` to regenerate `webapp/src/api-types.generated.ts` from FastAPI OpenAPI plus extra SSE models; output includes schema types, SSE event unions, `ApiOperationResponses`, and `ApiJsonRequestBodies`. Pytest `test_api_types_codegen.py` enforces generated output is current.
- Constraints: provider/tool HTTP via `urllib.request`; internal data in `~/.pbi-agent/`; no migrations/backcompat.
- Tools: built-in `python_exec`, `list_files`, `search_files` removed; use shell (`rg --files`, `find`, `rg -n`) and Python as needed.
- Project imports: top-level `skills`, `commands`, `agents`; public catalogs under `pbi-agent/{skills,commands,agents}`; local install to `.agents/...`.
- Sub-agents: `.agents/agents/*.md`; frontmatter only `name`/`description`; child model from active profile/CLI + `sub_agent_model`.
- Local commands: `plan` no questions; `review` Markdown; `fix-review` stops on `No findings.`; `ship-task` branch/merge helpers; `release` needs explicit publish wording and no history rewrite after PR unless approved.
- Release docs: `release-writing` skill governs releases; changelog index `docs/changelog/index.md`, files `docs/changelog/v<version>.md`, VitePress sidebar links releases; release retrospective added validation triage + publish verification + continuation gate safety.
- Branding: public copy = local coding agent; preserve `pbi-agent`, `pbi_agent`, `PBI_AGENT_*`, `~/.pbi-agent`; logo `src/pbi_agent/web/static/logo.jpg`.
- Web/session: saved sessions use session-scoped APIs; `/api/live-sessions/*` and `/sessions/live/:id` are removed from user-facing test expectations. Blank/saved sessions can start/continue without an active live id; completed Kanban-bound runs detach live ids without ending the saved conversation.
- Web session manager: `src/pbi_agent/web/session_manager.py` is a thin public facade for `WebSessionManager`/startup lease; implementation mixins live under `src/pbi_agent/web/session/` by utility scope. Patch worker/auth globals in `pbi_agent.web.session.workers` and `pbi_agent.web.session.provider_auth`.
- Web events: frontend app/session streams use SSE over `GET /api/events/{stream}` and `/api/events/sessions/{session_id}` with `server.connected`/heartbeat and `since`/`Last-Event-ID`; web UI WebSocket event routes/helpers are removed. SSE event payloads are generated TS unions, but the frontend stream boundary keeps defensive `parseSseEvent()` validation.
- Web message identity: saved history/live replay use canonical persisted item/message ids `msg-<messages.id>` plus stable part ids; optimistic/display-local live items are replaced by `message_rekeyed` once persisted.
- Web status contracts: session/live API models use lifecycle statuses (`idle`/`starting`/`running`/`waiting_for_input`/`ended`/`failed`/`stale`); run history/detail/all-runs use persisted run-record statuses (`started`/`completed`/`interrupted`/`failed`, etc.). Keep them distinct.
- Web live snapshots: `LiveSessionSnapshotModel` preserves typed `processing` and pending user-question payloads; frontend boundary types derive from generated models and keep `pending_user_questions` required nullable.
- Web frontend API boundary: `webapp/src/api.ts` should use generated `ApiOperationResponses`/`ApiJsonRequestBodies` via `apiRequest()` and `jsonBody()` when adding JSON API calls.
- Web durable runs: `run_sessions` has web projection fields/status, `snapshot_json` caches timeline from persisted `web_event` records, unfinished web runs become `stale` on startup, and web `RunTracer` attaches to canonical run ids.
- Web durable event replay: saved-session event streams reconstruct from persisted `web_event` records with original `seq`/`created_at`, so SSE `since` and `Last-Event-ID` cursors remain valid after restart.
- Saved-session timelines: API `history_items` are canonical chronological messages; frontend overlays only non-duplicate live/work snapshot items and avoids opening stale live streams for ended/static projections.
- Session compaction: clear completed `previous_id`; resume restores persisted user/assistant history; compaction includes unanswered trailing user turns and same-turn tool exchanges.
- Providers: OpenAI Responses use `instructions` + `previous_response_id`; ChatGPT subscription prepends system prompt; Codex transport is WebSocket-only (`chatgpt_codex_backend.py`), no unsupported compression.
- Web UI: prefer shadcn tokens/components; overlays use shared readable spacing; large modals need safe gutters + inner scroll; Radix tooltip `collisionPadding`/`sideOffset` may not protect cross-axis viewport gutters, so clamp both axes for edge-adjacent tooltips.
- Timeline: work runs coalesce thinking/tool groups; running closed by default; final assistant closes current collapsibles; file-edit results share `FILE_EDIT_TOOL_NAMES`.
- Web Working UI: OpenCode-inspired nested grouping uses collapsed Working summaries with animated counts, simple Thinking/Activity rows, friendly one-word tool labels, minimal sub-agent cards, read-only hidden child routes with back link, completed-run sub-agent id namespacing, and child processing suppressed after final child assistant response. Active Working label uses text shimmer instead of spinner.
- Syntax highlighting: `read_file` uses lazy Shiki code block; root `package.json` pins exact `shiki` `4.0.2`.
- v0.1.0 shipped.
- Kanban CLI: `pbi-agent kanban create` and `pbi-agent kanban list` are backed by `SessionStore`; lane/stage filters resolve existing board stages; `--json` includes image attachment metadata.
- Kanban task images: stored as task `image_attachments_json`, task create/update accepts `image_upload_ids`, uploads reuse `~/.pbi-agent/web_uploads` + `/api/uploads/{id}` previews, initial task run sends images only with first full prompt.
- Provider history restore preserves user message image attachments for image-capable providers (OpenAI/ChatGPT, Anthropic, Google) by reloading upload IDs from `~/.pbi-agent/web_uploads`.
- Web server startup: same-workspace active lease is rejected; implicit default port `8000` may auto-select a free port, explicit `--port` stays strict.
- Web UI session context gauge: compact donut uses top-level `session_usage.context_tokens` with turn fallback over runtime `compact_threshold`; tooltip is custom fixed-position with both-axis viewport clamping.
- Kanban: task cards omit technical project/session metadata and image counts; active task sessions show a Stop shortcut whose pending state is tied to the interrupt mutation.
- Saved sessions: sidebar supports inline title edit via `PATCH /api/sessions/{session_id}` with cache/app-event invalidation.
- Interactive ask-user: Web per-message `interactive_mode` exposes `ask_user`; pending questions persist in snapshots and are answered via session-scoped question-response endpoints; topbar uses shadcn `Toggle` and `UserQuestionsPanel`.
- UserQuestionsPanel UX: one question at a time with shadcn Card, selected filled Button state, keyboard nav, auto-focus active option, Prev/Next + dots, and custom textarea retained in fieldset.
- Ask-user notifications: frontend-only localStorage prefs for desktop/sound; AppShell effect fires hidden/unfocused browser notifications/sound, deduped by live/session + prompt id, click focuses/navigates to waiting session.
- Web production readiness hardening completed through Phase 8: documented sync/lifecycle invariants, durable SSE replay from persisted `web_event`, replay gap recovery, lifecycle ownership split, stale web-run startup handling, reducer/routing gap recovery, strict generated SSE/API contracts, long-stream replay coverage, refresh/reconnect regressions, ask-user/image restore, recovery states/logging/debug hooks, and fatal/interrupted surfacing. Release docs and manual browser smoke remain pending until explicit workflow/served UI.
- Saved-session timeline refresh must preserve persisted work-item anchors: merge canonical `history_items` with snapshot messages in order, keeping `thinking`/`tool_group` items between their original surrounding messages so prior turns retain separate `Working` blocks.
- Web lifecycle hardening: startup/shutdown/task setup races, stale unbound web runs, SSE persistence/cursors/recovery, saved-session deletion/live creation locks, and release workflow collision guards were production-readiness validated before v0.2.0 prep.
- Saved-session timelines: aggregate persisted web-run snapshots chronologically, namespace non-message work ids per run, preserve `Working` anchors around duplicate canonical messages, and avoid content-signature fallback once a persisted `messageId` is consumed.
- Timeline UI: work-run headers show context first (`Researcher · Working` / `3 agents · Working`); expanded Working uses strict nested grouping (summary counts → compact tool rows → one detail card). Main-session sub-agent output is collapsed to one status card per sub-agent id; clicking opens `/sessions/:parent/sub-agents/:id`, a hidden read-only child view filtered from parent timeline with no composer/interrupt/questions and a back link.
- Settings UI: opencode-inspired two-pane settings surface split into modular sections; command cards show compact metadata and open markdown previews through shared `MarkdownContent`; dialog close buttons use shared `app-close-icon-button`.
- Test hygiene: pytest isolates web upload root to per-test `tmp_path / "web_uploads"` to prevent fixture uploads leaking into `~/.pbi-agent/web_uploads`.

## Detailed Task Events
## 2026-05-07
- Fixed web session startup Working flicker by keeping the active no-anchor WorkRun on a stable placeholder key and showing a muted `Preparing…` summary until counts exist; active empty connected sessions now show Working instead of Welcome. Validation: `bun run test:web -- SessionTimeline`, `bun run lint`, `bun run typecheck`, `bun run web:build`, `bun run test:web` (first full run had a transient `SessionWelcome` timeout, rerun passed), and `git diff --check` passed.
- Slowed the active web Working `TextShimmer` wave by increasing shimmer duration and rebuilt static web assets. Validation: `bun run test:web -- SessionTimeline`, `bun run lint`, `bun run typecheck`, `bun run web:build`, and `git diff --check` passed.
- Simplified expanded web Working groups by removing the intermediate Activity/In motion collapsible level; Thinking, tool rows, and sub-agent cards now share the first expanded level while tool rows still expand to detail. Validation: `bun run test:web -- SessionTimeline`, `bun run lint`, `bun run typecheck`, `bun run web:build`, and `git diff --check` passed.
- Added `.agents/commands/commit.md` to standardize local-only commit workflow with explicit staging, validation freshness, and stop conditions. Validation: `git diff --check` passed.
- Raised the sub-agent provider request cap default from 100 to 200 in `src/pbi_agent/agent/session.py` and updated `AGENTS.md`. Validation: `uv run pytest -q --tb=short -x tests/test_cli.py` passed; attempted `tests/test_sub_agent.py` but no such file exists.
- Hid generic web session timeline retry messages matching `Retrying... (n/n)` for notice/error roles while preserving contextual retry notices and real errors; rebuilt static web assets. Validation: `bun run test:web -- SessionTimeline`, `bun run lint`, `bun run typecheck`, `bun run web:build`, `bun run test:web` (first full run had a transient `BoardStageEditorModal` timeout, targeted rerun and full rerun passed) passed.
