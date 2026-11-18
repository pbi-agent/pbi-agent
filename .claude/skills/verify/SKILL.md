---
name: verify
description: Run the pbi-agent web UI locally and drive a live session to verify web/frontend changes.
---

# Verify pbi-agent web changes

## Launch
- `bun run web:build` first (the server serves the built bundle from `src/pbi_agent/web/static/app`).
- `.claude/launch.json` has `pbi-agent-web` → `uv run pbi-agent web --port 7431` (isolated from the default 7424). Start via the browser pane's `preview_start`.
- Uses saved profiles in `~/.pbi-agent/config.json` (active web profile `worker`, GitHub Copilot). Live turns cost real tokens; keep prompts tiny.

## Gotchas
- Only one web instance may manage the workspace ("another web app instance is already managing this workspace"). If the user's own server (often 7424, `python main.py`) is up, ask them to stop or restart it; never kill it yourself. Check its start time vs. your edits — a server started before the change runs old code.
- The user can see and click in the same pane; unexpected submissions may be theirs. Ask before assuming a bug.
- `ref`-based clicks work; screenshots are scaled from a 1024px viewport, so read state via `javascript_tool` when a screenshot looks stale.
