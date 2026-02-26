# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**oai-ws / pbi-agent** is a WebSocket-based CLI scaffold for a Power BI editing "coding agent" built on the OpenAI Responses WebSocket API. It is intentionally a foundation: it wires up configuration, a CLI, a WebSocket client, and a tool-execution loop (including parallel tool calls), but does not ship real Power BI mutation tools yet.

## Commands

```bash
# Install dependencies
uv sync

# Run CLI
uv run pbi-agent --help
uv run pbi-agent run --prompt "..."    # Single-turn mode
uv run pbi-agent chat                  # Interactive mode

# Inspect tools
uv run pbi-agent tools list
uv run pbi-agent tools describe --name <tool_name>

# Initialize report template in a directory
uv run pbi-agent init --dest <path> [--force]

# Lint & format
uvx ruff check . --fix && uvx ruff format .
```

No automated test suite exists yet. Validate changes manually via the CLI commands above.

## Architecture

### Request Flow

1. **CLI** (`cli.py`) parses args and resolves settings via `config.py` (precedence: CLI args > env vars > defaults)
2. **Agent Session** (`agent/session.py`) orchestrates the main loop: send request, parse response, execute tool calls, repeat until no more tool calls
3. **WebSocket Client** (`agent/ws_client.py`) manages the streaming connection to the OpenAI Responses API
4. **Protocol** (`agent/protocol.py`) builds request payloads and parses streaming responses into structured models
5. **Display** (`display.py`) renders Rich terminal UI with streaming markdown, spinners, and token usage summaries

### Three Tool Runtimes

The agent supports three types of tool calls, each with its own runtime:

- **Function tools** (`agent/tool_runtime.py`) - Custom tools registered in `tools/registry.py`, executed via `ThreadPoolExecutor` with configurable parallelism (`--max-tool-workers`)
- **Shell** (`agent/shell_runtime.py`) - Command execution with workspace-confinement security (rejects path traversal)
- **Apply patch** (`agent/apply_patch_runtime.py`) - File create/update/delete via V4A diffs, parsed by `tools/apply_diff.py`

### Tool Registry

New function tools are added by:
1. Creating a handler in `src/pbi_agent/tools/`
2. Defining a `ToolSpec` and registering `(ToolSpec, handler)` in `tools/registry.py`

Currently registered tools: `skill_knowledge` (retrieves Power BI skill docs) and `init_report` (scaffolds PBIP template).

### Skill Knowledge Base

Markdown files in `src/pbi_agent/skills/` define Power BI domain knowledge (visual types, TMDL modeling, theming, filtering, etc.). The `skill_knowledge` tool loads these at runtime so the model can consult them before editing visuals.

### Bundled PBIP Template

Report template assets live under `src/pbi_agent/report/`. Packaging relies on `tool.hatch.build.targets.wheel.force-include` in `pyproject.toml` — keep template files in this location.

### Data Models

`models/messages.py` defines: `TokenUsage`, `ToolCall`, `ApplyPatchCall`, `ShellCall`, `CompletedResponse`, `AgentOutcome`. These are the structured types flowing through the agent loop.

## Key Configuration

| Setting | Env Variable | Default |
|---------|-------------|---------|
| API Key | `OPENAI_API_KEY` | (required) |
| Model | `PBI_AGENT_MODEL` | `gpt-5.3-codex` |
| WebSocket URL | `PBI_AGENT_WS_URL` | `wss://api.openai.com/v1/responses` |
| Max tool workers | `PBI_AGENT_MAX_TOOL_WORKERS` | `4` |
| WS retries | `PBI_AGENT_WS_MAX_RETRIES` | `2` |
| Reasoning effort | `PBI_AGENT_REASONING_EFFORT` | `xhigh` |
| Compact threshold | `PBI_AGENT_COMPACT_THRESHOLD` | `150000` |

## Constraints

- Python 3.12+ required
- Use `pbi-agent init` (not `init-report`) for the init command
- The `shell` runtime enforces workspace confinement — do not bypass path traversal protection
- The system prompt instructs the model to always consult `skill_knowledge` before creating/editing any Power BI visual
