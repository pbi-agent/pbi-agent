---
title: 'CLI Reference'
description: 'Commands, global options, defaults, and audit behavior for pbi-agent.'
layout: doc
outline: [2, 3]
---

# CLI Reference

`pbi-agent` uses `argparse`, so `-h` and `--help` are available at the root and on every subcommand.

::: tip
If you run `pbi-agent` without a command, the CLI inserts `web` automatically. Global-option-only invocations such as `pbi-agent --api-key ...` therefore launch the browser UI.
:::

## Global Options

| Flag | Env Var | Default | Description |
| --- | --- | --- | --- |
| `--provider` | `PBI_AGENT_PROVIDER` | `openai` | LLM provider backend: `openai`, `xai`, `google`, `anthropic`, or `generic`. |
| `--api-key` | `PBI_AGENT_API_KEY` | none | Shared API key override. If unset, provider-specific fallback env vars are checked. |
| `--model` | `PBI_AGENT_MODEL` | per-provider | Model override for the selected provider. Generic omits `model` when this is unset. |
| `--max-tokens` | `PBI_AGENT_MAX_TOKENS` | `16384` | Max output tokens for the selected provider. |
| `--reasoning-effort` | `PBI_AGENT_REASONING_EFFORT` | `xhigh` for OpenAI; `high` otherwise | Requested reasoning effort: `low`, `medium`, `high`, or `xhigh`. |
| `--max-tool-workers` | `PBI_AGENT_MAX_TOOL_WORKERS` | `4` | Maximum parallel workers for tool execution. |
| `--max-retries` | `PBI_AGENT_MAX_RETRIES` | `3` | Maximum retries for transient provider failures and rate limits. |
| `--compact-threshold` | `PBI_AGENT_COMPACT_THRESHOLD` | `150000` | Context compaction threshold sent to OpenAI. |
| `--responses-url` | `PBI_AGENT_RESPONSES_URL` | provider-specific | Override the Responses or Interactions endpoint for OpenAI, xAI, or Google. Ignored by Anthropic and Generic. |
| `--generic-api-url` | `PBI_AGENT_GENERIC_API_URL` | `https://openrouter.ai/api/v1/chat/completions` | Override the OpenAI-compatible Chat Completions endpoint used by the Generic backend. |
| `--verbose` | none | `false` | Enable verbose logging. |

Per-provider model defaults:

| Provider | Default model |
| --- | --- |
| OpenAI | `gpt-5.4-2026-03-05` |
| xAI | `grok-4-1-fast-reasoning` |
| Google | `gemini-3.1-flash-lite-preview` |
| Anthropic | `claude-opus-4-6` |
| Generic | none |

## Hidden API-Key Aliases

These flags exist in the parser but are suppressed from help output:

| Flag | Equivalent |
| --- | --- |
| `--openai-api-key` | `--api-key` |
| `--xai-api-key` | `--api-key` |
| `--google-api-key` | `--api-key` |
| `--anthropic-api-key` | `--api-key` |
| `--generic-api-key` | `--api-key` |

## `pbi-agent web` (default)

Serve the browser-based UI through Textual's web server.

```bash
pbi-agent web --host 127.0.0.1 --port 8000
```

| Option | Default | Description |
| --- | --- | --- |
| `--host` | `127.0.0.1` | Host interface to bind. |
| `--port` | `8000` | Port to bind. Valid range: `1-65535`. |
| `--dev` | `false` | Enable Textual web dev mode. |
| `--title` | none | Optional browser title passed to the web server. |
| `--url` | none | Optional public URL for reverse-proxy or externally published setups. |

::: details URL behavior
When `--url` is omitted, the browser target is derived from `--host` and `--port`. Wildcard binds such as `0.0.0.0` and `::` are converted to loopback URLs for browser launch.
:::

## `pbi-agent console`

Run the interactive terminal UI.

```bash
pbi-agent console
```

This command has no command-specific flags. It uses the global provider, model, and runtime options.

## `pbi-agent run`

Execute a single prompt turn and exit.

```bash
pbi-agent run --prompt "Summarize the tables in this model."
```

| Option | Default | Description |
| --- | --- | --- |
| `--prompt` | required | User prompt to send to the agent. |

## `pbi-agent audit`

Run report audit mode and write markdown output into the selected PBIP directory.

```bash
pbi-agent audit --report-dir .
```

| Option | Default | Description |
| --- | --- | --- |
| `--report-dir` | `.` | Relative report directory to audit. The path must exist and be a directory. |

### Audit Domains and Weights

| Domain | Weight |
| --- | --- |
| Security | `x3.0` |
| Performance | `x1.5` |
| DAX Quality | `x1.5` |
| Modeling | `x1.5` |
| Structure | `x1.5` |
| Documentation | `x1.0` |
| Anti-patterns | `x1.0` |

### Audit Output

| File | Meaning |
| --- | --- |
| `AUDIT-REPORT.md` | Detailed report with evidence, score card, consolidated findings, and action plan |
| `AUDIT-TODO.md` | Progress tracker used to resume incomplete audits |

### Audit Grades

| Grade | Range |
| --- | --- |
| `A` | `90-100%` |
| `B` | `80-89%` |
| `C` | `70-79%` |
| `D` | `60-69%` |
| `F` | `<60%` |

See [Audit System](/guide/audit) for the full scoring summary.

## `pbi-agent init`

Scaffold a new PBIP template project from the bundled report assets.

```bash
pbi-agent init --dest .
```

| Option | Default | Description |
| --- | --- | --- |
| `--dest` | current working directory | Target directory for the template files. |
| `--force` | `false` | Overwrite existing files that would otherwise block initialization. |

::: warning
`init` is the only command that does not resolve provider settings or require an API key. All other commands validate provider configuration before they start the session.
:::
