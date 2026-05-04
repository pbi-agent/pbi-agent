# MEMORY.md

## Metadata
- Last compacted: 2026-05-04
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

## Detailed Task Events
## 2026-05-04
- Added generated API operation contracts: codegen exports API response/request-body maps, frontend `api.ts` uses operation-keyed `apiRequest()`/`jsonBody()`, and `LiveSessionSnapshot.pending_user_questions` now matches the required nullable generated schema. Validation: API codegen pytest, Ruff check/format-check, `bun run test:web -- api`, `bun run typecheck`, `bun run lint`, `bun run web:build`, and `git diff --check` passed.
- Tightened saved-session image upload OpenAPI contract: `/api/sessions/{session_id}/images` now returns `SessionImageUploadResponse`, so generated operation responses use a named `{ uploads: ImageAttachmentModel[] }` model instead of a loose record. Validation: API codegen pytest, full web serve pytest, Ruff check/format-check, `bun run typecheck`, `bun run lint`, `bun run test:web -- api`, `bun run web:build`, and `git diff --check` passed.
- Added generated API parameter contracts: codegen exports `ApiOperationPathParams`/`ApiOperationQueryParams`, frontend query builders use `ApiQueryParams`, and dashboard/run/search query strings now flow through `queryString()`. Validation: API codegen pytest, Ruff check/format-check, `bun run typecheck`, `bun run lint`, `bun run test:web -- api`, `bun run web:build`, and `git diff --check` passed.
- Applied generated path parameter contracts: dynamic frontend API URLs now use `pathFor()` with `ApiPathParams`, so session/task/provider/run/model-profile path variables are checked against generated operation keys. Validation: API codegen pytest, Ruff check/format-check, `bun run typecheck`, `bun run lint`, `bun run test:web -- api`, `bun run web:build`, and `git diff --check` passed.
- Fixed saved-session continuation after Kanban-started runs: `attachLiveSession(... preserveEventCursor)` now preserves the SSE cursor only for the same live stream and resets when a new live run starts, preventing old high cursors from skipping new run events. Validation: focused `store`/`useLiveSessionEvents` tests, full `bun run test:web -- --maxWorkers=2`, `bun run typecheck`, `bun run lint`, `bun run web:build`, and `git diff --check` passed.
