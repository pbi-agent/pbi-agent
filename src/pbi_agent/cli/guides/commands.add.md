# pbi-agent commands add

Install one command file into `.agents/commands/<id>.md`, or list the commands a source offers.

## Purpose
Copies a command Markdown file from the official `pbi-agent/commands` catalog, a local
path, or a GitHub repository into the current workspace. The file is written as-is to
`.agents/commands/<id>.md`, where `<id>` is the slugified frontmatter `name` and
`/<id>` is the slash alias. Candidates in a source:
- GitHub repo root: `commands/*.md` only.
- GitHub tree URL to a subdirectory: `*.md` in that directory plus its `commands/*.md`.
- Local directory: its `commands/*.md`; also its own `*.md` when the directory is named `commands`.
- Local `.md` file: that file.

## Usage
```text
pbi-agent commands add [--command COMMAND_NAME] [--list] [--force] [source]
```

## Options and arguments
- `source` (positional, optional): default is the official `pbi-agent/commands` GitHub
  catalog. Accepts a local file or directory (`./x`, `../x`, `/abs/x`, `~/x`, `.`), GitHub
  `owner/repo`, `https://github.com/owner/repo`, or `https://github.com/owner/repo/tree/REF/dir`.
- `--command COMMAND_NAME`: pick one candidate by id; a leading `/` is allowed and the
  value is slugified (`Repo Review` and `/repo-review` both match `repo-review`).
  Required when the source holds more than one command.
- `--list`: print an `Available Commands` table (Name, Alias, Description, Source Path)
  and install nothing.
- `--force`: overwrite an existing `.agents/commands/<id>.md`.

## Examples
```bash
# Browse the official catalog (same as --list)
pbi-agent commands add
# Install one command from the official catalog
pbi-agent commands add --command execute
# Install one command from a local directory named commands
pbi-agent commands add ./shared/commands --command review
# Install from a private GitHub repo, replacing the local copy
pbi-agent commands add owner/private-repo --command repo-review --force
```

## Workflows
1. Catalog install: `pbi-agent commands add`, then `pbi-agent commands add --command NAME`,
   then `pbi-agent commands list`, and `/reload` in open sessions.
2. Copy from another repo's `.agents/commands/`: use a tree URL such as
   `https://github.com/owner/repo/tree/main/.agents/commands` with `--list`, then `--command NAME`.

## Related commands
- `pbi-agent commands list`: confirm the install and its alias.
- `pbi-agent kits add`: install commands with skills, agents, and MCP servers in one step.

## Pitfalls
- No `source` and no `--command`: only lists the official catalog. `--list` always wins.
- Several candidates and no `--command`: `Multiple commands were found in the source.
  Re-run with --list or --command <name>.` (exit 2).
- Existing file without `--force`: `Command already installed at PATH. Re-run with
  --force to replace it.` (exit 2).
- Invalid candidates (bad frontmatter, empty body, reserved alias like `/reload`) are
  skipped silently; `No valid commands found...` (exit 2) means none survived.
- Local paths must start with `./`, `../`, `/`, or `~/`; `commands/x` is read as GitHub `owner/repo`.
- GitHub sources need network access; a token from `GITHUB_TOKEN`, `GH_TOKEN`, or
  `gh auth token` is used if found, with a `git clone` fallback on HTTP 401/403/404.
- Success prints `Installed command '/ID' to PATH` (exit 0); any error exits 2.
