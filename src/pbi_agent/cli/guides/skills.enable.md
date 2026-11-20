# pbi-agent skills enable

Re-enable one installed project skill, or all of them, for the current workspace.

## Purpose
Removes skills from this workspace's disabled list so they appear again in the
`<available_skills>` prompt catalog. Skills are enabled by default, so this is only
needed after `pbi-agent skills disable`. State is saved in the local session database
(`~/.pbi-agent/sessions.db`), keyed by the lowercased absolute path of the current
directory; nothing in `.agents/skills/` is modified.

## Usage
```text
pbi-agent skills enable [--all] [skill]
```

## Options and arguments
- `skill` (positional, optional): name of an installed skill, matched case-insensitively
  against the `name` in each `SKILL.md`. Required unless `--all` is given.
- `--all`: enable every skill currently installed under `.agents/skills/`. When set,
  any `skill` argument is ignored.

## Examples
```bash
# Enable one skill
pbi-agent skills enable openai-docs
# Enable every installed skill
pbi-agent skills enable --all
```

## Workflows
1. Undo a disable: `pbi-agent skills list` to find `disabled` rows,
   `pbi-agent skills enable NAME`, then `/reload` in open sessions.
2. Reset the workspace: `pbi-agent skills enable --all`, then `pbi-agent skills list`
   to confirm every row is `enabled`.

## Related commands
- `pbi-agent skills disable`: the inverse operation.
- `pbi-agent skills list`: shows the current Status of each skill.
- `pbi-agent skills add`: install a skill first; enable only accepts installed skills.

## Pitfalls
- Neither `skill` nor `--all`: prints `Error: provide a skill name or --all.` and exits 2.
- A name that is not installed: prints `Error: unknown skill 'NAME'.` and exits 2.
- Success prints `Enabled skill 'NAME'.` or `Enabled N skill(s).` and exits 0.
  `--all` with no installed skills prints `Enabled 0 skill(s).`
- Run it from the workspace root; the state key is the current directory path.
- Open sessions keep their old catalog until `/reload`.
