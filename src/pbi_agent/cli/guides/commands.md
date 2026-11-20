# pbi-agent commands

List or install project-scoped slash commands under `.agents/commands/`.

## Purpose
A project command is a Markdown file `.agents/commands/<id>.md` with `name` and
`description` frontmatter. The slugified `name` becomes a slash alias such as
`/review`; when a message starts with that alias, the file body is injected as
instructions for that turn. Optional frontmatter (`model_profile_id`,
`allowed_tools`, `skills`, `sub_agents`) scopes the turn. Use this command group to
see and install commands from the terminal instead of the web UI (Settings,
Project, Commands). Everything acts on the current working directory.

## Usage
```text
pbi-agent commands <action> ...
```

## Subcommands
- `pbi-agent commands list`: show installed commands with their aliases. Guide: `pbi-agent commands list --doc`.
- `pbi-agent commands add`: install a command from the official catalog, a local path, or GitHub. Guide: `pbi-agent commands add --doc`.

An action is required: `pbi-agent commands` alone prints a usage error and exits 2.
There is no enable/disable or remove action; delete the `.md` file to remove a command.

## Options and arguments
No options besides `-h/--help` and `--doc`.

## Examples
```bash
# Browse the official pbi-agent/commands catalog (installs nothing)
pbi-agent commands add
# Install one command from the official catalog
pbi-agent commands add --command execute
# Show installed commands and their slash aliases
pbi-agent commands list
```

## Workflows
1. Add a catalog command: `pbi-agent commands add` to browse,
   `pbi-agent commands add --command NAME` to install, `pbi-agent commands list` to see
   its alias, then use `/NAME` in a session (run `/reload` in already open sessions).
2. Share team commands: keep them in a repo under `commands/*.md`, then teammates run
   `pbi-agent commands add owner/repo --list` and `pbi-agent commands add owner/repo --command NAME`.

## Related commands
- `pbi-agent skills`, `pbi-agent agents`: the same install workflow for skills and sub-agents.
- `pbi-agent kits add`: install commands together with skills, sub-agents, MCP servers, and instructions.
- `pbi-agent config profiles`: create the profiles that `model_profile_id` refers to.

## Pitfalls
- Commands use the current working directory as the workspace; `cd` to the project root first.
- Reserved aliases (`/status`, `/skills`, `/mcp`, `/agents`, `/init`, `/new`, `/reload`,
  `/compact`, `/extensions`, `/hooks`) cannot be used; such files are ignored.
- Files with missing frontmatter, empty `name`/`description`, an empty body, or invalid
  fields are skipped silently by both list and add.
- Errors print `Error: ...` on stderr and exit 2.
