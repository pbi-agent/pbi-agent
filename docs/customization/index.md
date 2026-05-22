---
title: 'Customization'
description: 'Workspace prompt files, project skills, commands, sub-agents, MCP tools, and reload behavior.'
---

# Customization

`pbi-agent` can be customized from files in the current workspace. These files
let you change the system prompt, add project-specific rules, install reusable
skills and commands, define specialist sub-agents, and expose project-local MCP
tools without changing global provider settings.

## Customization modules

| Module | Workspace path | Use it for |
| --- | --- | --- |
| [Custom system prompt](/customization/instructions) | `INSTRUCTIONS.md` | Replace the built-in system prompt for this workspace. |
| [Project rules](/customization/project-rules) | `AGENTS.md` | Add repository conventions on top of the active system prompt. |
| [Project skills](/customization/skills) | `.agents/skills/<skill>/SKILL.md` | Advertise task-specific skill instructions that the model can load on demand. |
| [Project commands](/customization/commands) | `.agents/commands/*.md` | Add reusable slash-command prompt presets. |
| [Project sub-agents](/customization/sub-agents) | `.agents/agents/*.md` | Define specialist child agents for the `sub_agent` tool. |
| [Workspace reload](/customization/reload) | `/reload` | Refresh prompt files and project catalogs in an active session. |
| [MCP servers](/customization/mcp) | `.agents/mcp.json` | Expose project-local MCP tools to the model. |
| [File constraints](/customization/file-constraints) | prompt files | Size, encoding, empty-file, and unreadable-file behavior. |

## Prompt file composition

`INSTRUCTIONS.md` and `AGENTS.md` compose cleanly:

| Files present | System prompt |
| --- | --- |
| Neither | Built-in default prompt |
| `AGENTS.md` only | Built-in default prompt + `<project_rules>` |
| `INSTRUCTIONS.md` only | Your custom prompt |
| Both | Your custom prompt + `<project_rules>` |

If project skill files are present, their catalog is appended after the active
prompt content in all of the cases above, including custom `INSTRUCTIONS.md`.

## When changes take effect

New one-shot runs and newly created sessions read customization files when their
provider starts. A live session keeps its provider open between turns, so edits
to workspace files are not applied until you run [`/reload`](/customization/reload)
or restart the session.
