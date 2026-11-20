# pbi-agent agents add

Install one sub-agent file into `.agents/agents/<name>.md`, or list the agents a source offers.

## Purpose
Copies a sub-agent Markdown file from the official `pbi-agent/agents` catalog, a local
path, or a GitHub repository into the current workspace, unchanged, as
`.agents/agents/<name>.md` where `<name>` is the frontmatter `name`. A candidate must
load like an installed definition (`name`, `description`, only supported keys).
Candidates in a source:
- GitHub repo root: `agents/*.md` only.
- GitHub tree URL to a subdirectory: `*.md` in that directory plus its `agents/*.md`.
- Local directory: its `agents/*.md`; also its own `*.md` when the directory is named `agents`.
- Local `.md` file: that file.

## Usage
```text
pbi-agent agents add [--agent AGENT_NAME] [--list] [--force] [source]
```

## Options and arguments
- `source` (positional, optional): default is the official `pbi-agent/agents` GitHub
  catalog. Accepts a local file or directory (`./x`, `../x`, `/abs/x`, `~/x`, `.`), GitHub
  `owner/repo`, `https://github.com/owner/repo`, or `https://github.com/owner/repo/tree/REF/dir`.
- `--agent AGENT_NAME`: pick the candidate whose `name` matches exactly (case-sensitive).
  Required when the source holds more than one agent.
- `--list`: print an `Available Agents` table (Name, Description, Source Path) and
  install nothing.
- `--force`: overwrite an existing `.agents/agents/<name>.md`.

## Examples
```bash
# Browse the official catalog (same as --list)
pbi-agent agents add
# Install one sub-agent from the official catalog
pbi-agent agents add --agent code-reviewer
# Install a single local definition file
pbi-agent agents add ./shared/agents/reviewer.md
# Install from a private GitHub repo, replacing the local copy
pbi-agent agents add owner/private-repo --agent repo-reviewer --force
```

## Workflows
1. Catalog install: `pbi-agent agents add`, then `pbi-agent agents add --agent NAME`,
   then `pbi-agent agents list`, and `/reload` in open sessions.
2. Copy from another repo's `.agents/agents/`: use a tree URL such as
   `https://github.com/owner/repo/tree/main/.agents/agents` with `--list`, then `--agent NAME`.

## Related commands
- `pbi-agent agents list`: confirm the install and its status.
- `pbi-agent --agents`: root flag listing the enabled sub-agents a session will offer.
- `pbi-agent kits add`: install sub-agents with skills, commands, and MCP servers in one step.

## Pitfalls
- No `source` and no `--agent`: only lists the official catalog. `--list` always wins.
- Several candidates and no `--agent`: `Source contains multiple agents. Re-run with
  --list or --agent <name>. Available agents: ...` (exit 2).
- Existing file without `--force`: `Agent 'NAME' is already installed at PATH. Use
  --force to replace it.` (exit 2).
- `--agent` is case-sensitive, unlike `skills add --skill` and `commands add --command`.
- Local paths must start with `./`, `../`, `/`, or `~/`; `agents/x` is read as GitHub `owner/repo`.
- GitHub sources need network access; a token from `GITHUB_TOKEN`, `GH_TOKEN`, or
  `gh auth token` is used if found, with a `git clone` fallback on HTTP 401/403/404.
- Success prints `Installed agent 'NAME' to PATH` (exit 0); any error exits 2.
