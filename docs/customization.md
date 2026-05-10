---
title: 'Customization'
description: 'Override the agent system prompt and add project-specific rules using INSTRUCTIONS.md and AGENTS.md.'
---

# Customization

`pbi-agent` supports two workspace-level Markdown files that let you tailor agent behavior without touching any configuration flags or environment variables. Both files are loaded from the current working directory when an agent provider starts.

## INSTRUCTIONS.md — custom system prompt

By default the agent uses a built-in prompt tuned for local coding workflows, tool use, and workspace-aware agent behavior. Placing an `INSTRUCTIONS.md` file in your workspace root replaces that built-in prompt entirely with your own content.

```text
my-project/
├── INSTRUCTIONS.md   ← replaces the built-in system prompt
├── AGENTS.md         ← optional project rules (appended on top)
└── ...
```

**When `INSTRUCTIONS.md` is present:**

- Its content becomes the agent's system prompt verbatim.
- All other tools (`shell`, `apply_patch`, `read_file`, `read_web_url`, `sub_agent`, `read_image`) remain available.
- `AGENTS.md` project rules are still appended if present (see below).

**Example — Python coding agent:**

```markdown
# INSTRUCTIONS.md
You are a Python expert coding agent. You help users write, review, debug, and refactor Python code.

<coding_rules>
- Follow PEP 8 and PEP 257 conventions.
- Use type hints for all function signatures.
- Prefer `pathlib.Path` over `os.path` for file system operations.
</coding_rules>
```

::: tip
`INSTRUCTIONS.md` is the right place for persona and capability definitions that apply to the whole workspace. Keep it focused — one clear role description with a small set of non-negotiable rules.
:::

::: warning
Removing `INSTRUCTIONS.md` (or leaving it empty) restores the default built-in prompt automatically. The file is re-read at each agent startup; in a live session, run `/reload` to apply the change before the next model request.
:::

## AGENTS.md — project rules

`AGENTS.md` adds project-specific rules on top of whatever system prompt is active (the default built-in prompt, or your custom `INSTRUCTIONS.md`). Use it for conventions, constraints, or context that is specific to the current repository or workspace.

```text
my-project/
├── AGENTS.md   ← injected as <project_rules> in every session
└── ...
```

The file contents are wrapped in `<project_rules>` tags and appended to the system prompt:

```xml
<project_rules>
... your AGENTS.md content ...
</project_rules>
```

**Example — repository conventions:**

```markdown
# AGENTS.md
- All Python files must pass `ruff check` before committing.
- Use `uv run pytest` to execute tests; never use bare `pytest`.
- Keep internal data in `~/.pbi-agent/`, never in the workspace root.
```

::: tip
`AGENTS.md` is checked into version control alongside your project. It is the right place for team conventions that every contributor and every agent session should follow.
:::

## Project skill files

`pbi-agent` also discovers project-local Agent Skills and advertises them to the model through the system prompt.

You can manage project-local installs from the web UI under **Settings → Project → Skills**. The add dialog can browse the official catalog or install from a GitHub owner/repo, GitHub URL/tree URL, or server-side local path. New sessions see installed skills immediately; active sessions can run `/reload` before the next model request.

You can also manage project-local installs directly from the CLI:

```bash
pbi-agent skills add
pbi-agent skills add --skill openai-docs
pbi-agent skills add ./skills/local-skill
pbi-agent skills add owner/private-repo --skill repo-review
```

Omitting `source` uses the official `pbi-agent/skills` catalog from `https://github.com/pbi-agent/skills` and lists the available entries. Explicit multi-skill sources still require `--skill <name>` when installing.

Supported roots:

- `.agents/skills/<skill-name>/SKILL.md`

Each `SKILL.md` must include YAML frontmatter with at least:

```yaml
---
name: repo-skill
description: Use this skill when the task matches this repository-specific workflow.
---
```

At runtime, discovered skills are appended to the active system prompt as an `<available_skills>` catalog with the absolute `SKILL.md` path. The model is expected to load a relevant skill itself with `read_file` before proceeding, then use `read_file` or bounded shell commands  to inspect referenced project-local resources as needed.

This v1 implementation is project-only. User-level skill directories are intentionally not scanned, and any files referenced by a project skill must remain inside the workspace so the existing file tools can access them safely.

## Project command files

`pbi-agent` also supports project-local command presets. These are single-turn prompt instructions loaded from Markdown files under `.agents/commands/`, with each file's frontmatter `name` becoming a slash command such as `/review`.

You can manage project-local command installs from the web UI under **Settings → Project → Commands**. The add dialog matches the skill workflow: browse the official catalog, or install from a GitHub owner/repo, GitHub URL/tree URL, or server-side local path. Installed commands are available from the composer command menu immediately.

You can manage project-local installs directly from the CLI:

```bash
pbi-agent commands add
pbi-agent commands add --command execute
pbi-agent commands add ./commands/local
pbi-agent commands add owner/private-repo --command repo-review
```

Omitting `source` uses the official `pbi-agent/commands` catalog from `https://github.com/pbi-agent/commands` and lists the available entries. Explicit multi-command sources still require `--command <name>` when installing.

Supported local install root:

- `.agents/commands/*.md`

Each command file must include YAML frontmatter with at least `name` and `description`. It may also include `model_profile_id` to use a specific saved profile for that command turn:

```yaml
---
name: review
description: Review proposed code changes as if written by another engineer.
model_profile_id: analysis
---
```

Remote public catalogs are discovered from:

- `commands/*.md`

If a source repository keeps command files under `.agents/commands/`, target that directory explicitly with a local path or GitHub tree URL.

At runtime, project commands are discovered from `.agents/commands/*.md`. The normalized frontmatter `name` becomes the slash alias, and the Markdown body is injected as active turn instructions when the user starts a message with that alias. Reserved built-in local commands such as `/skills`, `/mcp`, `/agents`, `/reload`, and `/compact` still take precedence. See [Session Commands](/session-commands) for how slash commands behave in interactive sessions.

## Project sub-agent files

`pbi-agent` can also discover project-local sub-agent definitions and advertise them to the main agent as specialized delegated worker choices for the `sub_agent` tool.

You can manage project-local agent installs from the web UI under **Settings → Project → Agents**. The add dialog follows the same workflow as skills and commands: browse the official catalog, or install from a GitHub owner/repo, GitHub URL/tree URL, or server-side local path. New sessions see installed agents immediately; active sessions can run `/reload` before the next model request.

You can manage project-local installs directly from the CLI:

```bash
pbi-agent agents add
pbi-agent agents add --agent code-reviewer
pbi-agent agents add ./agents/local
pbi-agent agents add owner/private-repo --agent repo-reviewer
```

Omitting `source` uses the official `pbi-agent/agents` catalog from `https://github.com/pbi-agent/agents` and lists the available entries. Explicit multi-agent sources still require `--agent <name>` when installing.

Supported root:

- `.agents/agents/<agent-name>.md`

Each sub-agent file must include YAML frontmatter with at least `name` and `description`. It may also include `model_profile_id` to use a specific saved profile whenever that sub-agent runs:

```yaml
---
name: code-reviewer
description: Review code changes for correctness and test gaps.
model_profile_id: analysis
---
```

The Markdown body becomes that sub-agent's system prompt. When `model_profile_id` is omitted, project sub-agents inherit the parent runtime and use the profile's configured `sub_agent_model` when present, falling back to the parent model.

Supported frontmatter in this implementation is intentionally narrow:

- Scalar `key: value` pairs for `name`, `description`, and optional `model_profile_id`
- Quoted strings
- `|` and `>` block scalars
- Blank lines and `#` comments

Nested mappings, lists, anchors, and other general YAML features are rejected and the file is skipped with a warning on stderr.

At runtime, discovered sub-agents are appended to the active system prompt as an `<available_sub_agents>` catalog. The main agent can then call `sub_agent` with `agent_type` set to the discovered `name`. Calling `sub_agent` without `agent_type` still uses the built-in generalist child agent.

Project sub-agents:

- Run in isolated child-agent contexts by default. Set `include_context: true` on the `sub_agent` tool call to inherit the parent conversation context.
- Use the same provider as the parent session unless their frontmatter sets `model_profile_id`.
- Cannot recursively spawn more sub-agents in this build.

You can inspect the discovered catalog without starting a model request:

- CLI: `pbi-agent --agents`
- Session UI: `/agents`

## Reloading workspace context

New one-shot runs and newly created sessions read the current workspace initialization files when their provider starts. A live session keeps its provider open between turns, so edits to workspace files are not applied to that active provider until you reload it.

Use the local session command:

```text
/reload
```

`/reload` does not call the model and is not stored as a user message. It refreshes the current live provider before the next model request by re-reading:

- `INSTRUCTIONS.md`
- `AGENTS.md`
- project skill catalogs
- project sub-agent catalogs
- non-MCP tool definitions

In the web UI, `/reload` also refreshes the `@file` mention cache so newly created, renamed, or removed workspace files show up in autocomplete. The web app also refreshes that file-mention cache when a live session ends, which keeps the next session's file suggestions current without silently changing an active provider mid-task. See [Session Commands](/session-commands) for the full `@file`, `!shell`, and slash-command reference.

`/reload` does not reload MCP server configuration or MCP tool catalogs for the active provider. Restart the session after changing `.agents/mcp.json` or an MCP server's exposed tools.

## MCP server config

`pbi-agent` can also discover project-local MCP server definitions and expose their tools to the model as ordinary function tools. The runtime reads a single JSON file from the workspace root:

- `.agents/mcp.json`

The file must contain a top-level `servers` object. Each entry can be either:

- `type: "stdio"` with `command`, optional `args`, optional `env`, and optional `cwd`
- `type: "http"` with `url` and optional `headers`

Example:

```json
{
  "servers": {
    "github": {
      "type": "http",
      "url": "https://api.githubcopilot.com/mcp"
    },
    "playwright": {
      "command": "npx",
      "args": ["-y", "@microsoft/mcp-server-playwright"]
    }
  }
}
```

Discovered MCP tools are added to the model-facing tool list at startup. In the UI, you can inspect the discovered server list with `/mcp`, or from the CLI with `pbi-agent --mcp`.

::: tip
Model-facing MCP tool names are namespaced per server, so a tool like `say_hi` from the `echo` server is exposed as `echo__say_hi`.
:::

## Using both files together

The two files compose cleanly:

| Files present | System prompt |
| --- | --- |
| Neither | Built-in default prompt |
| `AGENTS.md` only | Built-in default prompt + `<project_rules>` |
| `INSTRUCTIONS.md` only | Your custom prompt |
| Both | Your custom prompt + `<project_rules>` |

If project skill files are present, their catalog is appended after the active prompt content in all of the cases above, including custom `INSTRUCTIONS.md`.

## File constraints

| Property | Value |
| --- | --- |
| Maximum size | 1 MB (content beyond that is truncated with a warning on stderr) |
| Encoding | UTF-8 (invalid bytes are replaced, not rejected) |
| Empty file | Treated as absent — the default behavior applies |
| Permissions | Unreadable file emits a warning on stderr and is skipped |
