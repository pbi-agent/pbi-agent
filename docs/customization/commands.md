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
- `skills` to limit the skill catalog for that command turn to a
  comma-separated list of project skill names.
- `sub_agents` to limit delegated project sub-agents for that command turn to a
  comma-separated list of project sub-agent names.

```yaml
---
name: reviewer
description: Review implementation and test coverage.
model_profile_id: reviewer
allowed_tools: read,shell
skills: fastapi,shadcn
sub_agents: confidence-checker,fixer
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
profiles and `pbi-agent run`, plus command-only `ask-user`:

| Tool group | Built-ins |
| --- | --- |
| `read` | `explore_workspace` |
| `write` | `apply_patch`, `replace_in_file`, `write_file` |
| `web` | `read_web_url`, `web_search` |
| `sub-agent` | `sub_agent` |
| `shell` | `shell` |
| `ask-user` | `ask_user` clarification prompts for this command turn |

If `allowed_tools` is omitted, the command turn uses the selected profile's tool
visibility. If it is present, it replaces the selected profile's allow-list for
that command turn only; later non-command turns keep the session's selected
profile.

Use `write` only for commands that should be able to edit files. Omit `web` to
disable both `read_web_url` and Firecrawl-backed `web_search` for the command turn.
MCP and extension tools are not affected by this allow-list. Include `ask-user`
only on commands that should be allowed to ask browser users clarifying
questions during that command turn.

See [Built-in Tools](/tools#availability-controls) for full availability
semantics and precedence.

## Scoped skills and sub-agents

`skills` and `sub_agents` turn a command into a composable prompt preset with a
scoped catalog.

When `skills` is omitted, the command turn keeps the normal project skill
behavior: all enabled project skills are available, plus explicitly mentioned
disabled skills when supported by the current context. When `skills` is present,
only those configured skills are advertised. Missing or disabled configured
skills are soft references: `pbi-agent` prints a CLI warning and omits them from
the catalog. Skills are only useful when the command has the `read` tool group,
because the model must use `explore_workspace` to load each `SKILL.md`.

When `sub_agents` is omitted, the command turn keeps the normal delegation
behavior: the built-in `default` child agent plus enabled project sub-agents are
available. When `sub_agents` is present, the `sub_agent` tool is scoped to that
exact project-agent list, `agent_type` becomes required, and the built-in
`default` child agent is not exposed for that command turn. Missing or disabled
configured sub-agents are configuration errors when the runtime builds the
scoped catalog.

To use scoped delegation, the command must have access to the `sub-agent` tool
group either through its own `allowed_tools` value or through the selected model
profile. For example:

```yaml
---
name: review-with-checks
description: Review changes and delegate confidence checks.
allowed_tools: read,shell,sub-agent
sub_agents: confidence-checker
---
```

Frontmatter list fields use comma-separated scalar values only, not YAML arrays.
