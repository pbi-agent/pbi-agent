# AGENTS.md

This file provides guidance to Coding Agent when working with code in this repository.

## Project Summary

**pbi-agent** is a local CLI and browser-based coding agent for multi-domain workspace tasks. It supports project-local skills, commands, sub-agents, MCP tool integration, and provider backends including OpenAI, xAI, Google Gemini, Anthropic, and generic OpenAI-compatible endpoints. Provider HTTP calls must use `urllib.request`. The default branch is `master`.

## Workflow

- Do not commit, push, merge, or open PRs unless explicitly asked.
- Stop after local changes; leave Git steps to the user.
- Shell commands run from the workspace root by default; use relative paths and avoid `cd /full/workspace/path && ...` prefixes unless a task explicitly requires changing directories.
- When invoking Python directly in shell commands, use `python3` instead of `python`.
- Use the `gh` CLI for GitHub work; do not call the GitHub API with `curl`.
- Prefer `gh ... --json ...` for `pr view` / `issue view`; plain `gh pr view` and `gh issue view` can fail here because of the deprecated `projectCards` query.

## Common Commands

```bash
uv run pytest -q --tb=short -x
uv run pytest -q --tb=short -x tests/test_cli.py
uv run pytest -q --tb=short -x tests/test_cli.py::DefaultWebCommandTests::test_main_defaults_to_web_for_global_options_only
uv run pytest -q --tb=short -x -m slow
bun run test:web
bun run test:web:watch
uv run ruff check .
uv run ruff format .
uv run basedpyright
bun run lint
bun run lint:fix
bun run typecheck
uv build
bun run web:build
bun run docs:build
uv run pbi-agent --help
uv tool install --reinstall .
```

## Task Memory Protocol

- Use a single `MEMORY.md` file for both durable memory and recent task history.
- Keep `MEMORY.md` in three sections only: `Metadata`, `Long-Term Memory`, and `Detailed Task Events`.
- At the start of substantive work, read `Metadata`, `Long-Term Memory`, and any current-day detailed entries relevant to the task.
- Keep `Long-Term Memory` compact and edited in place. Store only durable facts: stable repo conventions, important decisions, reusable validation patterns, active follow-ups, and artifacts that matter beyond one task.
- Keep `Detailed Task Events` append-only within the active day. Group entries under one `## YYYY-MM-DD` heading per day.
- After each implementation, append one short task entry to the current day with only: what changed, validation, and next context if needed.
- On the first substantive task of a new day, compact the previous day's detailed entries before appending new ones.
- During compaction, first review every prior-day detailed entry and explicitly write a compact resume of its durable outcome into `Long-Term Memory` before deleting the dated section. Do not delete a prior-day section unless its durable facts, decisions, validation patterns, and unresolved follow-ups have been promoted or consciously deemed non-durable.
- Carry unresolved items into an active/open follow-up bullet if still relevant, then remove prior-day detail that is no longer needed.
- Avoid duplicating long-term bullets. Merge with existing bullets when the fact already exists.
- Keep the file token-efficient: prefer short bullets, avoid command noise, and do not preserve obsolete troubleshooting detail once compacted.

## Session TODO Protocol

- Use `TODO.md` for the current task session only.
- Create or reset `TODO.md` before starting substantive work.
- Use compact TODO markers: `[ ]` pending, `[>]` in progress, `[X]` done, `[!]` blocked, `[-]` dropped.
- Update `TODO.md` as you work. Mark steps complete when they finish, and revise the list when scope changes.
- If TODO.md contains a completed task list, reset it before adding new changes. If it contains an unfinished list, append the new task instead.

## Command Output

Protect context usage. **Any command with unknown or potentially large output must be byte-capped.**

Default pattern:

```bash
COMMAND 2>&1 | head -c 4000
```

For logs or recent failures:

```bash
COMMAND 2>&1 | tail -c 4000
```

Do not rely on line limits as the only cap. A single line can be huge. Avoid using only:

```bash
head -n
tail -n
sed -n '1,20p'
```

Scope before printing content:

- list files with `rg -l` before printing matches
- count matches with `rg -c` before reading them
- search specific paths instead of whole directories
- use `rg -m`, `--max-count`, `--max-filesize`, and small context when useful
- inspect file size before reading unknown generated files, logs, JSONL, or minified JSON

For commands where the exit code matters, capture output first, print a capped amount, then exit with the original status:

```bash
tmp="$(mktemp)"
COMMAND >"$tmp" 2>&1
status=$?
tail -c 5000 "$tmp"
rm -f "$tmp"
exit "$status"
```

Avoid unbounded output from:

```bash
cat path/to/file
rg -n "term" .
find .
ls -R
git diff
npm test
npm run build
select *
```

Use bounded versions instead:

```bash
rg -l "term" . | head -c 2000
rg -n -m 20 "term" src 2>&1 | head -c 2000
git diff -- path/to/file 2>&1 | head -c 6000
find . -type f 2>&1 | head -c 2000
```

If the capped output is insufficient, narrow the command. Do not repeatedly increase the cap unless the task requires more context.

## Communication

Before editing, state the approach only for non-trivial tasks.

During complex work, keep updates very short:

- what was found
- what changed
- what risk remains

After work, summarize:

- what changed
- files touched
- validation run, or why skipped
- remaining risk

Keep summaries short. Do not explain obvious edits.

Oververbosity:low

## Architecture Snapshot

- Entry point: `src/pbi_agent/__main__.py` calls `src/pbi_agent/cli.py`.
- CLI commands: `web`, `run`, `sessions`, `config`, `skills`, `commands`, and `agents`. When no command is provided, the CLI defaults to `web`.
- `pbi-agent web` uses saved web settings/profile resolution; provider/model runtime flags are for `run`, not `web`.
- Web backend: FastAPI under `src/pbi_agent/web/`, with routes in `src/pbi_agent/web/api/routes/`, orchestration in `src/pbi_agent/web/session_manager.py`, event/display publishing in `src/pbi_agent/web/display.py`, and Uvicorn startup helpers in `src/pbi_agent/web/server_runtime.py`.
- Frontend: Vite + React + TypeScript in `webapp/`, using `react-router-dom`, `@tanstack/react-query`, `zustand`, `@dnd-kit/core`, Tailwind CSS v4, and shadcn/ui. `bun run web:build` writes the SPA bundle to `src/pbi_agent/web/static/app`.
- shadcn/ui config lives at `webapp/components.json`: style `radix-nova`, Tailwind CSS file `webapp/src/styles/index.css`, aliases `@/components`, `@/components/ui`, `@/lib`, `@/hooks`, and icon library `lucide` (`lucide-react`). Shared UI primitives live in `webapp/src/components/ui/`; `cn()` lives in `webapp/src/lib/utils.ts`.
- When changing web API contracts, keep `src/pbi_agent/web/api/routes/`, `src/pbi_agent/web/api/schemas/`, `src/pbi_agent/web/session_manager.py`, `webapp/src/api.ts`, and `webapp/src/types.ts` aligned.
- Docs site: VitePress in `docs/`; build separately with `bun run docs:build`.
- Display abstraction: `src/pbi_agent/display/protocol.py` defines `DisplayProtocol`; console output lives in `src/pbi_agent/display/console_display.py`; tests commonly use `tests/conftest.py::DisplaySpy`.
- Providers: `src/pbi_agent/providers/base.py` defines the abstract `Provider`; `src/pbi_agent/providers/__init__.py` exposes `create_provider()`. API shapes are OpenAI/xAI `Responses`, Google `Interactions`, Anthropic `Messages`, and generic OpenAI-compatible `Chat Completions`.
- Agent loop: `src/pbi_agent/agent/session.py` runs turns and tool follow-ups, `src/pbi_agent/agent/system_prompt.py` composes workspace instructions into the runtime prompt, and `src/pbi_agent/agent/tool_runtime.py` executes tool calls in parallel. Sub-agents are capped at 200 requests, 1200 seconds, and cannot recurse.
- Tools: `src/pbi_agent/tools/registry.py` registers all tools. Handlers receive `ToolContext` (`settings`, `display`, usage, tracer, parent context). Core tools include `apply_patch`, `shell`, `sub_agent`, `read_file`, `read_image`, and `read_web_url`.
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

## Frontend UI Conventions

- Prefer shadcn/ui primitives from `webapp/src/components/ui/` before custom markup; add missing primitives with `bunx --bun shadcn@latest add <component> --cwd webapp` and read generated files before use.
- For shadcn docs/examples, use `bunx --bun shadcn@latest docs <component> --cwd webapp`; preview upstream changes with `--dry-run` / `--diff` and do not overwrite local component changes unless explicitly asked.
- Compose with shadcn patterns: full `Card` structure, `Alert` for callouts, `Empty` for empty states, `Separator` instead of ad-hoc borders, `Skeleton` for loading placeholders, `Badge` for labels, and `FieldGroup`/`Field` for forms.
- Styling should use semantic Tailwind/shadcn tokens (`bg-background`, `text-muted-foreground`, `border-border`, etc.) and `cn()` for conditionals; avoid raw color utilities, manual dark-mode color overrides, custom overlay z-indexes, and `space-x-*`/`space-y-*` utilities.
- For icons, use `lucide-react`; icons inside `Button` should use `data-icon="inline-start"` or `data-icon="inline-end"` and avoid manual sizing classes when the component styles them.
- Dialog, Sheet, and Drawer content must include an accessible title; use a visually hidden title only when the visible design already provides equivalent context.
- For floating UI near viewport edges (tooltips, popovers, badges in topbars), do not assume Radix/shadcn `sideOffset` or `collisionPadding` creates visible page-edge margin. Radix Popper may not shift on the cross axis, so content can still touch/crop against the viewport. Verify edge placement manually; when a tooltip must keep a guaranteed gutter from every viewport edge, use positioning that clamps both axes (for example a fixed-position portal tooltip) or a primitive/configuration that explicitly supports cross-axis shifting.

## Key Constraints

- Provider and tool HTTP communication must use `urllib.request`; do not add `requests` or alternate HTTP clients for those paths.
- Internal data files (indexes, caches, config, session DB) go in `~/.pbi-agent/`, never in the user's workspace.
- Workspace confinement: `shell` tool rejects path traversal; all file tools validate paths against workspace boundaries.
- Keep the web implementation aligned with the current FastAPI backend plus Vite/React frontend; do not introduce a parallel web framework or client stack.
- Validation by touched surface:
  - Python changes: `uv run ruff check .`, `uv run ruff format --check .`, `uv run basedpyright`, and the relevant `uv run pytest -q --tb=short -x ...` scope.
  - Frontend changes: `bun run test:web`, `bun run lint`, `bun run typecheck`, and `bun run web:build`.
  - Docs changes: `bun run docs:build`.
- Before handoff on broad changes, the repo-level checks are `uv run ruff check .`, `uv run ruff format --check .`, `uv run basedpyright`, `bun run lint`, `bun run typecheck`, and `uv run pytest -q --tb=short -x`.
- **No migration or backward-compatibility logic.** The project is in early development — do not add schema migrations, version checks, deprecation shims, or any other backward-compatibility code. When something changes, just change it directly.
