# pbi-agent commands list

Print the project commands installed under `.agents/commands/`.

## Purpose
Scans `.agents/commands/*.md` in the current working directory and prints a
`Project Commands` table with columns Name (frontmatter `name`), Alias (the slash
alias, for example `/review`), Description, and Location (path relative to the
workspace). Use it to check which slash commands a session will offer. It reads
only local files; no network access.

To see what a source offers before installing, use `pbi-agent commands add --list`.

## Usage
```text
pbi-agent commands list
```

## Options and arguments
No options besides `-h/--help` and `--doc`.

## Examples
```bash
# List commands in the current workspace
pbi-agent commands list
# Print this guide
pbi-agent commands list --doc
```

## Workflows
1. Verify an install: `pbi-agent commands add --command NAME`, then
   `pbi-agent commands list` to confirm the row and its alias.
2. Debug a missing slash command: `pbi-agent commands list`; if the file is absent from
   the table, check its frontmatter (`name`, `description`) and that its body is not empty.

## Related commands
- `pbi-agent commands add`: install commands; `--list` shows remote candidates.
- `pbi-agent skills list`, `pbi-agent agents list`: the equivalent listings for skills and sub-agents.

## Pitfalls
- With no commands it prints `No project commands discovered under .agents/commands/`
  and exits 0.
- Only `*.md` files directly in `.agents/commands/` are read; subdirectories are ignored.
- Invalid files (no frontmatter, empty fields or body, reserved alias such as `/reload`,
  invalid `allowed_tools`) are skipped without any warning.
- If two files slugify to the same alias, only the first (by file name) is listed.
- Always exits 0.
