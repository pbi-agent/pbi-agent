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
  - title: 'PBIP Template Scaffolding'
    details: 'Bootstrap a Power BI Project from the bundled template with the init command or the init_report tool.'
  - title: 'Browser & Terminal UI'
    details: 'Choose the default browser UI, the Textual console interface, or a single-prompt execution path.'
---

## Start Here

::: tip
Running `pbi-agent` without a command defaults to `pbi-agent web`, so a bare invocation launches the browser UI.
:::

```bash
uv run pbi-agent --api-key "$OPENAI_API_KEY"
```

| Section | What you will find |
| --- | --- |
| [Guide](/guide/) | Installation, provider setup, and architecture overview |
| [CLI Reference](/reference/cli) | Commands, flags, defaults, and audit behavior |
| [Tools](/reference/tools) | The built-in function tools available to the agent |
| [Environment Variables](/reference/environment) | `PBI_AGENT_*` settings and provider-specific key fallbacks |

::: details Why this project exists
`pbi-agent` is designed for local, file-based Power BI Project workflows. It edits PBIP assets directly and talks to LLM providers through synchronous HTTP REST requests implemented with Python's standard library.
:::
