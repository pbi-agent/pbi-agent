# MEMORY.md

## Metadata
- Last compacted: 2026-04-25
- Scope: durable repo memory + append-only active-day task events.
- Format: only `Metadata`, `Long-Term Memory`, `Detailed Task Events`; compact prior-day detail into durable notes before new work.

## Long-Term Memory
- Workflow: no commit/push/merge/PR unless asked. Use session-only `TODO.md`; reset before work; markers `[ ]`, `[>]`, `[X]`, `[!]`, `[-]`.
- Validate touched surface: Python = Ruff check/format + focused pytest; frontend = `bun run test:web`, `bun run lint`, `bun run typecheck`, `bun run web:build`; docs = `bun run docs:build`; broad = repo Ruff/Bun/pytest. Env quirk: Bun/Node/npm or lint/test may hang; note gaps.
- Architecture: CLI entry `src/pbi_agent/__main__.py` -> `cli.py`; system prompt says `pbi-agent`, check `pbi-agent -h`. Commands: `web` default, `run`, `sessions`, `config`, `skills`, `commands`, `agents`. Web FastAPI under `src/pbi_agent/web/`; frontend Vite React TS in `webapp/`; build output `src/pbi_agent/web/static/app`.
- Web API change: keep routes/schemas/session manager + `webapp/src/api.ts` + `types.ts` aligned. Tests use `DisplaySpy`; web tests beside `webapp/src/**/*.test.ts(x)`, behavior > snapshots.
- Provider/runtime: HTTP via `urllib.request`; providers under `src/pbi_agent/providers/`; internal data in `~/.pbi-agent/`; no migrations/backcompat. `chatgpt` + `github_copilot` first-class subscription providers, separate from API-key `openai`.
- Model discovery live at runtime: ChatGPT Codex, Gemini, OpenAI-compatible `/models`, GitHub Copilot `GET /models`; Copilot live default `gpt-5.4`.
- Tools: built-in `python_exec` was removed; use shell for Python as needed. `shell` truncates stdout/stderr at 12k chars each with middle omission; shared `bound_output` default remains 1k.
- Project imports: `skills`, `commands`, `agents` top-level CLI groups. Shared GitHub/local materializer discovers public `skills/*/SKILL.md`, `commands/*.md`, `agents/*.md`; ignores source repo `.agents/*` internals unless explicit; installs to local `.agents/...`. Official catalogs: `pbi-agent/{skills,commands,agents}`.
- Project sub-agents only `.agents/agents/*.md`; frontmatter only `name`/`description`; child model from active profile/CLI + `sub_agent_model`. Shared frontmatter parser supports YAML block scalars for `description`, rejects block-scalar `name`; install rejects unsafe names.
- Local commands: `plan.md` noninteractive, no clarifying questions or `request_user_input`, plain Markdown; `review.md` plain Markdown not JSON; `execute.md` compact prose; `fix-review.md` fixes prior findings, stops on `No findings.`; `ship-task.md` action-oriented, prefixed kebab-case branches, deletes merged local/remote branches; `retrospective.md` compressed. Local `compress` skill prompt-only/no network.
- Branding: public copy = general local coding agent; preserve `pbi-agent`, `pbi_agent`, `PBI_AGENT_*`, `~/.pbi-agent`. Canonical logo `src/pbi_agent/web/static/logo.jpg` + favicon/logo fallbacks; banner dark `BI`, `work smart.`, centered `v{__version__}`.
- Web/session: saved sessions reopen via `resume_session_id`; `_resume_session()` restores provider checkpoints when no replay; `WebSessionManager` uses SQLite lease heartbeat with `BEGIN IMMEDIATE`/`busy_timeout`; managed startup normalizes running tasks.
- Provider ordering: standard OpenAI Responses use `instructions` + `previous_response_id`; ChatGPT subscription prepends system prompt to replay/current input. `x-codex-turn-state` = sticky routing state, not incremental input; no tool-result-only deltas from that header alone.
- Recent fixes: failed provider turns delete unanswered user messages; sub-agent parent context excludes current user turn; project sub-agent discovery temp-workspace covered. `read_file.start_line` unbounded positive; `max_lines` capped. Kanban first runnable stage sends slash command + task details; later stages command-only; slash detection splits whitespace. Done sort newest-first; packaged SPA may need rebuild after frontend changes.
- Web UI: `!command` composer input calls live-session shell endpoint; persisted shell output to `SessionStore`; shell mode warning UI + refocus after completion. Multiline user timeline uses `pre-wrap`; websocket-only sessions bind `eventLiveSessionId` before `input_state`.
- Docs/artifacts: repo URL `https://github.com/pbi-agent/pbi-agent`; external catalog READMEs point there; `WEBAPP_CURRENT_STATE_SPEC.md` = web UX/UI redesign handoff.
- Env repair: if VS Code pytest discovery breaks after partial `.venv`, `uv sync --reinstall` fixed missing `pygments.formatters`/`packaging.version`; verify `.venv/bin/python -m pytest --collect-only -q ...` + `uv pip check`.
- Active follow-up: source-repo internal `.agents/skills/*` bundles never surface as downloadable/installable candidates.

## Detailed Task Events
## 2026-04-25
- Remove deprecated webapp TypeScript options: dropped `baseUrl` and now-unused `ignoreDeprecations` from `webapp/tsconfig.json`; `@/*` remains via `paths` + Vite alias. Validation: `bun run typecheck`.
- Continue shadcn webapp refactor: added ThemeProvider/theme switcher, mapped DESIGN.md Prism/light/dark tokens, refactored app shell/session/board/dashboard/settings UI to shadcn components, fixed test setup for shadcn/Radix. Validation: `bunx --bun shadcn@latest docs dialog --cwd webapp`; `bun run typecheck`; `bun run lint`; `bun run test:web -- --reporter dot`; `bun run web:build`; `git diff --check`.
- Init shadcn/ui for existing Vite webapp: add Tailwind v4/Vite plugin + `@/*` alias prereqs; generate `webapp/components.json`, shadcn theme CSS in `webapp/src/styles/index.css`, `webapp/src/lib/utils.ts`; no components added. Validation: `bunx --bun shadcn@latest info --cwd webapp`; `bun run typecheck`; `git diff --check` on touched files.
- Condense `Long-Term Memory` after prior compaction left verbose; keep durable repo facts, reduce bullets. Validation: read `MEMORY.md`; `git diff --check -- MEMORY.md TODO.md`.
- Audit removed 2026-04-24 log; promote missing durable facts into `Long-Term Memory`. Validation: compared removed diff vs memory; `git diff --check -- MEMORY.md TODO.md`.
- Compress whole `MEMORY.md` with local `compress` skill; preserve headings, inline code, paths, commands, URLs, dates, structure. Validation: `git diff --check -- MEMORY.md TODO.md`; `wc -l MEMORY.md`.
- Update `AGENTS.md` for shadcn switch: frontend stack/config paths plus UI conventions for primitives, docs, semantic tokens, icons, and accessible overlay titles. Validation: `git diff --check -- AGENTS.md TODO.md`.
