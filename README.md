<div align="center">

<img src="src/pbi_agent/web/static/favicon.png" alt="PBI Agent logo" width="120">

# PBI AGENT

*Lightweight local coding agent.*

[![Tests](https://github.com/pbi-agent/pbi-agent/actions/workflows/tests.yml/badge.svg?branch=master)](https://github.com/pbi-agent/pbi-agent/actions/workflows/tests.yml)
[![Publish](https://github.com/pbi-agent/pbi-agent/actions/workflows/publish.yml/badge.svg)](https://github.com/pbi-agent/pbi-agent/actions/workflows/publish.yml)
[![Release](https://github.com/pbi-agent/pbi-agent/actions/workflows/release.yml/badge.svg)](https://github.com/pbi-agent/pbi-agent/actions/workflows/release.yml)
[![Python](https://img.shields.io/badge/python-3.12%2B-blue)](https://www.python.org/downloads/)
[![License](https://img.shields.io/badge/license-MIT-gold)](LICENSE)

</div>

`pbi-agent` is a local CLI and browser-based coding agent for working directly in a repository through natural language.

Repository: [https://github.com/pbi-agent/pbi-agent](https://github.com/pbi-agent/pbi-agent)

Full documentation lives at [pbi-agent.github.io/pbi-agent](https://pbi-agent.github.io/pbi-agent/).

## Demo

[![Watch the demo](https://img.youtube.com/vi/vw3RVwbILbE/maxresdefault.jpg)](https://pbi-agent.github.io/pbi-agent/#demo)

## Quick Start

1. Install the CLI:

```bash
uv tool install pbi-agent
```

2. Set your provider credentials:

```bash
export PBI_AGENT_API_KEY="sk-..."
```

3. Open your project workspace:

```bash
cd /path/to/my-project
```

4. Start the app:

```bash
pbi-agent
```

Running `pbi-agent` with no command launches the browser UI on `http://localhost:8000`.

## Docs

- [Installation](https://pbi-agent.github.io/pbi-agent/guide/installation)
- [Provider Setup](https://pbi-agent.github.io/pbi-agent/guide/providers)
- [CLI Reference](https://pbi-agent.github.io/pbi-agent/reference/cli)
- [Environment Variables](https://pbi-agent.github.io/pbi-agent/reference/environment)
- [Customization](https://pbi-agent.github.io/pbi-agent/guide/customization)

## Customization

`pbi-agent` supports a few workspace-level customization points:

- `INSTRUCTIONS.md` replaces the default system prompt for the workspace.
- `AGENTS.md` adds project-specific rules on top of the active prompt.
- `.agents/skills/<skill-name>/SKILL.md` adds project-local skills that are advertised to the model.
- `.agents/agents/<agent-name>.md` adds project-local sub-agents that can be selected through the `sub_agent` tool.
- `.agents/mcp.json` declares MCP servers whose tools are exposed to the model at startup.

See the full [Customization guide](https://pbi-agent.github.io/pbi-agent/guide/customization) for examples and behavior details.

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
