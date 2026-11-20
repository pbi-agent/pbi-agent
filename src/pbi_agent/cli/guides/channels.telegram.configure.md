# pbi-agent channels telegram configure

Update the stored Telegram channel settings for the current workspace.

## Purpose
Changes only the fields you pass; everything else keeps its current stored value. The new configuration is validated and saved with a status (`disabled`, `configured`, or `error`) in the session database. It does not start or restart a runner: a running `pbi-agent web` keeps its old settings until `pbi-agent channels telegram restart` or a server restart.

## Usage
```text
pbi-agent channels telegram configure [--enable] [--disable] [--token-source {env,secret}] [--token-env-var TOKEN_ENV_VAR] [--token-secret TOKEN_SECRET] [--clear-token-secret] [--allowed-users ALLOWED_USERS] [--allowed-chats ALLOWED_CHATS] [--json]
```

## Options and arguments
- `--enable`: enable the channel. Cannot be combined with `--disable` (exit 2).
- `--disable`: disable the channel; settings are kept.
- `--token-source {env,secret}`: where the bot token comes from. Default when never set: `env`. Switching source keeps the other source's stored value.
- `--token-env-var TOKEN_ENV_VAR`: env var name for the `env` source. Default `PBI_AGENT_TELEGRAM_BOT_TOKEN`; an empty value keeps the current name.
- `--token-secret TOKEN_SECRET`: store the bot token for the `secret` source. It is saved as plain text in the session database. An empty value clears it.
- `--clear-token-secret`: remove the stored token; wins over `--token-secret`.
- `--allowed-users ALLOWED_USERS`: Telegram user IDs allowed in private chats, comma- or newline-separated. Replaces the whole list; an empty string clears it.
- `--allowed-chats ALLOWED_CHATS`: group/channel chat IDs, same format and replace semantics.
- `--json`: print the resulting settings as indented JSON (`{"telegram": {...}}`) instead of the summary and restart hint.

**Validation.** When enabled, the status is `error` unless a token is available (the env var is non-empty in this CLI's environment, or a secret is stored) and at least one allowlist has an entry. Validation problems are stored and printed, but the command still exits 0.

## Examples
```bash
# Enable with the token from the default env var and allow one user
pbi-agent channels telegram configure --enable --allowed-users 123456789

# Use a custom env var name and two groups
pbi-agent channels telegram configure --token-source env --token-env-var MY_TELEGRAM_TOKEN --allowed-chats=-1001234567890,-1009876543210

# Switch back from a stored secret and wipe it
pbi-agent channels telegram configure --token-source env --clear-token-secret --json
```

## Workflows
1. Enable and apply: `pbi-agent channels telegram configure --enable --allowed-users 123456789`, then `pbi-agent channels telegram restart` (or start `pbi-agent web`).
2. Rotate the allowlist: `pbi-agent channels telegram show` to read current IDs, `configure --allowed-users ...` with the full new list, then `restart`.

## Related commands
- `pbi-agent channels telegram show`: check stored values and the validation `error`.
- `pbi-agent channels telegram restart`: apply changes to a running web UI.

## Pitfalls
- At least one setting option is required; `--json` alone exits 2 with `Error: specify at least one configuration option.`
- `--token-secret` exposes the token in shell history and process lists; prefer the `env` source.
- The env var is checked in this shell, but the runner reads it in the `pbi-agent web` process; set it there too.
- A list starting with `-` must use `=`: `--allowed-chats=-1001,-1002`.
- `--d` is ambiguous here (`--disable` vs `--doc`); spell out the option.
