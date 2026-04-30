# MEMORY.md

## Metadata
- Last compacted: 2026-04-30
- Scope: durable repo memory + active-day task events.
- Format: only `Metadata`, `Long-Term Memory`, `Detailed Task Events`.

## Long-Term Memory
- Memory: token-efficient; keep durable decisions/follow-ups only, not logs.
- Workflow: no commit/push/merge/PR unless asked. Use session-only `TODO.md`; markers `[ ]`, `[>]`, `[X]`, `[!]`, `[-]`. Shell from workspace root.
- Validate touched surface: Python Ruff+pytest; frontend Bun tests/lint/typecheck/build; docs build. Note skipped/hung checks.
- Architecture: CLI `src/pbi_agent/__main__.py` -> `src/pbi_agent/cli.py`; default command `web`; backend FastAPI `src/pbi_agent/web/`; frontend Vite React `webapp/`.
- API changes: align routes/schemas/session manager with `webapp/src/api.ts` + `webapp/src/types.ts`.
- Constraints: provider/tool HTTP via `urllib.request`; internal data in `~/.pbi-agent/`; no migrations/backcompat.
- Tools: built-in `python_exec`, `list_files`, `search_files` removed; use shell (`rg --files`, `find`, `rg -n`) and Python as needed.
- Project imports: top-level `skills`, `commands`, `agents`; public catalogs under `pbi-agent/{skills,commands,agents}`; local install to `.agents/...`.
- Sub-agents: `.agents/agents/*.md`; frontmatter only `name`/`description`; child model from active profile/CLI + `sub_agent_model`.
- Local commands: `plan` no questions; `review` Markdown; `fix-review` stops on `No findings.`; `ship-task` branch/merge helpers; `release` needs explicit publish wording and no history rewrite after PR unless approved.
- Release docs: `release-writing` skill governs releases; changelog index `docs/changelog/index.md`, files `docs/changelog/v<version>.md`, VitePress sidebar links releases.
- Branding: public copy = local coding agent; preserve `pbi-agent`, `pbi_agent`, `PBI_AGENT_*`, `~/.pbi-agent`; logo `src/pbi_agent/web/static/logo.jpg`.
- Web/session: saved sessions reopen via `resume_session_id`; SQLite leases use `BEGIN IMMEDIATE`/`busy_timeout`; duplicate manager startup emits one warning.
- Session compaction: clear completed `previous_id`; resume restores persisted user/assistant history; compaction includes unanswered trailing user turns and same-turn tool exchanges.
- Providers: OpenAI Responses use `instructions` + `previous_response_id`; ChatGPT subscription prepends system prompt; Codex transport is WebSocket-only (`chatgpt_codex_backend.py`), no unsupported compression.
- Web UI: prefer shadcn tokens/components; overlays use shared readable spacing; large modals need safe gutters + inner scroll.
- Timeline: work runs coalesce thinking/tool groups; running closed by default; final assistant closes current collapsibles; file-edit results share `FILE_EDIT_TOOL_NAMES`.
- Syntax highlighting: `read_file` uses lazy Shiki code block; root `package.json` pins exact `shiki` `4.0.2`.
- v0.1.0 shipped.

## Detailed Task Events
## 2026-04-30
- Compressed `MEMORY.md` for daily purge using compress skill; later pruned `Long-Term Memory` to decision-only/token-efficient form per user preference. Validation: manual structure check.
- Applied release retrospective: release-writing validation triage + publish verification; release command continuation gate + no-history-rewrite safety. Validation: `uv run pytest tests/test_project_commands.py` passed.
- Compressed `.agents/skills/release-writing/SKILL.md` and `.agents/commands/release.md` prose with compress skill; preserved headings, code blocks, inline commands/paths, and release workflow semantics. Validation: `uv run pytest tests/test_project_commands.py` passed.
