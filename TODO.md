# TODO

- [X] Replace bottom processing indicator with phase-colored WorkRun header
  - [X] SessionTimeline: drop bottom `processing-indicator`, derive `activePhase`, append synthetic work_run when needed
  - [X] WorkRun: add `phase` prop, set `data-phase`, skip CollapsibleContent when items empty
  - [X] session.css: remove `.processing-indicator*` rules, add `data-phase` color variants on work-run header
  - [X] Update tests in SessionTimeline.test.tsx (5 new passing tests, 0 regressions)
- [X] Run validation: `bun run typecheck` ✓, `bun run web:build` ✓, focused `test:web SessionTimeline` (22 passed, 1 pre-existing welcome failure)
