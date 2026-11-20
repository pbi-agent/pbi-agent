# pbi-agent kits add

Preview or install a kit into the current workspace, from the official catalog, a local directory, or GitHub.

## Purpose
Copies a kit's parts into the workspace: `skills/`, `commands/`, and `agents/` into
`.agents/`, `mcp.json` servers merged into `.agents/mcp.json` (other servers untouched),
and `AGENTS.md` appended to the workspace `AGENTS.md` between
`<!-- kit:NAME:start -->` and `<!-- kit:NAME:end -->`. Each part may sit at the kit root
or under its `.agents/` (except `AGENTS.md`, root only). A source with a `kits/<name>/`
directory is a catalog; otherwise the source itself is one kit. The kit name is the
directory name, or the repository name for a GitHub repo root.

## Usage
```text
pbi-agent kits add [--kit KIT] [--list] [--force] [source]
```

## Options and arguments
- `source` (positional, optional): default is the official `pbi-agent/kits` GitHub
  catalog. Accepts a local directory (`./x`, `../x`, `/abs/x`, `~/x`, `.`), GitHub
  `owner/repo`, `https://github.com/owner/repo`, or `https://github.com/owner/repo/tree/REF/dir`.
- `--kit KIT`: select a kit from a catalog by directory name (case-insensitive). Not
  needed for a catalog with a single kit; rejected for a single-kit source.
- `--list`: write nothing. For a catalog without `--kit`, print an `Available Kits` table
  (Name, Description from `kit.json`, Source Path); otherwise print the preview table.
- `--force`: replace existing skills, commands, agents, same-named MCP servers, and this
  kit's `AGENTS.md` block.

## Examples
```bash
# Browse the official catalog
pbi-agent kits add
# Preview, then install, one official kit
pbi-agent kits add --kit coding --list
pbi-agent kits add --kit coding
# Install a local kit, replacing items that already exist
pbi-agent kits add ./kits/powerbi --force
# Install one kit from a GitHub tree URL
pbi-agent kits add https://github.com/owner/repo/tree/main/kits/powerbi
```

## Workflows
1. Safe install: `pbi-agent kits add --kit NAME --list` (Status `new`, `will replace`, or
   `exists`), then `pbi-agent kits add --kit NAME`, then `/reload` in open sessions; restart
   sessions to load new MCP servers.
2. Refresh after the kit changed upstream: `pbi-agent kits add --kit NAME --force`; local
   edits to the replaced files are lost.

## Related commands
- `pbi-agent skills add`, `pbi-agent commands add`, `pbi-agent agents add`: install single items.
- `pbi-agent --mcp`: root flag listing MCP servers after the install.

## Pitfalls
- No `source` and no `--kit` behaves like `--list`. With an explicit catalog `source` and
  several kits, omitting `--kit` fails: `Source is a catalog with several kits. Re-run
  with --kit <name>. Available kits: ...` (exit 2).
- Without `--force`, existing items are skipped (`skipped (exists)`) and it still exits 0.
- `Source is a single kit, not a catalog. Re-run without --kit.` and `No kit content
  found...` exit 2, as do invalid `mcp.json` files and an `AGENTS.md` start marker
  without its end marker under `--force`.
- Local paths must start with `./`, `../`, `/`, or `~/`, and must be directories.
- GitHub sources need network access; a token from `GITHUB_TOKEN`, `GH_TOKEN`, or
  `gh auth token` is used if found, with a `git clone` fallback on HTTP 401/403/404.
- There is no `kits remove` or `kits update`; delete or edit installed files directly.
