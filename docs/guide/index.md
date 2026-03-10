---
title: 'Introduction'
description: 'What pbi-agent is, how it is structured, and which providers it supports.'
layout: doc
outline: [2, 3]
---

# What Is pbi-agent?

`pbi-agent` is a local CLI tool for editing Power BI Project (`.pbip`) workspaces with an LLM agent. It communicates with providers over synchronous HTTP REST APIs using `urllib.request`, so the runtime does not depend on provider SDKs.

::: tip
The same CLI surface can target OpenAI, xAI, Google Gemini, Anthropic, or a generic OpenAI-compatible backend.
:::

## Architecture Overview

The runtime is intentionally small and linear:

```text
CLI
  -> config resolution (.env, env vars, flags)
  -> provider backend
  -> agent session
  -> tool runtime (parallel ThreadPoolExecutor)
  -> built-in tools
```

| Layer | Responsibility |
| --- | --- |
| CLI | Parses global options, inserts the default `web` command when needed, and dispatches subcommands. |
| Config | Resolves provider, API key, model, retry limits, and other runtime settings. |
| Provider | Sends synchronous HTTP requests to the selected API shape and normalizes tool calls and text output. |
| Agent Session | Runs interactive chat, single-turn execution, or audit mode. |
| Tool Runtime | Executes requested tools serially or in parallel based on `--max-tool-workers`. |
| Tools | Exposes `shell`, `apply_patch`, `skill_knowledge`, and `init_report`. |

## Supported Providers

| Provider | API Shape | Default Endpoint | Default Model |
| --- | --- | --- | --- |
| OpenAI | Responses API | `https://api.openai.com/v1/responses` | `gpt-5.4-2026-03-05` |
| xAI | Responses API | `https://api.x.ai/v1/responses` | `grok-4-1-fast-reasoning` |
| Google | Interactions API | `https://generativelanguage.googleapis.com/v1beta/interactions` | `gemini-3.1-flash-lite-preview` |
| Anthropic | Messages API | `https://api.anthropic.com/v1/messages` | `claude-opus-4-6` |
| Generic | Chat Completions API | `https://openrouter.ai/api/v1/chat/completions` | none; the `model` field is omitted when unset |

::: details Conversation history mode
OpenAI, xAI, and Google keep conversation state server-side by passing a previous response or interaction ID. Anthropic and Generic keep history client-side by re-sending accumulated messages on each turn.
:::

## Read Next

- [Installation](/guide/installation)
- [Providers](/guide/providers)
- [CLI Reference](/reference/cli)
- [Environment Variables](/reference/environment)
