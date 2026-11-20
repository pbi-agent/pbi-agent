# pbi-agent sessions

List saved agent sessions, newest first, for the current directory or for all directories.

## Purpose
Use it to find a session ID to resume with `pbi-agent run --session-id ID`, or to
review token usage and cost of past runs. Sessions are read from the local SQLite
store `~/.pbi-agent/sessions.db` (override with `PBI_AGENT_SESSION_DB_PATH`). It does
not need provider settings or an API key.

Output is a fixed-width table with columns `ID`, `Provider`, `Model`, `Title`
(truncated to 24 characters), `Tokens`, `Cost` (USD), and `Updated` (UTC timestamp),
sorted by last update. `-` marks zero tokens or cost.

## Usage
```text
pbi-agent sessions [--limit LIMIT] [--all-dirs]
```

## Options and arguments
- `--limit LIMIT`: maximum number of sessions to show (integer, default `20`).
- `--all-dirs`: list sessions from every workspace directory instead of only the
  current one.

## Examples
```bash
# Last 20 sessions for this workspace
pbi-agent sessions
# Last 5 sessions across all workspaces
pbi-agent sessions --all-dirs --limit 5
# Resume a session by ID from the listing
pbi-agent run --session-id 3f2c9a1b7d4e4f0a9b8c7d6e5f4a3b2c -p "Continue where we left off"
```

## Workflows
1. Resume work: run `pbi-agent sessions`, copy an `ID`, then
   `pbi-agent run --session-id ID -p "..."` (add `--include-tool-history` to replay
   prior tool calls).
2. Audit spend: run `pbi-agent sessions --all-dirs --limit 100` and read the `Tokens`
   and `Cost` columns.

## Related commands
- `pbi-agent run`: start or resume (`--session-id`) a session.
- `pbi-agent web`: browse and continue sessions in the browser UI.

## Pitfalls
- Without `--all-dirs`, only sessions whose stored directory matches the current
  working directory (case-insensitive absolute path, or `PBI_AGENT_WORKSPACE_KEY` when
  set) are listed. Run it from the workspace root you used before.
- Prints `No sessions found.` and exits 0 when nothing matches.
- Exits 1 with `Error: unable to open session store: ...` if the database cannot be opened.
- Old sessions may be purged by daily maintenance based on the configured retention.
