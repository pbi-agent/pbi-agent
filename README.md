# oai-ws / pbi-agent

WebSocket-based CLI scaffold for a Power BI editing “coding agent”, built on the **OpenAI Responses WebSocket API**.

This repository is intentionally a foundation: it wires up configuration, a CLI, a websocket client, and a tool-execution loop (including **parallel tool calls**), but it does **not** ship real Power BI mutation tools yet.

## Features

- **Python package**: `src/pbi_agent`
- **CLI entrypoint**: `pbi-agent` (also: `python -m pbi_agent`)
- Agent flows:
  - **Single-turn**: `pbi-agent run --prompt "..."`
  - **Interactive**: `pbi-agent chat`
  - **Audit mode**: `pbi-agent audit [--report-dir <relative-path>]`
- **Tool execution loop**
  - Supports OpenAI built-in tool types: `shell`, `apply_patch`
  - Extensible **function tool registry**: `src/pbi_agent/tools/registry.py`
  - Parallel-capable execution via `--max-tool-workers`

## Requirements

- Python **3.12+**
- An OpenAI API key in `OPENAI_API_KEY`
- Recommended: [`uv`](https://github.com/astral-sh/uv) (repo includes `uv.lock`)

## Install

```bash
uv sync
```

## Quick start

Show help:

```bash
uv run pbi-agent --help
```

Single turn:

```bash
uv run pbi-agent run --prompt "Summarize the tool capabilities of this agent."
```

Interactive:

```bash
uv run pbi-agent chat
```

Audit the current report folder and generate a local audit file:

```bash
uv run pbi-agent audit
```

Audit a report in a relative subfolder:

```bash
uv run pbi-agent audit --report-dir ./my-report
```

`audit` runs with a built-in prompt (no `--prompt` needed) and writes
`AUDIT-REPORT.md` in the audited report directory.

Compatibility runner (thin wrapper kept for convenience):

```bash
uv run python main.py --help
```

## Configuration

Configuration precedence is: **CLI args > environment variables > defaults**.

### CLI options

- `--api-key` (overrides `OPENAI_API_KEY`)
- `--ws-url` (overrides `PBI_AGENT_WS_URL`, default: `wss://api.openai.com/v1/responses`)
- `--model` (overrides `PBI_AGENT_MODEL`)
- `--max-tool-workers` (overrides `PBI_AGENT_MAX_TOOL_WORKERS`, default: `4`)
- `--ws-max-retries` (overrides `PBI_AGENT_WS_MAX_RETRIES`, default: `2`)
- `--verbose`

### Environment variables

- `OPENAI_API_KEY` (required for `run` / `chat` / `audit`)
- `PBI_AGENT_MODEL` (optional)
- `PBI_AGENT_WS_URL` (optional)
- `PBI_AGENT_MAX_TOOL_WORKERS` (optional)
- `PBI_AGENT_WS_MAX_RETRIES` (optional)

## Tooling model (how tools work here)

At runtime the agent advertises tools to the Responses API:

- **Built-in tool types**: `shell`, `apply_patch`
- **Function tools** registered in the local registry

When the model returns tool calls, the CLI executes them and feeds results back to the websocket session until the response completes.

### Security model: workspace confinement

The built-in `shell` runtime resolves a *workspace root* and rejects `working_directory` values that would escape it (path traversal protection). Treat `shell` as powerful and avoid running the agent on sensitive directories.

## Adding a new function tool

1. Create a handler under `src/pbi_agent/tools/` (e.g. `my_tool.py`).
2. Define a `ToolSpec` and register `(ToolSpec, handler)` in `src/pbi_agent/tools/registry.py`.
3. Validate locally:

```bash
uv run pbi-agent tools list
uv run pbi-agent tools describe --name <tool_name>
```

## Project layout

```text
.
├─ README.md
├─ pyproject.toml
├─ main.py                 # compatibility runner
└─ src/
   └─ pbi_agent/
      ├─ cli.py            # argparse CLI
      ├─ config.py         # env/CLI settings resolution
      ├─ agent/            # websocket session + tool loop
      ├─ models/           # request/response message models
      └─ tools/            # tool specs + implementations
```

## Limits / non-goals (for now)

- No concrete Power BI edit operations are implemented yet (this is scaffolding).
- In-memory sessions only.
- Minimal hardening; no automated test suite in this phase.
