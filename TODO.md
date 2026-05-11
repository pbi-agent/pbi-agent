# Sidebar UX refactor

- [X] Create global `AppSessionsContextPanel` (sessions list + delete modal + handlers).
- [X] Make `AppSidebarLayout` default the sessions panel as its context slot.
- [X] Remove duplicate session-list state/JSX from `SessionPage`.
- [X] CSS polish: align sidebar typography, spacing, and section header with the rest of the nav.
- [X] Tests: add `AppSessionsContextPanel.test.tsx`. Existing suites untouched.
- [X] `bun run test:web`, `bun run lint`, `bun run typecheck`, `bun run web:build`.
