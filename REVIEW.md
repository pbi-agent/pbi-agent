# Review Findings

- [X] [P2] webapp/src/components/session/Composer.tsx:625 — Reset history browsing when `inputHistory` changes. While a user is browsing recalled history, switching conversations or receiving a different history set only makes `activeHistoryIndex` evaluate to `null`; it leaves the old recalled text in the textarea and prevents ArrowDown from restoring the saved draft. Add an effect keyed on the history signature (or equivalent conversation/history identity) that clears history-browsing state and avoids carrying recalled text/draft state across histories.
  - Fixed: `Composer` now detects `inputHistory` signature changes, restores the saved draft when browsing history, clears history state, and updates the active signature.
  - Validation: `bun run test:web -- webapp/src/components/session/Composer.test.tsx` passed (32 tests; existing React act warnings emitted), `bun run lint` passed, and `bun run typecheck` passed.
