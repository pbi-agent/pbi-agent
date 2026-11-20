# pbi-agent config providers delete

Remove a saved provider from `~/.pbi-agent/config.json`.

## Purpose
Use it to retire a provider no model profile uses any more. The provider is
removed from the config and, if the web UI had it selected as the
speech-to-text provider, that selection is cleared. On success it prints
`Deleted provider 'ID'.` and exits 0. To keep the provider but change its
settings, use `update` instead.

## Usage
```text
pbi-agent config providers delete provider_id
```

## Options and arguments
- `provider_id` (positional): ID of the provider to delete. It is slugified
  first, so `"OpenAI Main"` and `openai-main` name the same provider.

## Examples
```bash
# Delete by ID
pbi-agent config providers delete openai-main
# Delete after logging out of its account session
pbi-agent config providers auth-logout chatgpt && pbi-agent config providers delete chatgpt
```

## Workflows
1. Retire a provider: `pbi-agent config profiles list` to find profiles whose
   `Provider` column is the ID, `pbi-agent config profiles delete PROFILE` (or
   `profiles update PROFILE --provider-id OTHER`) for each, then
   `pbi-agent config providers delete ID`.
2. Clean up an account provider: `auth-logout ID` to remove the stored
   session, then `delete ID`.

## Related commands
- `pbi-agent config profiles list`: shows which profiles still reference it.
- `pbi-agent config providers auth-logout`: removes the stored account session.
- `pbi-agent config providers list`: confirm the provider is gone.

## Pitfalls
- Fails with exit 2 while any profile references the provider:
  `Error: Cannot delete provider 'ID': model profile 'P' still references it.`
  Only the first blocking profile is named; repeat after fixing it.
- Unknown IDs print `Error: Unknown provider ID '...'.` and exit 2.
- Deleting does not remove the provider's account session from
  `~/.pbi-agent/auth.json`; run `auth-logout` before deleting. A later provider
  created with the same ID would pick that session up again.
- There is no confirmation prompt and no undo.
