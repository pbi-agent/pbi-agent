---
title: 'Project Commands'
description: 'Create reusable project slash commands from .agents/commands Markdown files.'
---

# Project Commands

`pbi-agent` supports project-local command presets. These are single-turn prompt
instructions loaded from Markdown files under `.agents/commands/`, with each
file's frontmatter `name` becoming a slash command such as `/review`.

## Manage commands from the web UI

Open **Settings → Project → Commands**. The add dialog can browse the official
catalog or install from a GitHub owner/repo, GitHub URL/tree URL, or server-side
local path. Installed commands are available from the composer command menu
immediately.

## Manage commands from the CLI

```bash
pbi-agent commands add
pbi-agent commands add --command execute
pbi-agent commands add ./commands/local
pbi-agent commands add owner/private-repo --command repo-review
```

Omitting `source` uses the official `pbi-agent/commands` catalog from
`https://github.com/pbi-agent/commands` and lists the available entries.
Explicit multi-command sources still require `--command <name>` when installing.

## Local file layout

Supported local install root:

- `.agents/commands/*.md`

Each command file must include YAML frontmatter with at least `name` and
`description`. It may also include:

- `model_profile_id` to use a specific saved profile for that command turn.
- `allowed_tools` to replace the selected profile's built-in tool visibility for
  that command turn.

```yaml
---
name: review
description: Review proposed code changes as if written by another engineer.
model_profile_id: analysis
allowed_tools: read,shell
---
```

Remote public catalogs are discovered from:

- `commands/*.md`

If a source repository keeps command files under `.agents/commands/`, target
that directory explicitly with a local path or GitHub tree URL.

## Slash command behavior

At runtime, project commands are discovered from `.agents/commands/*.md`. The
normalized frontmatter `name` becomes the slash alias, and the Markdown body is
injected as active turn instructions when the user starts a message with that
alias. Reserved built-in local commands such as `/skills`, `/mcp`, `/agents`,
`/reload`, and `/compact` still take precedence. See
[Session Commands](/session-commands) for how slash commands behave in
interactive sessions.

## Command tool visibility

`allowed_tools` uses the same comma-separated built-in tool groups as model
profiles and `pbi-agent run`:

| Tool group | Built-ins |
| --- | --- |
| `read` | `explore_workspace` |
| `write` | `apply_patch`, `replace_in_file`, `write_file` |
| `web` | `read_web_url` and provider-native web search |
| `sub-agent` | `sub_agent` |
| `shell` | `shell` |

If `allowed_tools` is omitted, the command turn uses the selected profile's tool
visibility. If it is present, it replaces the selected profile's allow-list for
that command turn only; later non-command turns keep the session's selected
profile.

Use `write` only for commands that should be able to edit files. Omit `web` to
disable both `read_web_url` and native provider web search for the command turn.
MCP and extension tools are not affected by this allow-list, and the UI-only
`ask_user` tool is not configurable through command frontmatter.

See [Built-in Tools](/tools#availability-controls) for full availability
semantics and precedence.
