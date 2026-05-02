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
- Ask-user notifications: frontend-only localStorage prefs for desktop/sound; AppShell effect fires hidden/unfocused browser notifications/sound, deduped by live/session + prompt id, click focuses/navigates to waiting session.

## Detailed Task Events
## 2026-05-02
- Tested `ask_user` workflow by asking 2 questions; tool returned both answers successfully. Validation: `ask_user` response received. Next: none.
- Redesigned the session topbar interactive-mode toggle only: kept shadcn `Toggle`, added label/track/thumb markup, and styled pill hover/focus/on states with semantic tokens, cursor hover lift, glow, and animated thumb. Validation: `bun run typecheck`, `bun run lint`, and `bun run test:web -- SessionPage` passed.
- Adjusted interactive topbar control to text-only `Interactive` and matched the Runs badge hover/active styling; no behavior/API changes. Validation: `bun run typecheck`, `bun run lint`, and `bun run test:web -- SessionPage` passed.
- Restyled `UserQuestionsPanel` with app CSS/BEM classes instead of Tailwind utilities so reset/layer ordering cannot wipe margins, button backgrounds, option hover, or selected state; centered card to timeline width and added explicit submit/nav/option/custom hover styles. Validation: `bun run typecheck`, `bun run lint`, `bun run test:web -- UserQuestionsPanel`, `bun run test:web`, and `bun run web:build` passed; reverted generated static bundle output after build.
- Evaluated session topbar action order: current `Interactive → context gauge → Runs → delete` can make the tiny context gauge read like Interactive's switch/status; recommended design-only order `Interactive → Runs → context gauge → delete`, keeping destructive delete last.
- Updated session topbar action order to `Interactive → Runs → context gauge → delete` in `SessionPage`; validation: `bun run typecheck`, `bun run lint`, and `bun run test:web -- SessionPage` passed.
- Implemented ask_user desktop/sound notification phase: added local notification prefs, Settings controls, global AppShell effects for hidden/unfocused prompt notifications, click-to-focus/navigate, sound chime, and tests. Validation: targeted notification/settings tests, `bun run lint`, `bun run test:web`, `bun run typecheck`, and `bun run web:build` passed; build warning only for existing large chunks.
- Fixed notification Settings checkboxes being reduced to bare check icons by reset CSS: added explicit settings checkbox class/styles for visible unchecked, checked, hover/focus, and disabled states. Validation: `bun run test:web -- SettingsPage`, `bun run typecheck`, and `bun run lint` passed.
- Fixed ask_user branch Python validation blockers before shipping: made provider tool exclusion idempotent, aligned registry/sub-agent expectations with `ask_user`, and updated session test stubs. Validation: targeted `uv run pytest tests/test_session.py tests/test_sub_agent_tool.py::test_run_sub_agent_task_uses_child_prompt_and_aggregates_usage tests/test_tool_registry.py` passed.
- Extended notification flow to live session completion: app websocket `live_session_ended` events now use desktop/sound prefs, hidden/unfocused gating, per-live-session dedupe, and click-to-open session; shared notification side effects with ask_user. Validation: `bun run test:web`, `bun run lint`, `bun run typecheck`, and `bun run web:build` passed; build warning only for existing large chunks.
- Fixed review finding for session-ended notifications: ignored app websocket replay events whose `created_at` predates the current connection start, preventing desktop notifications/sound for historical `live_session_ended` snapshot events. Validation: `bun run test:web -- useTaskEvents`, `bun run typecheck`, and `bun run lint` passed.
- Reworked session-ended notifications from app-event timestamp checks to bootstrap live-session state transitions: AppShell seeds observed active sessions, notifies only on observed active -> ended while hidden/unfocused, and leaves useTaskEvents as invalidation-only. Validation: targeted notification/useTaskEvents tests, `bun run typecheck`, `bun run lint`, `bun run test:web`, and `bun run web:build` passed.
- Fixed review finding for quick session-end notifications: `useTaskEvents` returns fresh live-session lifecycle events and `SessionEndedNotificationEffects` consumes them before dropping ended bootstrap snapshots, so fast start/end cycles can notify even without an intermediate running bootstrap snapshot. Validation: `bun run test:web -- SessionEndedNotificationEffects useTaskEvents`, `bun run typecheck`, and `bun run lint` passed.
- Made the session topbar `Interactive` toggle distinguish transient hover/focus from persistent active state: hover stays neutral surface/focus ring, active uses accent tint/text, and active-hover gets a stronger accent tint. Validation: `bun run typecheck`, `bun run lint`, and `bun run test:web -- SessionPage` passed.
