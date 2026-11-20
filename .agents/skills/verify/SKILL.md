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

## Scratch server (reproduce or verify UI on real or fixture sessions)
Use it for factory triage (reproduce on base), build (verify the change) and the verify stage. Scratch dir `S` = session scratchpad.
1. Consistent DB copy; never touch the original. Clear the lease in the copy only:
   `python3 -c "import sqlite3,sys; s=sqlite3.connect(f'file:{sys.argv[1]}?mode=ro',uri=True); d=sqlite3.connect(sys.argv[2]); s.backup(d); d.execute('DELETE FROM web_manager_leases'); d.commit()" ~/.pbi-agent/sessions.db "$S/sessions.db"`
2. Fixture workspace `$S/ws` with the content under test, e.g. markdown surfaces: `wide.md` (wide + small table), `TODO.md` (todo panel), `.agents/skills/<name>/SKILL.md` (settings preview). To open a real session against it, in the COPY only: `UPDATE sessions SET directory=lower('<abs $S/ws>') WHERE session_id=?`.
3. Run `bun run web:build` first. Start from the fixture workspace on a free non-default port (74xx), record the PID:
   `PBI_AGENT_SESSION_DB_PATH="$S/sessions.db" BROWSER=true nohup uv run --directory "$S/ws" --project <repo> pbi-agent web --port <p> --no-open > "$S/web.log" 2>&1 & echo $! > "$S/web.pid"` (`--directory` sets server cwd; `$!` is `uv`)
   Probe `curl -fsS http://127.0.0.1:<p>/api/bootstrap`.
4. Measure with `javascript_tool`, recording `clientWidth`/`scrollWidth` of the element under test, its scroll ancestors and `document.documentElement`. Containment check: set `scrollLeft` on the inner scroller; ancestors keep `scrollLeft` 0 and sibling x positions do not change.
5. Narrow width: resizing the window does not change `innerWidth` here; load the page in a same-origin `<iframe style="width:800px">` and measure inside it.
6. Theme: `localStorage.setItem('pbi-agent-theme','light'|'dark')` on the scratch origin, reload; reset to `system` after.
7. Stop: `kill "$(cat "$S/web.pid")"` (uv forwards SIGTERM to the server) or `fuser -k <p>/tcp`. Confirm `! fuser <p>/tcp` and that `pgrep -af '[p]bi-agent web --port <p>'` prints nothing (run this check in a separate command from the start line, or `pgrep` matches your own shell). Close browser tabs you opened. Record port, fixtures and numbers in the stage file.

## Gotchas
- `$!` after `cd X && nohup ... &` is the subshell, not the server; killing it leaves `uv` and the server running. Use `uv run --directory X` instead of `cd X &&`.
- Never `pkill -f <pattern>` with a pattern that also appears in the same command line: it matches the invoking `bash -c` and kills your own shell (exit 144). Stop by PID file or port; if a pattern is unavoidable, use `pkill -f '[p]bi-agent web --port <p>'`.
- Only one web instance may manage the workspace ("another web app instance is already managing this workspace"). Lease lives in session DB, keyed by cwd.
- If user's own server (often 7424, `python main.py`) holds lease, ask them to stop or restart it; never kill it yourself.
- To run alongside it: start from scratch dir (`uv run --project <repo> pbi-agent web`), or set `PBI_AGENT_SESSION_DB_PATH` to scratch DB. Scratch DB also keeps test sessions out of real DB.
- Check server start time vs. your edits — server started before change runs old code.
- User can see and click in same pane; unexpected submissions may be theirs. Ask before assuming bug.
- `ref`-based clicks work. Screenshots are scaled from 1024px viewport; if one looks stale, read state via `javascript_tool`.
