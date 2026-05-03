---
title: 'CLI Reference'
description: 'Commands, global options, and runtime defaults for pbi-agent.'
---

# CLI Reference

`pbi-agent` uses `argparse`, so `-h` and `--help` are available at the root and on every subcommand.

::: tip
If you run `pbi-agent` without a command, the CLI inserts `web` automatically. Global-option-only invocations such as `pbi-agent --api-key ...` therefore launch the browser UI.
:::

## Global Options

| Flag | Env Var | Default | Description |
| --- | --- | --- | --- |
| `--provider` | `PBI_AGENT_PROVIDER` | `openai` | LLM provider backend: `openai`, `azure`, `chatgpt`, `github_copilot`, `xai`, `google`, `anthropic`, or `generic`. |
| `--profile-id` | `PBI_AGENT_PROFILE_ID` | none | Select a saved model profile by ID before explicit CLI and env overrides are applied. |
| `--api-key` | `PBI_AGENT_API_KEY` | none | Shared API key override. If unset, provider-specific fallback env vars are checked. |
| `--model` | `PBI_AGENT_MODEL` | per-provider | Model override for the selected provider. Generic omits `model` when this is unset. |
| `--sub-agent-model` | `PBI_AGENT_SUB_AGENT_MODEL` | per-provider sub-model | Optional model override for `sub_agent`. When unset, child agents use the provider-specific sub-agent default from `config.py`. |
| `--max-tokens` | `PBI_AGENT_MAX_TOKENS` | `16384` | Max output tokens for the selected provider. |
| `--reasoning-effort` | `PBI_AGENT_REASONING_EFFORT` | `xhigh` for OpenAI; `high` otherwise | Requested reasoning effort: `low`, `medium`, `high`, or `xhigh`. |
| `--max-tool-workers` | `PBI_AGENT_MAX_TOOL_WORKERS` | `4` | Maximum parallel workers for tool execution. |
| `--max-retries` | `PBI_AGENT_MAX_RETRIES` | `3` | Maximum retries for transient provider failures and rate limits. |
| `--compact-threshold` | `PBI_AGENT_COMPACT_THRESHOLD` | `200000` | Context compaction threshold sent to OpenAI. |
| `--responses-url` | `PBI_AGENT_RESPONSES_URL` | provider-specific | Override the Responses or Interactions endpoint for OpenAI API, ChatGPT, GitHub Copilot, Azure, xAI, or Google. Ignored by Anthropic and Generic. |
| `--generic-api-url` | `PBI_AGENT_GENERIC_API_URL` | `https://openrouter.ai/api/v1/chat/completions` | Override the OpenAI-compatible Chat Completions endpoint used by the Generic backend. |
| `--service-tier` | `PBI_AGENT_SERVICE_TIER` | none | OpenAI service tier for request processing: `auto`, `default`, `flex`, or `priority`. Only valid with the OpenAI provider. |
| `--no-web-search` | none | `false` | Disable the provider's native web search tool when that backend supports it. |
| `--verbose` | none | `false` | Enable verbose logging. |
| `--mcp` | none | `false` | List discovered project MCP servers from `.agents/mcp.json` and exit. |
| `--agents` | none | `false` | List discovered project sub-agents from `.agents/agents/*.md` and exit. |

Saved config is only mutated by `pbi-agent config ...` commands. Runtime entry points such as `run` and `web` resolve settings but do not rewrite saved providers or profiles.

Per-provider model defaults:

| Provider | Default model | Default sub-model |
| --- | --- | --- |
| OpenAI API | `gpt-5.4` | `gpt-5.4-mini` |
| Azure | `gpt-4.1` | `gpt-4.1-mini` |
| ChatGPT subscription | `gpt-5.4` | `gpt-5.4-mini` |
| GitHub Copilot subscription | `gpt-5.4` | `gpt-5-mini` |
| xAI | `grok-4.20` | `grok-4-1-fast` |
| Google | `gemini-3.1-pro-preview` | `gemini-3-flash-preview` |
| Anthropic | `claude-opus-4-6` | `claude-sonnet-4-6` |
| Generic | none | none |

## Hidden API-Key Aliases

These flags exist in the parser but are suppressed from help output:

| Flag | Equivalent |
| --- | --- |
| `--openai-api-key` | `--api-key` |
| `--xai-api-key` | `--api-key` |
| `--google-api-key` | `--api-key` |
| `--anthropic-api-key` | `--api-key` |
| `--generic-api-key` | `--api-key` |

## `pbi-agent skills`

List installed project skills or install new ones into `.agents/skills/`.

```bash
pbi-agent skills list
pbi-agent skills add
pbi-agent skills add --skill openai-docs
pbi-agent skills add ./skills/local-skill
pbi-agent skills add owner/private-repo --skill custom-review
```

### `pbi-agent skills list`

Lists the currently installed project-local skills discovered under `.agents/skills/`.

### `pbi-agent skills add [source]`

Installs a skill bundle from the official catalog, a local directory, or a GitHub repository.

- Omitting `source` uses the official `pbi-agent/skills` catalog from `https://github.com/pbi-agent/skills`.
- `pbi-agent skills add` lists the official catalog and exits.
- `pbi-agent skills add --list` also lists candidate skills from the selected source.
- `pbi-agent skills add --skill NAME` installs one named skill from the selected source.
- Explicit multi-skill sources still require `--skill NAME` for installation.

| Option | Default | Description |
| --- | --- | --- |
| `source` | `pbi-agent/skills` when omitted | Local path, GitHub `owner/repo`, GitHub repository URL, or GitHub tree URL. |
| `--skill NAME` | none | Select one skill from a multi-skill source, or install one skill from the default catalog. |
| `--list` | `false` | List candidate skills from the selected source without installing anything. |
| `--force` | `false` | Replace an existing local install under `.agents/skills/<skill-name>`. |

## `pbi-agent commands`

List installed project commands or install reusable command presets into `.agents/commands/`.

```bash
pbi-agent commands list
pbi-agent commands add
pbi-agent commands add --command execute
pbi-agent commands add ./commands/local
pbi-agent commands add owner/private-repo --command repo-review
```

### `pbi-agent commands list`

Lists the currently installed project-local command files discovered under `.agents/commands/`.

### `pbi-agent commands add [source]`

Installs a command preset from the official catalog, a local path, or a GitHub repository.

- Omitting `source` uses the official `pbi-agent/commands` catalog from `https://github.com/pbi-agent/commands`.
- `pbi-agent commands add` lists the official catalog and exits.
- `pbi-agent commands add --list` also lists candidate commands from the selected source.
- `pbi-agent commands add --command NAME` installs one named command from the selected source.
- Explicit multi-command sources still require `--command NAME` for installation.

| Option | Default | Description |
| --- | --- | --- |
| `source` | `pbi-agent/commands` when omitted | Local path, GitHub `owner/repo`, GitHub repository URL, or GitHub tree URL. |
| `--command NAME` | none | Select one command from a multi-command source, or install one command from the default catalog. |
| `--list` | `false` | List candidate commands from the selected source without installing anything. |
| `--force` | `false` | Replace an existing local install under `.agents/commands/<command-name>.md`. |

Public command catalogs are discovered from `commands/*.md` by default. If a repository keeps command files under `.agents/commands/`, target that directory explicitly with a local path or GitHub tree URL.

## `pbi-agent agents`

List installed project agents or install reusable sub-agent definitions into `.agents/agents/`.

```bash
pbi-agent agents list
pbi-agent agents add
pbi-agent agents add --agent code-reviewer
pbi-agent agents add ./agents/local
pbi-agent agents add owner/private-repo --agent repo-reviewer
```

### `pbi-agent agents list`

Lists the currently installed project-local agent files discovered under `.agents/agents/`.

### `pbi-agent agents add [source]`

Installs an agent definition from the official catalog, a local path, or a GitHub repository.

- Omitting `source` uses the official `pbi-agent/agents` catalog from `https://github.com/pbi-agent/agents`.
- `pbi-agent agents add` lists the official catalog and exits.
- `pbi-agent agents add --list` also lists candidate agents from the selected source.
- `pbi-agent agents add --agent NAME` installs one named agent from the selected source.
- Explicit multi-agent sources still require `--agent NAME` for installation.

| Option | Default | Description |
| --- | --- | --- |
| `source` | `pbi-agent/agents` when omitted | Local path, GitHub `owner/repo`, GitHub repository URL, or GitHub tree URL. |
| `--agent NAME` | none | Select one agent from a multi-agent source, or install one agent from the default catalog. |
| `--list` | `false` | List candidate agents from the selected source without installing anything. |
| `--force` | `false` | Replace an existing local install under `.agents/agents/<agent-name>.md`. |

Public agent catalogs are discovered from `agents/*.md` by default. If a repository keeps agent files under `.agents/agents/`, target that directory explicitly with a local path or GitHub tree URL.

## `pbi-agent kanban`

Create and manage Kanban board tasks for the current workspace.

### `pbi-agent kanban create`

Create a task card from a terminal or automation script:

```bash
pbi-agent kanban create \
  --title "Refactor API endpoint" \
  --desc "Improve and optimize the main API endpoint for faster response time." \
  --lane "In Progress"
```

`kanban create` writes a task card to the same local board used by the web UI. It does not start the task automatically; open the web UI or use future Kanban commands to run or move tasks.

| Option | Default | Description |
| --- | --- | --- |
| `--title TITLE` | required | Task title shown on the card. |
| `--desc DESC` | required | Task description/prompt stored on the card. `--description` and `--prompt` are aliases. |
| `--lane LANE` | first board stage | Existing board stage by ID, name, or slugified name. `--stage` and `--state` are aliases. |
| `--project-dir DIR` | `.` | Workspace-relative project directory for future task runs. The directory must exist and stay inside the current workspace. |
| `--session-id ID` | none | Optional existing session ID to associate with the task. |
| `--json` | `false` | Print a machine-readable created-task payload for scripts. |

`--lane` must refer to an existing board stage. Configure custom stages in the web UI before targeting them from the CLI.

### `pbi-agent kanban list`

List task cards for the current workspace:

```bash
pbi-agent kanban list
pbi-agent kanban list --stage "In Progress"
pbi-agent kanban list --json
```

By default, `kanban list` shows tasks from every stage. Use `--stage` to filter by an existing board stage ID, name, or slugified name; `--lane` and `--state` are aliases. The human-readable output prints task details without truncating the prompt, including ID, title, prompt, stage, position, project directory, associated session/profile IDs, run status, timestamps, last result summary, and image attachment count. Use `--json` for a machine-readable array with the same task fields plus serialized image attachment metadata.

| Option | Default | Description |
| --- | --- | --- |
| `--stage STAGE` | all stages | Only show tasks in an existing board stage by ID, name, or slugified name. `--lane` and `--state` are aliases. |
| `--json` | `false` | Print a machine-readable task array for scripts. |

## `pbi-agent config`

Manage the saved internal config file under `~/.pbi-agent/config.json` (or `PBI_AGENT_INTERNAL_CONFIG_PATH` in tests and custom setups).

```bash
pbi-agent config providers create --name "OpenAI Main" --kind openai
pbi-agent config profiles create --name analysis --provider-id openai-main --model gpt-5.4
pbi-agent config profiles select analysis
```

### `pbi-agent config providers`

Stored providers hold connection-only settings: provider kind, API key, and endpoint overrides.

| Command | Purpose |
| --- | --- |
| `pbi-agent config providers list` | List saved providers. |
| `pbi-agent config providers create --name NAME [--id ID] --kind PROVIDER [--auth-mode api_key|chatgpt_account|copilot_account] [--api-key KEY] [--responses-url URL] [--generic-api-url URL]` | Create a provider. |
| `pbi-agent config providers update ID [--name NAME] [--kind PROVIDER] [--auth-mode api_key|chatgpt_account|copilot_account] [--api-key KEY] [--responses-url URL] [--generic-api-url URL]` | Update a provider by ID. |
| `pbi-agent config providers delete ID` | Delete a provider by ID. Deletion fails while any saved model profile still references it. |
| `pbi-agent config providers auth-status ID` | Show stored account-auth status for a provider. |
| `pbi-agent config providers auth-login ID [--method browser|device]` | Run the built-in browser or device login flow for a provider. |
| `pbi-agent config providers auth-refresh ID` | Refresh a stored account session for a provider. |
| `pbi-agent config providers auth-logout ID` | Delete the stored account session for a provider. |
| `pbi-agent config providers auth-import ID --access-token ...` | Import an account session manually. |

::: details Provider auth notes

- `chatgpt_account` is supported by the `chatgpt` subscription provider.
- `copilot_account` is supported by the `github_copilot` subscription provider.
- The built-in `auth-login` flow stores a local account session under the saved provider ID, so it is intended for saved provider/profile workflows rather than one-off `--provider ...` runs.
- ChatGPT `auth-login` defaults to the browser flow and also supports `--method device`; GitHub Copilot supports the device-code flow only.
- GitHub Copilot sessions do not support `auth-refresh`; reconnect by running `auth-login PROVIDER_ID --method device` again.

:::

### `pbi-agent config profiles`

Stored model profiles hold runnable model and runtime settings tied to one saved provider.

| Command | Purpose |
| --- | --- |
| `pbi-agent config profiles list` | List saved model profiles. |
| `pbi-agent config profiles create --name NAME [--id ID] --provider-id PROVIDER_ID [profile options]` | Create a model profile. |
| `pbi-agent config profiles update ID [--name NAME] [--provider-id PROVIDER_ID] [profile options]` | Update a model profile by ID. |
| `pbi-agent config profiles delete ID` | Delete a model profile by ID. |
| `pbi-agent config profiles select ID` | Set the active model profile used when `--profile-id` and `PBI_AGENT_PROFILE_ID` are absent. |

Profile options: `--model`, `--sub-agent-model`, `--reasoning-effort`, `--max-tokens`, `--service-tier`, `--web-search`, `--no-web-search`, `--max-tool-workers`, `--max-retries`, and `--compact-threshold`.

## `pbi-agent web` (default)

Serve the browser-based UI through the FastAPI web server.

```bash
pbi-agent web --host 127.0.0.1 --port 8000
```

| Option | Default | Description |
| --- | --- | --- |
| `--host` | `127.0.0.1` | Host interface to bind. |
| `--port` | `8000` | Port to bind. Valid range: `1-65535`. |
| `--dev` | `false` | Enable web development mode. |
| `--title` | none | Optional browser title for the served app. |
| `--url` | none | Optional public URL for reverse-proxy or externally published setups. |

::: details URL behavior
When `--url` is omitted, the browser target is derived from `--host` and `--port`. Wildcard binds such as `0.0.0.0` and `::` are converted to loopback URLs for browser launch.
:::

The browser session UI also supports interactive input shortcuts such as `@file` mentions, `!` shell command mode, built-in slash commands like `/skills` and `/compact`, and project slash commands from `.agents/commands/`.

See [Session Commands](/session-commands) for the complete interactive command reference.

## `pbi-agent run`

Execute a single prompt turn and exit.

```bash
pbi-agent run --prompt "Summarize the main modules in this repository."
pbi-agent run --prompt "Read the text in this image." --image ./general_ocr_002.png
```

| Option | Default | Description |
| --- | --- | --- |
| `--prompt` | required | User prompt to send to the agent. |
| `--image` | repeatable, none by default | Attach a local workspace image to the prompt. Paths must stay inside the workspace. |

## Image Input Support

Supported image formats are `.png`, `.jpg`, `.jpeg`, and `.webp`.

| Provider | Explicit image attachments (`--image`, `/image add`) | `read_image` tool |
| --- | --- | --- |
| OpenAI API | yes | yes |
| Azure | yes | yes |
| ChatGPT subscription | yes | yes |
| GitHub Copilot subscription | yes | yes |
| Google | yes | yes |
| Anthropic | yes | yes |
| xAI | no | no |
| Generic | no | no |

For unsupported providers, image input fails fast with a clear error.

::: warning
`skills`, `commands`, `agents`, `sessions`, and `config` do not resolve provider settings or require an API key. Runtime commands still validate provider configuration before they start the session.
:::
