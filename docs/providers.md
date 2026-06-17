---
title: 'Providers'
description: 'Provider selection, key resolution, endpoint overrides, history mode, and examples for every supported backend.'
---

# Provider Configuration

Saved configuration is split into two entities:

- Provider: connection-only settings such as provider kind, API key, endpoint
  overrides, and Google Cloud project/location metadata.
- Model Profile: runnable model/runtime settings tied to one saved Provider.

Speech-to-text (STT) also uses saved Providers, but it does not use model
profiles. Select the dictation provider in **Settings → Speech-to-text**. OpenAI
and xAI providers can be used for both model profiles and STT; Deepgram and
ElevenLabs are STT-only provider kinds.

Runtime resolution now happens in two phases:

1. Select a base model profile from `--profile-id`, then `PBI_AGENT_PROFILE_ID`, then the saved active default profile.
2. Compile that profile and its provider into runtime `Settings`, then overlay explicit CLI and environment overrides.

If no saved profile is selected, runtime settings fall back directly to CLI flags, environment variables, and provider defaults. The old provider-scoped saved runtime snapshot is no longer used, and runtime commands do not rewrite saved config.

API key precedence remains: `--api-key`, then `PBI_AGENT_API_KEY`, then the provider-specific fallback env var, then the saved Provider API key. Google Cloud Vertex AI can also fall back to Application Default Credentials (ADC) when no explicit bearer token is configured.

`sub_agent` uses the same provider as the parent session. Its sub-model defaults to a provider-specific sub-agent model from `config.py`, and you can override it independently with `--sub-agent-model` or `PBI_AGENT_SUB_AGENT_MODEL`.

## Saved Config Workflow

```bash
uv run pbi-agent config providers create \
  --name "OpenAI Main" \
  --kind openai \
  --api-key sk-...

uv run pbi-agent config profiles create \
  --name analysis \
  --provider-id openai-main \
  --model gpt-5.4 \
  --sub-agent-model gpt-5.4-mini \
  --reasoning-effort xhigh

uv run pbi-agent config profiles select analysis
uv run pbi-agent web
```

## Internal Config Shape

```json
{
  "providers": [
    {
      "id": "openai-main",
      "name": "OpenAI Main",
      "kind": "openai",
      "auth_mode": "api_key",
      "api_key": "sk-...",
      "api_key_env": null,
      "responses_url": "https://api.openai.com/v1/responses",
      "generic_api_url": null,
      "google_cloud_project": null,
      "google_cloud_location": null
    },
    {
      "id": "vertex-ai",
      "name": "Google Cloud Vertex AI",
      "kind": "google_gcp",
      "auth_mode": "api_key",
      "api_key": "",
      "api_key_env": null,
      "responses_url": null,
      "generic_api_url": null,
      "google_cloud_project": "my-project",
      "google_cloud_location": "global"
    },
    {
      "id": "deepgram-stt",
      "name": "Deepgram STT",
      "kind": "deepgram",
      "auth_mode": "api_key",
      "api_key": "",
      "api_key_env": "DEEPGRAM_API_KEY",
      "responses_url": null,
      "generic_api_url": null,
      "google_cloud_project": null,
      "google_cloud_location": null
    }
  ],
  "model_profiles": [
    {
      "id": "analysis",
      "name": "Analysis",
      "provider_id": "openai-main",
      "model": "gpt-5.4",
      "sub_agent_model": "gpt-5.4-mini",
      "reasoning_effort": "xhigh",
      "max_tokens": 16384,
      "service_tier": null,
      "allowed_tools": null,
      "max_tool_workers": 4,
      "max_retries": 3,
      "compact_threshold": 200000
    }
  ],
  "web": {
    "active_profile_id": "analysis",
    "stt_provider_id": "deepgram-stt"
  }
}
```

## Provider Matrix

| Provider | API Shape | Default Endpoint | Default Model | Default Sub-Model | Env Var for Key | Image Input | STT |
| --- | --- | --- | --- | --- | --- | --- | --- |
| OpenAI API | Responses API | `https://api.openai.com/v1/responses` | `gpt-5.4` | `gpt-5.4-mini` | `OPENAI_API_KEY` | yes | yes |
| ChatGPT subscription | Responses API | `https://chatgpt.com/backend-api/codex/responses` | `gpt-5.4` | `gpt-5.4-mini` | account session | yes | no |
| GitHub Copilot subscription | Responses API for OpenAI-family models; Chat Completions API for other Copilot models | `https://api.githubcopilot.com/responses` or `https://api.githubcopilot.com/chat/completions` | `gpt-5.4` | `gpt-5-mini` | account session | yes | no |
| Azure | Responses API, Chat Completions API, or Anthropic Messages API by endpoint | required `--responses-url` | `gpt-4.1` | `gpt-4.1-mini` | `AZURE_API_KEY` | yes | no |
| xAI | Responses API | `https://api.x.ai/v1/responses` | `grok-4.20` | `grok-4-1-fast` | `XAI_API_KEY` | no in this build | yes |
| Google | Interactions API | `https://generativelanguage.googleapis.com/v1beta/interactions` | `gemini-3.1-pro-preview` | `gemini-3-flash-preview` | `GEMINI_API_KEY` | yes | no |
| Google Cloud Vertex AI | Gemini `generateContent`, OpenAI Responses, OpenAI Chat Completions, or Anthropic Messages by model | derived from project/location or `--responses-url` | `gemini-2.5-flash` | `gemini-2.5-flash` | `GOOGLE_CLOUD_ACCESS_TOKEN` or ADC; Gemini API-key envs also supported | Gemini models | no |
| Anthropic | Messages API | `https://api.anthropic.com/v1/messages` | `claude-opus-4-6` | `claude-sonnet-4-6` | `ANTHROPIC_API_KEY` | yes | no |
| Generic | Chat Completions API | `https://openrouter.ai/api/v1/chat/completions` | none | none | `GENERIC_API_KEY` | no in this build | no |
| Deepgram | Speech-to-text only | `https://api.deepgram.com/v1/listen` | n/a | n/a | `DEEPGRAM_API_KEY` | n/a | yes |
| ElevenLabs | Speech-to-text only | `https://api.elevenlabs.io/v1/speech-to-text` | n/a | n/a | `ELEVENLABS_API_KEY` | n/a | yes |

Image input covers both explicit user attachments (`run --image`, `/image add`) and model-initiated local image inspection through the `read_image` tool.

::: warning
`--responses-url` is used by the OpenAI API, ChatGPT subscription, GitHub Copilot subscription, Azure, xAI, Google, and Google Cloud Vertex AI backends. For Azure it is required and selects the wire protocol from the endpoint path. For Google Cloud Vertex AI it can be a full Vertex endpoint or a base URL; otherwise pbi-agent derives the endpoint from Google Cloud project and location settings. ChatGPT and GitHub Copilot saved providers normally use their built-in account-session endpoints, Anthropic is hard-wired to `https://api.anthropic.com/v1/messages` in the current implementation, and Generic uses `--generic-api-url` instead.
:::

::: details Hidden compatibility aliases
The CLI also accepts provider-specific hidden aliases that map to `--api-key`: `--openai-api-key`, `--azure-api-key`, `--xai-api-key`, `--google-api-key`, `--anthropic-api-key`, and `--generic-api-key`.
:::

## OpenAI API

Use this provider when you want normal OpenAI Platform API-key billing. For subscription-account auth, use [ChatGPT Subscription](#chatgpt-subscription) instead.

| Setting | Value |
| --- | --- |
| Select it | `--provider openai` or `PBI_AGENT_PROVIDER=openai` |
| API key | `--api-key`, `PBI_AGENT_API_KEY`, or `OPENAI_API_KEY` |
| Endpoint override | `--responses-url` or `PBI_AGENT_RESPONSES_URL` |
| Default model | `gpt-5.4` |
| Default sub-model | `gpt-5.4-mini` |
| Model override | `--model` or `PBI_AGENT_MODEL` |
| History mode | Server-side via `previous_response_id` |
| Image input | Supported |

```bash
export OPENAI_API_KEY="sk-..."
uv run pbi-agent --provider openai web
```

## ChatGPT Subscription

`pbi-agent` can connect through a saved ChatGPT account session instead of an OpenAI API key. In the implementation this is a separate `chatgpt` provider kind with `chatgpt_account` auth and a built-in ChatGPT Codex Responses endpoint. This flow is tied to a saved Provider ID, so use saved provider/profile config rather than an ad hoc `--provider openai` invocation.

::: tip
OpenAI documents ChatGPT subscriptions and API billing as separate systems. A ChatGPT plan does not move API billing into `platform.openai.com`, but this app can use a ChatGPT subscription session through the built-in account-auth flow. See [Using Codex with your ChatGPT plan](https://help.openai.com/en/articles/11369540-codex-in-chatgpt) and [Billing settings in ChatGPT vs Platform](https://help.openai.com/en/articles/9039756).
:::

### CLI Workflow

Create a saved ChatGPT subscription provider, create a model profile that points at it, complete the sign-in flow, then select that profile for runtime use:

```bash
uv run pbi-agent config providers create \
  --id openai-chatgpt \
  --name "OpenAI ChatGPT" \
  --kind chatgpt \
  --auth-mode chatgpt_account

uv run pbi-agent config profiles create \
  --name chatgpt \
  --provider-id openai-chatgpt \
  --model gpt-5.4 \
  --sub-agent-model gpt-5.4-mini

uv run pbi-agent config providers auth-login openai-chatgpt
uv run pbi-agent config providers auth-status openai-chatgpt

uv run pbi-agent config profiles select chatgpt
uv run pbi-agent web
```

Notes:

- `auth-login` uses the browser flow by default.
- Use `uv run pbi-agent config providers auth-login openai-chatgpt --method device` when you need a device-code fallback.
- Use `auth-refresh` to refresh a stored session and `auth-logout` to delete the local session.
- The provider ID in this example is `openai-chatgpt`; if you omit `--id`, the ID is generated from `--name`.
- Runtime commands use the ChatGPT-backed provider when you select the saved profile or provider. If you only pass `--provider chatgpt` without selecting a saved config, pbi-agent has no Provider ID to load the account session from.

### Web UI Workflow

The browser UI exposes the same flow from **Settings**:

1. Add or edit a **ChatGPT Subscription** provider.
2. Leave **Authentication** as **ChatGPT account** and save it.
3. On the provider card, click **Connect**.
4. Complete the browser sign-in, or switch to **Device code** in the modal if needed.
5. Create or update a model profile that uses that provider, then make it active.

The provider card shows the stored account email, plan label when available, expiry, and `Connect` / `Refresh` / `Disconnect` actions for the saved ChatGPT session.

## GitHub Copilot Subscription

`pbi-agent` can also use a saved GitHub Copilot subscription account. This is implemented as the `github_copilot` provider kind with `copilot_account` auth. It does not use an API key; runtime requests are authorized with the locally stored Copilot OAuth session for the saved Provider ID.

| Setting | Value |
| --- | --- |
| Select it | saved provider kind `github_copilot`, `--provider github_copilot`, or `PBI_AGENT_PROVIDER=github_copilot` |
| Auth mode | `copilot_account` |
| Login method | device-code flow only |
| Endpoint | built in: `https://api.githubcopilot.com/responses` for OpenAI-family models, `https://api.githubcopilot.com/chat/completions` for other Copilot models |
| Default model | `gpt-5.4` |
| Default sub-model | `gpt-5-mini` |
| Model override | `--model` or `PBI_AGENT_MODEL` |
| History mode | Client-side full message replay |
| Image input | Supported |

The provider chooses its wire protocol from the model name: model IDs beginning with `gpt-`, `o1`, `o3`, or `o4` use the Copilot Responses endpoint; other model IDs use the Copilot Chat Completions endpoint.

### CLI Workflow

Create a saved GitHub Copilot provider, create a model profile that points at it, complete the device-code sign-in flow, then select that profile for runtime use:

```bash
uv run pbi-agent config providers create \
  --id github-copilot \
  --name "GitHub Copilot" \
  --kind github_copilot \
  --auth-mode copilot_account

uv run pbi-agent config profiles create \
  --name copilot \
  --provider-id github-copilot \
  --model gpt-5.4 \
  --sub-agent-model gpt-5-mini

uv run pbi-agent config providers auth-login github-copilot --method device
uv run pbi-agent config providers auth-status github-copilot

uv run pbi-agent config profiles select copilot
uv run pbi-agent web
```

Notes:

- GitHub Copilot account auth supports the device-code flow only, so `--method device` is the normal path.
- The stored Copilot session does not support refresh; use `auth-login ... --method device` again to reconnect, or `auth-logout` to delete the local session.
- The provider ID in this example is `github-copilot`; if you omit `--id`, the ID is generated from `--name`.
- Runtime commands use the Copilot-backed provider when you select the saved profile or provider. If you only pass `--provider github_copilot` without selecting a saved config, pbi-agent has no Provider ID to load the account session from.

### Web UI Workflow

The browser UI exposes the same flow from **Settings**:

1. Add or edit a **GitHub Copilot (Subscription)** provider.
2. Leave **Authentication** as **GitHub Copilot account** and save it.
3. On the provider card, click **Connect**.
4. Complete the device-code sign-in shown in the modal.
5. Create or update a model profile that uses that provider, then make it active.

The provider card shows the stored account label and `Connect` / `Disconnect` actions for the saved Copilot session. Because Copilot sessions do not refresh through pbi-agent, reconnect by running the login flow again.

## Azure

| Setting | Value |
| --- | --- |
| Select it | `--provider azure` or `PBI_AGENT_PROVIDER=azure` |
| API key | `--api-key`, `PBI_AGENT_API_KEY`, or `AZURE_API_KEY` |
| Endpoint override | required: `--responses-url` or `PBI_AGENT_RESPONSES_URL` |
| Default model | `gpt-4.1` |
| Default sub-model | `gpt-4.1-mini` |
| Model override | `--model` or `PBI_AGENT_MODEL` |
| History mode | Server-side via `previous_response_id` for Responses endpoints; client-side full message replay for Chat Completions or Anthropic Messages endpoints |
| Image input | Supported |

Azure model names are deployment names. Set `--model` and `--sub-agent-model` to the deployment names configured on your Azure resource.

The Azure provider routes by the path in `--responses-url`:

| Endpoint path | Backend used |
| --- | --- |
| `/openai/v1/responses` | OpenAI Responses-compatible provider |
| `/openai/v1/chat/completions` or another `/openai/v1` base URL | OpenAI-compatible Chat Completions provider |
| `/anthropic/v1/messages` | Anthropic Messages-compatible provider |

```bash
export AZURE_API_KEY="..."
uv run pbi-agent \
  --provider azure \
  --responses-url https://my-resource.openai.azure.com/openai/v1/responses \
  --model my-gpt-4-1-deployment \
  --sub-agent-model my-gpt-4-1-mini-deployment \
  web
```

Saved config works the same way:

```bash
uv run pbi-agent config providers create \
  --name "Azure OpenAI" \
  --kind azure \
  --api-key-env AZURE_API_KEY \
  --responses-url https://my-resource.openai.azure.com/openai/v1/responses

uv run pbi-agent config profiles create \
  --name azure-main \
  --provider-id azure-openai \
  --model my-gpt-4-1-deployment \
  --sub-agent-model my-gpt-4-1-mini-deployment

uv run pbi-agent config profiles select azure-main
uv run pbi-agent web
```

::: tip
For Azure Chat Completions, you can pass either the full `/openai/v1/chat/completions` URL or the `/openai/v1` base URL; `pbi-agent` appends `/chat/completions` when needed.
:::

## xAI

| Setting | Value |
| --- | --- |
| Select it | `--provider xai` or `PBI_AGENT_PROVIDER=xai` |
| API key | `--api-key`, `PBI_AGENT_API_KEY`, or `XAI_API_KEY` |
| Endpoint override | `--responses-url` or `PBI_AGENT_RESPONSES_URL` |
| Default model | `grok-4.20` |
| Default sub-model | `grok-4-1-fast` |
| Model override | `--model` or `PBI_AGENT_MODEL` |
| History mode | Server-side via `previous_response_id` |
| Image input | Not enabled in this build |

```bash
export XAI_API_KEY="xai-..."
uv run pbi-agent --provider xai run --prompt "Summarize the main folders and scripts in this repository."
```

## Google

| Setting | Value |
| --- | --- |
| Select it | `--provider google` or `PBI_AGENT_PROVIDER=google` |
| API key | `--api-key`, `PBI_AGENT_API_KEY`, or `GEMINI_API_KEY` |
| Endpoint override | `--responses-url` or `PBI_AGENT_RESPONSES_URL` |
| Default model | `gemini-3.1-pro-preview` |
| Default sub-model | `gemini-3-flash-preview` |
| Model override | `--model` or `PBI_AGENT_MODEL` |
| History mode | Server-side via `previous_interaction_id` |
| Image input | Supported |

```bash
export GEMINI_API_KEY="AIza..."
uv run pbi-agent --provider google web
```

## Google Cloud Vertex AI

Use `google_gcp` when you want to run Vertex AI models through Google Cloud
auth, project, and location settings. The provider chooses a wire protocol from
the model ID:

| Model pattern | Vertex API shape |
| --- | --- |
| `gemini...` or `google/gemini...` | Gemini `generateContent` |
| `grok...` or `xai/...` | OpenAI Responses-compatible endpoint |
| `claude...` or `anthropic/...` | Anthropic Messages-compatible `rawPredict` endpoint |
| Other publisher IDs containing `/`, such as `deepseek-ai/deepseek-v3.1-maas` | OpenAI Chat Completions-compatible endpoint |

Set `PBI_AGENT_GOOGLE_GCP_SHAPE` to `gemini_generate_content`,
`openai_chat_completions`, `openai_responses`, or `anthropic_messages` when you
need to override automatic model routing.

| Setting | Value |
| --- | --- |
| Select it | `--provider google_gcp` or `PBI_AGENT_PROVIDER=google_gcp` |
| OAuth2 / ADC auth | `--api-key` with an OAuth2 access token, `PBI_AGENT_API_KEY`, `GOOGLE_CLOUD_ACCESS_TOKEN`, or ADC via `gcloud auth application-default print-access-token` |
| Gemini API-key auth | saved API key/env or one of `GOOGLE_API_KEY`, `GEMINI_API_KEY`, `GOOGLE_CLOUD_API_KEY`, `VERTEX_AI_API_KEY`, `VERTEX_API_KEY`; sent as `x-goog-api-key` for Gemini express mode |
| Project | `--google-cloud-project`, `PBI_AGENT_GOOGLE_CLOUD_PROJECT`, `GOOGLE_CLOUD_PROJECT`, or `GOOGLE_CLOUD_PROJECT_ID` |
| Location | `--google-cloud-location`, `PBI_AGENT_GOOGLE_CLOUD_LOCATION`, `PBI_AGENT_GOOGLE_CLOUD_REGION`, `GOOGLE_CLOUD_LOCATION`, or `GOOGLE_CLOUD_REGION`; defaults to `global` |
| Endpoint override | `--responses-url` or `PBI_AGENT_RESPONSES_URL` |
| Default model | `gemini-2.5-flash` |
| Default sub-model | `gemini-2.5-flash` |
| Model override | `--model` or `PBI_AGENT_MODEL` |
| History mode | Client-side full message replay |
| Image input | Supported for Gemini `generateContent` models; not enabled for the xAI/OpenAI-compatible Responses shape in this build |

ADC setup with a saved provider/profile:

```bash
gcloud auth application-default login

uv run pbi-agent config providers create \
  --id vertex-ai \
  --name "Google Cloud Vertex AI" \
  --kind google_gcp \
  --google-cloud-project my-project \
  --google-cloud-location global

uv run pbi-agent config profiles create \
  --name vertex-gemini \
  --provider-id vertex-ai \
  --model gemini-2.5-flash \
  --sub-agent-model gemini-2.5-flash

uv run pbi-agent config profiles select vertex-gemini
uv run pbi-agent web
```

Gemini express-mode API keys can be used for Gemini models. Include project and
location when possible so pbi-agent can retry with OAuth2/ADC if Google rejects
the API-key token type:

```bash
export GEMINI_API_KEY="AIza..."

uv run pbi-agent config providers create \
  --id vertex-gemini-key \
  --name "Vertex Gemini API key" \
  --kind google_gcp \
  --api-key-env GEMINI_API_KEY \
  --google-cloud-project my-project \
  --google-cloud-location global
```

OpenAI-compatible and Anthropic Vertex endpoints require OAuth2 bearer auth or
ADC; API-key auth is only used for Gemini express-mode requests.

## Anthropic

| Setting | Value |
| --- | --- |
| Select it | `--provider anthropic` or `PBI_AGENT_PROVIDER=anthropic` |
| API key | `--api-key`, `PBI_AGENT_API_KEY`, or `ANTHROPIC_API_KEY` |
| Endpoint override | not currently supported; the provider posts to `https://api.anthropic.com/v1/messages` |
| Default model | `claude-opus-4-6` |
| Default sub-model | `claude-sonnet-4-6` |
| Model override | `--model` or `PBI_AGENT_MODEL` |
| History mode | Client-side full message replay |
| Image input | Supported in live sessions; resumed sessions replay only persisted text history |

```bash
export ANTHROPIC_API_KEY="sk-ant-..."
uv run pbi-agent --provider anthropic web
```

## Generic

| Setting | Value |
| --- | --- |
| Select it | `--provider generic` or `PBI_AGENT_PROVIDER=generic` |
| API key | `--api-key`, `PBI_AGENT_API_KEY`, or `GENERIC_API_KEY` |
| Endpoint override | `--generic-api-url` or `PBI_AGENT_GENERIC_API_URL` |
| Default model | none; the request omits `model` when unset |
| Default sub-model | none; `sub_agent` also omits `model` when unset |
| Model override | `--model` or `PBI_AGENT_MODEL` |
| History mode | Client-side full message replay |
| Image input | Not enabled in this build |

```bash
export GENERIC_API_KEY="or-..."
uv run pbi-agent \
  --provider generic \
  --generic-api-url https://openrouter.ai/api/v1/chat/completions \
  --model openai/gpt-5.4 \
  run --prompt "Summarize the measures in this model."
```

::: tip
For the Generic backend, leaving `--model` unset is intentional when you want the upstream router to pick the model.
:::

## Related pages

- [Speech-to-text](/speech-to-text)
- [Model Profiles](/model-profiles)
- [Environment Variables](/environment)
