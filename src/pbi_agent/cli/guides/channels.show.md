# pbi-agent channels show

Print the stored channel configuration and last recorded status for the current workspace.

## Purpose
Read-only view of every channel's settings (currently only Telegram) for scripts or quick checks. It reads the per-workspace record in the session database; it does not contact Telegram or a running web server. If nothing was ever configured, it shows Telegram defaults: disabled, token source `env`, env var `PBI_AGENT_TELEGRAM_BOT_TOKEN`.

## Usage
```text
pbi-agent channels show [--json]
```

## Options and arguments
- `--json`: print indented JSON instead of the text summary. Shape: `{"telegram": {"enabled", "token_source", "token_env_var", "has_token_secret", "allowed_users", "allowed_chats", "last_update_id", "status": {"state", "error"}}}`.

**Text output.**
```text
Channels for the current workspace:
Telegram
  enabled: True
  status: configured
  token_source: env
  token_env_var: PBI_AGENT_TELEGRAM_BOT_TOKEN
  has_token_secret: False
  allowed_users: ['123456789']
  allowed_chats: []
```
An `error:` line appears after `status:` when the stored status has an error message.

## Examples
```bash
# Human summary
pbi-agent channels show

# Read the Telegram state from a script
pbi-agent channels show --json | jq -r '.telegram.status.state'
```

## Workflows
1. After `pbi-agent channels telegram configure ...`, run `pbi-agent channels show` to confirm the change and read any validation `error`.
2. With `pbi-agent web` running, check that `status` is `running`; if it is `error`, fix settings and run `pbi-agent channels telegram restart`.

## Related commands
- `pbi-agent channels telegram show`: identical output (same handler).
- `pbi-agent channels telegram configure`: change the settings shown here.

## Pitfalls
- `status` is the last value stored in the database (written by `configure`, `restart`, or the web server), not a live probe.
- Acts on the workspace of the current working directory.
- The bot token is never printed; `has_token_secret` only says whether a stored secret exists.
- Always exits 0.
