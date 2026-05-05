# Web Production Readiness Plan

## Goal

Make the pbi-agent web backend and frontend stable enough to ship as a production-ready release, using opencode's sync architecture as the reference bar while preserving this repo's FastAPI, SQLite, SSE, Vite/React, and local-first architecture.

## Current Assessment

The web UI is good enough for local beta use, but not production-stable. The main risk is not one isolated bug; it is that live events, saved-session hydration, Kanban task runs, run records, snapshots, and frontend reducers still form a loosely coupled sync system. Small lifecycle mismatches can silently drop or misroute updates.

## Production Bar

A production-ready web release must satisfy these criteria:

- Event delivery has durable replay semantics across reconnects and server restarts.
- The frontend detects missed event ranges and recovers through a canonical snapshot/API reload.
- Saved sessions, task-origin runs, manual continuations, interrupts, ask-user, and refresh/reconnect flows have explicit lifecycle rules.
- API and event contracts are typed, generated where practical, and covered by contract freshness tests.
- Frontend state transitions are deterministic and covered by reducer/hook tests plus end-to-end recovery scenarios.
- Release validation includes backend tests, frontend tests, lint/typecheck/build, and manual smoke paths.

## Architecture Direction

Keep the existing SSE transport, but upgrade it from an in-memory live stream to a sync model:

- Persist every web event for web-owned runs with stable per-stream sequence metadata.
- Expose enough cursor metadata for clients to know whether replay is complete or a snapshot refresh is required.
- Treat saved-session streams as canonical streams over the active web run plus persisted history, not as best-effort projections.
- Keep timeline history canonical in persisted messages, and use live events only to advance the current turn.
- Keep frontend optimistic events replaceable through canonical message IDs.

## Canonical Sync Invariants

### Stream Identity

A web event stream has one stable owner:

- `app` for workspace/app-level lifecycle events.
- `live_session_id` for exactly one live run instance.
- `session_id` only as a saved-session alias to the current or replayable run stream.

Saved-session event endpoints must not create an independent sequence domain. Session timeline events must include `live_session_id` while live-run-owned and `session_id` once bound to durable saved history.

### Sequence Scope

`seq` is scoped to one stream owner. Starting a new live run for the same saved session starts a new sequence domain. A cursor from one live run must never suppress events from another live run.

### Cursor Ownership

A valid cursor is logically:

```text
(stream_owner_id, stream_generation/run_session_id, last_seq)
```

A numeric `last_seq` alone is insufficient. `Last-Event-ID` should take precedence over `since` for the same stream; the server must not merge unrelated cursor values by taking `max()`. The frontend may advance a cursor only after applying an event whose stream identity matches the attached stream generation.

### Saved Session Vs Live Run Ownership

Saved sessions own durable conversation history. Live runs own transient execution state and live timeline events. A saved session may have zero or one active live run. Completed runs are durable replay/snapshot sources, not active owners.

### Snapshot Fallback

Snapshots are authoritative when replay cannot be proven complete. If the server cannot replay every event after the requested cursor, it must explicitly signal snapshot recovery. The frontend must invalidate the relevant session/run queries, hydrate from the canonical snapshot/detail payload, reset the stale stream cursor, and resubscribe.

## Known Unstable Paths And Regression Targets

| Priority | Path | Risk | Regression Target |
| --- | --- | --- | --- |
| Critical | SSE cursor ownership | `Last-Event-ID` and `since` are merged by `max()` even though numeric cursors are stream-scoped. | Backend test for `Last-Event-ID` precedence without cross-stream max merging. |
| Critical | Missing replay gap detection | Reconnect after retained history rolls over can silently drop events. | Backend snapshot-required test; frontend recovery test for incomplete replay. |
| Critical | Durable replay after manager restart | Saved-session replay reconstructs latest run only; live-run streams disappear after restart. | Backend restart/lost-memory replay tests for saved-session streams. |
| High | Saved-session alias crossing run sequence domains | New saved-session run can start at low seq while old cursor is high. | Backend and frontend tests for new run cursor reset and replay. |
| High | Kanban task run then manual continuation | Completed task-origin run can stay attached, duplicate history, or block continuation. | Backend continuation test plus frontend store cursor/history test. |
| High | Multi-tab/session-key routing | Events can apply to wrong saved/live session key when identity is stale or missing. | Frontend reducer/hook routing tests for stale live ids and session-scoped events. |
| High | History/live snapshot overlay | Refresh during active runs can duplicate or drop optimistic/rekeyed messages. | Frontend overlay/rekey tests; backend detail separation test. |
| Medium | Ask-user refresh/reconnect | Pending questions can disappear or answers can target no active run. | Backend pending-question persistence test; frontend reconnect restoration test. |
| Medium | Loose event payload contracts | Envelope validation allows malformed known payloads into reducer logic. | Frontend known-event payload rejection tests and schema freshness tests. |
| Medium | Image attachments in continuation | Attachments can be lost across task prompt, saved history, live replay, and provider restore. | Backend image persistence/live payload test; frontend timeline render test. |

## Phase 1 Audit Result

Current event flow:

- Backend display events publish through `WebSessionManager._publish_live_event()` into per-live-session `EventStream`.
- `EventStream.publish()` assigns stream-local `seq`, stores bounded in-memory history, and notifies subscribers.
- `_apply_live_event()` mutates the live snapshot and `_persist_live_event_record()` stores a `web_event` observability row plus `run_sessions.last_event_seq` and `snapshot_json`.
- `/api/events/{live_session_id}` serves only active in-memory live streams.
- `/api/events/sessions/{session_id}` serves the active live stream when present, otherwise reconstructs the latest persisted web run into an ephemeral stream.
- Frontend `useLiveSessionEvents()` subscribes with numeric `since`, parses SSE envelopes, resolves event identity from payload or hook fallback, and `store.applyEvent()` drops `seq <= lastEventSeq`.

Validated first implementation:

- Live web events are now enriched centrally at publish time with canonical `live_session_id` and bound `session_id`/`resume_session_id` before in-memory publish and persistence.
- This does not complete durable replay, but it reduces routing/replay risk by making persisted events self-identifying instead of relying on frontend fallback state.

Validated durable replay implementation:

- Live/session SSE routes now load persisted `web_event` replay events before serving the in-memory snapshot, with duplicate suppression by stream-local `seq`.
- Direct `/api/events/{live_session_id}` can replay completed persisted web runs after manager restart when the run belongs to the current workspace.
- Active live streams can recover from lost in-memory event history by replaying persisted events for the same stream.
- Saved-session SSE aliases reset stale high cursors when the selected latest web run has a lower sequence domain, so an older run cursor does not suppress newer run replay.
- `server.replay_incomplete` now reports `cursor_too_old` and `cursor_ahead` with `requested_since`, `resolved_since`, `oldest_available_seq`, `latest_seq`, and `snapshot_required: true`.
- Frontend session/live stream hooks now reset partial stream state, invalidate canonical session/run queries, and reconnect from cursor zero after `server.replay_incomplete`.
- Valid `Last-Event-ID` now takes precedence over `since`; invalid or negative `Last-Event-ID` falls back to `since`.
- App-level durable replay remains intentionally unchanged.

## Lifecycle State Machine

Owners:

- Saved sessions own durable identity and message history; their lifecycle status is an API/UI projection, not a stored session column.
- Live web sessions own active in-memory execution state and live event streams.
- Persisted run sessions own durable run status, metrics, snapshots, and replay metadata.
- Kanban tasks own board-level run summary only and remain restartable after completion/failure.
- CLI/child agent runs own their own persisted observability lifecycle.

Status domains:

- Saved-session projection: `idle`, `starting`, `running`, `waiting_for_input`, `ended`, `failed`, `stale`.
- Live-session projection: `starting`, `running`, `waiting_for_input`, `ended`, `failed`, `stale`.
- Persisted run records: `started`, `running`, `waiting_for_input`, `completed`, `interrupted`, `failed`, `stale`.
- Kanban task run summary: `idle`, `running`, `completed`, `failed`.

Rules:

- A saved session may have zero or one active live owner.
- Completed/failed live runs detach from saved-session active ownership but remain durable replay sources.
- Persisted web run terminal status must use `completed` or `failed`; live `ended` is a stream lifecycle state, not a durable run terminal status.
- Saved-session `session_state: ended` keeps the saved conversation continuable; it clears active live state rather than marking the conversation permanently ended.
- Startup stale handling applies only to non-terminal active persisted web runs and running Kanban task summaries.
- Implemented first hardening rule: persisted web run terminal status is normalized to `completed` or `failed`, and saved-session status projection considers latest web runs.
- Implemented active-owner split: `active_live_session`/`live_session` now represent only active in-memory live owners, `active_run` represents only non-web active run fallback, and completed/failed web runs are replay-only timeline sources.
- Completed Kanban-bound runs now stay detached after terminal status while preserving saved-session history/timeline replay and allowing manual continuation to start a fresh live run.
- Added lifecycle regressions for repeated saved-session continuation after task completion, failed task continuation, and interrupted task continuation; tests wait for session-detail detachment rather than task status alone.
- Added startup stale-run regression coverage: manager startup marks only active `web_session` runs stale, preserves saved history, persisted timeline snapshots, and replayable web events, and does not promote stale runs to active owners.
- Formalized frontend session event handling with pure `resolveSessionEventTarget()` and `reduceSessionEvent()` helpers while preserving the Zustand public API; added pure tests for routing, cursor decisions, timeline mutations, and runtime updates.
- Added deterministic reducer coverage for all session reducer event types plus duplicate, replayed, stale-live-session, and out-of-order event handling.
- Added multi-key routing coverage for saved-session, live-session, unknown-target, live-to-saved identity, and Kanban-origin late events. `applyEvent()` now only moves fallback state when the event binds the same live stream, avoiding cross-tab state corruption.
- Added snapshot overlay coverage for active idle, active processing, dormant/ended, and Kanban-origin timelines. Overlay signature dedupe now consumes skipped historical snapshot messages so historical duplicates are removed without dropping new live messages with repeated content.
- Added forced snapshot recovery for unrecoverable reducer sequence gaps: `reduceSessionEvent()` reports `sequence-gap`, `applyEvent()` exposes reload metadata, and `useLiveSessionEvents()` resets stream state, invalidates snapshots/runs, closes, and reconnects from `since=0`.
- Tightened high-value SSE payload schemas for usage updates, message roles, and tool-call metadata; generated TypeScript contracts now expose typed token usage and tool metadata payloads.
- Frontend event aliases now use the generated discriminated SSE unions. Session reducers narrow typed payloads in high-value branches instead of broad `Record<string, unknown>` assumptions, and parser validation rejects malformed envelopes plus malformed high-value known payloads.
- Existing generated-type freshness coverage is confirmed for event schemas: `test_generated_api_types_are_current()` compares generated output byte-for-byte, and high-value SSE schema assertions cover the new payload contracts.
- Added an API contract guard that limits generated `unknown` responses to SSE streams and file upload retrieval, preventing JSON routes from silently losing response models.
- Added frontend boundary rejection for unknown SSE event types, invalid sequence values, malformed replay control payloads, and malformed high-value session payloads before they reach hooks/reducers.
- Added backend integration coverage for saved-session SSE replay when persisted web events exceed the 1000-event in-memory retention window, including duplicate suppression between persisted replay and retained snapshot tail.
- Added frontend EventSource reconnect coverage proving the hook resumes with the stored cursor and applies sequential server replay events without triggering snapshot fallback; existing replay-incomplete tests cover fallback reset/invalidation/reconnect.
- Added SessionPage refresh wiring coverage for active saved-session runs and completed persisted timelines: active refresh attaches the live SSE stream with the snapshot cursor, while completed refresh stays sendable without reconnecting to a terminal run.
- Added ask-user refresh coverage: backend session detail and persisted snapshots expose pending questions until answered, session-scoped answer submission resumes the worker and persists resolution, and SessionPage submits hydrated prompts through the saved-session endpoint.
- Added image continuation/provider restore coverage: saved-session continuations preserve uploaded image attachments in persisted history, and restored user-message images replay through OpenAI ChatGPT, Anthropic, and Google request builders.
- Added visible frontend recovery states: `reconnecting`, `recovering`, `recovered`, and `recovery_failed` flow through the store, EventSource hook, topbar badge, and SessionPage recovery banners without being masked as ready.
- Added structured SSE route logging for subscriptions, replay ranges, replay-incomplete recovery, and unsubscribe summaries using `pbi_sse` log fields without per-event noise.
- Added dev/test-only frontend live-session debug state on `window.__PBI_AGENT_LIVE_DEBUG__` plus SessionPage `data-debug-*` attributes for stream/session/live/cursor/connection inspection without console noise.
- Added consistent fatal/interrupted surfacing: interrupted web projections persist as `interrupted`, run detail exposes fatal/interruption text, and SessionPage/RunDetailModal render hydrated fatal errors.

## Work Loop

For each checklist item in `todo.md`:

- Run exactly one sub-agent for focused investigation or implementation guidance.
- Review the sub-agent output against repo constraints and existing code.
- If valid, implement or accept the change; if invalid, fix it locally before moving on.
- Add or update focused tests for the exact failure mode.
- Run scoped validation before marking the item complete.
- Update `todo.md`, `TODO.md`, and `MEMORY.md` with concise state.

## Release Gate

The web implementation is not production-ready until all critical and high-priority `todo.md` items are complete and these checks pass:

- `uv run ruff check .`
- `uv run ruff format --check .`
- `uv run pytest -q --tb=short -x`
- `bun run test:web -- --maxWorkers=2`
- `bun run lint`
- `bun run typecheck`
- `bun run web:build`
- Manual smoke: new saved chat, saved-session continuation, Kanban task start, Kanban-to-chat continuation, browser refresh during run, EventSource reconnect, interrupt, ask-user prompt/answer, server restart with saved history.

## Manual Smoke Checklist

Run this checklist against the production-built UI served by `pbi-agent web`, not the Vite dev server. Use a disposable workspace, a configured provider/model profile, one small text/code file, and one small image if image flows are in scope. Open browser DevTools with Console and Network recording enabled, with Preserve log on.

Capture for every smoke run: commit/version, browser/version, provider/model profile, workspace path, session ids, task ids, run ids, server terminal log, browser console state, and relevant Network HAR/screenshots.

| Area | Steps | Expected Result | Capture |
| --- | --- | --- | --- |
| App boot | Start `pbi-agent web`, open the UI, wait for bootstrap. | App shell, sidebar, sessions, and settings load without blank screen or uncaught console errors. | Startup log, console screenshot, bootstrap network calls. |
| Settings/profile | Open Settings, confirm provider/model profile, return to chat. | Settings loads without API errors; active profile is reflected in chat/session controls. | Profile screenshot, network errors if any. |
| New saved chat | Create a saved session and send `Reply with exactly: smoke ok`. | User message appears once; assistant streams/finalizes; session appears in sidebar. | Session URL/id, message API call, SSE activity, run logs. |
| Saved continuation | Send a second message in the same session, then refresh after completion. | History persists in order; no duplicates; continuation is not detached or blocked. | Before/after screenshots, session detail response if inspected. |
| Mentions/commands | Trigger file mention and slash-command search; insert a harmless result. | Suggestions render and insert sane text; no console errors. | UI screenshot, search API calls. |
| Image attachment | Upload/paste a small image and send an acknowledgement prompt. | Upload succeeds; preview appears; refresh preserves attachment in timeline/history. | Upload network call, upload id, before/after screenshots. |
| Kanban run | Create a short task on the board and run it. | Task status/progress updates; completed run links to session/run records where applicable. | Task id, board screenshot, run logs. |
| Kanban-to-chat continuation | Open the task-associated session and send a manual follow-up. | Manual continuation works; no duplicated history; task-origin run does not block chat. | Session screenshots, run history, logs. |
| Refresh during active run | Start a multi-second prompt and refresh while running. | Active session rehydrates; stream resumes or canonical snapshot loads; no lost/duplicated messages. | Refresh timestamp, SSE network entries, before/after screenshots. |
| EventSource reconnect | Simulate offline/online or briefly block network, then restore. | EventSource reconnects; cursor remains valid; timeline stays ordered. | Failed/reopened SSE entries, console state. |
| Interrupt | Start a long prompt and click stop/interrupt. | Run stops cleanly; composer becomes usable; run history records final state. | Interrupt API call, final UI state, run detail. |
| Ask-user | Trigger ask-user behavior, refresh while pending, then answer. | Pending question persists; answer resumes run; UI remains recoverable. | Question/answer screenshots, question-response API call. |
| Server restart | Complete a saved chat, stop/restart server, reopen same session URL. | Saved history and run records load from durable storage. | Stop/start logs, before/after screenshots. |
| Dashboard/run history | Open Dashboard and run detail for smoke runs. | Runs show correct status/provider/model/timestamps; detail opens without crash. | Dashboard and run-detail screenshots. |
| Error state | Open a harmless invalid/deleted/nonexistent session URL if feasible. | UI shows error/empty state; server returns appropriate 404/400. | Screenshot, network entry, console state. |

Manual smoke passes only if there are no blank screens, no unrecoverable UI states, no uncaught browser console errors in normal paths, no duplicated/dropped/misrouted timeline messages, and all captured artifacts are sufficient to diagnose later regressions.
