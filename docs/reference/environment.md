---
title: 'Environment Variables'
description: 'Runtime configuration variables and provider-specific key fallbacks for pbi-agent.'
layout: doc
outline: [2, 3]
---

# Environment Variables

The CLI calls `load_dotenv()` during settings resolution, so a local `.env` file is part of the standard configuration path.

## `PBI_AGENT_*` Variables

| Variable | Default | Notes |
| --- | --- | --- |
| `PBI_AGENT_PROVIDER` | `openai` | Selects the provider backend. |
| `PBI_AGENT_API_KEY` | none | Shared API key used before provider-specific fallback env vars. |
| `PBI_AGENT_MODEL` | per-provider | Overrides the provider default model. For Generic, leaving this unset omits `model` from the request body. |
| `PBI_AGENT_MAX_TOKENS` | `16384` | Output-token limit currently used by Anthropic and Google request bodies. |
| `PBI_AGENT_REASONING_EFFORT` | `xhigh` for OpenAI; `high` otherwise | Requested reasoning effort. Providers may map this to provider-specific values internally. |
| `PBI_AGENT_MAX_TOOL_WORKERS` | `4` | Maximum tool execution workers. |
| `PBI_AGENT_MAX_RETRIES` | `2` | Retry count for transient provider failures. |
| `PBI_AGENT_COMPACT_THRESHOLD` | `150000` | Intended context compaction threshold for OpenAI. |
| `PBI_AGENT_RESPONSES_URL` | provider-specific | Responses or Interactions endpoint override for OpenAI, xAI, or Google. |
| `PBI_AGENT_GENERIC_API_URL` | `https://openrouter.ai/api/v1/chat/completions` | Chat Completions endpoint override for the Generic backend. |

::: warning Current Behavior
`PBI_AGENT_COMPACT_THRESHOLD` is defined in config resolution, but the CLI parser also sets `--compact-threshold` to `150000` by default. In normal CLI use, that parser default wins, so the environment variable does not currently override the threshold.
:::

## Provider-Specific API Key Fallbacks

These are only consulted when both `--api-key` and `PBI_AGENT_API_KEY` are absent.

| Provider | Fallback env var |
| --- | --- |
| OpenAI | `OPENAI_API_KEY` |
| xAI | `XAI_API_KEY` |
| Google | `GEMINI_API_KEY` |
| Anthropic | `ANTHROPIC_API_KEY` |
| Generic | `GENERIC_API_KEY` |

## Example `.env`

```bash
PBI_AGENT_PROVIDER=openai
PBI_AGENT_API_KEY=sk-...
PBI_AGENT_MODEL=gpt-5.4-2026-03-05
PBI_AGENT_MAX_TOOL_WORKERS=4
PBI_AGENT_MAX_RETRIES=2
PBI_AGENT_MAX_TOKENS=16384
```

::: tip
Prefer provider-specific key variables only when you switch providers often and do not want a single shared `PBI_AGENT_API_KEY` to apply to every run.
:::
