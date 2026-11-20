# pbi-agent config providers create

Save a new provider (backend kind, auth mode, credentials source and endpoint
overrides) to `~/.pbi-agent/config.json`.

## Purpose
Create a provider once, then build model profiles on it with
`pbi-agent config profiles create --provider-id ID`. Kinds `deepgram` and
`elevenlabs` are speech-to-text only and cannot back a model profile. On
success it prints `Created provider 'ID'.` and exits 0.

## Usage
```text
pbi-agent config providers create --name NAME [--id ID] --kind KIND [--auth-mode MODE] [--api-key KEY] [--api-key-env VAR] [--responses-url URL] [--generic-api-url URL] [--google-cloud-project PROJECT] [--google-cloud-location LOCATION]
```

## Options and arguments
- `--name NAME` (required): display name; must not be blank.
- `--id ID`: stable provider ID, slugified (lowercase, non-alphanumerics become
  `-`). Default: the slug of `--name`, so `OpenAI Main` gives `openai-main`.
- `--kind KIND` (required): one of `openai`, `azure`, `chatgpt`,
  `github_copilot`, `xai`, `google`, `google_gcp`, `anthropic`, `generic`,
  `deepgram`, `elevenlabs`.
- `--auth-mode MODE`: `api_key`, `chatgpt_account`, `copilot_account` or
  `xai_account`. Default: `chatgpt_account` for `chatgpt`, `copilot_account`
  for `github_copilot`, else `api_key`. Only `xai` accepts two modes
  (`api_key` or `xai_account`).
- `--api-key KEY`: key stored in plaintext in the config file.
- `--api-key-env VAR`: name of an environment variable read at run time
  instead of storing the key. Preferred over `--api-key`. Both are discarded
  when the auth mode is not `api_key`.
- `--responses-url URL`: endpoint override for the OpenAI, ChatGPT, Copilot,
  Azure, xAI, Google and Google Cloud backends. Default: the kind's built-in
  endpoint. Azure has no default and needs it before the provider can run.
- `--generic-api-url URL`: OpenAI-compatible Chat Completions endpoint for
  kind `generic`. Default: `https://openrouter.ai/api/v1/chat/completions`.
- `--google-cloud-project PROJECT`: Vertex AI project for kind `google_gcp`.
- `--google-cloud-location, --google-cloud-region LOCATION`: Vertex AI
  location for kind `google_gcp`; `global` is used when unset everywhere.
  Both Google Cloud fields are dropped for other kinds.

## Examples
```bash
# OpenAI API key read from the environment
pbi-agent config providers create --name "OpenAI Main" --kind openai --api-key-env OPENAI_API_KEY
# Azure needs its resource endpoint
pbi-agent config providers create --name "Azure" --kind azure --api-key-env AZURE_API_KEY --responses-url https://my-resource.openai.azure.com/openai/v1/responses
# Vertex AI with Application Default Credentials
pbi-agent config providers create --name "Vertex AI" --kind google_gcp --google-cloud-project my-project --google-cloud-location global
# X account instead of an xAI API key
pbi-agent config providers create --name "Grok" --kind xai --auth-mode xai_account
```

## Workflows
1. `create`, then `pbi-agent config providers list` to confirm the ID, then
   `pbi-agent config profiles create --name main --provider-id ID --model M`.
2. Account auth: `create --kind chatgpt`, then `auth-login ID`, then
   `auth-status ID` to confirm `Session status: connected`.

## Related commands
- `pbi-agent config providers update`: change a provider after creation.
- `pbi-agent config providers auth-login`: connect an account-mode provider.
- `pbi-agent config profiles create`: attach a model to the new provider.

## Pitfalls
- Exit 2 with `Error: Provider 'ID' already exists.` if the slug is taken.
- Exit 2 with `Error: Provider auth_mode must be one of: ...` when the mode does
  not fit the kind (for example `--kind openai --auth-mode chatgpt_account`).
- Nothing is checked against the provider: a missing env var or wrong URL
  only fails when a run uses it.
