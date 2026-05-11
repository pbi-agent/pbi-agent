# Sidebar/topbar header bottom-border alignment

- [X] Lock `.app-sidebar__head` to `block-size: var(--topbar-height)` with `padding-block: 0`, keep grid.
- [X] Lock `.session-topbar` to `block-size: var(--topbar-height)` with `padding-block: 0`, keep flex.
- [X] Keep `min-block-size` as a safety net on both so a flex shell can't collapse them under content.
- [X] Update responsive `@media (max-width: 768px)` rule to use `block-size: auto; min-block-size: 0` so the stacked mobile topbar still expands.
- [X] `bun run lint`, `bun run typecheck`, `bun run test:web`, `bun run web:build`.
