# pbi-agent upgrade

Upgrade pbi-agent to the latest release on PyPI, or only check whether one exists.
`pbi-agent update` is an alias: it runs the same command and `pbi-agent update --doc`
prints this same guide.

## Purpose
Queries `https://pypi.org/pypi/pbi-agent/json` for the latest version and compares it
with the running version. If newer, it detects how pbi-agent was installed and runs
the matching installer:
- `uv tool install`: `uv tool upgrade pbi-agent`
- `pipx install`: `pipx upgrade pbi-agent`
- `pip` in a virtual environment: `<python> -m pip install --upgrade pbi-agent`

After the installer succeeds it re-reads the installed version and fails if it did
not change (for example a pinned version). Use `--check` in scripts to only detect
updates. The daily startup maintenance of other commands also shows an update
notice; `upgrade` skips that background check and does its own.

## Usage
```text
pbi-agent upgrade [--check]
pbi-agent update [--check]
```

## Options and arguments
- `--check`: only report whether a newer version exists; never installs. Prints the
  version comparison and, when an update exists, a hint (`Run: pbi-agent upgrade` or
  a manual command). Exit codes: `0` up to date, `100` update available, `1` error.

## Examples
```bash
# Upgrade in place if a newer release exists
pbi-agent upgrade
# Same command through the alias
pbi-agent update
# Script-friendly check; exit code 100 means an update is available
pbi-agent upgrade --check
```

## Workflows
1. CI or cron check: run `pbi-agent upgrade --check`, treat exit `100` as
   "update available" and `1` as a network/PyPI error, then run `pbi-agent upgrade`.
2. After upgrading, confirm the new version with `pbi-agent --version`.

## Related commands
- `pbi-agent --version`: print the installed version.
- `pbi-agent web`: shows the same update notice in the browser UI.

## Pitfalls
- Without `--check`, exit codes are `0` when up to date or upgraded, `1` on errors
  (PyPI unreachable, unsupported install, version unchanged), or the installer's own
  non-zero exit code if the installer fails.
- Source installs (editable checkout, local path, git URL) are not upgraded: it prints
  "Update your source checkout and reinstall it." and exits 1.
- If `uv`/`pipx` is not on `PATH` or the install method is unknown, it prints a manual
  command (fallback: `uv tool install pbi-agent --upgrade`) and exits 1.
- On Windows the installer runs in a new console window after pbi-agent exits, and
  the command returns 0 once that window starts; wait for it before rerunning pbi-agent.
- Requires network access to pypi.org (10 second timeout).
