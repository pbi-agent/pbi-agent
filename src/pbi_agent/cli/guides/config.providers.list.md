# pbi-agent config providers list

Print a table of every saved provider with its kind, auth mode, auth status,
masked API key and endpoint settings.

## Purpose
Use it to find provider IDs (needed by `update`, `delete`, the `auth-*`
commands and `pbi-agent config profiles create --provider-id`) and to check at
a glance whether each provider has credentials. It only reads
`~/.pbi-agent/config.json` (or `PBI_AGENT_INTERNAL_CONFIG_PATH`) and
`~/.pbi-agent/auth.json`; it never contacts a provider.

## Usage
```text
pbi-agent config providers list
```

## Options and arguments
No options besides `-h/--help` and `--doc`.

## Examples
```bash
# Show all saved providers
pbi-agent config providers list
# Search the table for one provider ID
pbi-agent config providers list | grep openai-main
```

## Workflows
1. Pick a provider for a profile: `pbi-agent config providers list`, copy the
   `ID` column value, then `pbi-agent config profiles create --name analysis
   --provider-id openai-main --model gpt-5.4`.
2. Find providers missing credentials: run `list`, look for `missing` or
   `expired` in `Auth Status`, then fix with `update --api-key-env ...` or
   `auth-login ID`.

## Related commands
- `pbi-agent config providers auth-status`: full session detail for one ID.
- `pbi-agent config providers create`: add a provider when the list is empty.
- `pbi-agent config profiles list`: profiles and the provider ID each uses.

## Pitfalls
- With no providers it prints `No saved providers.` and exits 0.
- Output is a Rich table (160 columns wide, rows sorted by name) meant for
  humans; there is no JSON mode. Long cells may be truncated with an ellipsis.
- `Auth Status` for `api_key` providers is `env:VAR` when `api_key_env` is set
  (whether or not that variable is currently set), `configured` when a key is
  stored, else `missing`. For account modes it is the session status
  (`connected`, `expired`, `missing`), suffixed with `:email` or `:plan` when
  known.
- The `API Key` column shows only the first and last four characters of a
  stored key; the full key is still plaintext in the config file.
