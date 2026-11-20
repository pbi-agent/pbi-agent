# pbi-agent agents

List or install project-scoped sub-agent definitions under `.agents/agents/`.

## Purpose
A project sub-agent is a Markdown file `.agents/agents/<name>.md` with `name` and
`description` frontmatter; the body becomes the child agent's system prompt.
Optional frontmatter (`model_profile_id`, `allowed_tools`, `skills`, `commands`,
`sub_agents`) scopes the child run. Enabled definitions are offered to the main
agent as delegation targets for the `sub_agent` tool. Use this command group to see
and install definitions from the terminal; enabling and disabling agents is done in
the web UI (Settings, Project, Agents). Everything acts on the current working directory.

## Usage
```text
pbi-agent agents <action> ...
```

## Subcommands
- `pbi-agent agents list`: show installed sub-agents with enabled/disabled status. Guide: `pbi-agent agents list --doc`.
- `pbi-agent agents add`: install a sub-agent from the official catalog, a local path, or GitHub. Guide: `pbi-agent agents add --doc`.

An action is required: `pbi-agent agents` alone prints a usage error and exits 2.
There is no enable, disable, or remove action on the CLI; delete the `.md` file to remove one.

## Options and arguments
No options besides `-h/--help` and `--doc`.

## Examples
```bash
# Browse the official pbi-agent/agents catalog (installs nothing)
pbi-agent agents add
# Install one sub-agent from the official catalog
pbi-agent agents add --agent code-reviewer
# Show every installed definition, including disabled ones
pbi-agent agents list
# Root flag: list only the sub-agents a session would offer, then exit
pbi-agent --agents
```

## Workflows
1. Add a catalog sub-agent: `pbi-agent agents add` to browse,
   `pbi-agent agents add --agent NAME` to install, `pbi-agent agents list` to confirm,
   then `/reload` in open sessions.
2. Share team sub-agents: keep them in a repo under `agents/*.md`, then run
   `pbi-agent agents add owner/repo --list` and `pbi-agent agents add owner/repo --agent NAME`.

## Related commands
- `pbi-agent --agents`: root flag (not this command) that prints only enabled sub-agents
  (Name, Description) and exits.
- `pbi-agent skills`, `pbi-agent commands`: the same install workflow for skills and commands.
- `pbi-agent kits add`: install sub-agents with skills, commands, MCP servers, and instructions.
- `pbi-agent config profiles`: create profiles referenced by `model_profile_id`.

## Pitfalls
- Do not confuse `pbi-agent agents ...` (this command group) with the root flag
  `pbi-agent --agents`, which lists enabled sub-agents and skips disabled ones.
- Enabled/disabled state is stored per workspace path in `~/.pbi-agent/sessions.db`,
  not in the repository; definitions with no saved state are enabled.
- Files with unsupported frontmatter keys, a missing `name`/`description`, or an invalid
  `model_profile_id` are skipped with a warning on stderr.
- Errors print `Error: ...` on stderr and exit 2.
