# pbi-agent channels telegram restart

Ask the local web UI serving this workspace to restart its Telegram runner, or re-validate the stored settings if no such server is running.

## Purpose
Use after `pbi-agent channels telegram configure` so a running `pbi-agent web` picks up the new settings without a full server restart. The command calls `GET http://127.0.0.1:<port>/api/bootstrap` (3 second timeout) and checks that the server's workspace matches the current workspace (case-insensitive). If it does, it sends `POST /api/channels/telegram/restart`; the server stops the runner and starts it again from the stored config. Otherwise it falls back to validating the stored settings and rewriting the stored status, without starting anything.

## Usage
```text
pbi-agent channels telegram restart [--web-port WEB_PORT] [--json]
```

## Options and arguments
- `--web-port WEB_PORT`: port of the local web UI (always `127.0.0.1`). Default `7424`, matching `pbi-agent web --port`.
- `--json`: print the resulting settings as indented JSON (`{"telegram": {...}}`) in both outcomes.

**Text output.** On success: `Restarted Telegram channel via the local web UI.` plus the Telegram block. On fallback: `No local web UI responded on http://127.0.0.1:<port>/api/channels/telegram/restart.`, `Validated stored Telegram channel settings for the current workspace.`, the Telegram block, and a hint to start or restart `pbi-agent web`.

## Examples
```bash
# Restart the runner of the web UI on the default port
pbi-agent channels telegram restart

# Web UI started with --port 8080
pbi-agent channels telegram restart --web-port 8080

# Script check of the outcome
pbi-agent channels telegram restart --json | jq -r '.telegram.status.state'
```

## Workflows
1. Apply config: `pbi-agent channels telegram configure ...`, then `pbi-agent channels telegram restart`, then confirm `status` is `running` (or read `error`).
2. Recover from a runner error (for example a fixed env var or token): fix it, then `restart`. A changed env var is not visible to an already running server; restart `pbi-agent web` itself in a shell where it is set.

## Related commands
- `pbi-agent channels telegram configure`: change the settings first.
- `pbi-agent web`: the process whose runner is restarted.

## Pitfalls
- Always exits 0, even when no web UI responded. In `--json` mode the two outcomes look alike; use `status.state` (`running` or a runner `error` after a real restart; `configured`, `disabled`, or a validation `error` after the fallback).
- A web UI serving a different workspace on that port is ignored, and the fallback runs.
- Only `127.0.0.1` is contacted; a web UI not reachable there (other host binding, other port without `--web-port`) triggers the fallback.
- Run it from the same directory that `pbi-agent web` serves.
