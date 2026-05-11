# Reduce topbar header height & keep sidebar/topbar aligned

- [X] Drop `--topbar-height` from `56px` to `48px` in `webapp/src/styles/tokens.css`.
- [X] Drop `--sidebar-width-collapsed` to `48px` so the collapsed sidebar head stays a square that matches the topbar height.
- [X] Verify 40 px toggle + 32 px controls + 28 px workspace badge still center inside the 48 px head.
- [X] `bun run lint`, `bun run typecheck`, `bun run test:web`, `bun run web:build`.
