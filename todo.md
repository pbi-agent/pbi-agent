# Web Production Readiness TODO

## Phase 0: Baseline And Guardrails

- [X] Define canonical web sync invariants: stream identity, sequence scope, cursor ownership, saved-session vs live-run ownership, and snapshot fallback behavior.
- [X] Document current known unstable paths and map each to a regression test target.
- [X] Add a focused smoke-test checklist for manual release validation.

## Phase 1: Durable Event Replay

- [X] Audit current event persistence and replay paths in `session_manager.py`, `session_store.py`, `events.py`, and frontend SSE hooks.
- [X] Persist enough web event metadata to replay active and completed web streams after reconnect or restart without relying on in-memory history.
- [X] Add backend tests for saved-session event replay across multiple web runs.
- [X] Add backend tests for replay after manager restart or in-memory stream loss.
- [X] Ensure persisted replay keeps original event ordering, sequence, type, payload, and creation time.

## Phase 2: Cursor Gap Detection And Recovery

- [X] Add server-side detection for cursor gaps or too-old `since` values.
- [X] Add an explicit SSE control event or API signal that tells the frontend to reload a snapshot when replay is incomplete.
- [X] Add frontend recovery logic that invalidates session/run queries and resets stream state on gap detection.
- [X] Add frontend tests for stale cursor, missed range, reconnect, and snapshot recovery.
- [X] Add backend tests for `Last-Event-ID` and `since` precedence in gap scenarios.

## Phase 3: Session And Run Lifecycle Hardening

- [X] Define lifecycle state machine for saved sessions, live sessions, Kanban task runs, CLI child runs, interrupts, failures, and stale runs.
- [X] Remove ambiguous state transitions or duplicate ownership paths between active live sessions and persisted run records.
- [X] Ensure completed Kanban-bound runs detach cleanly while preserving saved-session continuation.
- [X] Add tests for task run completion followed by manual continuation, repeated continuation, failed run continuation, and interrupted run continuation.
- [X] Add tests for web manager startup marking stale active runs and preserving history.

## Phase 4: Frontend Sync Reducer Stability

- [X] Split or formalize reducer logic so event routing, cursor handling, timeline mutation, and runtime state updates are separately testable.
- [X] Add deterministic reducer tests for every web event type and duplicate/out-of-order events.
- [X] Add multi-tab/session-key routing tests for saved sessions, live sessions, and Kanban-origin sessions.
- [X] Add snapshot overlay tests proving history items and live items do not duplicate or disappear.
- [X] Add forced reload behavior for unrecoverable reducer state.

## Phase 5: API And Event Contracts

- [X] Tighten SSE event payload schemas for high-value events instead of relying on broad record payloads.
- [X] Generate frontend types for event payloads and reduce manual payload assumptions in reducers.
- [X] Add contract freshness tests for new event schemas.
- [X] Keep FastAPI routes, Pydantic schemas, generated TypeScript, and frontend API helpers aligned.
- [X] Add negative contract tests for malformed event payloads at the frontend boundary.

## Phase 6: End-To-End Recovery Coverage

- [X] Add backend integration tests for long event streams exceeding in-memory history size.
- [X] Add frontend tests for EventSource reconnect with server replay and snapshot fallback.
- [X] Add component/integration tests for refresh during active run and after run completion.
- [X] Add tests for ask-user pending question persistence and answer submission after refresh/reconnect.
- [X] Add tests for image attachments in saved-session continuation and provider history restore.

## Phase 7: Observability And Debuggability

- [X] Add user-visible connection/recovery state for reconnecting, recovering, recovered, and failed-to-recover cases.
- [X] Add structured server logs or observability records for SSE subscriptions, replay ranges, and gap recovery.
- [X] Add low-noise frontend debug hooks for stream id, session id, live id, cursor, and recovery reason.
- [X] Ensure fatal errors and interrupted runs surface consistently in UI and persisted run detail.

## Phase 8: Release Readiness

- [X] Run full backend validation: Ruff check, Ruff format check, and full pytest.
- [X] Run full frontend validation: web tests with bounded workers, lint, typecheck, and web build.
- [ ] Run manual smoke checklist from `plan.md`.
- [X] Update docs/release notes with web stability status and pending manual-smoke gate.
- [ ] Sign off web UI production readiness only after the manual smoke checklist passes with captured evidence.
