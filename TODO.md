# TODO: Issue #119 - Customizable Kanban Stages

Context: implement https://github.com/nasirus/pbi-agent/issues/119

Goal:
- allow adding new kanban stages
- allow reordering stages
- allow attaching a default model profile to a stage
- allow attaching a default mode command to a stage
- allow toggling auto-start per stage
- ensure each next step for a task follows configured stage order

Design decision used:
- store board stage configuration per workspace in the session DB, not in global `~/.pbi-agent/config.json`
- keep model profiles and modes global, but reference them from board stages by ID
- stop treating `processing` as a real board stage; use `run_status` for execution state and move tasks by configured stage order

## Phase 1 - Analysis and target design

- [x] Inspect the current board/task backend and frontend implementation.
  Context: stages were hard-coded in the session store, FastAPI models, session manager, and React board UI.

- [x] Choose the target workflow model for custom stages.
  Context: implemented a stage-order-driven progression model with `run_status` representing execution instead of a special `processing` column.

## Phase 2 - Data model and persistence

- [x] Add workspace-scoped stage configuration persistence to the SQLite session store.
  Context: added `kanban_stage_configs` keyed by `(directory, stage_id)` with `name`, `position`, `model_profile_id`, `mode_id`, `auto_start`, and timestamps.

- [x] Seed default stage configuration for workspaces that do not yet have one.
  Context: new workspaces start with `backlog`, `plan`, and `review`; `plan` defaults to mode `plan`, and `review` defaults to mode `review`.

- [x] Add session-store APIs for stage configuration.
  Context: implemented board-stage listing, lookup, and full-list replacement to keep reorder and validation simple.

- [x] Make task stage validation use persisted stage IDs instead of the hard-coded `KANBAN_STAGES` tuple.
  Context: task create, update, and move operations now validate against the board config for the current workspace.

- [x] Replace hard-coded task ordering with configured stage ordering.
  Context: `list_kanban_tasks()` now sorts by persisted stage positions, then by task position within each stage.

- [x] Remove implicit stage transitions tied to `processing` and `review`.
  Context: running/completion updates no longer force stage moves; stage progression is driven by configured stage order in the task worker.

## Phase 3 - Backend workflow logic

- [x] Add board stage serialization to the web session manager bootstrap payload.
  Context: bootstrap now returns structured stage objects instead of a fixed list of stage strings.

- [x] Add backend helpers to resolve effective runtime for a task.
  Context: runtime selection order is task profile override -> stage default profile -> current web default runtime.

- [x] Add backend helpers to resolve effective mode for a task run.
  Context: stages store `mode_id`, which is resolved to the current slash alias at runtime and prefixed only when the prompt does not already start with a slash command.

- [x] Update task run workflow to advance by configured stage order.
  Context: successful runs advance to the next configured stage; failed runs stay in the current stage and mark the task failed.

- [x] Implement auto-start chaining when entering a stage with `auto_start = true`.
  Context: after a successful run advances a task into the next stage, the worker continues automatically when that stage is configured for auto-start.

- [x] Normalize or reject now-invalid task states after the workflow change.
  Context: startup normalization now handles interrupted running tasks via `run_status`, and the web/task code no longer relies on a `processing` board column.

## Phase 4 - API surface

- [x] Replace hard-coded board stage typing in FastAPI models with dynamic string-based stage IDs.
  Context: the API now accepts custom stage IDs instead of using a fixed `Literal[...]`.

- [x] Add API models for board stage config payloads.
  Context: the API exposes stage `id`, `name`, `position`, `profile_id`, `mode_id`, and `auto_start`.

- [x] Add board stage endpoints.
  Context: added `GET /api/board/stages` and `PUT /api/board/stages`.

- [x] Update task endpoints to accept dynamic stage IDs.
  Context: task create/update APIs now validate against workspace stage config rather than Pydantic `Literal`s.

## Phase 5 - Frontend board behavior

- [x] Replace static board stage constants with server-provided stage config.
  Context: the board page now renders columns from `/api/board/stages`.

- [x] Remove `processing`-specific UI behavior.
  Context: drag/edit/delete restrictions now depend on `run_status === "running"` instead of a special stage name.

- [x] Update frontend types for dynamic stage IDs and board stage config.
  Context: `TaskRecord["stage"]` is now `string`, and shared board-stage types were added.

- [x] Show stage metadata in the board columns.
  Context: columns display stage name plus badges for auto-start, bound mode, and bound profile when present.

- [x] Update the task modal to actually expose stage selection.
  Context: the task form now uses live board stage options instead of an implicit hidden field.

- [x] Add profile and mode selection support to the task modal only if task-level overrides remain editable.
  Context: the task modal now exposes the existing task-level profile override while stage mode/defaults remain part of the board-stage editor.

## Phase 6 - Frontend board customization UI

- [x] Add a board customization entry point in the board page.
  Context: the board page now has an `Edit Stages` action because this feature is workspace-scoped.

- [x] Build a board stages editor modal.
  Context: the modal supports add, rename, reorder, remove, default model profile, default mode, and auto-start.

- [x] Prevent invalid board configurations in the editor.
  Context: the backend rejects empty boards, duplicate stage IDs, and unknown profile/mode references; the modal preserves at least one stage and surfaces save errors.

- [x] Handle stale data and live refresh in the board editor.
  Context: stage updates publish app events, and the frontend invalidates `board-stages`, `tasks`, and `bootstrap`.

## Phase 7 - Tests

- [x] Add session-store tests for stage config persistence and ordering.
  Context: added coverage for preserved-stage results and task ordering after board-stage replacement.

- [x] Add backend tests for stage-driven task progression.
  Context: added a web test that verifies a successful run advances to the next configured stage.

- [x] Add backend tests for stage default profile and mode resolution.
  Context: task contract and run-path coverage now exercises stage-aware runtime resolution and slash-mode integration through the web/session stack.

- [x] Add FastAPI tests for board stage endpoints and dynamic stage IDs.
  Context: added round-trip coverage for `/api/board/stages` and updated bootstrap/task API assertions to use the new shape.

- [x] Add frontend tests if the project already has the right coverage entry points.
  Context: no dedicated frontend test harness exists here, so validation relied on lint, typecheck, build, and backend integration coverage.

## Phase 8 - Validation and cleanup

- [x] Run Python lint checks.
  Context: `uv run ruff check .`

- [x] Run Python format check.
  Context: `uv run ruff format --check .`

- [x] Run frontend lint.
  Context: `bun run lint`

- [x] Run frontend typecheck.
  Context: `bun run typecheck`

- [x] Run frontend production build.
  Context: `bun run web:build`

- [x] Run the Python test suite.
  Context: `uv run pytest`

- [x] Review remaining hard-coded stage assumptions before finishing.
  Context: removed board-stage assumptions across backend, frontend, and tests, and rebuilt the bundled web assets.

## Follow-up fixes

- [x] Prevent terminal auto-start stages from re-running the same task forever.
  Context: the worker now only auto-starts when a successful run actually moved the task into a different next stage; a final stage with `auto_start = true` runs once and stops.

- [x] Treat backlog as a queue-only stage when users click `Run`.
  Context: manual runs from `backlog` now move the task into the next configured stage before execution so stage defaults come from the real working stage, while all non-backlog stages keep the existing behavior.

- [x] Rename the board action label from `Run` to `Start`.
  Context: the task card action now matches the updated backlog semantics in the UI without changing the underlying API route or execution flow.

- [x] Add a fixed `done` archive stage as the terminal board column.
  Context: the default board now seeds `backlog -> plan -> review -> done`, existing board configs are normalized to include `done`, and successful runs can advance into that final archive stage.

- [x] Enforce `backlog` first and `done` last across board reads and writes.
  Context: the store now canonicalizes those two fixed stages on every board load/save, strips runtime settings from them, and preserves custom middle-stage ordering only between those bookends.

- [x] Prevent tasks in `done` from running and hide the `Start` action there.
  Context: backend execution rejects manual runs from `done`, backlog promotion skips non-runnable stages, and the board UI removes the run control for archived tasks.

## Phase 9 - Drag-and-drop stage reordering

- [x] Install `@dnd-kit/sortable` package.
  Context: installed `@dnd-kit/sortable@10.0.0` via bun.
- [x] Update `BoardPage.tsx` to use a single DndContext with discriminated drag types (task vs stage) and wrap stages in `SortableContext`.
  Context: added `SortableContext` with `horizontalListSortingStrategy`, discriminated drag types via `sortable-stage:` prefix, and `arrayMove` for reordering.
- [x] Update `StageColumn.tsx` to use `useSortable` alongside `useDroppable`, add a grip-icon drag handle to the column header.
  Context: column uses `useSortable` for stage reordering and keeps `useDroppable` for task drops; both refs merged on the same DOM node.
- [x] Add CSS styles for stage dragging state and drag handle.
  Context: added `.board-column--dragging`, `.board-column--overlay`, `.board-column__drag-handle`, and `.board-column__grip-icon` styles.
- [x] Run frontend lint, typecheck, and build to validate.
  Context: `bun run lint`, `bun run typecheck`, and `bun run web:build` all pass.
