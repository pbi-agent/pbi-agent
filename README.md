# oai-ws / pbi-agent

`pbi-agent` is a local CLI foundation for a Power BI editing agent built on the **OpenAI Responses WebSocket API**.

The project includes:
- a websocket session loop for Responses API,
- local tool execution (including parallel tool calls),
- a bundled PBIP template scaffold,
- and a skill knowledge base for Power BI editing guidance.

It is still a foundation project: it provides the runtime and extensibility points, not a full end-user Power BI product.

## Requirements

- Python **3.12+**
- `OPENAI_API_KEY` set in your environment (default provider)
- `ANTHROPIC_API_KEY` required when using `--provider anthropic`
- Recommended: [`uv`](https://github.com/astral-sh/uv)

## Install

```bash
uv sync
```

## CLI quick start

Show top-level help:

```bash
uv run pbi-agent --help
```

Run one prompt turn:

```bash
uv run pbi-agent run --prompt "Summarize available tools."
```

Start interactive mode:

```bash
uv run pbi-agent chat
```

Serve the chat app in a browser:

```bash
uv run pbi-agent web
uv run pbi-agent web --host 0.0.0.0 --port 8000 --dev
```

Run report audit mode (writes `AUDIT-REPORT.md`):

```bash
uv run pbi-agent audit
```

Scaffold a PBIP report template in the current directory:

```bash
uv run pbi-agent init --dest . --force
```

Compatibility runner:

```bash
uv run python main.py --help
```

## Commands

- `run --prompt "..."`: single-turn request.
- `chat`: interactive REPL loop.
- `web [--host <host>] [--port <port>] [--dev] [--title <name>] [--url <public_url>]`: run the Textual web server and open the chat UI in a browser.
- `audit [--report-dir <path>]`: runs built-in audit prompt and writes `AUDIT-REPORT.md` to the target report directory.
- `init [--dest <path>] [--force]`: copy bundled Power BI template assets.

## Configuration

Precedence: **CLI args > environment variables > defaults**.

### CLI options

- `--openai-api-key`
- `--anthropic-api-key`
- `--model`
- `--max-tokens`
- `--ws-url`
- `--reasoning-effort` (`low|medium|high|xhigh`)
- `--max-tool-workers`
- `--ws-max-retries`
- `--compact-threshold`
- `--verbose`

### Environment variables

- `OPENAI_API_KEY` (required by default provider)
- `ANTHROPIC_API_KEY` (required when `--provider anthropic`)
- `PBI_AGENT_MODEL`
- `PBI_AGENT_MAX_TOKENS`
- `PBI_AGENT_WS_URL`
- `PBI_AGENT_REASONING_EFFORT`
- `PBI_AGENT_MAX_TOOL_WORKERS`
- `PBI_AGENT_WS_MAX_RETRIES`
- `PBI_AGENT_COMPACT_THRESHOLD`

## Tool model

At runtime, the agent advertises:

- built-in tool types: `shell`, `apply_patch`
- function tools from `src/pbi_agent/tools/registry.py`

Current bundled function tools include:

- `skill_knowledge`: loads local Power BI skill docs from `src/pbi_agent/skills/`
- `init_report`: scaffolds the bundled report template

Tool calls returned by the model are executed locally and fed back into the websocket session until completion.

## Security notes

- The `shell` runtime is workspace-confined and blocks path traversal via `working_directory`.
- Even with confinement, treat shell execution as powerful and use trusted workspaces.

## Development

Lint and format:

```bash
uvx ruff check . --fix && uvx ruff format .
```

Project-specific bootstrap command:

```bash
uv run pbi-agent init --dest . --force
```

## Project layout

```text
.
├─ README.md
├─ pyproject.toml
├─ main.py
└─ src/
   └─ pbi_agent/
      ├─ cli.py
      ├─ config.py
      ├─ agent/        # websocket protocol/session + runtimes
      ├─ tools/        # function tool specs + handlers
      ├─ skills/       # Power BI skill markdown knowledge base
      └─ report/       # bundled PBIP template assets
```

## Current limits

- No automated test suite is configured yet.
- Foundation-level implementation focused on CLI/runtime scaffolding.
- Sessions are in-memory.
