# pbi-agent config maintenance set

Save how many days of local session, run and upload data daily maintenance
keeps.

## Purpose
Writes `maintenance.retention_days` into `~/.pbi-agent/config.json` (or the file
named by `PBI_AGENT_INTERNAL_CONFIG_PATH`), leaving providers, profiles and
other saved settings unchanged. Daily startup maintenance uses this value to
delete sessions (and their messages, runs and observability events) not updated
within the window, plus unreferenced web uploads older than the window. Use it
to shrink `~/.pbi-agent` disk usage or to keep history longer than the default
30 days.

## Usage
```text
pbi-agent config maintenance set --retention-days RETENTION_DAYS
```

## Options and arguments
- `--retention-days RETENTION_DAYS` (required): integer number of days to keep.
  Minimum 1; there is no upper limit. The built-in default, used when nothing is
  saved, is 30.

## Examples
```bash
# Keep one week of history
pbi-agent config maintenance set --retention-days 7
# Keep a year of history
pbi-agent config maintenance set --retention-days 365
```

On success it prints `Updated maintenance retention to 7 days.` and exits 0.

## Workflows
1. Change and verify: `pbi-agent config maintenance set --retention-days 14`,
   then `pbi-agent config maintenance show`.
2. Before lowering retention, review what would age out with
   `pbi-agent sessions --all-dirs --limit 100`, then run
   `pbi-agent config maintenance set --retention-days 7`.

## Related commands
- `pbi-agent config maintenance show`: read the current value.
- `pbi-agent sessions`: browse the history that retention prunes.
- `pbi-agent web`: Settings edits the same value.

## Pitfalls
- Values below 1 fail with `Error: Maintenance retention days must be at least 1.`
  and exit 2. A non-integer value is an argparse usage error, also exit 2.
- Saving does not purge anything immediately. Maintenance runs once per UTC
  day, before the command, so the new value takes effect on the first
  `pbi-agent` invocation of the next UTC day.
- Lowering the value permanently deletes older data on that next run; there is
  no undo or trash.
- Shell raw-output logs use a fixed 24-hour lifetime and ignore this setting.
