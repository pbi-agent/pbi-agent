# pbi-agent config profiles update

Change selected fields of an existing saved model profile.

## Purpose
Loads the profile named by `profile_id`, replaces only the fields you pass,
keeps every omitted field as saved, re-validates the merged profile against its
(possibly new) provider, writes `~/.pbi-agent/config.json`, and prints
`Updated model profile 'ID'.` The profile ID and the default-profile selection
never change. Use `create` for a new profile and `select` to change the default.

## Usage
```text
pbi-agent config profiles update [--name NAME] [--provider-id PROVIDER_ID] [--model MODEL] [--sub-agent-model SUB_AGENT_MODEL] [--reasoning-effort REASONING_EFFORT] [--reasoning-mode {standard,pro} | --clear-reasoning-mode] [--max-tokens MAX_TOKENS] [--service-tier {auto,default,flex,priority}] [--allowed-tools ALLOWED_TOOLS] [--max-tool-workers MAX_TOOL_WORKERS] [--max-retries MAX_RETRIES] [--compact-threshold COMPACT_THRESHOLD] [--compact-tail-turns COMPACT_TAIL_TURNS] [--compact-preserve-recent-tokens COMPACT_PRESERVE_RECENT_TOKENS] [--compact-tool-output-max-chars COMPACT_TOOL_OUTPUT_MAX_CHARS] profile_id
```

## Options and arguments
Every option is optional; omitted options keep the saved value. Value rules match `pbi-agent config profiles create`.
- `profile_id` (positional, required): ID of the profile to change (slugified before lookup).
- `--name NAME`: new display name; must not be blank.
- `--provider-id PROVIDER_ID`: move the profile to another saved LLM provider.
- `--model MODEL`, `--sub-agent-model SUB_AGENT_MODEL`: main and sub-agent models.
- `--reasoning-effort REASONING_EFFORT`: free-form effort value; an empty string (`""`) clears it.
- `--reasoning-mode {standard,pro}`: OpenAI-only reasoning mode, checked against the models.
- `--clear-reasoning-mode`: remove the saved reasoning mode; mutually exclusive with `--reasoning-mode`.
- `--max-tokens MAX_TOKENS` (>= 1), `--max-tool-workers MAX_TOOL_WORKERS` (>= 1), `--max-retries MAX_RETRIES` (>= 0).
- `--service-tier {auto,default,flex,priority}`: OpenAI-only service tier.
- `--allowed-tools ALLOWED_TOOLS`: comma-separated groups (`read-image`/`read`, `write`, `web`, `sub-agent`, `shell`); replaces the whole saved list, and `""` allows none.
- `--compact-threshold COMPACT_THRESHOLD`, `--compact-tail-turns COMPACT_TAIL_TURNS`: compaction trigger and preserved user turns (>= 0).
- `--compact-preserve-recent-tokens COMPACT_PRESERVE_RECENT_TOKENS`, `--compact-tool-output-max-chars COMPACT_TOOL_OUTPUT_MAX_CHARS`: compaction tail budget and tool-output cap (>= 0).

## Examples
```bash
# Switch the main model only
pbi-agent config profiles update analysis --model gpt-5.4
# Restrict tools to reading and web access
pbi-agent config profiles update analysis --allowed-tools read-image,web
# Drop the reasoning mode while moving to a non-OpenAI provider
pbi-agent config profiles update analysis --provider-id anthropic-main --model claude-opus-4-6 --clear-reasoning-mode
```

## Workflows
1. Inspect then edit: `pbi-agent config profiles list` to see current values,
   then `pbi-agent config profiles update ID --flag value`, then list again.
2. Re-enable all tools after a restriction: pass every group explicitly with
   `pbi-agent config profiles update ID --allowed-tools read-image,write,web,sub-agent,shell`.

## Related commands
- `pbi-agent config profiles create`: full description of each field.
- `pbi-agent config profiles list`: verify the result.
- `pbi-agent config providers list`: find valid `--provider-id` values.

## Pitfalls
- Unknown IDs fail with `Error: Unknown profile ID 'x'.` (exit 2).
- Passing both `--reasoning-mode` and `--clear-reasoning-mode` is an argparse
  usage error (exit 2).
- Only reasoning effort (`""`) and reasoning mode (`--clear-reasoning-mode`)
  can be cleared; other fields can only be overwritten. To unset them, delete
  and re-create the profile.
- A saved `--service-tier` blocks moving the profile to a non-OpenAI provider
  because it cannot be cleared; re-create the profile instead.
- Validation covers the merged result, so a saved reasoning mode can make a
  `--model` change fail if the new model does not support that mode.
