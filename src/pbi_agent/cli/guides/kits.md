# pbi-agent kits

Install kits: packaged workspace setups of skills, commands, sub-agents, MCP servers, and instructions.

## Purpose
A kit is a directory (local or on GitHub) that bundles everything needed for one kind
of work. Installing it is a one-shot copy into the current workspace:
- `skills/<name>/` to `.agents/skills/<name>/`
- `commands/*.md` to `.agents/commands/<id>.md`
- `agents/*.md` to `.agents/agents/<name>.md`
- `mcp.json` servers merged into `.agents/mcp.json`
- `AGENTS.md` appended to the workspace `AGENTS.md` inside `<!-- kit:NAME:start -->` /
  `<!-- kit:NAME:end -->` markers

Nothing tracks the kit afterwards: the files become ordinary workspace files, so there
is no update or remove action. Use a kit instead of separate `skills add`,
`commands add`, and `agents add` calls when you want a whole setup at once.

## Usage
```text
pbi-agent kits <action> ...
```

## Subcommands
- `pbi-agent kits add`: preview or install a kit from the official catalog, a local directory, or GitHub. Guide: `pbi-agent kits add --doc`.

An action is required: `pbi-agent kits` alone prints a usage error and exits 2.

## Options and arguments
No options besides `-h/--help` and `--doc`.

## Examples
```bash
# Browse the official pbi-agent/kits catalog (writes nothing)
pbi-agent kits add
# Preview what one catalog kit would write
pbi-agent kits add --kit coding --list
# Install it
pbi-agent kits add --kit coding
```

## Workflows
1. Set up a workspace: `pbi-agent init` (optional), `pbi-agent kits add` to browse,
   `pbi-agent kits add --kit NAME --list` to preview, `pbi-agent kits add --kit NAME`
   to install, then `/reload` in open sessions and restart them for new MCP servers.
2. Reuse an existing workspace repo as a kit: its `.agents/skills`, `.agents/commands`,
   `.agents/agents`, `.agents/mcp.json`, and root `AGENTS.md` are recognized, so
   `pbi-agent kits add owner/repo --list` works without restructuring.

## Related commands
- `pbi-agent skills add`, `pbi-agent commands add`, `pbi-agent agents add`: install single items.
- `pbi-agent skills list`, `pbi-agent commands list`, `pbi-agent agents list`: inspect results.
- `pbi-agent --mcp`: root flag that lists the MCP servers discovered after install.

## Pitfalls
- Kits write into the current working directory; `cd` to the workspace root first.
- A kit can add MCP servers that run local commands and instructions that steer the
  agent. Preview with `--list` and review the files before using an untrusted source.
- Existing items are kept (reported as skipped) unless `--force` is passed.
- Errors print `Error: ...` on stderr and exit 2.
