# pbi-agent skills disable

Disable one installed project skill, or all of them, for the current workspace.

## Purpose
Hides skills from the `<available_skills>` prompt catalog without deleting them.
The skill files under `.agents/skills/` stay in place (and in version control); only
this workspace's disabled list in the local session database
(`~/.pbi-agent/sessions.db`) changes. Use it to keep a shared repo's skills
installed while not offering some of them to the model on your machine. To remove
a skill completely, delete its `.agents/skills/<name>/` directory instead.

## Usage
```text
pbi-agent skills disable [--all] [skill]
```

## Options and arguments
- `skill` (positional, optional): name of an installed skill, matched case-insensitively
  against the `name` in each `SKILL.md`. Required unless `--all` is given.
- `--all`: disable every skill currently installed under `.agents/skills/`. When set,
  any `skill` argument is ignored.

## Examples
```bash
# Disable one skill
pbi-agent skills disable openai-docs
# Disable every installed skill
pbi-agent skills disable --all
```

## Workflows
1. Trim the catalog: `pbi-agent skills list`, `pbi-agent skills disable NAME` for each
   unwanted skill, then `/reload` in open sessions.
2. Allow-list a few skills: `pbi-agent skills disable --all`, then
   `pbi-agent skills enable NAME` for each skill to keep.

## Related commands
- `pbi-agent skills enable`: the inverse operation.
- `pbi-agent skills list`: shows the current Status of each skill.

## Pitfalls
- Neither `skill` nor `--all`: prints `Error: provide a skill name or --all.` and exits 2.
- A name that is not installed: prints `Error: unknown skill 'NAME'.` and exits 2.
- Success prints `Disabled skill 'NAME'.` or `Disabled N skill(s).` and exits 0.
- `--all` only covers skills installed now; a skill added later starts enabled.
- State is keyed by the lowercased absolute workspace path, so it does not travel with
  the repository and does not apply to other checkouts.
- Open sessions keep their old catalog until `/reload`.
