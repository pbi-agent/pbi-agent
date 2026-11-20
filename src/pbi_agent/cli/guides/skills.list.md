# pbi-agent skills list

Print the project skills installed under `.agents/skills/` with their enabled status.

## Purpose
Scans `.agents/skills/*/SKILL.md` in the current working directory and prints a
`Project Skills` table with columns Name, Status (`enabled` or `disabled`), and
Description. Use it to check what the model can see before or after
`pbi-agent skills add`, `enable`, or `disable`. It reads only local files and the
local session database; no network access.

To see what a source offers before installing, use `pbi-agent skills add --list` instead.

## Usage
```text
pbi-agent skills list
```

## Options and arguments
No options besides `-h/--help` and `--doc`.

## Examples
```bash
# List skills in the current workspace
pbi-agent skills list
# Print this guide
pbi-agent skills list --doc
```

## Workflows
1. Verify an install: `pbi-agent skills add --skill NAME`, then `pbi-agent skills list`
   and check the new row shows `enabled`.
2. Audit the prompt catalog: `pbi-agent skills list`, then `pbi-agent skills disable NAME`
   for anything that should not be offered, and `/reload` in open sessions.

## Related commands
- `pbi-agent skills enable`, `pbi-agent skills disable`: change the Status column.
- `pbi-agent skills add`: install skills; `--list` shows remote candidates.
- `pbi-agent commands list`, `pbi-agent agents list`: the equivalent listings for commands and sub-agents.

## Pitfalls
- With no skills it prints `No project skills discovered under .agents/skills/` and exits 0.
- Only direct child directories of `.agents/skills/` that contain `SKILL.md` are listed.
  A `SKILL.md` missing frontmatter, `name`, or `description` is skipped with a warning
  on stderr. A `name` that differs from its directory name loads anyway, with a warning.
- Status is per workspace path (stored in `~/.pbi-agent/sessions.db`); a skill with no
  saved state is shown as `enabled`.
- Always exits 0.
