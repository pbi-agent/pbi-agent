---
title: 'pbi-agent'
description: 'Local coding agent for skills, commands, agents, and multi-domain workflows'
layout: home
hero:
  name: 'pbi-agent'
  text: 'Documentation'
  tagline: 'Local coding agent for skills, commands, agents, and multi-domain workflows'
  actions:
    - theme: brand
      text: 'Get Started'
      link: '/introduction'
    - theme: alt
      text: 'GitHub'
      link: 'https://github.com/pbi-agent/pbi-agent'
features:
  - title: 'Multi-Provider Support'
    details: 'Target OpenAI, xAI, Google Gemini, Anthropic, or an OpenAI-compatible gateway from the same CLI.'
  - title: 'Project Skills & Commands'
    details: 'Install reusable project-local skills and slash-command presets from local sources or GitHub catalogs.'
  - title: 'Parallel Tool Execution'
    details: 'Run multiple model-requested tool calls concurrently with a configurable worker limit.'
  - title: 'Project Sub-Agents'
    details: 'Discover project-local sub-agent definitions from `.agents/agents/*.md` and route delegated work through `sub_agent`.'
  - title: 'Browser UI & Headless Runs'
    details: 'Use the default browser UI for interactive work, or switch to single-prompt runs for headless execution.'
  - title: 'MCP Tool Integration'
    details: 'Discover project-local MCP servers from `.agents/mcp.json` and expose their tools to the model.'
---

## Demo

<ClientOnly>
<div style="position: relative; width: 100%; padding-bottom: 56.25%; margin: 1.5rem 0;">
  <iframe
    src="https://www.youtube.com/embed/vw3RVwbILbE"
    title="pbi-agent demo"
    style="position: absolute; inset: 0; width: 100%; height: 100%; border: 0; border-radius: 12px;"
    allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture; web-share"
    referrerpolicy="strict-origin-when-cross-origin"
    allowfullscreen
  ></iframe>
</div>
</ClientOnly>

## Start Here

::: tip
Running `pbi-agent` without a command defaults to `pbi-agent web`, so a bare invocation launches the browser UI.
:::

### 1. Install uv

::: code-group

```bash [macOS / Linux]
curl -LsSf https://astral.sh/uv/install.sh | sh
```

```powershell [Windows]
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
```

:::

### 2. Install pbi-agent

```bash
uv tool install pbi-agent
```

::: warning
If this is your first `uv tool install`, reload your shell before running `pbi-agent` or the command may not be on your `PATH` yet.
:::

### 3. Run pbi-agent

```bash
pbi-agent --api-key "$OPENAI_API_KEY"
```

| Section | What you will find |
| --- | --- |
| [Introduction](/introduction) | Project overview and architecture |
| [Installation](/installation) | Prerequisites, install options, and first run |
| [Providers](/providers) | Provider setup, auth, and endpoint examples |
| [Web UI](/web-ui) | Browser sessions, Settings, images, and local commands |
| [Kanban Dashboard](/kanban-dashboard) | Task board automation and observability dashboard |
| [Model Profiles](/model-profiles) | Saved runtime presets and profile resolution |
| [Session Commands](/session-commands) | Interactive `@file`, `!shell`, slash commands, and `/compact` behavior |
| [CLI](/cli) | Terminal commands, flags, and runtime defaults |
| [Customization](/customization) | `INSTRUCTIONS.md`, `AGENTS.md`, project skills, sub-agents, and MCP discovery |
| [Built-in Tools](/tools) | The function tools available to the model |
| [Environment Variables](/environment) | `PBI_AGENT_*` settings and provider-specific key fallbacks |

::: details Why this project exists
`pbi-agent` is built for local, file-based coding workflows that need more than a bare chat loop. It keeps the runtime small, talks to providers through synchronous HTTP REST requests implemented with Python's standard library, and lets each workspace define its own skills, commands, agents, and MCP integrations.
:::
