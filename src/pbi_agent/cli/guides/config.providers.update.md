# pbi-agent config providers update

Change selected fields of a saved provider; every option left out keeps its
current value.

## Purpose
Use it to rotate credentials, switch between a stored key and an env var,
change endpoints, or move a provider to another kind or auth mode without
re-creating it (which would break the profiles that reference its ID). On
success it prints `Updated provider 'ID'.` and exits 0.

## Usage
```text
pbi-agent config providers update [--name NAME] [--kind KIND] [--auth-mode MODE] [--api-key KEY] [--api-key-env VAR] [--responses-url URL] [--generic-api-url URL] [--google-cloud-project PROJECT] [--google-cloud-location LOCATION] provider_id
```

## Options and arguments
- `provider_id` (positional): ID of the provider to change; slugified before
  lookup. The ID itself cannot be changed.
- `--name NAME`: new display name (the ID stays the same).
- `--kind KIND`: new backend kind; same choices as `create`.
- `--auth-mode MODE`: `api_key`, `chatgpt_account`, `copilot_account` or
  `xai_account`; must be valid for the resulting kind.
- `--api-key KEY`: replace the stored plaintext key; `--api-key ""` clears it.
- `--api-key-env VAR`: environment variable to read the key from at run
  time; `--api-key-env ""` clears it.
- `--responses-url URL`: endpoint override; `""` falls back to the kind's
  default endpoint.
- `--generic-api-url URL`: endpoint for kind `generic`; `""` falls back to
  the default.
- `--google-cloud-project PROJECT`: Vertex AI project (kind `google_gcp`).
- `--google-cloud-location, --google-cloud-region LOCATION`: Vertex AI
  location (kind `google_gcp`).

## Examples
```bash
# Stop storing a key in plaintext and read it from the environment
pbi-agent config providers update openai-main --api-key "" --api-key-env OPENAI_API_KEY
# Point a provider at another endpoint
pbi-agent config providers update azure --responses-url https://other-resource.openai.azure.com/openai/v1/responses
# Switch an xAI provider from API key to X account login
pbi-agent config providers update grok --auth-mode xai_account
```

## Workflows
1. Rotate a key: export the new value in the variable named by
   `api_key_env`, or `update ID --api-key NEW`; confirm with
   `pbi-agent config providers list`.
2. Change auth mode: `update grok --auth-mode xai_account`, then
   `auth-login grok`, then `auth-status grok`.

## Related commands
- `pbi-agent config providers list`: see current values before editing.
- `pbi-agent config providers create`: the full option reference.
- `pbi-agent config profiles update`: change model settings, not connection.

## Pitfalls
- Changing `--kind` does not reset the auth mode. Moving a `chatgpt` or
  `xai_account` provider to `openai` fails with exit 2
  (`Provider auth_mode must be one of: ...`) unless you also pass
  `--auth-mode api_key`.
- Profiles that use the provider are re-validated against the new kind; an
  incompatible profile (for example one with a reasoning mode on a non-OpenAI
  kind) makes the update fail with exit 2 and nothing is saved.
- Setting a non-`api_key` auth mode discards the stored key and env var name.
  Switching back to `api_key` leaves any stored account session in place;
  remove it with `auth-logout` first if it is no longer needed.
- Unknown `provider_id` prints `Error: Unknown provider ID '...'.` and exits 2.
