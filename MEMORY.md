# MEMORY.md

## Metadata
- Last compacted: 2026-05-17
- Scope: durable repo memory + active-day task events.
- Format: only `Metadata`, `Long-Term Memory`, and `Detailed Task Events`.

## Long-Term Memory
- Memory: token-efficient. Keep durable decisions/follow-ups only; drop logs. New day: promote useful prior-day outcomes, delete old detail.
- Workflow: no commit/push/merge/PR unless asked. Use session-only `TODO.md` with `[ ]`, `[>]`, `[X]`, `[!]`, `[-]`. Shell from workspace root; direct Python uses `python3`.
- Validation: Python Ruff+basedpyright+pytest; frontend Bun tests/lint/typecheck/build; docs build. Note skipped/hung checks.
- Core: CLI `src/pbi_agent/__main__.py` -> `src/pbi_agent/cli.py`; default command `web`; backend FastAPI `src/pbi_agent/web/`; frontend Vite React `webapp/`.
- API changes: align routes/schemas/session manager with `webapp/src/api.ts`, `webapp/src/types.ts`, generated API types. `bun run web:api-types` runs `scripts/generate_api_types.py`; `test_api_types_codegen.py` enforces output.
- Constraints: provider/tool HTTP via `urllib.request`; internal data under `~/.pbi-agent/`; no migrations/backcompat.
- Tools: built-in `python_exec`, `list_files`, `search_files` removed; use shell (`rg --files`, `find`, `rg -n`) and Python. `read_web_url` only with `web_search`.
- Tool availability: V4A providers (`openai`, `chatgpt`) advertise `apply_patch` and hide duplicate `replace_in_file`/`write_file`; non-V4A invert.
- OpenAI/ChatGPT `apply_patch`: Codex-compatible freeform custom tool; exact Lark grammar; raw V4A `custom_tool_call` input; local Lark validation/move support; reject empty `Update File`/move-only hunks; compact plain text output (`Success. Updated the following files\nA/M/D path`), not `{ok,result}` JSON.
- Web `apply_patch` cards: raw V4A parsing carries per-file operation/path/diff/count + move context (`move_file old → new`); running/completed multi-op calls render one card per file and completed replacements preserve mixed tool order.
- Project catalogs: top-level `skills`, `commands`, `agents`; public catalogs under `pbi-agent/{skills,commands,agents}`; local install to `.agents/...`.
- Sub-agents: `.agents/agents/*.md`; frontmatter only `name`/`description`; child model from active profile/CLI + `sub_agent_model`.
- Local commands: `plan` no questions; `review` Markdown and autonomous; `fix-review` stops on `No findings.`; `refine-task` clarifies draft tasks with `ask_user` and forbids solutions; `ship-task` branch/merge helpers; `release` needs explicit publish wording and no history rewrite after PR unless approved.
- Project command `/create-task` creates Kanban cards through `pbi-agent kanban create`; no implementation.
- Release docs: use `release-writing`; changelog index `docs/changelog/index.md`, files `docs/changelog/v<version>.md`, VitePress sidebar links releases; release workflow needs validation triage, publish verification, continuation-gate safety.
- Branding: public copy = local coding agent; preserve `pbi-agent`, `pbi_agent`, `PBI_AGENT_*`, `~/.pbi-agent`; logo `src/pbi_agent/web/static/logo.jpg`.
- Providers: OpenAI Responses use `instructions` + `previous_response_id`; ChatGPT subscription prepends system prompt; Codex transport WebSocket-only (`chatgpt_codex_backend.py`), no unsupported compression.
- ChatGPT Codex WebSocket: split connect/idle/request timeouts; retryable connect/upgrade/send/read/request timeout failures; provider emits `model_call_start`/`model_call_retry`; retry backoff covered in OpenAI provider tests.
- Web/session: saved sessions use session-scoped APIs; no user-facing `/api/live-sessions/*` or `/sessions/live/:id`. Blank/saved sessions can start/continue without active live id; completed Kanban-bound runs detach live ids without ending saved conversation.
- Web session manager: `src/pbi_agent/web/session_manager.py` thin facade; mixins under `src/pbi_agent/web/session/`. Patch worker/auth globals in `pbi_agent.web.session.workers` and `pbi_agent.web.session.provider_auth`.
- Web events: app/session streams use SSE `GET /api/events/{stream}` and `/api/events/sessions/{session_id}` with `server.connected`/heartbeat and `since`/`Last-Event-ID`; WebSocket event routes/helpers removed. Frontend keeps defensive `parseSseEvent()` validation.
- Web message identity: saved history/live replay use canonical persisted ids `msg-<messages.id>` + stable part ids; optimistic/display-local live items rekey via `message_rekeyed`.
- Web status: session/live API lifecycle statuses differ from persisted run-record statuses; keep contracts distinct.
- Web command input: direct saved-session shell commands disable `WebDisplay` input with `begin_direct_command()`/`finish_direct_command()`; `attachLiveSession(..., preserveEventCursor)` preserves input/processing when SSE cursor is equal/newer than submit response cursor.
- Web live snapshots: `LiveSessionSnapshotModel` preserves typed `processing` and pending user-question payloads; frontend boundary keeps `pending_user_questions` required nullable.
- Web frontend API boundary: add JSON API calls through generated `ApiOperationResponses`/`ApiJsonRequestBodies` via `apiRequest()` and `jsonBody()`.
- Web durable runs/replay: `run_sessions` stores web projection fields/status; `snapshot_json` caches timeline from persisted `web_event`; unfinished web runs become `stale`; `RunTracer` attaches canonical run ids; saved-session event streams replay original `seq`/`created_at`.
- Saved-session timelines: API `history_items` are canonical chronological messages; frontend overlays only non-duplicate live/work snapshot items, avoids stale live streams for ended/static projections, and anchors first saved history before pre-history live/work items.
- Session compaction: clear completed `previous_id`; resume restores persisted user/assistant history; include unanswered trailing user turns and same-turn tool exchanges.
- Saved-session fork: `POST /api/sessions/{session_id}/fork` duplicates messages/uploads through target message ids, resets usage/previous_id, stores fork metadata/title `Fork-{original-title}`, cleans copied uploads on failure.
- Web UI: prefer shadcn tokens/components; overlays use readable spacing; large modals need safe gutters + inner scroll; clamp edge-adjacent tooltips on both axes.
- Web timeline/composer UX: Composer highlights `@file` and `$skill`; `$skill` completions use `/api/skills/search`; user/assistant timelines support copy/fork; fenced code uses Shiki `CodeBlock`; shared `WorkingSummary` categorizes read/search/shell/edit/sub-agent/question/other counts + duration; Working durations prefer item timestamps then surrounding turn message timestamps.
- Timeline: work runs coalesce thinking/tool activity between chat messages; stable active placeholder keys; historical expansion must not reset auto-follow; expanded Working activity scroll follows latest and centers opened tool cards; one shadcn Accordion closes other tool cards.
- Session follow UX: image user-message updates/rekeys force bottom follow and clear stale new-message badges; active last Working first-open follows after layout settles with composer-edge gutter; Working blocks single-open at outer level.
- Web layout/session chrome: global `AppSessionsContextPanel` on Sessions/Kanban/Dashboard; sidebar head and session topbar share `--topbar-height: 48px`; collapsed sidebar 48px; New Session closes sessions sidebar.
- Frontend shadcn normalization: `FormDialog`/`ConfirmDialog` canonical; Badge variants include `success`/`warning`/`info`/`running`/`completed`/`failed`; status dots render except `asChild`; `StatusPill` preserves running/completed groups.
- Composer history: SessionPage passes main-session non-empty user messages; Composer ArrowUp/ArrowDown browses history with draft restore and resets on history change.
- Test hygiene: pytest isolates web upload root to per-test `tmp_path / "web_uploads"`.
- Maintenance: startup runs `run_startup_maintenance()` once per UTC day via SQLite `maintenance_state`; retention config `maintenance.retention_days` (default 30, min 1) exposed via CLI/web settings; purge removes old sessions/messages/run_sessions/observability_events/web_manager_leases and old unreferenced uploads while preserving referenced uploads; PyPI check uses `urllib.request`.
- Run Detail UI: shared `StatusPill`/Badge status styling; event rows avoid duplicate model/status-code chips; payload cards use shared `CopyShortcut`; header stats wrap safely and keep duration/cost separated.
- CLI startup maintenance warning: PyPI check emits Rich stderr update warning only for newer versions; `MaintenanceResult.update_notice` stays plain string.
- Sandbox: `pbi-agent sandbox [web|run]` builds bundled-package Dockerfile from `src/pbi_agent/sandbox/Dockerfile.sandbox`, installs matching PyPI version, ignores workspace Dockerfiles, shares sessions/Kanban/runs with non-sandbox, uses per-workspace writable `/home/pbi` Docker volume.
- Sandbox container names: explicit Docker `--name pbi-agent-{normalized-workspace-folder}`; folder lowercased, invalid chars/spaces to `-`, trimmed, fallback `workspace`; duplicate names use Docker conflict behavior.
- Sandbox validation: focused sandbox pytest, Ruff, basedpyright, docs build, `uv build`, Docker build/smoke when available.
- Project install UI: Settings Project Skills/Commands/Agents support official/custom install, force-replace conflict flow, flat ProviderModal-style add dialogs, and API types/static rebuilds after contract changes.
- CLI web startup: server banner sole `Serving on...`; Linux browser launch strips only legacy `atk-bridge` from `GTK_MODULES`.
- Shell tool timeout: default `timeout_ms` 30000, max 300000; reject non-positive/non-integer/bool before subprocess. ChatGPT shell schema compact command-only; runtime/base schema accepts optional overrides.
- Sub-agent web UI: parent timeline keeps child work in stable cards; child routes own wait/input/processing/usage; aggregate child processing/interruptability controls parent Working without child transcript churn.
- Startup stale cleanup: orphan active turn/sub-agent run records in stale web-session intervals become stale; stale projections clear processing/wait/pending and downgrade running tool/sub-agent snapshots.
- Working summaries: final per-turn summaries can show cost; intermediate Working headers/sub-agent cards omit cost; active durations tick timestamp-to-now and stale turn usage clears on new user turns.
- `pbi-agent init` and interactive `/init` create starter `AGENTS.md`; default skips existing; `--force`/`--overwrite` replace. Shared helper `src/pbi_agent/init_agents.py`; built-in aliases reserve `/init` and `/compact`.

## Detailed Task Events
## 2026-05-17
- Prepared v0.10.0 release PR: bumped pyproject/uv.lock, added changelog/sidebar/index links, ran full release checks, opened PR #302. Publish not requested.
- Published v0.9.2 after approved PR #301: merged to master, release workflow succeeded, PyPI wheel/sdist and GitHub Release verified.
- Fixed saved-session active snapshot ordering: first saved history anchors before pre-history live/work items; final assistant stays after Working. Added SessionPage regressions, including pending pre-history non-message work. Validation: `bun run typecheck`, `bun run lint`, `bun run web:build` passed; focused `bun run test:web -- SessionPage.test.tsx` fails before assertions because `fetchBootstrap` is not mocked as a vi.fn.
- Merged `origin/master` with local sandbox naming work; resolved MEMORY/TODO conflicts; kept upstream session timeline changes/static assets. Validation: `git diff --check` plus focused sandbox pytest.
- Diagnosed session `615819c502fe4dfeac04b3705b78d95b`: external release completed, but saved run stayed `started`/live `running` after final `gh run view`; suspected follow-up ChatGPT Codex WebSocket hung/died before trace. Follow-up later addressed by WebSocket timeout/retry hardening.
- Released v0.9.1: PR #300 merged; release workflow uploaded PyPI and published GitHub Release. Release body frontmatter stripped after workflow.
- Compared upstream `~/codex` retry behavior, then hardened ChatGPT Codex WebSocket: connect/idle/request timeouts, retryable timeout normalization, `model_call_start`/`model_call_retry`, retry backoff. Validation: `uv run pytest -q --tb=short -x tests/test_openai_provider.py`, focused Ruff check/format, `uv run basedpyright` passed.
- Prepared v0.9.2 release PR from ChatGPT WebSocket hardening + orchestrate command docs refactor; bumped versions/changelog/sidebar/index, ran full release checks, opened PR #301. Publish not requested then.
- Added `pbi-agent init` and interactive `/init` to create starter `AGENTS.md`; default skip, `--force`/`--overwrite` replace. Shared helper `src/pbi_agent/init_agents.py`; built-in aliases reserve `/init` and `/compact`. Validation: focused CLI/session/web slash tests and Ruff passed.
- Published v0.10.0 after approved PR #302: merged to master, release workflow succeeded, PyPI wheel/sdist and GitHub Release verified.
- Compressed `MEMORY.md`: curated durable memory, collapsed release/debug history, kept active follow-up about `SessionPage.test.tsx` mock failure. Validation: `git diff --check -- MEMORY.md TODO.md` passed; tests skipped (markdown-only).
