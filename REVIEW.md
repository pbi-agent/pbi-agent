# Review Findings

- [X] [P1] `webapp/src/components/session/Composer.tsx:532` — Fixed cold/stale `@` file suggestion polling while `scan_status === "scanning"`, including empty cold scans. Polling now re-queries the same active mention until `ready`/`failed`, keeps request-id/query/mode stale guards, and Escape dismissal invalidates pending retries. Validation: `bun run test:web -- webapp/src/components/session/Composer.test.tsx`, `bun run lint`, and `bun run typecheck` passed.
