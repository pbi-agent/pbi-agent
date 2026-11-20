# pbi-agent config maintenance show

Print the saved maintenance retention setting.

## Purpose
Reads `~/.pbi-agent/config.json` (or the file named by
`PBI_AGENT_INTERNAL_CONFIG_PATH`) and prints the number of days of session,
run, observability and upload data that daily maintenance keeps. When nothing
was ever saved, the default of 30 is shown. It never modifies the config.

Use it to check the current window before changing it with
`pbi-agent config maintenance set`.

## Usage
```text
pbi-agent config maintenance show
```

## Options and arguments
No options besides `-h/--help` and `--doc`.

## Examples
```bash
# Print the retention window
pbi-agent config maintenance show
# Extract just the number in a script
pbi-agent config maintenance show | cut -d " " -f 2
```

Output is a single plain-text line:

```text
retention_days: 30
```

## Workflows
1. Verify a change: `pbi-agent config maintenance set --retention-days 14`,
   then `pbi-agent config maintenance show` and expect `retention_days: 14`.
2. Check a custom config file: run
   `PBI_AGENT_INTERNAL_CONFIG_PATH=/tmp/pbi-test/config.json pbi-agent config maintenance show`
   to inspect an isolated config.

## Related commands
- `pbi-agent config maintenance set`: change the value shown here.
- `pbi-agent sessions`: see the history that the retention window governs.

## Pitfalls
- Exit code 0 on success. A missing, unparseable, or invalid config file (or a
  stored value below 1) is not an error: the default `retention_days: 30` is
  printed instead.
- The value shown is the setting, not a report of what was purged; there is no
  CLI output listing deleted data.
