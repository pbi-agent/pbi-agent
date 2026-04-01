# CLAUDE.md

This file provides guidance to Coding Agent when working with code in this repository.

## Project Summary

**pbi-agent** is a local CLI agent for creating, auditing, and editing Power BI PBIP reports through natural language. It supports multiple LLM providers (OpenAI, xAI, Google Gemini, Anthropic, and OpenAI-compatible gateways) using synchronous HTTP via `urllib.request`. The default branch is `master`.

## GitHub

Use the `gh` CLI for all GitHub interactions — never construct API URLs manually or use `curl` against the GitHub API.

```bash
# View a PR (description, status, checks)
# NOTE: plain `gh pr view` / `gh issue view` fail with a Projects Classic
# deprecation error. Always use --json to bypass the broken projectCards query.
gh pr view <number> --json title,body,state,author,labels,headRefName,baseRefName

# View an issue
gh issue view <number> --json title,body,state,author,labels,comments

# List PRs or issues
gh pr list
gh issue list

# View PR comments
gh pr view <number> --json comments

# View PR diff
gh pr diff <number>
```

## Common Commands

```bash
# Run all tests
uv run pytest

# Run a specific test file or test
uv run pytest tests/test_cli.py
uv run pytest tests/test_cli.py::DefaultWebCommandTests::test_main_defaults_to_web_for_global_options_only

# Run marked tests
uv run pytest -m slow

# Lint and format
uv run ruff check . --fix && uv run ruff format .

# Build
uv build

# Run CLI from source
uv run pbi-agent --help

# Install from source
uv tool install --reinstall .
```

## Architecture

**Entry point:** `src/pbi_agent/__main__.py` → `cli.py` parses args and routes to commands (web, console, run, audit, init, sessions, open).

## Web Stack

- Backend web server: FastAPI in `src/pbi_agent/web/serve.py`, served by Uvicorn. It exposes JSON endpoints under `/api/*`, websocket event streams under `/api/events/*`, and serves the SPA shell plus built static assets.
- Frontend app: Vite + React + TypeScript in `webapp/`. The app uses `react-router-dom` for client routing, `@tanstack/react-query` for server state, `zustand` for chat session state, and `@dnd-kit/core` for board drag-and-drop.
- Build output: `npm run web:build` writes the production bundle to `src/pbi_agent/web/static/app`, which FastAPI serves in non-dev flows.
- Docs site: VitePress in `docs/`, built separately with `npm run docs:build`.

## Frontend Implementation Notes

- Treat the web UI as a SPA mounted by FastAPI. Preserve the catch-all route pattern and keep client-side routes compatible with the backend SPA fallback.
- Keep API contract changes coordinated across `src/pbi_agent/web/serve.py`, `src/pbi_agent/web/session_manager.py`, and `webapp/src/api.ts`.
- Prefer extending the existing stack instead of introducing overlapping frontend frameworks, state managers, or data-fetching layers.
- For local frontend development, use Vite dev server for the client and FastAPI/Uvicorn for the backend rather than replacing the current build pipeline.

### Provider Layer (`providers/`)
Abstract `Provider` base class with implementations for each LLM. All use synchronous HTTP (`urllib.request`). Key methods: `connect()`, `close()`, `request_turn()`, `execute_tool_calls()`, `reset_conversation()`. Factory: `create_provider()` in `providers/__init__.py`.

| Provider | API Shape | Key File |
|---|---|---|
| OpenAI | Responses API | `openai_provider.py` |
| xAI | Responses API | `xai_provider.py` |
| Google | Interactions API | `google_provider.py` |
| Anthropic | Messages API | `anthropic_provider.py` |
| Generic | Chat Completions API | `generic_provider.py` |

### Agent Loop (`agent/`)
- `session.py` — Core agentic loop: `run_single_turn()` and `run_chat_loop()`. Handles tool call → execute → feed back cycle.
- `system_prompt.py` — Dynamic system prompt generation, loads workspace `AGENTS.md` rules.
- `tool_runtime.py` — Parallel tool execution via `ThreadPoolExecutor`.
- Sub-agents: spawned with limited scope (max 30 requests, 300s timeout, no recursive sub-agents).

### Tools (`tools/`)
Registered in `tools/registry.py`. All tools receive `ToolContext` (workspace, display, settings). Key tools: `apply_patch` (V4A diffs), `shell` (workspace-confined), `python_exec` (local Python with pandas/pypdf/python-docx), `skill_knowledge` (retrieves Power BI Markdown docs from `skills/`), `sub_agent`, `read_file`, `search_files`, `list_files`, `read_web_url`, `init_report`.

### UI Layer (`ui/`)
Built on Textual. `DisplayProtocol` abstracts UI so implementations can be swapped (web TUI via `app.py`, console via `console_display.py`, test spy via `conftest.py::DisplaySpy`).

### Settings Resolution (`config.py`)
Precedence: CLI flags > `PBI_AGENT_*` env vars > provider-specific env vars (e.g., `OPENAI_API_KEY`) > internal config (`~/.pbi-agent/config.json`, per-provider) > defaults. Supports `.env` files via `python-dotenv`.

### Models (`models/messages.py`)
`TokenUsage`, `CompletedResponse`, `ToolCall` dataclasses. Contains pricing tables and context window lookups per model.

## Testing Conventions

- Test files: `tests/test_*.py`, auto-discovered by pytest.
- Prefer pytest-style with plain `assert` and `@pytest.mark.parametrize`.
- Shared fixtures in `tests/conftest.py` (notably `DisplaySpy` for mocking UI).
- Provider changes must update `test_<provider>_provider.py`; tool changes must update `test_<tool>.py`.
- Register new custom markers in `pyproject.toml` under `tool.pytest.ini_options.markers`.
- Import from `pbi_agent` directly — pytest adds `src/` to `sys.path`.

## Key Constraints

- All HTTP communication must use `urllib.request` (no async frameworks, no `requests` library).
- Internal data files (indexes, caches, config, session DB) go in `~/.pbi-agent/`, never in the user's workspace.
- Bundled PBIP template assets must stay under `src/pbi_agent/report/`; hatchling packaging relies on git tracking for non-Python assets.
- Workspace confinement: `shell` tool rejects path traversal; all file tools validate paths against workspace boundaries.
- `python_exec` runs trusted local Python — it is not a sandbox.
- After every frontend edit, run the relevant npm build command and confirm it passes before finishing. Use `npm run web:build` for web app changes and `npm run docs:build` for VitePress/docs changes.
- When changing the FastAPI web server or Vite frontend, keep the implementation aligned with the existing FastAPI + Vite/React architecture rather than introducing an alternative web framework.
- `uv run ruff check .`, `uv run ruff format --check .`, and `uv run pytest` must all pass before merging.
- **No migration or backward-compatibility logic.** The project is in early development — do not add schema migrations, version checks, deprecation shims, or any other backward-compatibility code. When something changes, just change it directly.
