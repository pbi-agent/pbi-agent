# pbi-agent config providers auth-status

Print the stored account-session state for one saved provider.

## Purpose
Use it after `auth-login`, `auth-import` or `auth-refresh` to confirm a
subscription provider (`chatgpt_account`, `copilot_account`, `xai_account`)
is connected, see which account and plan it belongs to, and whether it can
refresh. It reads `~/.pbi-agent/auth.json` (or `PBI_AGENT_AUTH_STORE_PATH`)
only and makes no network calls. For `api_key` providers it has nothing
useful to report; use `pbi-agent config providers list` instead.

## Usage
```text
pbi-agent config providers auth-status provider_id
```

## Options and arguments
- `provider_id` (positional): saved provider ID (slugified before lookup).

## Examples
```bash
# Check a ChatGPT subscription provider
pbi-agent config providers auth-status chatgpt
# Only the session line
pbi-agent config providers auth-status github-copilot | grep "Session status"
```

Output is plain `Key: value` lines: `Provider`, `Kind`, `Auth mode`,
`Session status` (`connected`, `expired` or `missing`), `Backend`
(`openai_chatgpt`, `github_copilot`, `xai_account`, or `n/a` for API keys),
`Can refresh` (`yes`/`no`), then `Email`, `Account ID`, `Plan` and
`Expires at` (Unix seconds) when known.

## Workflows
1. Verify a login: `auth-login ID`, then `auth-status ID` and look for
   `Session status: connected`.
2. Recover an expired session: if `Session status: expired` and
   `Can refresh: yes`, run `auth-refresh ID`; otherwise run `auth-login ID`.

## Related commands
- `pbi-agent config providers auth-login`: create a session when it is missing.
- `pbi-agent config providers auth-refresh`: renew an expired session.
- `pbi-agent config providers list`: auth status of all providers at once.

## Pitfalls
- `api_key` providers always show `Session status: missing` and
  `Backend: n/a`, even when a key is configured; that is not an error.
- `expired` is computed from the stored expiry time only. GitHub Copilot
  sessions have no expiry and always show `connected` while stored, even if
  GitHub has revoked the token.
- Unknown IDs print `Error: Unknown provider ID '...'.` and exit 2.
