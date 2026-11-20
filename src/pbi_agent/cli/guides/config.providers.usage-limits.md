# pbi-agent config providers usage-limits

Fetch and print the subscription usage limits (quota windows, remaining
share, reset times) for a ChatGPT or GitHub Copilot account provider.

## Purpose
Use it to see how much of a subscription allowance is left before a long run
or when requests start being rate-limited. Supported providers:
- kind `chatgpt` with `chatgpt_account`: queries the ChatGPT usage endpoint,
  derived from the provider's `responses_url` (default
  `https://chatgpt.com/backend-api/wham/usage`).
- kind `github_copilot` with `copilot_account`: queries
  `https://api.github.com/copilot_internal/user`.

It uses the stored session from `~/.pbi-agent/auth.json` and does not modify
it.

## Usage
```text
pbi-agent config providers usage-limits provider_id
```

## Options and arguments
- `provider_id` (positional): saved provider ID (slugified before lookup).

## Examples
```bash
# ChatGPT subscription limits
pbi-agent config providers usage-limits chatgpt
# GitHub Copilot quotas
pbi-agent config providers usage-limits github-copilot
```

Output starts with `Provider:`, optional `Account:` and `Plan:` lines and
`Fetched:` (timestamp), then a table titled `Subscription Usage Limits` with
columns `Limit`, `Window`, `Used`, `Remaining`, `Reset`, `Status` and `Notes`
(for example `unlimited`, `overage allowed`, credit balance). If the service
returns no buckets it prints `No usage limits returned.`. Exit 0 on success.

## Workflows
1. Check before a big job: `auth-status ID` shows `connected`, then
   `usage-limits ID`, then start `pbi-agent run` or the web UI.
2. Expired ChatGPT session: `auth-refresh ID` (or `auth-login ID`), then
   `usage-limits ID`.

## Related commands
- `pbi-agent config providers auth-status`: the session must be `connected`.
- `pbi-agent config providers auth-login`: connect the account first.
- `pbi-agent config providers auth-refresh`: renew an expired session.

## Pitfalls
- Exit 2 with `Error: Provider 'ID' does not have a connected subscription
  auth session.` for `api_key` providers and for missing or expired
  sessions; it does not refresh automatically.
- Exit 2 with `Error: Provider 'ID' does not support subscription usage
  limits.` for connected X (`xai_account`) providers.
- HTTP or network failures from the usage endpoint are uncaught and end with
  a traceback and exit 1.
- The table is human-oriented Rich output; there is no JSON mode.
