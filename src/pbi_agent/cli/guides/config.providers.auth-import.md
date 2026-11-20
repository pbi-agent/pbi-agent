# pbi-agent config providers auth-import

Store an account session from tokens you already have, without running a
login flow.

## Purpose
Use it when the built-in `auth-login` flow cannot run (no browser, blocked
callback port, automation) but you hold valid OAuth tokens for a
`chatgpt_account`, `copilot_account` or `xai_account` provider. The session
is saved under the provider ID in `~/.pbi-agent/auth.json` (or
`PBI_AGENT_AUTH_STORE_PATH`). On success it prints
`Imported auth session for 'ID' (email).` plus the `auth-status` block, and
exits 0. Nothing is sent to the provider; tokens are not verified.

## Usage
```text
pbi-agent config providers auth-import --access-token TOKEN [--refresh-token TOKEN] [--account-id ID] [--email EMAIL] [--plan-type PLAN] [--expires-at EPOCH] [--id-token TOKEN] provider_id
```

## Options and arguments
- `provider_id` (positional): saved account-mode provider ID.
- `--access-token TOKEN` (required): bearer access token; must not be blank.
- `--refresh-token TOKEN`: enables `auth-refresh` (ChatGPT, X). When omitted,
  the refresh token of the session being replaced is kept. Ignored for Copilot.
- `--account-id ID`: account identifier. ChatGPT requires it unless the
  access or ID token carries a `chatgpt_account_id` claim; X defaults it to
  the token `sub` claim.
- `--email EMAIL`: account email; ChatGPT and X fall back to the token claims.
- `--plan-type PLAN`: plan label; ChatGPT falls back to the token claim,
  Copilot defaults to `github_copilot`.
- `--expires-at EPOCH`: expiry as integer Unix seconds. Default: the access
  token's `exp` claim (ChatGPT, X). Ignored for Copilot.
- `--id-token TOKEN`: OpenID ID token whose claims fill in missing fields
  (ChatGPT, X). Ignored for Copilot.

## Examples
```bash
# ChatGPT session from tokens kept in environment variables
pbi-agent config providers auth-import chatgpt --access-token "$CHATGPT_ACCESS_TOKEN" --refresh-token "$CHATGPT_REFRESH_TOKEN" --account-id acct-example
# GitHub Copilot OAuth token
pbi-agent config providers auth-import github-copilot --access-token "$COPILOT_TOKEN" --email me@example.com
```

## Workflows
1. Move a session to another machine: on the target, `create` the provider
   with the same kind and auth mode, then `auth-import ID --access-token ...
   --refresh-token ...`, then `auth-status ID`.
2. Import then renew: `auth-import ID ... --refresh-token ...`, then
   `auth-refresh ID` to obtain a fresh access token.

## Related commands
- `pbi-agent config providers auth-login`: the interactive alternative.
- `pbi-agent config providers auth-status`: check what was stored.
- `pbi-agent config providers auth-logout`: remove an imported session.

## Pitfalls
- `api_key` providers cannot import sessions; the command raises an uncaught
  error (`does not support auth mode 'api_key'`) with a traceback, exit 1.
  A ChatGPT import without a resolvable account ID fails the same way.
- Passing `--expires-at` in the past stores the session as `expired`.
- Tokens passed on the command line land in shell history and process
  listings; prefer expanding them from environment variables.
