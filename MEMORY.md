# MEMORY.md

## Metadata
- Last compacted: 2026-05-02
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
- Release docs: `release-writing` skill governs releases; changelog index `docs/changelog/index.md`, files `docs/changelog/v<version>.md`, VitePress sidebar links releases; release retrospective added validation triage + publish verification + continuation gate safety.
- Branding: public copy = local coding agent; preserve `pbi-agent`, `pbi_agent`, `PBI_AGENT_*`, `~/.pbi-agent`; logo `src/pbi_agent/web/static/logo.jpg`.
- Web/session: saved sessions reopen via `resume_session_id`; SQLite leases use `BEGIN IMMEDIATE`/`busy_timeout`; duplicate manager startup emits one warning.
- Session compaction: clear completed `previous_id`; resume restores persisted user/assistant history; compaction includes unanswered trailing user turns and same-turn tool exchanges.
- Providers: OpenAI Responses use `instructions` + `previous_response_id`; ChatGPT subscription prepends system prompt; Codex transport is WebSocket-only (`chatgpt_codex_backend.py`), no unsupported compression.
- Web UI: prefer shadcn tokens/components; overlays use shared readable spacing; large modals need safe gutters + inner scroll; Radix tooltip `collisionPadding`/`sideOffset` may not protect cross-axis viewport gutters, so clamp both axes for edge-adjacent tooltips.
- Timeline: work runs coalesce thinking/tool groups; running closed by default; final assistant closes current collapsibles; file-edit results share `FILE_EDIT_TOOL_NAMES`.
- Syntax highlighting: `read_file` uses lazy Shiki code block; root `package.json` pins exact `shiki` `4.0.2`.
- v0.1.0 shipped.
- Kanban task images: stored as task `image_attachments_json`, task create/update accepts `image_upload_ids`, uploads reuse `~/.pbi-agent/web_uploads` + `/api/live-sessions/uploads/{id}` previews, initial task run sends images only with first full prompt.
- Provider history restore preserves user message image attachments for image-capable providers (OpenAI/ChatGPT, Anthropic, Google) by reloading upload IDs from `~/.pbi-agent/web_uploads`.
- Web server startup: same-workspace active lease is rejected; implicit default port `8000` may auto-select a free port, explicit `--port` stays strict.
- Web UI session context gauge: compact donut uses top-level `session_usage.context_tokens` with turn fallback over runtime `compact_threshold`; tooltip is custom fixed-position with both-axis viewport clamping.
- Kanban: task cards omit technical project/session metadata and image counts; active task live sessions show a Stop shortcut whose pending state is tied to the interrupt mutation.
- Saved sessions: sidebar supports inline title edit via `PATCH /api/sessions/{session_id}` with cache/app-event invalidation.
- Interactive ask-user: Web per-message `interactive_mode` exposes `ask_user`; pending questions persist in snapshots and are answered via `/api/live-sessions/{id}/question-response`; topbar uses shadcn `Toggle` and `UserQuestionsPanel`.
- UserQuestionsPanel UX: one question at a time with shadcn Card, selected filled Button state, keyboard nav, auto-focus active option, Prev/Next + dots, and custom textarea retained in fieldset.

## Detailed Task Events
## 2026-05-02
- Tested `ask_user` workflow by asking a multiple-choice question; tool returned an answer successfully. Validation: `ask_user` response received. Next: none.
- Redesigned the session topbar interactive-mode toggle only: kept shadcn `Toggle`, added label/track/thumb markup, and styled pill hover/focus/on states with semantic tokens, cursor hover lift, glow, and animated thumb. Validation: `bun run typecheck`, `bun run lint`, and `bun run test:web -- SessionPage` passed.
- Adjusted interactive topbar control to text-only `Interactive` and matched the Runs badge hover/active styling; no behavior/API changes. Validation: `bun run typecheck`, `bun run lint`, and `bun run test:web -- SessionPage` passed.
- Restyled `UserQuestionsPanel` with app CSS/BEM classes instead of Tailwind utilities so reset/layer ordering cannot wipe margins, button backgrounds, option hover, or selected state; centered card to timeline width and added explicit submit/nav/option/custom hover styles. Validation: `bun run typecheck`, `bun run lint`, `bun run test:web -- UserQuestionsPanel`, `bun run test:web`, and `bun run web:build` passed; reverted generated static bundle output after build.
- Evaluated session topbar action order: current `Interactive → context gauge → Runs → delete` can make the tiny context gauge read like Interactive's switch/status; recommended design-only order `Interactive → Runs → context gauge → delete`, keeping destructive delete last.
- Updated session topbar action order to `Interactive → Runs → context gauge → delete` in `SessionPage`; validation: `bun run typecheck`, `bun run lint`, and `bun run test:web -- SessionPage` passed.
