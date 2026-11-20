# pbi-agent config providers auth-refresh

Exchange the stored refresh token for a new access token and save the
updated session.

## Purpose
Use it when `auth-status` shows `Session status: expired` (or before a long
unattended run) for a ChatGPT (`chatgpt_account`) or X (`xai_account`)
provider whose session has a refresh token (`Can refresh: yes`). It contacts
the provider's OAuth token endpoint, then rewrites the session in
`~/.pbi-agent/auth.json` (or `PBI_AGENT_AUTH_STORE_PATH`). On success it
prints `Refreshed auth session for 'ID' (email).` plus the `auth-status`
block, and exits 0. Model requests also refresh automatically once after an
HTTP 401 when a refresh token is present, so this is rarely required.

## Usage
```text
pbi-agent config providers auth-refresh provider_id
```

## Options and arguments
- `provider_id` (positional): saved account-mode provider ID (slugified
  before lookup).

## Examples
```bash
# Renew a ChatGPT session
pbi-agent config providers auth-refresh chatgpt
# Renew, then show only the new expiry
pbi-agent config providers auth-refresh grok | grep "Expires at"
```

## Workflows
1. Expired session: `auth-status ID` shows `expired` and `Can refresh: yes`,
   so run `auth-refresh ID`, then `auth-status ID` shows `connected`.
2. Refresh fails (revoked token): `auth-logout ID`, then `auth-login ID`.

## Related commands
- `pbi-agent config providers auth-status`: shows `Can refresh` and expiry.
- `pbi-agent config providers auth-login`: start over when refresh fails.
- `pbi-agent config providers usage-limits`: needs a `connected` session.

## Pitfalls
- GitHub Copilot sessions cannot be refreshed; the command fails with
  `GitHub Copilot auth sessions do not support token refresh.` Re-run
  `auth-login ID --method device` instead.
- These failures are uncaught and end with a traceback and exit 1: no stored
  session (`No auth session is stored for provider 'ID'.`), a session without
  a refresh token, an `api_key` provider, and HTTP or network errors from
  the token endpoint.
- Unknown IDs print `Error: Unknown provider ID '...'.` and exit 2.
- Requires network access to the provider's auth server.
