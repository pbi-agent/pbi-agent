# pbi-agent config profiles list

Print a table of saved model profiles and mark the default one.

## Purpose
Reads `~/.pbi-agent/config.json` (or `PBI_AGENT_INTERNAL_CONFIG_PATH`) and
renders a "Saved Model Profiles" table sorted by ID. Use it to find profile IDs
for `--profile-id`, `update`, `delete`, and `select`, and to confirm which
profile is the default. It never modifies the config.

Columns: `ID`, `Active` (`yes` for the default profile), `Name`, `Provider`
(saved provider ID), `Model`, `Sub-Agent`, `Reasoning` (reasoning effort), and
`Mode` (OpenAI reasoning mode). Empty cells mean the field is unset and the
provider or runtime default applies. Other fields (max tokens, service tier,
allowed tools, retries, compaction) are stored but not shown.

## Usage
```text
pbi-agent config profiles list
```

## Options and arguments
No options besides `-h/--help` and `--doc`.

## Examples
```bash
# Show all saved profiles
pbi-agent config profiles list
# Find the default profile row
pbi-agent config profiles list | grep yes
```

## Workflows
1. Pick a profile for one run: `pbi-agent config profiles list`, copy an ID,
   then `pbi-agent --profile-id fast run -p "..."`.
2. Change the default: `pbi-agent config profiles list`, then
   `pbi-agent config profiles select analysis`, then list again to see `yes`
   moved.

## Related commands
- `pbi-agent config providers list`: resolve the `Provider` column to a saved
  provider.
- `pbi-agent config profiles select`: change which row shows `Active` `yes`.
- `pbi-agent config profiles update`: edit fields shown here.

## Pitfalls
- With no saved profiles it prints `No saved model profiles.` and exits 0.
- Output is a human-readable Rich table with no JSON mode; column widths follow
  the terminal, so long values may wrap. Avoid parsing it in scripts beyond
  simple grep.
- No row shows `yes` when no default is set (for example after deleting the
  default profile).
