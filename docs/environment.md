---
title: 'Environment Variables'
description: 'Runtime configuration variables and provider-specific key fallbacks for pbi-agent.'
---

# Environment Variables

The CLI calls `load_dotenv()` during settings resolution, so a local `.env` file is part of the standard configuration path.

## `PBI_AGENT_*` Variables

| Variable | Default | Notes |
| --- | --- | --- |
| `PBI_AGENT_PROVIDER` | `openai` | Selects the provider backend: `openai`, `azure`, `chatgpt`, `github_copilot`, `xai`, `google`, `google_gcp`, `anthropic`, or `generic`. |
| `PBI_AGENT_PROFILE_ID` | none | Selects a saved model profile by ID before runtime overrides are applied. |
| `PBI_AGENT_API_KEY` | none | Shared API key used before provider-specific fallback env vars. |
| `PBI_AGENT_MODEL` | per-provider | Overrides the provider default model. For Generic, leaving this unset omits `model` from the request body. |
| `PBI_AGENT_SUB_AGENT_MODEL` | per-provider sub-model | Optional override for the model used by `sub_agent`. When unset, child agents use the provider-specific sub-agent default from `config.py`. |
| `PBI_AGENT_MAX_TOKENS` | `16384` | Output-token limit applied to the selected provider request body. |
| `PBI_AGENT_REASONING_EFFORT` | `xhigh` for OpenAI; `high` otherwise | Requested reasoning effort. Providers may map this to provider-specific values internally. |
| `PBI_AGENT_MAX_TOOL_WORKERS` | `4` | Maximum tool execution workers. |
| `PBI_AGENT_MAX_RETRIES` | `3` | Retry count for transient provider failures. |
| `PBI_AGENT_COMPACT_THRESHOLD` | `200000` | Intended context compaction threshold for OpenAI. |
| `PBI_AGENT_RESPONSES_URL` | provider-specific | Responses, Interactions, or Vertex endpoint override for OpenAI API, ChatGPT, GitHub Copilot, Azure, xAI, Google, or Google Cloud Vertex AI. |
| `PBI_AGENT_GOOGLE_CLOUD_PROJECT` | none | Google Cloud project ID for the `google_gcp` provider. `GOOGLE_CLOUD_PROJECT` and `GOOGLE_CLOUD_PROJECT_ID` are also checked when deriving Vertex endpoints. |
| `PBI_AGENT_GOOGLE_CLOUD_LOCATION` | `global` | Google Cloud Vertex AI location for the `google_gcp` provider. `PBI_AGENT_GOOGLE_CLOUD_REGION`, `GOOGLE_CLOUD_LOCATION`, and `GOOGLE_CLOUD_REGION` are also checked. |
| `PBI_AGENT_GOOGLE_GCP_SHAPE` | automatic | Overrides `google_gcp` model routing. Allowed values: `gemini_generate_content`, `openai_chat_completions`, `openai_responses`, or `anthropic_messages`. |
| `PBI_AGENT_GOOGLE_GCP_AUTH` | automatic | Forces `google_gcp` explicit token classification to `api_key` or `bearer_token`. |
| `PBI_AGENT_GOOGLE_GCP_ACCESS_TOKEN_TIMEOUT` | `30` | Seconds to wait for `gcloud auth application-default print-access-token` when ADC is used. |
| `PBI_AGENT_GENERIC_API_URL` | `https://openrouter.ai/api/v1/chat/completions` | Chat Completions endpoint override for the Generic backend. |
| `PBI_AGENT_SERVICE_TIER` | none | OpenAI service tier: `auto`, `default`, `flex`, or `priority`. Only valid with the OpenAI provider. |

Settings resolution happens in two phases:

1. Select a base model profile from `--profile-id`, then `PBI_AGENT_PROFILE_ID`, then the saved active default profile.
2. Compile that profile and its saved provider, then overlay explicit CLI and environment overrides.

If no saved profile is selected, runtime settings fall back directly to CLI flags, environment variables, and provider defaults.

## Provider-Specific API Key Fallbacks

These are only consulted when both `--api-key` and `PBI_AGENT_API_KEY` are absent. That fallback still applies when a saved model profile is selected.

For speech-to-text, saved STT providers first use their saved API key or
explicit `--api-key-env` reference. If neither is set, pbi-agent checks the
provider-specific fallback below. OpenAI STT can also fall back to
`PBI_AGENT_API_KEY`.

| Provider | Fallback env var |
| --- | --- |
| OpenAI API | `OPENAI_API_KEY` |
| Azure | `AZURE_API_KEY` |
| xAI | `XAI_API_KEY` |
| Google | `GEMINI_API_KEY` |
| Google Cloud Vertex AI | `GOOGLE_CLOUD_ACCESS_TOKEN` |
| Anthropic | `ANTHROPIC_API_KEY` |
| Generic | `GENERIC_API_KEY` |
| Deepgram STT | `DEEPGRAM_API_KEY` |
| ElevenLabs STT | `ELEVENLABS_API_KEY` |

ChatGPT and GitHub Copilot subscription providers use saved account sessions instead of provider-specific API key fallback variables.

For Google Cloud Vertex AI (`google_gcp`), `GOOGLE_CLOUD_ACCESS_TOKEN` is treated
as an OAuth2 bearer token. If no explicit bearer token is configured, pbi-agent
can resolve ADC with `gcloud auth application-default print-access-token`.
Gemini express-mode requests can also use API-key environment variables such as
`GOOGLE_API_KEY`, `GEMINI_API_KEY`, `GOOGLE_CLOUD_API_KEY`, `VERTEX_AI_API_KEY`,
or `VERTEX_API_KEY`; OpenAI-compatible and Anthropic Vertex endpoints require
OAuth2 bearer auth or ADC.

## Example `.env`

```bash
PBI_AGENT_PROFILE_ID=analysis
PBI_AGENT_PROVIDER=openai
PBI_AGENT_API_KEY=sk-...
PBI_AGENT_MODEL=gpt-5.4
PBI_AGENT_SUB_AGENT_MODEL=gpt-5.4-mini
PBI_AGENT_GOOGLE_CLOUD_PROJECT=my-project
PBI_AGENT_GOOGLE_CLOUD_LOCATION=global
PBI_AGENT_MAX_TOOL_WORKERS=4
PBI_AGENT_MAX_RETRIES=3
PBI_AGENT_MAX_TOKENS=16384
```

::: tip
Prefer provider-specific key variables when you switch model providers often and
do not want a single shared `PBI_AGENT_API_KEY` to apply to every model run. For
STT-only providers, use the provider-specific variable or a saved provider API
key.
:::
