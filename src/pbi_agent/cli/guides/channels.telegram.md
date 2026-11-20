# pbi-agent channels telegram

Show, configure, and restart the Telegram channel for the current workspace.

## Purpose
The Telegram channel lets allowed Telegram users, groups, or channels chat with the agent in this workspace through a bot. Settings are stored per workspace in the session database; the bot is polled only by a running `pbi-agent web` for the same workspace, which starts the runner when the channel is enabled and valid. Each Telegram source (a private chat, a group, a group topic, or a channel) maps to its own agent session; sending `/new` starts a fresh session for that source. Text, captions, and images are accepted; messages from bots and from sources not on the allowlist are ignored.

## Usage
```text
pbi-agent channels telegram <action> ...
```

## Subcommands
- `pbi-agent channels telegram show`: print stored Telegram settings and status (same output as `pbi-agent channels show`). Guide: `pbi-agent channels telegram show --doc`.
- `pbi-agent channels telegram configure`: update enable state, token source, and allowlists. Guide: `pbi-agent channels telegram configure --doc`.
- `pbi-agent channels telegram restart`: ask a running local web UI to restart the runner, or just re-validate stored settings. Guide: `pbi-agent channels telegram restart --doc`.

An action is required: `pbi-agent channels telegram` with no subcommand prints an argparse usage error and exits 2.

## Options and arguments
No options besides `-h/--help` and `--doc`.

**Bot token.** Token source `env` (default) reads the token from an environment variable, `PBI_AGENT_TELEGRAM_BOT_TOKEN` unless changed with `pbi-agent channels telegram configure --token-env-var`. Token source `secret` uses a token stored with `pbi-agent channels telegram configure --token-secret`, kept as plain text in the channel record of the session database.

**Allowlist.** Private chats are accepted only when the sender's user ID is in `allowed_users`; groups and channels only when the chat ID is in `allowed_chats`. An enabled channel needs at least one entry in either list.

## Examples
```bash
# Inspect current settings
pbi-agent channels telegram show

# Enable with the default env var token and allow one user and one group
pbi-agent channels telegram configure --enable --allowed-users 123456789 --allowed-chats -1001234567890

# Apply changes to the running web UI on the default port
pbi-agent channels telegram restart
```

## Workflows
1. Setup: create a bot with BotFather, `export PBI_AGENT_TELEGRAM_BOT_TOKEN=...` in the shell that will run the server, `pbi-agent channels telegram configure --enable --allowed-users 123456789`, then `pbi-agent web` from the same workspace.
2. Update while running: `pbi-agent channels telegram configure --allowed-chats ...`, then `pbi-agent channels telegram restart`, then `pbi-agent channels telegram show` to check `status`.
3. Turn off: `pbi-agent channels telegram configure --disable`, then `pbi-agent channels telegram restart`.

## Related commands
- `pbi-agent channels show`: same view, for all channels.
- `pbi-agent web`: hosts the Telegram runner; also editable under **Settings > Channels**.

## Pitfalls
- The env var must be set in the environment of the `pbi-agent web` process. `configure` validates against the CLI's own environment, so the stored status can differ from what the server sees.
- Within one web server, a bot token can be active in only one workspace; a second one gets status `error` ("This Telegram bot token is already active in another workspace.").
- Group and channel IDs are usually negative. A single one works as `--allowed-chats -1001234567890`, but a list starting with `-` (`-1001,-1002`) is rejected as a missing argument (exit 2); write `--allowed-chats=-1001,-1002`.
