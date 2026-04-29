---
title: 'Installation'
description: 'Prerequisites, package installation, source setup, and a minimal first-run flow.'
---

# Installation

## Prerequisites

| Requirement | Notes |
| --- | --- |
| Python | `>= 3.12` |
| `uv` | Recommended for local development and running the CLI from source |

## Install from PyPI

```bash
uv tool install pbi-agent
```

::: warning
If this is your first `uv tool install`, reload your shell before running `pbi-agent` or the command may not be on your `PATH` yet.
:::

To update an existing installation later, run:

```bash
uv tool install pbi-agent --upgrade
```

## Install from Source

```bash
git clone https://github.com/pbi-agent/pbi-agent.git
cd pbi-agent
uv sync
```

## Verify the Install

```bash
pbi-agent --help
```

## Quick Start
Run the web server and follow the instructions to set up a provider and profile:
```bash
pbi-agent
```

Or, run a prompt directly from the CLI:

```bash
pbi-agent run --prompt "Summarize this repository and identify the main moving parts."
```

::: tip
Startup loads environment variables from a local `.env` file automatically through `python-dotenv`, so you can keep `PBI_AGENT_API_KEY`, `PBI_AGENT_PROVIDER`, and related settings there.
:::

## Alternative: Connect a Subscription Account

You can save a provider that uses a subscription account session instead of an API key.

### ChatGPT

```bash
uv run pbi-agent config providers create \
  --id openai-chatgpt \
  --name "OpenAI ChatGPT" \
  --kind chatgpt \
  --auth-mode chatgpt_account

uv run pbi-agent config profiles create \
  --name chatgpt \
  --provider-id openai-chatgpt \
  --model gpt-5.4

uv run pbi-agent config providers auth-login openai-chatgpt
uv run pbi-agent config profiles select chatgpt
uv run pbi-agent
```

The `--id openai-chatgpt` value is the saved Provider ID. Later commands reuse that exact ID in `--provider-id` and `auth-login`. If you omit `--id`, `pbi-agent` creates a slug from `--name`; for example, `"OpenAI ChatGPT"` also becomes `openai-chatgpt`.

`auth-login` opens the browser flow by default. Use `--method device` for the device-code fallback.

### GitHub Copilot

```bash
uv run pbi-agent config providers create \
  --id github-copilot \
  --name "GitHub Copilot" \
  --kind github_copilot \
  --auth-mode copilot_account

uv run pbi-agent config profiles create \
  --name copilot \
  --provider-id github-copilot \
  --model gpt-5.4

uv run pbi-agent config providers auth-login github-copilot --method device
uv run pbi-agent config profiles select copilot
uv run pbi-agent
```

GitHub Copilot auth uses the device-code flow. The stored Copilot session does not support refresh; run `auth-login github-copilot --method device` again when you need to reconnect.

The full saved-provider workflows, including the equivalent Settings-page flows in the web UI, are documented in [Providers](/providers#chatgpt-subscription) and [GitHub Copilot Subscription](/providers#github-copilot-subscription).
