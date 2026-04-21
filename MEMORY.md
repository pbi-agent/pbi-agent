# MEMORY.md

## Metadata
- Last compacted: 2026-04-21
- Scope: durable repo memory plus append-only detailed task events for the active day.
- Format rule: keep only `Metadata`, `Long-Term Memory`, and `Detailed Task Events`; compact prior-day detail into durable notes before appending new work.

## Long-Term Memory
- Workflow: do not commit, push, merge, or open PRs unless explicitly asked. Use `TODO.md` only for the current task session, reset it before substantive work, and keep markers compact: `[ ]`, `[>]`, `[X]`, `[!]`, `[-]`.
- Validation by surface: Python changes should run `uv run ruff check .`, `uv run ruff format --check .`, and relevant `uv run pytest ...`; frontend changes should run `bun run test:web`, `bun run lint`, `bun run typecheck`, and `bun run web:build`; docs changes should run `bun run docs:build`; broad handoff checks are the full repo Ruff, Bun lint/typecheck, and pytest commands.
- Environment quirk: `bun run lint` and occasionally focused `bun run test:web -- ...` have intermittently hung in this environment, so treat lint/test hangs as an environment risk unless a code-specific failure is evident.
- Architecture: CLI entry is `src/pbi_agent/__main__.py` -> `src/pbi_agent/cli.py`; default command is `web`, and runtime commands are `web`, `run`, `audit`, `init`, `sessions`, `config`, and `skills`.
- Web stack: FastAPI backend lives under `src/pbi_agent/web/` with routes in `web/api/routes/`, schemas in `web/api/schemas/`, orchestration in `web/session_manager.py`, display publishing in `web/display.py`, and startup helpers in `web/server_runtime.py`. The frontend is Vite + React + TypeScript in `webapp/`, and `bun run web:build` writes the built SPA into `src/pbi_agent/web/static/app`.
- API contract rule: when changing web API contracts, keep `src/pbi_agent/web/api/routes/`, `src/pbi_agent/web/api/schemas/`, `src/pbi_agent/web/session_manager.py`, `webapp/src/api.ts`, and `webapp/src/types.ts` aligned.
- Display/testing conventions: `src/pbi_agent/display/protocol.py` defines `DisplayProtocol`, console output lives in `src/pbi_agent/display/console_display.py`, and tests commonly use `tests/conftest.py::DisplaySpy`. Webapp tests live alongside source under `webapp/src/**/*.test.ts(x)` and should prefer behavior and state assertions over snapshots.
- Provider/runtime rules: outbound provider and tool HTTP must use `urllib.request`; provider abstractions live under `src/pbi_agent/providers/`; internal data belongs in `~/.pbi-agent/`; no migration or backward-compatibility shims should be added.
- Current product/provider shape: `chatgpt` and `github_copilot` are first-class subscription-backed provider kinds, distinct from API-key `openai`; provider-auth UI is metadata-driven; ChatGPT/Copilot account flows are implemented across CLI and web settings.
- Model discovery: settings-side model selection is runtime provider discovery, not the local catalog. Discovery supports ChatGPT Codex backend, Google Gemini, generic OpenAI-compatible `/models`, and GitHub Copilot `GET /models`; Copilot’s live default model is `gpt-5.4`.
- Project skills: `pbi-agent skills list` and `pbi-agent skills add` are the top-level project-skill commands. Installer logic lives in `src/pbi_agent/skills/project_catalog.py` and `project_installer.py`, supports public GitHub shorthand/repo/tree sources plus local filesystem sources, uses authenticated GitHub archive download with git fallback when needed, and only treats a root `SKILL.md` and public `skills/*/SKILL.md` entries as installable bundles.
- Active follow-up: if more project-skill source edge cases appear, preserve the rule that source-repo internal `.agents/skills/*` bundles are never surfaced as downloadable or installable candidates.

## Detailed Task Events
### 2026-04-21
- Expanded `pbi-agent skills add` to support `pbi-agent skills add [source]` with default-catalog auto-listing, local filesystem sources, authenticated GitHub archive downloads, git fallback for private or unavailable repos, and guaranteed temp cleanup for list/install flows. Validation: `uv run ruff check src/pbi_agent/cli.py src/pbi_agent/skills/project_installer.py tests/test_cli.py tests/test_project_skills.py`; `uv run ruff format --check` on the same files; `uv run pytest tests/test_cli.py tests/test_project_skills.py -q`; `bun run docs:build`.
- Tightened project-skill source discovery so `pbi-agent skills add` excludes source-repo `.agents/skills/*` bundles and only exposes a root `SKILL.md` plus public `skills/*/SKILL.md` candidates. Validation: `uv run ruff check src/pbi_agent/skills/project_installer.py tests/test_project_skills.py`; `uv run ruff format --check src/pbi_agent/skills/project_installer.py tests/test_project_skills.py`; `uv run pytest tests/test_project_skills.py -q`.
- Ran daily memory management. Changed `MEMORY.md` to the required three-section format, compacted historical detail into durable notes, preserved 2026-04-21 task history, and reset `TODO.md` for this session. Validation: structure review of `MEMORY.md` and `TODO.md` against `AGENTS.md` task-memory rules.
