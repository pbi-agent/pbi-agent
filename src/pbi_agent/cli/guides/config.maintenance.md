# pbi-agent config maintenance

Show or change the retention window used by pbi-agent's daily startup
maintenance.

## Purpose
Every `pbi-agent` invocation that gets past argument parsing (so not `--help`
or `--doc`) first runs startup maintenance, at most once per UTC day. That
pass deletes local data older than the retention window:

- sessions whose last update is older than the cutoff, plus their messages,
  run records and observability events (stored in `~/.pbi-agent/sessions.db`);
- older standalone run records and observability events, and stale web
  manager leases;
- web upload files under `~/.pbi-agent/web_uploads/` that are older than the
  cutoff and no longer referenced by any message or Kanban task.

Kanban tasks themselves are kept; only their link to a purged session is
cleared. Shell raw-output logs are purged after 24 hours regardless of this
setting. The retention value is stored under `maintenance.retention_days` in
`~/.pbi-agent/config.json` and defaults to 30 days.

## Usage
```text
pbi-agent config maintenance <action> [OPTIONS ...]
```

## Subcommands
- `pbi-agent config maintenance show`: print the current retention setting. Guide: `pbi-agent config maintenance show --doc`.
- `pbi-agent config maintenance set`: change the retention setting. Guide: `pbi-agent config maintenance set --doc`.

An action is required: `pbi-agent config maintenance` alone prints a usage
error (`the following arguments are required: <action>`) and exits 2.

## Options and arguments
No options besides `-h/--help` and `--doc`.

## Examples
```bash
# Show the current retention window
pbi-agent config maintenance show
# Keep two weeks of history
pbi-agent config maintenance set --retention-days 14
```

## Workflows
1. Audit before changing: `pbi-agent config maintenance show`, then
   `pbi-agent sessions --all-dirs` to see what history exists, then
   `pbi-agent config maintenance set --retention-days N`.
2. Keep more history for a long project: raise the value with
   `pbi-agent config maintenance set --retention-days 180` before old
   sessions age out.

## Related commands
- `pbi-agent sessions`: lists the saved sessions that retention prunes.
- `pbi-agent config`: parent command for all saved settings.
- `pbi-agent web`: its Settings page edits the same retention value.

## Pitfalls
- A new value does not trigger an immediate purge. Maintenance runs before the
  command itself, so the first run of the day already used the old value; the
  new value applies on the next UTC day's first invocation.
- Lowering the value deletes older history permanently on that next run.
- Maintenance failures are not fatal: they print
  `Warning: maintenance skipped: ...` to stderr and the command continues.
