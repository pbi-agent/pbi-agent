# oai-ws / pbi-agent

WebSocket-based CLI scaffold for a Power BI editing “coding agent”, built on the **OpenAI Responses WebSocket API**.

This repository is intentionally a foundation: it wires up configuration, a CLI, a websocket client, and a tool-execution loop (including parallel function tool calls), but it does **not** ship real Power BI mutation tools yet.

## What’s in this repo

- **Python package**: `src/pbi_agent`
- **CLI entrypoint**: `pbi-agent` (also: `python -m pbi_agent`)
- **Single-turn** agent flow: `pbi-agent run --prompt "..."`
- **Interactive** agent flow: `pbi-agent chat`
- **Tool system**
  - Built-in runtime handlers for OpenAI built-ins: `shell`, `apply_patch`
  - Extensible function-tool registry (centralized): `src/pbi_agent/tools/registry.py`
  - Parallel-capable execution via `--max-tool-workers`

## Requirements

- Python **3.12+**
- An OpenAI API key in `OPENAI_API_KEY`
- Recommended: [`uv`](https://github.com/astral-sh/uv) for dependency management (repo includes `uv.lock`)

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
- `--verbose`

### Environment variables

- `OPENAI_API_KEY` (required for `run` / `chat`)
- `PBI_AGENT_MODEL` (optional)
- `PBI_AGENT_WS_URL` (optional)
- `PBI_AGENT_MAX_TOOL_WORKERS` (optional)

## Tooling model (how tools work here)

At runtime the agent advertises tools to the Responses API:

- **Built-in tool types**: `shell`, `apply_patch`
- **Function tools** registered in the local registry (see below)

When the model returns tool calls, the CLI executes them and feeds results back to the websocket session until the response completes.

## Adding a new function tool

1. Create a handler under `src/pbi_agent/tools/` (e.g. `my_tool.py`).
2. Define a `ToolSpec` and register `(ToolSpec, handler)` in `src/pbi_agent/tools/registry.py`.
3. Validate locally:

```bash
uv run pbi-agent tools list
uv run pbi-agent tools describe --name <tool_name>
```

## Project layout

```
.
├─ README.md
├─ pyproject.toml
├─ main.py                 # compatibility runner
└─ src/
   └─ pbi_agent/
      ├─ cli.py            # argparse CLI
      ├─ config.py         # env/CLI settings resolution
      ├─ agent/            # websocket session + tool loop
      └─ tools/            # tool specs + implementations
```

## Current limits / non-goals (for now)

- No concrete Power BI edit operations are implemented yet (this is scaffolding).
- In-memory sessions only.
- Minimal hardening; no automated test suite in this phase.
