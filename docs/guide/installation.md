---
title: 'Installation'
description: 'Prerequisites, package installation, source setup, and a minimal first-run flow.'
layout: doc
outline: [2, 3]
---

# Installation

## Prerequisites

| Requirement | Notes |
| --- | --- |
| Python | `>= 3.12` |
| `uv` | Recommended for local development and running the CLI from source |

::: warning
`pbi-agent` operates on PBIP projects, not `.pbix` files. If you are starting from Power BI Desktop, save the report as a Power BI Project first or bootstrap one with `pbi-agent init`.
:::

## Install from PyPI

```bash
pip install pbi-agent
```

## Install from Source

```bash
git clone https://github.com/nasirus/pbi-agent.git
cd pbi-agent
uv sync
```

## Verify the Install

```bash
uv run pbi-agent --help
```

If you installed the package globally with `pip`, use `pbi-agent --help` instead.

## Quick Start

Set an API key, then run the browser UI or a single prompt:

```bash
export PBI_AGENT_API_KEY="sk-..."
uv run pbi-agent
```

```bash
uv run pbi-agent run --prompt "Describe the PBIP project structure in this workspace."
```

::: tip
Startup loads environment variables from a local `.env` file automatically through `python-dotenv`, so you can keep `PBI_AGENT_API_KEY`, `PBI_AGENT_PROVIDER`, and related settings there.
:::

::: details First-time bootstrap
If you do not already have a PBIP workspace, create one in the current directory with `uv run pbi-agent init --dest .`. The `init` command does not require provider credentials because it only copies the bundled report template.
:::
