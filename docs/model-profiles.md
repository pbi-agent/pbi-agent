---
title: 'Model Profiles'
description: 'Saved model profiles, runtime resolution, profile selection, and profile fields.'
---

# Model Profiles

A model profile is a saved runtime preset tied to one saved provider. Providers answer “how do I connect?”; model profiles answer “what model and runtime settings should this run use?”

## Providers vs profiles

| Entity | Stores | Examples |
| --- | --- | --- |
| Provider | Connection settings | provider kind, API key, ChatGPT or GitHub Copilot account auth, Azure endpoint, generic API URL |
| Model Profile | Runtime settings | model, sub-agent model, reasoning effort, max tokens, web search, retries, compaction threshold |

This separation lets you create multiple profiles for the same provider, such as `fast`, `analysis`, `review`, or `azure-prod`.

## Create a profile in the web UI

1. Open **Settings**.
2. Add at least one provider.
3. In **Model Profiles**, choose **Add Profile**.
4. Select the provider.
5. Choose or enter the model.
6. Set optional runtime fields.
7. Save the profile.
8. Select it as **Active default** if you want new sessions and runs to use it automatically.

The profile selector in the Sessions page can override the active default for the current live session.

## Create a profile from the CLI

```bash
pbi-agent config providers create \
  --name "OpenAI Main" \
  --kind openai \
  --api-key "$OPENAI_API_KEY"

pbi-agent config profiles create \
  --name analysis \
  --provider-id openai-main \
  --model gpt-5.4 \
  --sub-agent-model gpt-5.4-mini \
  --reasoning-effort xhigh \
  --max-tool-workers 4

pbi-agent config profiles select analysis
```

## Runtime resolution order

When a runtime command starts, pbi-agent resolves settings in two phases:

1. Select a base model profile from `--profile-id`, then `PBI_AGENT_PROFILE_ID`, then the saved active default profile.
2. Compile that profile with its provider, then overlay explicit CLI flags and environment variables.

If no profile is selected, pbi-agent falls back to CLI flags, environment variables, and provider defaults.

## Profile fields

| Field | Purpose |
| --- | --- |
| Name | Human-readable label shown in Settings, Sessions, and board configuration. |
| ID | Stable identifier used by CLI flags and saved records. If omitted on create, it is generated from the name. |
| Provider | Saved provider this profile uses for connection/auth settings. |
| Model | Main model for normal turns. Empty means provider default. |
| Sub-agent model | Model used by the `sub_agent` tool. Empty falls back to the profile's main model/default behavior. |
| Reasoning effort | Optional provider-level reasoning setting: `low`, `medium`, `high`, or `xhigh`. |
| Max tokens | Provider output-token cap. Empty means the project default. |
| Service tier | OpenAI-only service tier such as `auto`, `default`, `flex`, or `priority`. |
| Web search | Enables or disables provider-native web search when supported. |
| Max tool workers | Maximum number of local tool calls that can execute in parallel. |
| Max retries | Retry count for transient provider failures. |
| Compact threshold | Context-token threshold for automatic compaction where supported. |

## Model discovery and custom values

For providers that support model discovery, the profile form can show a model dropdown. You can switch to **Custom value** whenever you need a model ID that is not listed yet.

Azure uses deployment names as model values, so enter your Azure deployment name manually.

## Active default profile

The active default profile is used by:

- New web sessions when no explicit profile is selected.
- `pbi-agent run` when no `--profile-id` or environment override is provided.
- Kanban task runs when neither the task nor its stage specifies a profile.

You can clear the active default in Settings by choosing **No default**.

## Profile overrides by workflow

| Workflow | Override location |
| --- | --- |
| One CLI run | `--profile-id PROFILE_ID` |
| Environment default | `PBI_AGENT_PROFILE_ID=PROFILE_ID` |
| Web session | Profile selector in the session header |
| Kanban stage | Stage profile in the board editor |
| Kanban task | Task profile override in the task modal |

## Related pages

- [Providers](/providers)
- [Web UI](/web-ui)
- [Kanban Dashboard](/kanban-dashboard)
- [Environment Variables](/environment)
