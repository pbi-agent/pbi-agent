# TODO

[X] Audit existing sidebar/nav design (AppSidebar, SessionSidebar, AppShell, layout/session CSS)
[X] Add unified collapsible sidebar store + Cmd/Ctrl+B shortcut hook (`webapp/src/hooks/useSidebar.ts`)
[X] Refactor AppSidebar into single component: brand + toggle, workspace badge, primary nav, context-panel slot, footer (theme + settings)
[X] Drop the standalone top header; move workspace badge & theme into the sidebar
[X] Reduce SessionSidebar to a session-list context panel (no own nav/footer/toggle/collapse mode)
[X] Wrap SessionPage in AppSidebarLayout with session list as the context panel; remove its own .session-layout sidebar grid
[X] Refactor layout.css + session.css for the unified shell + collapsed strip
[X] Update AppShell.test.tsx + SessionSidebar.test.tsx and add coverage for Cmd/Ctrl+B shortcut + head toggle (`webapp/src/hooks/useSidebar.test.tsx`)
[X] Run `bun run test:web` (365 passed), `bun run lint`, `bun run typecheck`, `bun run web:build`
