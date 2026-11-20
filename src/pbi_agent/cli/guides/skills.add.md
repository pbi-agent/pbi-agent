# pbi-agent skills add

Install a skill bundle into `.agents/skills/<name>/`, or list the skills a source offers.

## Purpose
Copies one skill directory (its `SKILL.md` plus every file next to it) from the
official `pbi-agent/skills` catalog, a local directory, or a GitHub repository into
the current workspace. Inside a source, a skill is the source root itself (if it has a
`SKILL.md`) or each `skills/<dir>/SKILL.md`. Each `SKILL.md` needs `name` and
`description` frontmatter; the `name` becomes the install directory.

## Usage
```text
pbi-agent skills add [--skill SKILL] [--list] [--force] [source]
```

## Options and arguments
- `source` (positional, optional): where to install from. Default: the official
  `pbi-agent/skills` GitHub catalog. Accepts a local directory (`./dir`, `../dir`,
  `/abs/dir`, `~/dir`, `.`), GitHub `owner/repo`, `https://github.com/owner/repo`, or a
  tree URL `https://github.com/owner/repo/tree/REF/sub/dir`.
- `--skill SKILL`: install the candidate whose `name` matches (case-insensitive).
  Required when the source holds more than one skill.
- `--list`: print an `Available Skills` table (Name, Description, Source Path) and
  install nothing.
- `--force`: delete an existing `.agents/skills/<name>/` and replace it.

## Examples
```bash
# Browse the official catalog (same as --list)
pbi-agent skills add
# Install one skill from the official catalog
pbi-agent skills add --skill openai-docs
# Install the single skill in a local directory
pbi-agent skills add ./skills/local-skill
# List, then install, from a GitHub repository
pbi-agent skills add owner/private-repo --list
pbi-agent skills add owner/private-repo --skill custom-review --force
```

## Workflows
1. Catalog install: `pbi-agent skills add`, pick a name, `pbi-agent skills add --skill NAME`,
   then `pbi-agent skills list` and `/reload` in open sessions.
2. Update an installed skill: rerun the same install with `--force` (the old directory is
   removed first, so local edits are lost).

## Related commands
- `pbi-agent skills list`: confirm the install and its enabled status.
- `pbi-agent kits add`: install a set of skills plus commands, agents, and MCP servers at once.

## Pitfalls
- With no `source` and no `--skill` it only lists the official catalog. `--list` always wins
  over `--skill`.
- Several candidates and no `--skill`: `Multiple skills were found in the source. Re-run
  with --list or --skill <name>.` (exit 2). An unknown `--skill` lists the available names.
- Existing install without `--force`: `Skill already installed at PATH. Re-run with --force
  to replace it.` (exit 2).
- Local paths must start with `./`, `../`, `/`, or `~/`; `skills/foo` is parsed as GitHub
  `owner/repo`. Local sources must be directories.
- A source repo's `.agents/skills/` is not scanned from the repo root; point a tree URL or
  local path at its `.agents` directory (which holds `skills/`) or at one skill directory.
- GitHub sources need network access. A token from `GITHUB_TOKEN`, `GH_TOKEN`, or
  `gh auth token` is sent if found; on HTTP 401/403/404 it falls back to `git clone`
  (HTTPS, then SSH), so private repos work with git credentials.
- Success prints `Installed skill 'NAME' to PATH` (exit 0); any error exits 2.
