---
title: 'Session Commands'
description: 'Interactive web session commands, composer shortcuts, file mentions, shell mode, and slash commands.'
---

# Session Commands

Session commands are input shortcuts handled by the interactive browser session. Some run locally without a model request, while others transform the next user turn before it is sent to the model.

This page is separate from the [CLI Reference](/cli) and the [Built-in Tools](/tools): CLI commands are terminal entry points such as `pbi-agent run`, and built-in tools are model-callable functions such as `shell` and `read_file`.

## Quick reference

| Syntax | Scope | What it does |
| --- | --- | --- |
| `@path/to/file` | Web session prompt | References a workspace file; autocomplete opens after `@`. |
| `@path/to/image.png` | Web session prompt | References an image file and attaches it to the next turn when the provider supports images. |
| `!command` | Web session prompt | Runs a workspace shell command directly, without a model request. |
| `/skills` | Web and interactive runtime | Shows discovered project skills. |
| `/mcp` | Web and interactive runtime | Shows discovered project MCP servers. |
| `/agents` | Web and interactive runtime | Shows discovered project sub-agents. |
| `/reload` | Web and interactive runtime | Reloads workspace instructions, project catalogs, non-MCP tools, and the web file-mention cache. |
| `/compact` | Web and interactive runtime | Summarizes the current live session into compact context for future turns. |
| `/<command-name>` | Web and interactive runtime | Applies a project command from `.agents/commands/*.md` to the current turn. |

::: tip
In the web composer, type `/` at the start of the message to search available slash commands. Type `@` in a normal prompt to search workspace files.
:::

## File mentions with `@`

Use `@` to reference files from the workspace in a normal prompt:

```text
Summarize @docs/providers.md and compare it with @docs/cli.md
```

The web UI searches the workspace file index as you type after `@`. Selecting a suggestion inserts the path with spaces escaped, for example `@notes/product\ plan.md`.

When the message is submitted, pbi-agent expands valid mentions before sending the turn:

- The visible `@` prefix is removed from the model-facing text.
- Referenced paths are recorded on the message for the session timeline.
- Missing workspace files produce a warning instead of silently attaching nothing.
- Email-like text is ignored, so `person@example.com` is not treated as a file mention.

### Image mentions

Image file mentions use the same `@` syntax:

```text
What changed in @screenshots/before.png compared with @screenshots/after.png?
```

Supported image suffixes are `.png`, `.jpg`, `.jpeg`, and `.webp`. Image mentions are attached to the model turn when the active provider supports explicit image input. If the provider does not support images, the UI drops the image attachment and shows a warning.

::: warning
File mentions are expanded only for normal prompts. Inputs that start with `/` are treated as slash commands, and inputs that start with `!` are treated as shell commands, so their `@` text is not expanded.
:::

## Shell command mode with `!`

Start a web composer input with `!` to run a shell command locally:

```text
!uv run pytest -q --tb=short -x tests/test_session.py
```

Shell command mode:

- Strips the leading `!` and sends the remaining text to the web session shell endpoint.
- Runs in the workspace through the same shell implementation used by the model-facing `shell` tool.
- Shows the command and output in the session timeline.
- Persists the user command and shell output if the live session is already bound to a saved session.
- Does not call the model.
- Does not allow image attachments.

::: danger
Shell commands can modify files or run arbitrary workspace commands. Review commands before pressing Enter.
:::

## Built-in slash commands

Slash commands must start at the beginning of the input. Built-in local slash commands are handled by the session runtime and do not call the model.

### `/skills`

Shows the project skills discovered from `.agents/skills/*/SKILL.md`. Use this to verify which skill descriptions are currently visible to the model.

### `/mcp`

Shows MCP servers discovered from `.agents/mcp.json`, including their configured transport. MCP tool definitions are loaded when the provider starts.

### `/agents`

Shows project sub-agent definitions discovered from `.agents/agents/*.md`. These are the `agent_type` choices available to the model-facing `sub_agent` tool.

### `/reload`

Reloads the active provider initialization for future model turns. It refreshes:

- `INSTRUCTIONS.md`
- `AGENTS.md`
- project skill catalogs
- project sub-agent catalogs
- non-MCP tool definitions
- the web `@file` mention cache

`/reload` does not reload `.agents/mcp.json` or already-started MCP server tool catalogs. Restart the session after changing MCP configuration.

### `/compact`

Compacts the current live session by asking the active provider to summarize the useful conversation context. Future turns continue from that summary instead of the full older transcript.

Use `/compact` when a long session is approaching the model context limit, after large tool-output bursts, or before switching to a new subtask in the same session.

If no saved session context exists yet, pbi-agent reports that there is no active context to compact.

## Project slash commands

Project command presets live in:

```text
.agents/commands/*.md
```

Each command file requires YAML frontmatter with the same `name` and `description` shape used by project skills. The command `name` is normalized into the slash alias, and the Markdown body is used as the command instructions:

```md
---
name: fastapi
description: FastAPI best practices and conventions. Use when working with FastAPI APIs and Pydantic models for them.
model_profile_id: analysis
---

# FastAPI mode

Apply FastAPI conventions before changing API code.
```

For example:

| Frontmatter `name` | Slash alias |
| --- | --- |
| `plan` | `/plan` |
| `review` | `/review` |
| `fix-review` | `/fix-review` |

When the user starts a turn with a project command alias, the command file content is injected as active instructions for that model turn. The user text is still sent as the turn prompt, so you can include details after the alias:

```text
/plan Add OAuth device-flow support to provider auth
```

Use optional `model_profile_id` to force a specific saved model profile whenever the command is submitted from the web UI. The profile id is normalized the same way as saved profile ids. If the command sets `model_profile_id`, the command turn uses that profile instead of the profile currently selected in the session header. The selected default/profile is not changed for future non-command turns.

Project slash commands are model turns, unlike built-in local commands such as `/skills` and `/compact`.

Reserved built-in aliases take precedence and cannot be defined by project command files:

- `/skills`
- `/mcp`
- `/agents`
- `/reload`
- `/compact`

::: tip
Install reusable command presets with `pbi-agent commands add`, or add Markdown files directly under `.agents/commands/`.
:::

## Image uploads from the composer

For providers that support image input, the web composer can also attach local image files through the `+` action menu or from the clipboard. These uploads are attached to the next normal prompt or project slash-command turn and then cleared.

Image uploads cannot be combined with `!` shell command mode.

## Related references

- [CLI Reference](/cli) for terminal commands and flags.
- [Built-in Tools](/tools) for model-callable function tools.
- [Customization](/customization) for `INSTRUCTIONS.md`, `AGENTS.md`, project skills, project commands, sub-agents, and MCP setup.
