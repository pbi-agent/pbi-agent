<div align="center">

<img src="src/pbi_agent/web/static/logo.jpg" alt="pbi-agent logo" width="120">

# pbi-agent

*work smart.*

[![Tests](https://github.com/pbi-agent/pbi-agent/actions/workflows/tests.yml/badge.svg?branch=master)](https://github.com/pbi-agent/pbi-agent/actions/workflows/tests.yml)
[![Release](https://github.com/pbi-agent/pbi-agent/actions/workflows/release.yml/badge.svg)](https://github.com/pbi-agent/pbi-agent/actions/workflows/release.yml)
[![Python](https://img.shields.io/badge/python-3.12%2B-blue)](https://www.python.org/downloads/)
[![License](https://img.shields.io/badge/license-MIT-gold)](LICENSE)

</div>

`pbi-agent` is a token-efficient local coding agent designed to cut session token usage by up to 60% while keeping the model focused on the task. Its main interface is the browser-based web UI, and it also offers a non-interactive CLI mode for scripted or terminal-first runs. It combines interactive sessions, reusable project skills and commands, sub-agents, MCP tools, and kanban-style coordination in one workspace-first runtime.

Repository: [https://github.com/pbi-agent/pbi-agent](https://github.com/pbi-agent/pbi-agent)

Full documentation lives at [pbi-agent.github.io/pbi-agent](https://pbi-agent.github.io/pbi-agent/).

## Three pillars

Modern LLMs are more intuitive and capable, so a coding agent does not need to over-script every step. `pbi-agent` is built around three concise defaults that let the model choose the trajectory while the runtime protects the context window.

1. **Compact default system instructions**
   The default prompt is intentionally small: define the goal, active tools, and hard workspace rules, then let the model reason from the task. Users can still add `INSTRUCTIONS.md`, `AGENTS.md`, skills, commands, and sub-agents when a project needs more guidance.

2. **Bounded workspace output**
   Shell output is returned raw with size guardrails, while workspace search, read, and list operations use `codetool-explore` to return compact, model-ready file evidence. The agent avoids dumping unbounded terminal logs or whole files when snippets are enough.

3. **Tool history omitted by default**
   When resuming a session, `pbi-agent` keeps the conversation useful without replaying every prior tool call and result by default. This supports isolated flows such as planning, review, or fresh task runs. If previous tool traces matter, enable them with `--include-tool-history` or the web UI tool-history toggle.

Together, these defaults are designed to reduce session token usage by up to 60%, with larger savings possible in long multi-turn sessions where tool output and history would otherwise dominate the context.

## Quick Start

1. Install the CLI:

```bash
uv tool install pbi-agent
```

2. Open your project workspace:

```bash
cd /path/to/my-project
```

3. Start the app:

```bash
pbi-agent
```

Running `pbi-agent` with no command launches the browser UI on `http://localhost:8000`.

## Docs

- [Installation](https://pbi-agent.github.io/pbi-agent/installation)
- [Provider Setup](https://pbi-agent.github.io/pbi-agent/providers)
- [CLI Reference](https://pbi-agent.github.io/pbi-agent/cli)
- [Environment Variables](https://pbi-agent.github.io/pbi-agent/environment)
- [Customization](https://pbi-agent.github.io/pbi-agent/customization)

## Customization

`pbi-agent` supports a few workspace-level customization points:

- `INSTRUCTIONS.md` replaces the default system prompt for the workspace.
- `AGENTS.md` adds project-specific rules on top of the active prompt.
- `.agents/skills/<skill-name>/SKILL.md` adds project-local skills that are advertised to the model.
- `.agents/agents/<agent-name>.md` adds project-local sub-agents that can be selected through the `sub_agent` tool.
- `.agents/mcp.json` declares MCP servers whose tools are exposed to the model at startup.

See the full [Customization guide](https://pbi-agent.github.io/pbi-agent/customization) for examples and behavior details.

## Common Commands

```bash
pbi-agent
pbi-agent web
pbi-agent run --prompt "Summarize this repository."
pbi-agent skills add
pbi-agent skills add --skill openai-docs
pbi-agent commands add
pbi-agent commands add --command execute
pbi-agent agents add
pbi-agent agents add --agent code-reviewer
```
