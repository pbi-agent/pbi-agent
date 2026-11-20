# pbi-agent channels telegram show

Print the stored Telegram channel settings and last recorded status for the current workspace.

## Purpose
Read-only check of the Telegram configuration: whether it is enabled, where the bot token comes from, the allowlists, and the stored runtime status. It uses the same handler as `pbi-agent channels show`, so the output is identical. It reads the session database only; it does not contact Telegram or a running web server.

## Usage
```text
pbi-agent channels telegram show [--json]
```

## Options and arguments
- `--json`: print indented JSON instead of the text summary: `{"telegram": {"enabled", "token_source", "token_env_var", "has_token_secret", "allowed_users", "allowed_chats", "last_update_id", "status": {"state", "error"}}}`.

**Text output** starts with `Channels for the current workspace:`, then a `Telegram` block with `enabled`, `status` (plus `error` when set), `token_source`, `token_env_var`, `has_token_secret`, `allowed_users`, and `allowed_chats`.

**Status values.** `disabled`, `configured` (valid, not known to be running), `error` (for example `Telegram bot token source is required.` or `Add at least one allowed Telegram user or chat/channel ID.`), `running`, `stopped`.

## Examples
```bash
# Human summary
pbi-agent channels telegram show

# Just the allowlists
pbi-agent channels telegram show --json | jq '.telegram | {allowed_users, allowed_chats}'
```

## Workflows
1. Before editing: `pbi-agent channels telegram show` to see current values, then `pbi-agent channels telegram configure` with only the fields to change (others are kept).
2. After `pbi-agent channels telegram restart`, run `pbi-agent channels telegram show` to confirm `status` is `running`.

## Related commands
- `pbi-agent channels show`: same output.
- `pbi-agent channels telegram configure`: change these settings.
- `pbi-agent channels telegram restart`: apply them to a running web UI.

## Pitfalls
- `status` is the last value stored in the database, not a live probe of the runner.
- Defaults are shown when nothing was ever configured (disabled, `env`, `PBI_AGENT_TELEGRAM_BOT_TOKEN`).
- The token value is never printed. Always exits 0.
