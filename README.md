# pbi-agent

**A local CLI agent that creates, edits, and audits Power BI reports through natural language.**

`pbi-agent` turns plain English into production-ready Power BI reports. Instead of clicking through dozens of menus, you describe what you need and the agent handles the rest: scaffolding projects, building visuals, writing DAX measures, and running best-practice audits -- all from your terminal.

## Why pbi-agent?

Power BI development involves a large amount of repetitive, manual work: creating report structures, configuring visuals, writing measures, and enforcing best practices. `pbi-agent` eliminates that friction by letting you express intent in natural language and delegating the implementation to an LLM-powered agent that understands the Power BI project format (PBIP) natively.

**What this means for developer productivity:**

- **Minutes instead of hours** -- Scaffold a complete report project, add pages, and wire up visuals in a single conversation rather than navigating menus and property panels.
- **Consistent quality** -- The built-in audit engine checks 90+ rules across modeling, performance, security, and DAX quality, catching issues that manual reviews miss.
- **Lower barrier to entry** -- Junior developers and analysts can produce well-structured reports without deep Power BI expertise; the agent encodes best practices into every action it takes.
- **Repeatable workflows** -- Single-turn prompts (`pbi-agent run`) integrate into scripts and CI pipelines, making report generation and auditing automatable.
- **Bring your own model** -- Works with **OpenAI** (GPT-5.4, default) and **Anthropic** (Claude Opus, Sonnet). Switch providers with a single flag (`--provider anthropic`).

## Use Cases

### 1. Create a full dashboard from a data file

Drop a CSV (or any flat file) into your workspace and let the agent do the rest. It analyzes the data, imports it into the semantic model, creates measures, and builds a complete dashboard -- no manual configuration required:

```bash
pbi-agent chat
# > "Here is sales_data.csv. Analyze the file, import it into the model,
#    and build a dashboard with a revenue trend line chart, a top-10
#    products bar chart, and KPI cards for total revenue, order count,
#    and average order value."
```

The agent will:

1. Inspect the CSV to understand columns, data types, and cardinality.
2. Import the file into the semantic model as a new table.
3. Create DAX measures (total revenue, order count, average order value, etc.).
4. Build report pages with the requested visuals, properly bound to the model.

From a single file and one prompt, you get a working Power BI report ready to open in Power BI Desktop.

> **Demo:** See this workflow in action -- [watch the video](<!-- TODO: insert demo video URL -->).

### 2. Edit an existing report

Point the agent at an existing PBIP directory and describe the changes you need:

```bash
pbi-agent chat
# > "On the Sales page, replace the table visual with a clustered bar chart
#    grouped by product category. Add a slicer for fiscal year."
```

The agent reads the report definition files, applies the edits, and preserves existing configuration.

### 3. Audit a report for issues

Run a comprehensive best-practice audit that checks 90+ rules across seven domains:

```bash
pbi-agent audit --report-dir ./my-report
```

The audit covers:

| Domain | What it checks |
| --- | --- |
| Structure & Star Schema | Table relationships, fact/dimension separation |
| Modeling & Naming | Conventions, data types, calculated columns |
| Performance | Query folding, cardinality, aggregation patterns |
| Security | RLS configuration, data exposure risks |
| DAX Quality | Measure patterns, CALCULATE usage, time intelligence |
| Metadata & Documentation | Descriptions, display folders, formatting |
| Anti-Patterns | Hidden fields, unused objects, dead code |

Output is written to `AUDIT-REPORT.md` (detailed findings with severity scores and a letter grade) and `AUDIT-TODO.md` (a progress checklist you can track).

### 4. Single-turn scripting

Run one-off prompts for automation or CI integration:

```bash
pbi-agent run --prompt "List all measures in the semantic model that lack descriptions."
```

### 5. Browser-based chat

Serve the chat UI in a browser for a richer experience:

```bash
pbi-agent web --port 8000
```

## Prerequisites

- Python **3.12+**
- [`uv`](https://docs.astral.sh/uv/) (recommended) or `pip`
- An API key for one of the supported LLM providers:
  - Set `PBI_AGENT_API_KEY`
  - Use `--provider anthropic` for Anthropic
  - Use `--provider generic` for OpenAI-compatible gateways such as OpenRouter

### Installing uv

**macOS / Linux:**

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

**Windows (PowerShell):**

```powershell
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
```

## Installation

### From PyPI (recommended)

Install the CLI globally so it can be called from any directory:

```bash
uv tool install pbi-agent
```

Verify the installation:

```bash
pbi-agent --help
```

### From source

```bash
git clone https://github.com/<your-org>/pbi-agent.git
cd pbi-agent
uv tool install --reinstall .
```

This installs `pbi-agent` globally from the local checkout. Use `--reinstall` to overwrite a previous installation.

## Quick Start

> **Warning:** `pbi-agent` works directly on Power BI projects saved in **PBIP format** (Power BI Project). You must run the CLI from the directory that contains your `.pbip` project files, or scaffold a new one with `pbi-agent init`. Reports saved as `.pbix` are not supported -- save your report as a PBIP project from Power BI Desktop first (`File > Save as > Power BI Project`).

1. Set your API key:

**macOS / Linux:**

```bash
export PBI_AGENT_API_KEY="sk-..."
```

**Windows (PowerShell):**

```powershell
$env:PBI_AGENT_API_KEY = "sk-..."
```

You can also place these in a `.env` file in your project directory to avoid setting them every session.

2. Navigate to your PBIP project directory (or scaffold a new one):

```bash
# Option A: start from an existing PBIP project
cd /path/to/my-report

# Option B: scaffold a new project in the current directory
pbi-agent init --dest .
```

3. Start a conversation:

```bash
pbi-agent chat
```

## Commands

| Command | Description |
| --- | --- |
| `run --prompt "..."` | Execute a single prompt turn and exit |
| `chat` | Interactive REPL session |
| `web` | Serve the chat UI in a browser |
| `audit` | Run a best-practice audit, writes `AUDIT-REPORT.md` |
| `init` | Scaffold a new PBIP report from the bundled template |
| `tools list` | List all registered tools |
| `tools describe --name <tool>` | Show a tool's schema |

## Configuration

**Precedence:** CLI flags > environment variables > defaults.

### Environment variables

| Variable | Description | Default |
| --- | --- | --- |
| `PBI_AGENT_API_KEY` | API key for the selected provider | -- |
| `PBI_AGENT_PROVIDER` | LLM provider (`openai`, `anthropic`, or `generic`) | `openai` |
| `PBI_AGENT_MODEL` | Model override | `gpt-5.4-2026-03-05` for OpenAI, `claude-opus-4-6` for Anthropic, provider default for generic |
| `PBI_AGENT_MAX_TOKENS` | Max output tokens | `16384` |
| `PBI_AGENT_REASONING_EFFORT` | Reasoning effort (`low`, `medium`, `high`, `xhigh`) | `xhigh` |
| `PBI_AGENT_MAX_TOOL_WORKERS` | Parallel tool execution threads | `4` |
| `PBI_AGENT_WS_MAX_RETRIES` | Retry count for transient failures | `2` |
| `PBI_AGENT_COMPACT_THRESHOLD` | Context compaction token threshold | `150000` |
| `PBI_AGENT_WS_URL` | Custom WebSocket endpoint | `wss://api.openai.com/v1/responses` |
| `PBI_AGENT_RESPONSES_URL` | Custom HTTP Responses endpoint | derived from WS URL |
| `PBI_AGENT_GENERIC_API_URL` | Generic OpenAI-compatible Chat Completions endpoint | `https://openrouter.ai/api/v1/chat/completions` |

Legacy provider-specific environment variables (`OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, `GENERIC_API_KEY`) are still accepted as fallbacks.

You can also place these in a `.env` file in your project root.

### CLI flags

All environment variables have corresponding CLI flags. Run `pbi-agent --help` for the full list:

```bash
pbi-agent --provider anthropic --model claude-opus-4-6 chat
```

For generic providers, omit `--model` to use the gateway default model selection, or pass one explicitly:

```bash
pbi-agent --provider generic --model openai/gpt-5-mini chat
```

## How It Works

`pbi-agent` connects to the OpenAI Responses WebSocket API, Anthropic Messages API, or a generic OpenAI-compatible Chat Completions API and runs an agentic loop:

1. Your prompt is sent alongside the agent's system instructions and tool definitions.
2. The model responds with text, reasoning, or tool calls.
3. Tool calls are executed locally in parallel (shell commands, file patches, skill lookups, template scaffolding).
4. Tool results are fed back to the model for the next turn.
5. The loop continues until the model produces a final text response.

### Built-in tools

| Tool | Description |
| --- | --- |
| `shell` | Execute shell commands (workspace-confined, blocks path traversal) |
| `apply_patch` | Create, update, or delete files via V4A diffs |
| `skill_knowledge` | Retrieve Power BI knowledge from the bundled skill library (14 topics) |
| `init_report` | Scaffold the PBIP template into a target directory |

### Knowledge base

The agent ships with 14 Power BI skill documents covering visual types, TMDL modeling, theme branding, filter propagation, and more. The agent consults these automatically before creating or editing visuals, ensuring correct JSON schemas and best practices.

## Security Notes

- The `shell` tool is confined to the workspace directory and rejects path traversal attempts.
- Even with confinement, treat shell execution as powerful. Only run the agent in trusted workspaces.
- Never commit `.env` files containing API keys to version control.

## Development

```bash
# Lint and format
uvx ruff check . --fix && uvx ruff format .

# Run the CLI from source
uv run pbi-agent --help
```

## Project Layout

```
.
├── pyproject.toml
├── main.py                     # Compatibility entry point
└── src/pbi_agent/
    ├── cli.py                  # CLI parser and command handlers
    ├── config.py               # Settings resolution (CLI > env > defaults)
    ├── display.py              # Textual TUI chat application
    ├── agent/
    │   ├── session.py          # Agentic loop (single-turn and chat)
    │   ├── protocol.py         # WebSocket protocol handling
    │   ├── ws_client.py        # WebSocket client
    │   ├── tool_runtime.py     # Parallel tool execution engine
    │   ├── system_prompt.py    # Agent persona and instructions
    │   └── audit_prompt.py     # 90+ rule audit prompt builder
    ├── providers/
    │   ├── openai_provider.py  # OpenAI Responses WebSocket provider
    │   ├── anthropic_provider.py # Anthropic Messages HTTP provider
    │   └── generic_provider.py # Generic OpenAI-compatible Chat Completions HTTP provider
    ├── tools/
    │   ├── registry.py         # Tool registration and format conversion
    │   ├── shell.py            # Shell command execution
    │   ├── apply_patch.py      # V4A diff-based file operations
    │   ├── skill_knowledge.py  # Skill document retrieval
    │   └── init_report.py      # PBIP template scaffolding
    ├── skills/                 # 14 Power BI skill markdown documents
    └── report/                 # Bundled PBIP template assets
```

## License

See [LICENSE](LICENSE) for details.
