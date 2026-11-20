# pbi-agent agents list

Print every project sub-agent definition under `.agents/agents/`, with its enabled status.

## Purpose
Scans `.agents/agents/*.md` in the current working directory and prints a
`Project Agents` table with columns Name, Status (`enabled` or `disabled`),
Description (suffixed with `[profile: ID]` when `model_profile_id` is set), and
Location (absolute file path). It reads only local files and the local session
database; no network access.

Compared with the root flag `pbi-agent --agents`, this listing includes disabled
definitions and shows status and file location. To see what a source offers before
installing, use `pbi-agent agents add --list`.

## Usage
```text
pbi-agent agents list
```

## Options and arguments
No options besides `-h/--help` and `--doc`.

## Examples
```bash
# List all sub-agent definitions in the current workspace
pbi-agent agents list
# Compare with the sub-agents a session would actually offer
pbi-agent --agents
```

## Workflows
1. Verify an install: `pbi-agent agents add --agent NAME`, then `pbi-agent agents list`
   and check the row shows `enabled`.
2. Debug a sub-agent that is never used: `pbi-agent agents list` to check it loads and is
   `enabled` (toggle it in the web UI if not), then `/reload` in open sessions.

## Related commands
- `pbi-agent --agents`: root flag listing only enabled sub-agents (Name, Description).
- `pbi-agent agents add`: install definitions; `--list` shows remote candidates.
- `pbi-agent skills list`, `pbi-agent commands list`: the equivalent listings for skills and commands.

## Pitfalls
- With no definitions it prints `No project agents discovered under .agents/agents/`
  and exits 0.
- Only `*.md` files directly in `.agents/agents/` are read.
- Invalid files (no frontmatter, missing `name` or `description`, unsupported keys, bad
  `model_profile_id`) are skipped with a warning on stderr. A duplicate `name` keeps the
  first file by file name and warns about the rest.
- Status comes from `~/.pbi-agent/sessions.db` for the current workspace path; there is
  no CLI action to change it.
- Always exits 0.
