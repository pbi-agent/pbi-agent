---
title: 'Customization'
description: 'Override the agent system prompt and add project-specific rules using INSTRUCTIONS.md and AGENTS.md.'
layout: doc
outline: [2, 3]
---

# Customization

`pbi-agent` supports two workspace-level Markdown files that let you tailor agent behavior without touching any configuration flags or environment variables. Both files are loaded at startup from the current working directory.

## INSTRUCTIONS.md — custom system prompt

By default the agent operates in Power BI mode with a built-in system prompt that encodes PBIP conventions and best practices. Placing an `INSTRUCTIONS.md` file in your workspace root replaces that built-in prompt entirely with your own content.

```text
my-project/
├── INSTRUCTIONS.md   ← replaces the built-in system prompt
├── AGENTS.md         ← optional project rules (appended on top)
└── ...
```

**When `INSTRUCTIONS.md` is present:**

- Its content becomes the agent's system prompt verbatim.
- The Power BI-specific tools `skill_knowledge` and `init_report` are automatically excluded from the tool list, since they are only meaningful in a Power BI context.
- All other tools (`shell`, `python_exec`, `apply_patch`, `read_file`, `search_files`, `list_files`, `read_web_url`, `sub_agent`, `read_image`) remain available.
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
Removing `INSTRUCTIONS.md` (or leaving it empty) restores the default Power BI mode automatically. No restart is required; the file is re-read at each agent startup.
:::

## AGENTS.md — project rules

`AGENTS.md` adds project-specific rules on top of whatever system prompt is active (the default Power BI prompt, or your custom `INSTRUCTIONS.md`). Use it for conventions, constraints, or context that is specific to the current repository or workspace.

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

`pbi-agent` also discovers project-local Agent Skills and advertises them to the model through the system prompt. This is separate from the built-in Power BI `skill_knowledge` tool.

Supported roots:

- `.agents/skills/<skill-name>/SKILL.md`

Each `SKILL.md` must include YAML frontmatter with at least:

```yaml
---
name: repo-skill
description: Use this skill when the task matches this repository-specific workflow.
---
```

At runtime, discovered skills are appended to the active system prompt as an `<available_skills>` catalog with the absolute `SKILL.md` path. The model is expected to load a relevant skill itself with `read_file` before proceeding, then use `read_file`, `list_files`, and `search_files` to inspect referenced project-local resources as needed.

This v1 implementation is project-only. User-level skill directories are intentionally not scanned, and any files referenced by a project skill must remain inside the workspace so the existing file tools can access them safely.

## Project sub-agent files

`pbi-agent` can also discover project-local sub-agent definitions and advertise them to the main agent as specialized delegated worker choices for the `sub_agent` tool.

Supported root:

- `.agents/<agent-name>.md`

Each sub-agent file must include YAML frontmatter with at least:

```yaml
---
name: code-reviewer
description: Review code changes for correctness and test gaps.
---
```

The Markdown body becomes that sub-agent's system prompt. Two optional frontmatter keys can override the child runtime configuration for that specific sub-agent:

```yaml
---
name: code-reviewer
description: Review code changes for correctness and test gaps.
model: gpt-5.4-mini
reasoning_effort: high
---
```

Supported frontmatter in this implementation is intentionally narrow:

- Scalar `key: value` pairs
- Quoted strings
- `|` and `>` block scalars
- Blank lines and `#` comments

Nested mappings, lists, anchors, and other general YAML features are rejected and the file is skipped with a warning on stderr.

At runtime, discovered sub-agents are appended to the active system prompt as an `<available_sub_agents>` catalog. The main agent can then call `sub_agent` with `agent_type` set to the discovered `name`. Calling `sub_agent` without `agent_type` still uses the built-in generalist child agent.

Project sub-agents:

- Run in isolated child-agent contexts and do not inherit the full parent conversation history.
- Use the same provider as the parent session.
- Can override the child `model` and `reasoning_effort` per sub-agent.
- Cannot recursively spawn more sub-agents in this build.

You can inspect the discovered catalog without starting a model request:

- CLI: `pbi-agent --agents`
- Chat UI: `/agents`
- Chat UI reload after editing files: `/agents reload`

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
| Neither | Built-in Power BI prompt |
| `AGENTS.md` only | Built-in Power BI prompt + `<project_rules>` |
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
