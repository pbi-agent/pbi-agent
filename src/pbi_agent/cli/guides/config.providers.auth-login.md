# pbi-agent config providers auth-login

Run the built-in browser (OAuth callback) or device-code login for an
account-mode provider and store the resulting session.

## Purpose
Subscription providers authenticate with an account session instead of an
API key. This command connects one: ChatGPT (`chatgpt_account`), GitHub
Copilot (`copilot_account`) or X (`xai_account`). The session is saved under
the provider ID in `~/.pbi-agent/auth.json` (or `PBI_AGENT_AUTH_STORE_PATH`),
replacing any earlier one. On success it prints
`Connected auth session for 'ID' (email).` followed by the `auth-status`
block, and exits 0. Use `auth-import` instead when you already have tokens.

## Usage
```text
pbi-agent config providers auth-login [--method {browser,device}] provider_id
```

## Options and arguments
- `provider_id` (positional): saved provider ID (slugified before lookup).
- `--method {browser,device}`: flow to run. Default: `browser` when the
  provider supports it, else `device`. Support: ChatGPT both (default
  browser), GitHub Copilot `device` only, X account `browser` only.

## Examples
```bash
# ChatGPT, browser flow
pbi-agent config providers auth-login chatgpt
# ChatGPT from a headless or remote machine
pbi-agent config providers auth-login chatgpt --method device
# GitHub Copilot (device flow is the only option)
pbi-agent config providers auth-login github-copilot --method device
```

**Browser flow:** starts a loopback listener, prints the authorization URL
and the callback URL, then tries to open your browser. ChatGPT listens on
`http://localhost:1455/auth/callback` (falls back to a free port if 1455 is
busy); X listens on `http://127.0.0.1:56121/callback` and fails if that port
is taken. It waits up to 5 minutes for the callback.

**Device flow:** prints a verification URL and a one-time `Code:`; open the
URL on any device and enter the code. It polls for up to 15 minutes.

## Workflows
1. New subscription provider: `pbi-agent config providers create --name
   "ChatGPT" --kind chatgpt`, then `auth-login chatgpt`, then
   `auth-status chatgpt`, then create a profile on it.
2. Reconnect Copilot (no refresh support): `auth-login github-copilot
   --method device` again.

## Related commands
- `pbi-agent config providers auth-status`: confirm the session afterwards.
- `pbi-agent config providers auth-import`: store tokens without a flow.
- `pbi-agent config providers auth-logout`: remove the session.

## Pitfalls
- `api_key` providers have no login flow:
  `Error: Provider 'ID' does not support built-in auth flows.` (exit 2).
- Requesting an unsupported method (for example `--method browser` for
  Copilot) raises an uncaught error with a traceback and exit 1; so do
  timeouts, a busy X callback port, and network or OAuth errors.
- The browser callback must reach the machine running pbi-agent; on a remote
  host use `--method device` where the provider supports it.
- The command blocks while waiting; it is interactive and not suited to
  unattended scripts.
