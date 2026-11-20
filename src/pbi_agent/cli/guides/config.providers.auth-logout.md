# pbi-agent config providers auth-logout

Delete the locally stored account session for a provider.

## Purpose
Use it to disconnect a subscription provider (ChatGPT, GitHub Copilot, X
account) on this machine, to clear a broken or revoked session before
logging in again, or to clean up before deleting a provider. It removes the
provider's entry from `~/.pbi-agent/auth.json` (or
`PBI_AGENT_AUTH_STORE_PATH`). The saved provider itself stays in the config,
and nothing is revoked on the provider's side.

## Usage
```text
pbi-agent config providers auth-logout provider_id
```

## Options and arguments
- `provider_id` (positional): saved provider ID (slugified before lookup).

## Examples
```bash
# Remove the ChatGPT session
pbi-agent config providers auth-logout chatgpt
# Log out, then reconnect GitHub Copilot
pbi-agent config providers auth-logout github-copilot && pbi-agent config providers auth-login github-copilot --method device
```

Output is `Deleted auth session for 'ID'.` or, when nothing was stored,
`No stored auth session for 'ID'.`, followed by the `auth-status` block
(which now shows `Session status: missing`). Both cases exit 0.

## Workflows
1. Reset a bad session: `auth-logout ID`, then `auth-login ID`, then
   `auth-status ID`.
2. Retire an account provider: `auth-logout ID`, remove or repoint its
   profiles, then `pbi-agent config providers delete ID`.

## Related commands
- `pbi-agent config providers auth-login`: create a new session.
- `pbi-agent config providers delete`: remove the provider; it does not
  delete the session, so log out first.
- `pbi-agent config providers auth-status`: confirm the session is gone.

## Pitfalls
- Runs after logout that use this provider fail with
  `Missing authentication for provider '...'` until you log in again.
- Works for any provider ID, including `api_key` providers, and leaves their
  API key or env var setting untouched.
- Unknown IDs print `Error: Unknown provider ID '...'.` and exit 2.
- The token stays valid at the provider until it expires or is revoked
  there; logout only forgets it locally.
