# pbi-agent config profiles select

Set the default saved model profile used by CLI runs and the web UI.

## Purpose
Stores `profile_id` as `web.active_profile_id` in `~/.pbi-agent/config.json`
and prints `Selected default model profile 'ID'.` The default profile is used
when nothing more specific is given:

- `pbi-agent run` when neither the global `--profile-id` option nor the
  `PBI_AGENT_PROFILE_ID` environment variable is set;
- `pbi-agent web` and new web sessions without an explicit profile;
- Kanban task runs when neither the task nor its stage names a profile.

It does not change any profile's fields. For a one-off run, prefer
`pbi-agent --profile-id ID run ...` over changing the default.

## Usage
```text
pbi-agent config profiles select profile_id
```

## Options and arguments
- `profile_id` (positional, required): ID of an existing saved profile;
  slugified before lookup, and the slugified ID is what gets stored.

## Examples
```bash
# Make "analysis" the default profile
pbi-agent config profiles select analysis
# Confirm: the Active column shows yes for it
pbi-agent config profiles list
```

## Workflows
1. Switch defaults: `pbi-agent config profiles list`, then
   `pbi-agent config profiles select fast`, then `pbi-agent run -p "..."`.
2. Temporary override without changing the default:
   `PBI_AGENT_PROFILE_ID=fast pbi-agent run -p "..."` or
   `pbi-agent --profile-id fast run -p "..."`.

## Related commands
- `pbi-agent config profiles list`: shows which profile is active.
- `pbi-agent config profiles create`: the first profile created becomes the
  default automatically.
- `pbi-agent run`: consumes the default.

## Pitfalls
- Unknown IDs fail with `Error: Unknown profile ID 'x'.` and exit 2.
- There is no CLI command to clear the default without selecting another one;
  deleting the default profile clears it, and the web UI Settings offers
  "No default".
- `--profile-id` and `PBI_AGENT_PROFILE_ID` take precedence over the default
  for `run`, so selecting a profile has no visible effect while they are set.
