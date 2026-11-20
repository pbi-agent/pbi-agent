# pbi-agent config providers

Manage saved providers: named connection settings (backend kind, auth mode,
API key or env var, endpoint overrides) stored in `~/.pbi-agent/config.json`.

## Purpose
A saved provider says how to reach one model or speech-to-text backend. It
holds no model choice; model profiles (`pbi-agent config profiles`) point at a
provider by ID and add the model and runtime settings. Use these commands to
create, inspect, change and delete providers, and to manage the local account
sessions used by subscription providers (ChatGPT, GitHub Copilot, X account).

Each provider has an `auth_mode`:
- `api_key`: a key stored in the config (`--api-key`) or read at run time from
  an environment variable (`--api-key-env`). Valid for every kind.
- `chatgpt_account`: only for kind `chatgpt` (browser or device login).
- `copilot_account`: only for kind `github_copilot` (device login only).
- `xai_account`: optional for kind `xai` (browser login), instead of an API key.

Account sessions are stored per provider ID in `~/.pbi-agent/auth.json`
(override with `PBI_AGENT_AUTH_STORE_PATH`). The config file path can be
overridden with `PBI_AGENT_INTERNAL_CONFIG_PATH`.

## Usage
```text
pbi-agent config providers <action> ...
```

## Subcommands
- `pbi-agent config providers list`: table of saved providers. Guide: `pbi-agent config providers list --doc`.
- `pbi-agent config providers create`: add a provider. Guide: `pbi-agent config providers create --doc`.
- `pbi-agent config providers update`: change fields of a provider. Guide: `pbi-agent config providers update --doc`.
- `pbi-agent config providers delete`: remove an unused provider. Guide: `pbi-agent config providers delete --doc`.
- `pbi-agent config providers auth-status`: show the stored session state. Guide: `pbi-agent config providers auth-status --doc`.
- `pbi-agent config providers auth-login`: run the browser or device login flow. Guide: `pbi-agent config providers auth-login --doc`.
- `pbi-agent config providers auth-import`: store tokens obtained elsewhere. Guide: `pbi-agent config providers auth-import --doc`.
- `pbi-agent config providers auth-refresh`: refresh a stored session now. Guide: `pbi-agent config providers auth-refresh --doc`.
- `pbi-agent config providers auth-logout`: delete the stored session. Guide: `pbi-agent config providers auth-logout --doc`.
- `pbi-agent config providers usage-limits`: show ChatGPT or Copilot subscription limits. Guide: `pbi-agent config providers usage-limits --doc`.

An action is required: `pbi-agent config providers` alone prints a usage error
(`the following arguments are required: <action>`) and exits 2.

## Options and arguments
No options besides `-h/--help` and `--doc`.

## Examples
```bash
# API-key provider that reads its key from the environment
pbi-agent config providers create --name "OpenAI Main" --kind openai --api-key-env OPENAI_API_KEY
# Subscription provider, then log in
pbi-agent config providers create --name "ChatGPT" --kind chatgpt
pbi-agent config providers auth-login chatgpt
pbi-agent config providers list
```

## Workflows
1. API-key setup: `pbi-agent config providers create --name "OpenAI Main"
   --kind openai --api-key-env OPENAI_API_KEY`, then
   `pbi-agent config profiles create --name analysis --provider-id openai-main
   --model gpt-5.4`, then `pbi-agent config profiles select analysis`.
2. Subscription setup: `create --kind chatgpt` (or `github_copilot`), then
   `auth-login ID`, check with `auth-status ID`, then create a profile on it.
3. Retire a provider: `pbi-agent config profiles delete` (or update) every
   profile that uses it, then `pbi-agent config providers delete ID`.

## Related commands
- `pbi-agent config profiles`: model profiles that reference provider IDs.
- `pbi-agent config`: parent of all saved-settings commands.
- `pbi-agent web`: its Settings page edits the same saved providers.

## Pitfalls
- Validation and lookup failures (unknown ID, duplicate ID, invalid auth mode
  for the kind, provider still referenced) print `Error: ...` to stderr and
  exit 2. Some auth backend failures (no stored session, refresh unsupported,
  bad import payload, network errors) are not caught and end with a Python
  traceback and exit 1.
- Provider IDs are slugs: `OpenAI Main` becomes `openai-main`. Commands taking
  `provider_id` slugify the argument, so either spelling works.
- `run` resolves keys with higher-priority sources first (`--api-key`,
  `PBI_AGENT_API_KEY`, the kind's default env var such as `OPENAI_API_KEY`)
  before the saved provider's `api_key_env` and `api_key`.
