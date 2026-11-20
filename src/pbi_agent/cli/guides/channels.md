# pbi-agent channels

Show and configure messaging channels that let chat apps talk to the agent for the current workspace. Telegram is the only channel today.

## Purpose
A channel connects an external chat (Telegram) to agent sessions in one workspace. Settings are stored per workspace (keyed by the current working directory) in the local session database (`~/.pbi-agent/sessions.db`, or `PBI_AGENT_SESSION_DB_PATH`), the same settings the web UI edits under **Settings > Channels**. These commands only read and write that stored configuration. The channel runner itself (polling Telegram and running turns) lives inside `pbi-agent web` for the workspace; nothing polls Telegram while only the CLI is running.

## Usage
```text
pbi-agent channels <action> ...
```

## Subcommands
- `pbi-agent channels show`: print the stored configuration and last recorded status of every channel. Guide: `pbi-agent channels show --doc`.
- `pbi-agent channels telegram`: show, configure, or restart the Telegram channel. Guide: `pbi-agent channels telegram --doc`.

An action is required: `pbi-agent channels` with no subcommand prints an argparse usage error and exits 2.

## Options and arguments
No options besides `-h/--help` and `--doc`.

**Status states.** Each channel carries a stored `status.state`: `disabled` (not enabled), `configured` (enabled and valid, but not running in this view), `error` (see `status.error`), `running` (a web server runner is polling), or `stopped`. The CLI shows the last state written to the database; it does not probe a live runner.

## Examples
```bash
# Summary of all channels for this workspace
pbi-agent channels show

# Same data as JSON for scripts
pbi-agent channels show --json

# Enable Telegram using the default token env var and one allowed user
pbi-agent channels telegram configure --enable --allowed-users 123456789
```

## Workflows
1. First-time Telegram setup: export `PBI_AGENT_TELEGRAM_BOT_TOKEN` in the shell that will run the web server, run `pbi-agent channels telegram configure --enable --allowed-users 123456789`, then start `pbi-agent web` from the same workspace.
2. Change settings while the web UI is running: `pbi-agent channels telegram configure ...`, then `pbi-agent channels telegram restart` so the running server reloads them.
3. Diagnose: `pbi-agent channels show --json` and read `telegram.status.state` and `telegram.status.error`.

## Related commands
- `pbi-agent web`: hosts the channel runner; it starts enabled channels on startup.
- `pbi-agent sessions`: channel conversations are ordinary sessions and can be listed there.

## Pitfalls
- Settings are per workspace: run these commands from the same directory you serve with `pbi-agent web`.
- Configuration changes do not affect a running web server until `pbi-agent channels telegram restart` (or a web UI restart).
- Output never prints a stored bot token; it only reports `has_token_secret`.
