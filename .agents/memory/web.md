# Web backend and UI

Migrated from `MEMORY.md` on 2026-11-07; entries predate verification tags.

- API contracts: align FastAPI routes/schemas/session manager, `webapp/src/api.ts`, `webapp/src/types.ts`, generated types/static bundle. Generate `bun run web:api-types` (`scripts/generate_api_types.py`); enforced by `test_api_types_codegen.py`. JSON helpers `ApiOperationResponses`/`ApiJsonRequestBodies`, `apiRequest()`, `jsonBody()`. Non-GCP views keep nullable GCP fields.
- Web sessions: session-scoped APIs; no `/api/live-sessions/*`. `session_manager.py` facade → `src/pbi_agent/web/session/` (patch globals in `workers`/`provider_auth`). `WebDisplay` input state uses RLock, publishes under lock, stays disabled while input queue non-empty.
- Channels: Telegram `urllib.request` polling, token leases, per-source queues; Markdown `src/pbi_agent/channels/telegram_markdown.py`. `pbi-agent channels` show/configure/restart.
- Events/workspaces: SSE `/api/events/{stream}`, `/api/events/sessions/{session_id}` with heartbeat/`Last-Event-ID`; no event WebSockets. Explicit workspace key everywhere; `workspace_switched` clears state. `/api/sessions?q=` literal search.
- Timeline: stable `msg-<messages.id>` ids, `message_rekeyed`; `history_items` canonical; `run_sessions` projection; startup orphans → `stale`.
- Compaction/fork: `POST /api/sessions/{session_id}/fork` copies through target, resets usage/previous_id. Direct shell disables input via `begin_direct_command()`/`finish_direct_command()`.
- Notifications: finished once per AFK working→ready edge; ended on terminated/errored; ask-user prompts.
- UI: unlayered `webapp/src/styles/reset.css` beats Tailwind v4/shadcn styles → scoped fixes in `webapp/src/styles/overlays.css` (explicit padding/border/hover). Radix `ScrollArea` lets width grow; use overflow-x hidden + min-width:0 for truncation. Destructive small buttons reuse `tool-result-card__interrupt-button`. General shadcn/token rules live in `AGENTS.md`.
- Composer: `@file`/`$skill` highlights; Ctrl+Space dictation/enhancement; `web.prompt_enhancement_profile_id`; history arrows. Reply-to-selection: `ReplySelectionPopover` → `ComposerHandle.addReplySnippet` → `<reply_snippet>` XML (`lib/replySnippets.ts`), parsed back into cards; frontend-only.
- Follow-ups: checkpoint steering via `steer_user_input` at tool boundaries; FIFO after-finish fallback. Open bug: post-delivery interrupt removes accepted live user item; should keep accepted steers.
- Work UI: coalesce thinking/tools; ended turns collapse behind `Intermediate results`; collapsed header shows `WorkingIntentTicker` (last main-run tool intent, `lastWorkIntent` in `SessionTimeline.tsx`, `.working-intent*`). Expansion preserves auto-follow.
- Mentions/explorer/diff: coalesced in-memory index; dependency-free tree, `webapp/src/lib/workspaceFileIcons.ts`; `/api/files/tree`, `/api/files/diff`; stdlib `.gitignore` fallback.
