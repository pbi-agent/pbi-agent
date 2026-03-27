---
title: 'pbi-agent'
description: 'Multi-provider LLM CLI agent for Power BI report editing'
layout: home
hero:
  name: 'pbi-agent'
  text: 'Documentation'
  tagline: 'Multi-provider LLM CLI agent for Power BI report editing'
  actions:
    - theme: brand
      text: 'Get Started'
      link: '/guide/'
    - theme: alt
      text: 'GitHub'
      link: 'https://github.com/nasirus/pbi-agent'
features:
  - title: 'Multi-Provider Support'
    details: 'Target OpenAI, xAI, Google Gemini, Anthropic, or an OpenAI-compatible gateway from the same CLI.'
  - title: 'Parallel Tool Execution'
    details: 'Run multiple model-requested tool calls concurrently with a configurable worker limit.'
  - title: 'Project Sub-Agents'
    details: 'Discover project-local sub-agent definitions from `.agents/*.md` and route delegated work through `sub_agent`.'
  - title: 'PBIP Template Scaffolding'
    details: 'Bootstrap a Power BI Project from the bundled template with the init command or the init_report tool.'
  - title: 'Browser & Terminal UI'
    details: 'Choose the default browser UI, the Textual console interface, or a single-prompt execution path.'
  - title: 'MCP Tool Integration'
    details: 'Discover project-local MCP servers from `.agents/mcp.json` and expose their tools to the model.'
---

## Demo

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

## Start Here

::: tip
Running `pbi-agent` without a command defaults to `pbi-agent web`, so a bare invocation launches the browser UI.
:::

### 1. Install uv

macOS / Linux:

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

Windows (PowerShell):

```powershell
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
```

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
| [Guide](/guide/) | Installation, provider setup, and architecture overview |
| [CLI Reference](/reference/cli) | Commands, flags, defaults, and audit behavior |
| [Tools](/reference/tools) | The built-in function tools available to the agent |
| [Environment Variables](/reference/environment) | `PBI_AGENT_*` settings and provider-specific key fallbacks |
| [Customization](/guide/customization) | `INSTRUCTIONS.md`, `AGENTS.md`, project skills, sub-agents, and MCP discovery |

::: details Why this project exists
`pbi-agent` is designed for local, file-based Power BI Project workflows. It edits PBIP assets directly and talks to LLM providers through synchronous HTTP REST requests implemented with Python's standard library.
:::
