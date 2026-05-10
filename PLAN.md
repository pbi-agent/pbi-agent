# Plan: Up-Arrow Chat Input History Recall

## Summary
Add frontend-only input history recall for the session composer. When the Message textbox is focused and completions are not active, `ArrowUp` recalls the latest user message from the current main conversation so it can be resent or edited. Repeated `ArrowUp` walks older user inputs; `ArrowDown` walks newer inputs and restores the in-progress draft. No backend/API contract changes are needed.

## Checklist
- [X] Add a `inputHistory?: string[]` prop to `Composer`, documented as chronological oldest-to-newest user input text for the current conversation.
- [X] In `SessionPage`, derive `inputHistory` from the displayed main-session timeline: include only non-empty `TimelineMessageItem` entries where `role === "user"` and no `subAgentId`; pass it to `Composer`.
- [X] In `Composer`, add history navigation state: current history index plus a saved draft value captured before history browsing starts.
- [X] Handle keyboard shortcuts in `Composer` after the existing completion-menu branch so completions keep priority:
  - `ArrowUp` with no modifiers recalls latest/older history when history exists, no images are pending, and the cursor is on the first line or the input is empty.
  - `ArrowDown` with no modifiers works only while browsing history; it moves newer, then restores the saved draft and exits history mode.
  - Recalled text is written into the textbox, cursor moves to the end, completions close, and auto-resize runs.
- [X] Reset history-browsing state on manual input changes, submit success, restored input consumption, completion insertion, and when `inputHistory` changes to a different conversation/history set.
- [X] Keep image attachments out of recall; recalled history is text only. Shell commands and slash commands are recalled as their stored text (for example `!pwd` or `/plan`).
- [X] Update `SessionPage.test.tsx` Composer mock typing to accept the new optional prop.

## Public Interfaces / Types
- Frontend component interface only: `ComposerProps` gains optional `inputHistory?: string[]`.
- No FastAPI, generated API types, persisted schema, or provider/tool behavior changes.

## Test Plan
- [X] Add/extend `Composer.test.tsx` coverage for focused empty textbox + `ArrowUp` recalling the latest history item.
- [X] Test repeated `ArrowUp` moves to older inputs and stops at the oldest input.
- [X] Test `ArrowDown` moves newer and restores the pre-history draft.
- [X] Test `ArrowUp` continues to navigate completion suggestions when a completion list is open.
- [X] Test `ArrowUp` does not override normal multiline navigation when the cursor is not on the first line.
- [X] Add/extend `SessionPage.test.tsx` coverage that only main-session user messages are supplied as composer history.
- [X] Validate with `bun run test:web -- webapp/src/components/session/Composer.test.tsx webapp/src/components/session/SessionPage.test.tsx`, then `bun run typecheck` and `bun run lint`.

## Validation Notes
- Passed: `bun run test:web -- webapp/src/components/session/Composer.test.tsx webapp/src/components/session/SessionPage.test.tsx` (81 tests). React act warnings were emitted by Composer tests, but the focused suite passed.
- Passed: `bun run typecheck`.
- Passed: `bun run lint`.
- Passed: `git diff --check`.
- Review fix passed: `bun run test:web -- webapp/src/components/session/Composer.test.tsx` (32 tests; existing React act warnings emitted), `bun run lint`, and `bun run typecheck`.
- Final validation passed: `bun run test:web` (37 files, 474 tests). Existing React act warnings were emitted in Composer and TimelineEntry tests.
- Final validation passed: `bun run web:build`. Vite/Rolldown emitted existing chunk-size warnings only.

## Assumptions / Scope
- “Current conversation” means the visible main session timeline in the Session tab, not sub-agent transcripts or other sessions.
- Recall uses stored message text, so previously expanded file mentions are recalled as stored text rather than reconstructing original `@file` tokens.
- The shortcut is frontend-only and does not persist a separate input-history store.
