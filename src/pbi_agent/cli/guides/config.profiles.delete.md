# pbi-agent config profiles delete

Remove a saved model profile.

## Purpose
Deletes the profile named by `profile_id` from `~/.pbi-agent/config.json` and
prints `Deleted model profile 'ID'.` The referenced provider is left untouched.

If the deleted profile was the default, the default is cleared (no profile is
selected; nothing else is auto-selected). If it was the web UI's prompt
enhancement profile, that setting is cleared too. Use `update` to change a
profile instead of deleting it.

## Usage
```text
pbi-agent config profiles delete profile_id
```

## Options and arguments
- `profile_id` (positional, required): ID of the profile to delete; slugified
  before lookup, so `Analysis` matches `analysis`.

## Examples
```bash
# Delete a profile
pbi-agent config profiles delete analysis
# Make another profile the default first, then delete the old one
pbi-agent config profiles select fast && pbi-agent config profiles delete analysis
```

## Workflows
1. Retire the default profile safely: `pbi-agent config profiles list`, then
   `pbi-agent config profiles select fast`, then
   `pbi-agent config profiles delete analysis`.
2. Remove a provider entirely: delete every profile that uses it with
   `pbi-agent config profiles delete ID`, then
   `pbi-agent config providers delete PROVIDER_ID`.

## Related commands
- `pbi-agent config profiles list`: confirm the ID and whether it is the default.
- `pbi-agent config profiles select`: choose a new default afterwards.
- `pbi-agent config providers delete`: fails while any profile still uses the provider.

## Pitfalls
- Unknown IDs fail with `Error: Unknown profile ID 'x'.` and exit 2.
- There is no confirmation prompt and no undo.
- After deleting the default, `pbi-agent run` without `--profile-id` or
  `PBI_AGENT_PROFILE_ID` falls back to CLI flags, environment variables and
  provider defaults, and the web UI starts without an active profile until one
  is selected.
- References elsewhere are not checked: `model_profile_id` in
  `.agents/commands/*.md` or `.agents/agents/*.md`, and Kanban stage or task
  profiles, keep pointing at the deleted ID.
