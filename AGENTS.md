# AGENTS.md

This file provides guidance to Coding Agent when working with code in this repository.

## Project Summary

**pbi-agent** is a local CLI and browser-based agent for creating, auditing, and editing Power BI PBIP reports with natural-language prompts. Provider integrations support OpenAI, xAI, Google Gemini, Anthropic, and generic OpenAI-compatible endpoints, and provider HTTP calls must use `urllib.request`. The default branch is `master`.

## Workflow

- Do not commit, push, merge, or open PRs unless explicitly asked.
- Stop after local changes; leave Git steps to the user.
- Use the `gh` CLI for GitHub work; do not call the GitHub API with `curl`.
- Prefer `gh ... --json ...` for `pr view` / `issue view`; plain `gh pr view` and `gh issue view` can fail here because of the deprecated `projectCards` query.

## Common Commands

```bash
uv run pytest
uv run pytest tests/test_cli.py
uv run pytest tests/test_cli.py::DefaultWebCommandTests::test_main_defaults_to_web_for_global_options_only
uv run pytest -m slow
bun run test:web
bun run test:web:watch
uv run ruff check .
uv run ruff format --check .
bun run lint
bun run lint:fix
bun run typecheck
uv build
bun run web:build
bun run docs:build
uv run pbi-agent --help
uv tool install --reinstall .
```

## Task Memory

- Use `MEMORY.md` for long-term agent memory and session continuity. At the start of substantive work, consult it when available for relevant prior context.
- After each implementation, append a brief entry to `MEMORY.md` describing what changed, why it changed, validation performed, and any context useful for the next session.
- Always add new `MEMORY.md` entries at the end of the file in append mode. Never insert a new memory entry in the middle of existing history.
- Use `TODO.md` for the current task session only.
- Create or reset `TODO.md` before starting substantive work.
- Use compact TODO markers: `[ ]` pending, `[>]` in progress, `[X]` done, `[!]` blocked, `[-]` dropped.
- Update `TODO.md` as you work. Mark steps complete when they finish, and revise the list when scope changes.
- If `TODO.md` contains an old completed or unrelated list, replace it before making new changes.

## Architecture Snapshot

- Entry point: `src/pbi_agent/__main__.py` calls `src/pbi_agent/cli.py`.
- CLI commands: `web`, `run`, `audit`, `init`, `sessions`, `config`. When no command is provided, the CLI defaults to `web`.
- `pbi-agent web` uses saved web settings/profile resolution; provider/model runtime flags are for `run` and `audit`, not `web`.
- Web backend: FastAPI under `src/pbi_agent/web/`, with routes in `src/pbi_agent/web/api/routes/`, orchestration in `src/pbi_agent/web/session_manager.py`, event/display publishing in `src/pbi_agent/web/display.py`, and Uvicorn startup helpers in `src/pbi_agent/web/server_runtime.py`.
- Frontend: Vite + React + TypeScript in `webapp/`, using `react-router-dom`, `@tanstack/react-query`, `zustand`, and `@dnd-kit/core`. `bun run web:build` writes the SPA bundle to `src/pbi_agent/web/static/app`.
- When changing web API contracts, keep `src/pbi_agent/web/api/routes/`, `src/pbi_agent/web/api/schemas/`, `src/pbi_agent/web/session_manager.py`, `webapp/src/api.ts`, and `webapp/src/types.ts` aligned.
- Docs site: VitePress in `docs/`; build separately with `bun run docs:build`.
- Display abstraction: `src/pbi_agent/display/protocol.py` defines `DisplayProtocol`; console output lives in `src/pbi_agent/display/console_display.py`; tests commonly use `tests/conftest.py::DisplaySpy`.
- Providers: `src/pbi_agent/providers/base.py` defines the abstract `Provider`; `src/pbi_agent/providers/__init__.py` exposes `create_provider()`. API shapes are OpenAI/xAI `Responses`, Google `Interactions`, Anthropic `Messages`, and generic OpenAI-compatible `Chat Completions`.
- Agent loop: `src/pbi_agent/agent/session.py` runs turns and tool follow-ups, `src/pbi_agent/agent/system_prompt.py` composes workspace instructions into the runtime prompt, and `src/pbi_agent/agent/tool_runtime.py` executes tool calls in parallel. Sub-agents are capped at 100 requests, 1200 seconds, and cannot recurse.
- Tools: `src/pbi_agent/tools/registry.py` registers all tools. Handlers receive `ToolContext` (`settings`, `display`, usage, tracer, parent context). Core tools include `apply_patch`, `shell`, `python_exec`, `sub_agent`, `init_report`, `skill_knowledge`, `read_file`, `read_image`, `search_files`, `list_files`, and `read_web_url`.
- Settings: `src/pbi_agent/config.py` resolves runtime field-by-field from CLI flags, `PBI_AGENT_*` env vars, provider-specific env vars, saved providers/model profiles in `~/.pbi-agent/config.json`, then defaults, and loads `.env` via `python-dotenv`.
- Models and usage accounting: `src/pbi_agent/models/messages.py` defines `TokenUsage`, `ToolCall`, and `CompletedResponse`, and also loads model pricing/context windows (with optional user overrides from `~/.pbi-agent/model_catalog.json`).

## Testing Conventions

- Test files: `tests/test_*.py`, auto-discovered by pytest.
- Prefer pytest-style with plain `assert` and `@pytest.mark.parametrize`.
- Shared fixtures live in `tests/conftest.py`; `DisplaySpy` is the main display test double.
- Webapp tests use Vitest + jsdom + Testing Library and live alongside the frontend source under `webapp/src/**/*.test.ts` and `webapp/src/**/*.test.tsx`.
- Webapp test setup lives in `webapp/src/test/setup.ts`; shared frontend test helpers live under `webapp/src/test/`.
- Prefer testing user-visible behavior and state transitions over snapshots.
- For frontend networked code, mock at the `webapp/src/api.ts` boundary for unit/component tests instead of re-testing FastAPI responses in depth.
- For websocket flows, prefer mocked `WebSocket` instances with fake timers so reconnect behavior stays deterministic.
- Provider changes must update `test_<provider>_provider.py`; tool changes must update `test_<tool>.py`.
- Register new custom markers in `pyproject.toml` under `tool.pytest.ini_options.markers`.
- Import from `pbi_agent` directly — pytest adds `src/` to `sys.path`.

## Key Constraints

- Provider and tool HTTP communication must use `urllib.request`; do not add `requests` or alternate HTTP clients for those paths.
- Internal data files (indexes, caches, config, session DB) go in `~/.pbi-agent/`, never in the user's workspace.
- Bundled PBIP template assets must stay under `src/pbi_agent/report/`; hatchling packaging relies on git tracking for non-Python assets.
- Workspace confinement: `shell` tool rejects path traversal; all file tools validate paths against workspace boundaries.
- `python_exec` runs trusted local Python — it is not a sandbox.
- Keep the web implementation aligned with the current FastAPI backend plus Vite/React frontend; do not introduce a parallel web framework or client stack.
- Validation by touched surface:
  - Python changes: `uv run ruff check .`, `uv run ruff format --check .`, and the relevant `uv run pytest ...` scope.
  - Frontend changes: `bun run test:web`, `bun run lint`, `bun run typecheck`, and `bun run web:build`.
  - Docs changes: `bun run docs:build`.
- Before handoff on broad changes, the repo-level checks are `uv run ruff check .`, `uv run ruff format --check .`, `bun run lint`, `bun run typecheck`, and `uv run pytest`.
- **No migration or backward-compatibility logic.** The project is in early development — do not add schema migrations, version checks, deprecation shims, or any other backward-compatibility code. When something changes, just change it directly.
