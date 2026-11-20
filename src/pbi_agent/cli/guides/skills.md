# pbi-agent skills

List, enable, disable, and install project-scoped Agent Skills under `.agents/skills/`.

## Purpose
A project skill is a directory `.agents/skills/<name>/SKILL.md` with `name` and
`description` YAML frontmatter. Enabled skills are advertised to the model in the
system prompt as an `<available_skills>` catalog with each `SKILL.md` path; the model
reads a skill itself when a task matches. Use this command group to manage that
catalog from the terminal instead of the web UI (Settings, Project, Skills).

Everything acts on the current working directory. Only project skills are
supported; user-level skill directories are not scanned.

## Usage
```text
pbi-agent skills <action> ...
```

## Subcommands
- `pbi-agent skills list`: show installed skills with enabled/disabled status. Guide: `pbi-agent skills list --doc`.
- `pbi-agent skills enable`: enable one skill or all skills for this workspace. Guide: `pbi-agent skills enable --doc`.
- `pbi-agent skills disable`: disable one skill or all skills for this workspace. Guide: `pbi-agent skills disable --doc`.
- `pbi-agent skills add`: install a skill from the official catalog, a local directory, or GitHub. Guide: `pbi-agent skills add --doc`.

An action is required: `pbi-agent skills` alone prints a usage error and exits 2.

## Options and arguments
No options besides `-h/--help` and `--doc`.

## Examples
```bash
# Browse the official pbi-agent/skills catalog (installs nothing)
pbi-agent skills add
# Install one skill from the official catalog
pbi-agent skills add --skill openai-docs
# See what is installed and which skills are disabled
pbi-agent skills list
# Hide a skill from the prompt catalog in this workspace
pbi-agent skills disable openai-docs
```

## Workflows
1. Add a catalog skill: `pbi-agent skills add` to browse, `pbi-agent skills add --skill NAME`
   to install, `pbi-agent skills list` to confirm, then `/reload` in open sessions.
2. Install from your own repo: `pbi-agent skills add owner/repo --list` to see candidates,
   then `pbi-agent skills add owner/repo --skill NAME`.
3. Narrow the catalog temporarily: `pbi-agent skills disable --all`, then
   `pbi-agent skills enable NAME` for the ones you want.

## Related commands
- `pbi-agent kits add`: install skills together with commands, sub-agents, MCP servers, and instructions.
- `pbi-agent commands`, `pbi-agent agents`: the same install workflow for slash commands and sub-agents.
- `pbi-agent init`: create a starter `AGENTS.md` for the workspace.

## Pitfalls
- Commands use the current working directory as the workspace; `cd` to the project root first.
- Enable/disable state is not stored in the workspace: it lives in the session database
  (`~/.pbi-agent/sessions.db`, overridable with `PBI_AGENT_SESSION_DB_PATH`), keyed by
  the lowercased absolute workspace path. Moving the project resets it.
- Open sessions keep their prompt until `/reload`; new sessions pick up changes immediately.
- Skill directories with a missing or invalid `SKILL.md` are skipped with a warning on stderr.
- Errors print `Error: ...` on stderr and exit 2.
