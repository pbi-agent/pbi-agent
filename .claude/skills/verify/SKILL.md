---
name: verify
description: Run the pbi-agent web UI locally and drive a live session to verify web/frontend or CLI changes.
---

# Verify pbi-agent web changes

## CLI-only changes
- No server needed. Run the changed command: `uv run pbi-agent <command> ...`. Check `--help`, `--doc`, output and exit code.
- State-writing commands use `~/.pbi-agent/sessions.db`. Set `PBI_AGENT_SESSION_DB_PATH` to a scratch file to keep real DB clean.

## Launch
- Run `bun run web:build` first. Server serves built bundle from `src/pbi_agent/web/static/app`.
- `.claude/launch.json` has `pbi-agent-web` → `uv run pbi-agent web --port 7431` (isolated from default 7424). Start via browser pane's `preview_start` if available.
- No browser pane: start in background with Bash, `uv run pbi-agent web --port 7431 --no-open`. Probe with `curl http://127.0.0.1:7431/api/bootstrap`.
- Explicit `--port` is used as given, even if busy. Only default 7424 falls back to a free port, reported on stderr.
- `--no-open` (hidden flag) or `BROWSER=true` suppresses browser opening.
- Profiles come from `~/.pbi-agent/config.json`. Web UI uses `web.active_profile_id`; it changes, so check it. Live turns cost real tokens; keep prompts tiny.
- `POST /api/sessions` creates session without live turn (no tokens), but writes row to session DB.

## Gotchas
- Only one web instance may manage the workspace ("another web app instance is already managing this workspace"). Lease lives in session DB, keyed by cwd.
- If user's own server (often 7424, `python main.py`) holds lease, ask them to stop or restart it; never kill it yourself.
- To run alongside it: start from scratch dir (`uv run --project <repo> pbi-agent web`), or set `PBI_AGENT_SESSION_DB_PATH` to scratch DB. Scratch DB also keeps test sessions out of real DB.
- Check server start time vs. your edits — server started before change runs old code.
- User can see and click in same pane; unexpected submissions may be theirs. Ask before assuming bug.
- `ref`-based clicks work. Screenshots are scaled from 1024px viewport; if one looks stale, read state via `javascript_tool`.
