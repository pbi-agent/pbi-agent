---
title: 'Kits'
description: 'Install a packaged, specialized workspace setup: skills, commands, sub-agents, MCP servers, and instructions.'
---

# Kits

A kit packages a specialized working environment so a workspace can be set up
for one kind of work in a single step. A kit can provide:

- project skills
- project commands
- project sub-agents
- MCP servers
- instructions (project rules)

Install one from the official catalog, a local directory, or a GitHub
repository:

```bash
pbi-agent kits add                      # list the official catalog
pbi-agent kits add --kit coding         # install a kit from the official catalog
pbi-agent kits add owner/repo
pbi-agent kits add https://github.com/owner/repo/tree/main/kits/powerbi
pbi-agent kits add ./kits/powerbi
```

The official catalog is [pbi-agent/kits](https://github.com/pbi-agent/kits).

Installation is a one-shot copy into the current workspace. After that the
files are ordinary workspace customization files: edit, commit, or delete them
like any other. pbi-agent does not track which kit a file came from, so there is
no `kits remove` or `kits update`.

## Kit layout

A kit is a directory. Every part is optional, but at least one must be present.

```text
my-kit/
├── AGENTS.md                 # instructions
├── skills/<skill>/SKILL.md   # project skills
├── commands/*.md             # project commands
├── agents/*.md               # project sub-agents
└── mcp.json                  # MCP servers
```

`skills/`, `commands/`, `agents/`, and `mcp.json` may also live under `.agents/`
in the kit, so an existing pbi-agent workspace repository works as a kit without
restructuring. Each part uses the same file format as its workspace
counterpart: see [Project skills](/customization/skills),
[Project commands](/customization/commands),
[Project sub-agents](/customization/sub-agents), and
[MCP servers](/customization/mcp).

The kit name is the repository name, or the directory name for local paths and
GitHub tree URLs.

An optional `kit.json` with a `description` string describes the kit in catalog
listings.

## Catalogs

A source that has a `kits/` directory is a catalog: each `kits/<name>/`
directory is one kit. Select a kit with `--kit NAME`; a catalog with a single
kit needs no selection. A GitHub tree URL or local path that points at one
`kits/<name>/` directory installs that kit directly.

```bash
pbi-agent kits add owner/catalog-repo --list        # list its kits
pbi-agent kits add owner/catalog-repo --kit powerbi
```

## What gets written

| Kit part | Workspace destination | If it already exists |
| --- | --- | --- |
| `skills/<skill>/` | `.agents/skills/<skill>/` | Kept; `--force` replaces the directory. |
| `commands/<name>.md` | `.agents/commands/<name>.md` | Kept; `--force` replaces the file. |
| `agents/<name>.md` | `.agents/agents/<name>.md` | Kept; `--force` replaces the file. |
| `mcp.json` servers | merged into `.agents/mcp.json` | Server with the same name is kept; `--force` replaces that server. Other servers are never touched. |
| `AGENTS.md` | appended to the workspace `AGENTS.md` | A block from the same kit is kept; `--force` replaces that block. |

Kit instructions are appended inside marker comments, so your own rules stay
intact and a repeated install does not duplicate the block:

```md
<!-- kit:my-kit:start -->
...kit instructions...
<!-- kit:my-kit:end -->
```

Use `--list` to preview what a kit would install without writing anything:

```bash
pbi-agent kits add --kit coding --list
```

After installing, run [`/reload`](/customization/reload) in open sessions.
Restart a session to load newly added MCP servers.

::: warning
A kit can add MCP servers that run local commands and instructions that steer
the agent. Preview with `--list` and review the installed files before using a
kit from a source you do not control.
:::
