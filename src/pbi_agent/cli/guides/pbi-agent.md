# pbi-agent

Local CLI and browser-based coding agent for workspace tasks. This guide covers global options, how runtime settings are resolved, and an index of every command.

## Overview
pbi-agent runs an agent loop against an LLM provider and gives it tools that act on the current working directory (the workspace): file edits (`apply_patch`), `shell`, `sub_agent`, image reading, web fetch, plus project MCP servers. Workspaces are customized with project-local files under `.agents/` (skills, commands, sub-agents, hooks, `mcp.json`) and an `AGENTS.md` instruction file.

Provider backends: OpenAI (Responses API), Azure, ChatGPT subscription, GitHub Copilot subscription, xAI, Google Gemini, Google Cloud Vertex AI (`google_gcp`), Anthropic (Messages API), and any generic OpenAI-compatible Chat Completions endpoint.

There are two ways to run the agent:
- `pbi-agent web` serves the browser UI (chat, Kanban board, settings). It is the default command: `pbi-agent` with no command runs `web`.
- `pbi-agent run -p "..."` runs one prompt turn in the terminal and exits, for scripts and automation.

Everything else manages the workspace (`init`, `skills`, `commands`, `agents`, `kits`, `hooks`, `kanban`, `channels`), saved user-level configuration (`config`), past sessions (`sessions`), the Docker sandbox (`sandbox`) and the installation itself (`upgrade`).

User-level data lives in `~/.pbi-agent/`: `config.json` (saved providers, profiles, maintenance), `sessions.db` (sessions, Kanban, channel and skill state) and account auth sessions. Nothing internal is written to the workspace.

## Usage
```text
pbi-agent [GLOBAL OPTIONS] [<command>] [COMMAND OPTIONS]
pbi-agent [GLOBAL OPTIONS] <command> [<subcommand> ...] --doc
```

Global options go before the command name. Command options go after it.

## Global options
Global options are accepted before any command, but only `run` (and `sandbox`, which forwards them into the container) uses the provider and model options. `web` rejects them; see Pitfalls.

General:
- `-h, --help`: print argparse help and exit.
- `-v, --version`: print the installed version and exit.
- `--doc`: print this guide and exit. Every command and subcommand also takes `--doc`.

Provider and API:
- `--provider PROVIDER`: runtime backend, one of `openai`, `azure`, `xai`, `google`, `google_gcp`, `anthropic`, `generic`. Env `PBI_AGENT_PROVIDER`. Default: the selected profile's provider, else `openai`. Account-based kinds (`chatgpt`, `github_copilot`) are used through saved providers and profiles.
- `--responses-url RESPONSES_URL`: override the provider API URL (Responses, Interactions, or Vertex endpoint). Env `PBI_AGENT_RESPONSES_URL`.
- `--google-cloud-project GOOGLE_CLOUD_PROJECT`: Google Cloud project ID for `google_gcp`. Env `PBI_AGENT_GOOGLE_CLOUD_PROJECT`.
- `--google-cloud-location, --google-cloud-region GOOGLE_CLOUD_LOCATION`: Vertex AI location for `google_gcp`. Env `PBI_AGENT_GOOGLE_CLOUD_LOCATION` or `PBI_AGENT_GOOGLE_CLOUD_REGION`.
- `--api-key API_KEY`: API key override. Env `PBI_AGENT_API_KEY`. Hidden per-provider aliases (such as `--openai-api-key`) set the same value and are not shown in `--help`.
- `--generic-api-url GENERIC_API_URL`: Chat Completions URL for the `generic` backend. Env `PBI_AGENT_GENERIC_API_URL`. Default `https://openrouter.ai/api/v1/chat/completions`.

Model behavior:
- `--profile-id PROFILE_ID`: select a saved model profile as the base before explicit overrides are applied. Env `PBI_AGENT_PROFILE_ID`.
- `--model MODEL`: main model. Env `PBI_AGENT_MODEL`. Default: profile model, else a per-provider default (none for `generic`, which then omits the model from requests).
- `--sub-agent-model SUB_AGENT_MODEL`: model for `sub_agent` children. Env `PBI_AGENT_SUB_AGENT_MODEL`. Default: the profile's sub-agent model, else the profile main model; with no profile, a per-provider sub-agent default.
- `--max-tokens MAX_TOKENS`: max output tokens. Env `PBI_AGENT_MAX_TOKENS`. Default `16384`.
- `--reasoning-effort LEVEL`: reasoning effort (common values `low`, `medium`, `high`, `xhigh`; provider-specific values are accepted). Env `PBI_AGENT_REASONING_EFFORT`. Default `medium`.
- `--service-tier TIER`: OpenAI service tier, one of `auto`, `default`, `flex`, `priority`. Env `PBI_AGENT_SERVICE_TIER`. Only valid with the OpenAI provider.

Runtime and resilience:
- `--max-tool-workers MAX_TOOL_WORKERS`: parallel tool workers. Env `PBI_AGENT_MAX_TOOL_WORKERS`. Default `4`.
- `--max-retries MAX_RETRIES`: retries for transient failures and rate limits. Env `PBI_AGENT_MAX_RETRIES`. Default `3`.
- `--compact-threshold COMPACT_THRESHOLD`: context compaction token threshold. Env `PBI_AGENT_COMPACT_THRESHOLD`. Default `200000`.
- `--compact-tail-turns COMPACT_TAIL_TURNS`: recent user turns kept verbatim after compaction. Env `PBI_AGENT_COMPACT_TAIL_TURNS`. Default `2`.
- `--compact-preserve-recent-tokens COMPACT_PRESERVE_RECENT_TOKENS`: token budget for the preserved recent tail. Env `PBI_AGENT_COMPACT_PRESERVE_RECENT_TOKENS`. Default `8000`.
- `--compact-tool-output-max-chars COMPACT_TOOL_OUTPUT_MAX_CHARS`: max characters per tool-result string in compaction prompts. Env `PBI_AGENT_COMPACT_TOOL_OUTPUT_MAX_CHARS`. Default `2000`.

Diagnostics:
- `--verbose`: verbose logs.
- `--dangerously-bypass-hook-trust`: run untrusted or modified command hooks without review. Env `PBI_AGENT_DANGEROUSLY_BYPASS_HOOK_TRUST`. Automation only.
- `--mcp`: list the project MCP servers discovered under `.agents/` (from `.agents/mcp.json`) and exit.
- `--agents`: list the enabled project sub-agents from `.agents/agents/*.md` and exit.

## Settings resolution
Settings are resolved only by the commands that need a provider (`run` and `web`; `sandbox` forwards global options into its container), after argument parsing. `--help` and `--doc` never resolve settings.

For `run`, resolution works in two phases:
1. Pick a base profile: `--profile-id`, then `PBI_AGENT_PROFILE_ID`, then the saved default profile (`pbi-agent config profiles select`). An unknown profile ID, or a profile whose provider is missing, is an error (exit 2). With no profile at all, built-in defaults are the base.
2. Resolve each field separately, first match wins: CLI flag, then its `PBI_AGENT_*` env var, then the selected profile and its saved provider (provider fields only apply when the resolved provider kind matches), then the built-in default.

API keys (for providers in `api_key` auth mode) follow: `--api-key`, then `PBI_AGENT_API_KEY`, then the provider-specific env var (`OPENAI_API_KEY`, `AZURE_API_KEY`, `XAI_API_KEY`, `GEMINI_API_KEY`, `ANTHROPIC_API_KEY`, `GENERIC_API_KEY`), then the saved provider's `api_key_env` variable, then its saved `api_key`. Account-based auth modes use the stored auth session instead (`pbi-agent config providers auth-login`).

Settings resolution calls `load_dotenv()` (python-dotenv) first, so a `.env` file can supply these environment variables; variables already set in the environment win.

`web` does not use runtime flags: it uses the saved default profile (selected in the web Settings or with `pbi-agent config profiles select`). If none is selected, the server still starts and the UI asks you to configure one. Saved configuration is written only by `pbi-agent config ...` commands and by the web UI Settings page (providers, model profiles, default profile, maintenance); `run` and starting `web` only read it, so the file can change while a web server is running.

## Commands
Agent runtime:
- `pbi-agent web`: serve the browser UI (the default command).
- `pbi-agent run`: run one prompt turn in the terminal.
- `pbi-agent sandbox`: run pbi-agent inside a Docker Desktop sandbox (defaults to `sandbox web`).
  - `pbi-agent sandbox web`: serve the browser UI from the sandbox.
  - `pbi-agent sandbox run`: run one prompt turn in the sandbox.
- `pbi-agent sessions`: list past sessions for the current directory.

Workspace setup:
- `pbi-agent init`: create a starter `AGENTS.md`.
- `pbi-agent skills`: list, enable, disable or install project skills.
  - `pbi-agent skills list`, `pbi-agent skills enable`, `pbi-agent skills disable`, `pbi-agent skills add`.
- `pbi-agent commands`: list or install project commands.
  - `pbi-agent commands list`, `pbi-agent commands add`.
- `pbi-agent agents`: list or install project sub-agents.
  - `pbi-agent agents list`, `pbi-agent agents add`.
- `pbi-agent kits`: install kits (skills, commands, sub-agents, MCP servers, instructions).
  - `pbi-agent kits add`.
- `pbi-agent hooks`: list command hooks and review them (lists when no action is given).
  - `pbi-agent hooks trust`, `pbi-agent hooks enable`, `pbi-agent hooks disable`.

Workspace data:
- `pbi-agent kanban`: manage Kanban board tasks.
  - `pbi-agent kanban create`, `pbi-agent kanban list`.
- `pbi-agent channels`: show and configure chat channels.
  - `pbi-agent channels show`: show all channel settings.
  - `pbi-agent channels telegram`: manage the Telegram channel.
    - `pbi-agent channels telegram show`, `pbi-agent channels telegram configure`, `pbi-agent channels telegram restart`.

Saved configuration (`~/.pbi-agent/config.json`):
- `pbi-agent config`: manage saved maintenance, providers and model profiles.
  - `pbi-agent config maintenance`: retention settings.
    - `pbi-agent config maintenance show`, `pbi-agent config maintenance set`.
  - `pbi-agent config providers`: saved provider connections.
    - `pbi-agent config providers list`, `pbi-agent config providers create`, `pbi-agent config providers update`, `pbi-agent config providers delete`.
    - `pbi-agent config providers auth-status`, `pbi-agent config providers auth-login`, `pbi-agent config providers auth-import`, `pbi-agent config providers auth-refresh`, `pbi-agent config providers auth-logout`, `pbi-agent config providers usage-limits`.
  - `pbi-agent config profiles`: saved model profiles.
    - `pbi-agent config profiles list`, `pbi-agent config profiles create`, `pbi-agent config profiles update`, `pbi-agent config profiles delete`, `pbi-agent config profiles select`.

Installation:
- `pbi-agent upgrade`: upgrade pbi-agent from PyPI. `pbi-agent update` is an alias.

## Examples
```bash
# Start the browser UI for the current directory
pbi-agent

# One scripted turn with a saved profile
pbi-agent --profile-id work run -p "Summarize the open TODO items in this repo"

# One turn with explicit provider settings (key read from ANTHROPIC_API_KEY)
pbi-agent --provider anthropic --model claude-sonnet-4-6 run -p "Explain src/main.py"

# Inspect the workspace setup
pbi-agent --mcp
pbi-agent --agents

# Read the guide of any command
pbi-agent config providers create --doc
```

## Getting more detail
- `pbi-agent --doc` prints this guide.
- `pbi-agent <command> --doc` prints a command guide, and `pbi-agent <command> <subcommand> ... --doc` prints a subcommand guide at any depth (for example `pbi-agent channels telegram configure --doc`). Parent guides list their subcommands with the matching `--doc` command.
- Put `--doc` after the deepest command name: `pbi-agent --doc run` prints this root guide, not the `run` guide.
- `--doc` works like `--help`: it exits during argument parsing, so required arguments are not needed and nothing else runs (no server, provider call, config write or network). It needs no saved config or API key.
- Aliases show the guide of their target: `pbi-agent update --doc` prints the `upgrade` guide.
- Output is plain Markdown on stdout with no colors or pager, so it can be saved: `pbi-agent run --doc > run-guide.md`.
- `pbi-agent <command> --help` prints the shorter argparse option list.

## Pitfalls
- Global options must come before the command: `pbi-agent --model gpt-5.4 run -p "..."` works, `pbi-agent run --model gpt-5.4 -p "..."` is a usage error (exit 2).
- Runtime provider/model flags (`--provider`, `--model`, `--profile-id`, `--api-key`, `--max-tokens`, `--reasoning-effort`, and so on) are rejected for `web`, including the implicit `web` of a bare `pbi-agent --model x`: exit 2. Use a saved profile for the web UI.
- `--mcp` and `--agents` run before any command, so `pbi-agent --mcp run -p "..."` only prints the MCP list.
- The root parser does not accept abbreviated options. Subcommands do, so `--d` is ambiguous where a command also has `--dev`, `--detach` or `--disable`; spell options out.
- Every command except `--help`, `--doc` and `--version` first runs startup maintenance. At most once per UTC day it purges data older than the retention window (`pbi-agent config maintenance`) and checks PyPI for a newer release (not for `upgrade`, which checks itself).
- Exit codes: `0` success, `2` usage or configuration error; some commands document other codes (for example `pbi-agent upgrade --check` returns `100` when an update is available).
